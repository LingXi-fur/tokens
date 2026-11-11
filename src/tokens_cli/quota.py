"""Subscription quota snapshots and crash projections.

Codex exposes official rate-limit snapshots. Claude exposes only rate-limit
events, so its capacity is an explicitly labelled estimate built from direct
Anthropic usage inside the five hours before each event. OpenCode has no quota
signal. Only timestamps, quota fields, model names, and token totals leave the
scanners; message bodies are never read.
"""
import json
import os
import statistics
import tempfile
from datetime import datetime, timezone

from . import codex_usage, config, readers

DEFAULT_SOURCES = ("claude", "codex", "opencode")
CLAUDE_WINDOW_SECONDS = 5 * 60 * 60
WEEK_WINDOW_MINUTES = 10080
SHORT_WINDOW_MINUTES = 300
VELOCITY_WINDOW_SECONDS = 60 * 60
MIN_VELOCITY_SPAN_SECONDS = 5 * 60
RECENT_EVENTS = 5
CACHE_SCHEMA = 1


# ---------- time and value parsing ----------

def _epoch(value):
    """Accept epoch seconds or ISO timestamps; return float seconds or None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    return None


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _text(value):
    return value if isinstance(value, str) and value else None


def _local(epoch):
    return datetime.fromtimestamp(epoch, config.TZ)


def _iso(epoch):
    return None if epoch is None else _local(epoch).isoformat()


# ---------- file scanning ----------

def _cache_path():
    return os.path.join(config.CACHE_DIR, "quota-v1.json")


def _prefiltered_lines(path, needle):
    """Yield raw lines containing a byte marker; other lines never reach JSON."""
    with open(path, "rb") as handle:
        for raw in handle:
            if needle not in raw:
                continue
            yield raw


def _scan_claude_file(path):
    events = []
    for raw in _prefiltered_lines(path, b'"rate_limit"'):
        try:
            obj = json.loads(raw)
        except (TypeError, ValueError, RecursionError):
            continue
        if not isinstance(obj, dict):
            continue
        if (obj.get("error") != "rate_limit"
                or obj.get("isApiErrorMessage") is not True
                or obj.get("apiErrorStatus") != 429):
            continue
        at = _epoch(obj.get("timestamp"))
        if at is None:
            continue
        quota = obj.get("quotaLimits") if isinstance(obj.get("quotaLimits"), dict) else {}
        params = obj.get("apiErrorParams") if isinstance(obj.get("apiErrorParams"), dict) else {}
        info = params.get("rate_limit_info") if isinstance(params.get("rate_limit_info"), dict) else {}
        source = quota or info
        limit_type = _text(source.get("rateLimitType")) or _text(info.get("rateLimitType"))
        status = _text(source.get("status")) or _text(info.get("status"))
        resets_at = _epoch(source.get("resetsAt"))
        if resets_at is None:
            resets_at = _epoch(info.get("resetsAt"))
        events.append({
            "at": at,
            "type": limit_type,
            "status": status,
            "resets_at": resets_at,
        })
    return events


def _scan_codex_file(path):
    snapshots = []
    for raw in _prefiltered_lines(path, b'"rate_limits"'):
        try:
            obj = json.loads(raw)
        except (TypeError, ValueError, RecursionError):
            continue
        if not isinstance(obj, dict) or not isinstance(obj.get("payload"), dict):
            continue
        limits = obj["payload"].get("rate_limits")
        if not isinstance(limits, dict):
            continue
        observed = _epoch(obj.get("timestamp"))
        if observed is None:
            continue
        base = {
            "observed_at": observed,
            "plan_type": _text(limits.get("plan_type")),
            "limit_id": _text(limits.get("limit_id")),
            "limit_name": _text(limits.get("limit_name")),
        }
        # Window type comes from window_minutes, never the primary/secondary label.
        windows = {}
        for key in ("primary", "secondary"):
            window = limits.get(key)
            if not isinstance(window, dict):
                continue
            minutes = _number(window.get("window_minutes"))
            used = _number(window.get("used_percent"))
            if minutes is None or used is None:
                continue
            minutes = int(minutes)
            candidate = dict(base, window_minutes=minutes, used_percent=used,
                             resets_at=_epoch(window.get("resets_at")))
            prior = windows.get(minutes)
            if prior is None or candidate["used_percent"] > prior["used_percent"]:
                windows[minutes] = candidate
        snapshots.extend(windows.values())
    return snapshots


def _valid_cache_entry(entry, size, mtime_ns, kind):
    return (isinstance(entry, dict) and entry.get("size") == size
            and entry.get("mtime_ns") == mtime_ns and entry.get("kind") == kind
            and isinstance(entry.get("items"), list))


def _load_cache():
    try:
        with open(_cache_path(), "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, TypeError, ValueError, RecursionError):
        return {}
    if (not isinstance(payload, dict) or payload.get("v") != CACHE_SCHEMA
            or not isinstance(payload.get("files"), dict)):
        return {}
    return payload["files"]


def _save_cache(entries):
    path = _cache_path()
    temporary = None
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".quota-", dir=os.path.dirname(path))
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({"v": CACHE_SCHEMA, "files": entries}, handle,
                      ensure_ascii=False, separators=(",", ":"))
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    except OSError:
        if temporary:
            try:
                os.unlink(temporary)
            except OSError:
                pass


def scan_rate_limits(sources, use_cache=True):
    """Scan Claude/Codex files with a per-file cache keyed by size and mtime."""
    selected = set(sources)
    claude_files = readers.SOURCES["claude"][0]() if "claude" in selected else []
    codex_files = codex_usage.discover() if "codex" in selected else []
    codex_files = [path for path in codex_files if path.endswith(".jsonl")]

    cache = _load_cache() if use_cache else {}
    entries = {}
    claude_events, codex_snapshots = [], []
    scanned = 0
    for kind, files, parser, sink in (
        ("claude", claude_files, _scan_claude_file, claude_events),
        ("codex", codex_files, _scan_codex_file, codex_snapshots),
    ):
        for path in files:
            try:
                stat = os.stat(path)
            except OSError:
                continue
            key = os.path.abspath(path)
            entry = cache.get(key)
            if use_cache and _valid_cache_entry(entry, stat.st_size, stat.st_mtime_ns, kind):
                items = entry["items"]
            else:
                try:
                    items = parser(path)
                except OSError:
                    continue
                scanned += 1
            entries[key] = {
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
                "kind": kind,
                "items": items,
            }
            sink.extend(items)
    _save_cache(entries)
    return {
        "claude_events": claude_events,
        "codex_snapshots": codex_snapshots,
        "claude_files": len(claude_files),
        "codex_files": len(codex_files),
        "parsed_files": scanned,
    }


# ---------- pure calculations ----------

def direct_claude_records(records):
    """Keep Anthropic-direct Claude records only; CCR backends never count."""
    direct = []
    for record in records:
        if not isinstance(record, dict) or record.get("source") != "claude":
            continue
        model = record.get("model")
        request = record.get("request_model")
        if not isinstance(model, str) or not model.startswith("claude-"):
            continue
        if not isinstance(request, str) or readers._native_model_identity(request) != model:
            continue
        at = _epoch(record.get("ts"))
        total = record.get("total")
        if at is None or isinstance(total, bool) or not isinstance(total, int) or total < 0:
            continue
        direct.append({"at": at, "total": total})
    direct.sort(key=lambda row: row["at"])
    return direct


def window_label(minutes):
    if minutes == SHORT_WINDOW_MINUTES:
        return "5h"
    if minutes == WEEK_WINDOW_MINUTES:
        return "week"
    if minutes % 1440 == 0:
        return f"{minutes // 1440}d"
    if minutes % 60 == 0:
        return f"{minutes // 60}h"
    return f"{minutes}m"


def _velocity(rows, latest, now_ts):
    if latest.get("resets_at") is None:
        window_rows = [row for row in rows
                       if now_ts - VELOCITY_WINDOW_SECONDS <= row["observed_at"] <= now_ts]
    else:
        window_rows = [row for row in rows
                       if row.get("resets_at") == latest["resets_at"]
                       and now_ts - VELOCITY_WINDOW_SECONDS <= row["observed_at"] <= now_ts]
    window_rows.sort(key=lambda row: row["observed_at"])
    if len(window_rows) < 2:
        return None
    span = window_rows[-1]["observed_at"] - window_rows[0]["observed_at"]
    if span < MIN_VELOCITY_SPAN_SECONDS:
        return None
    delta = window_rows[-1]["used_percent"] - window_rows[0]["used_percent"]
    return {
        "rate_per_hour": delta / (span / 3600),
        "span_seconds": span,
        "anchor": window_rows[-1]["observed_at"],
    }


def _codex_projection(used, resets_at, velocity, now_ts):
    if used is None:
        return {"status": "expired", "projected_at": None}
    if used >= 100:
        return {"status": "hit", "projected_at": now_ts}
    if velocity is None:
        return {"status": "insufficient", "projected_at": None}
    rate = velocity["rate_per_hour"]
    if rate <= 0:
        return {"status": "flat", "projected_at": None}
    projected = velocity["anchor"] + (100 - used) / rate * 3600
    if resets_at is not None and projected > resets_at:
        return {"status": "safe", "projected_at": projected}
    return {"status": "hit", "projected_at": projected}


def summarize_codex(snapshots, now):
    """Group official Codex snapshots by limit and window.

    ``plan_type`` is display-only: the same quota can appear as null in older
    snapshots and as ``plus`` later, so it must not split the group.
    """
    now_ts = now.timestamp()
    groups = {}
    for snapshot in snapshots:
        if not isinstance(snapshot, dict):
            continue
        minutes = snapshot.get("window_minutes")
        used = snapshot.get("used_percent")
        observed = snapshot.get("observed_at")
        if (isinstance(minutes, bool) or not isinstance(minutes, int)
                or isinstance(used, bool) or not isinstance(used, (int, float))
                or isinstance(observed, bool) or not isinstance(observed, (int, float))):
            continue
        key = (snapshot.get("limit_id"), snapshot.get("limit_name"), minutes)
        groups.setdefault(key, []).append(dict(
            snapshot,
            observed_at=float(observed),
            used_percent=float(used),
            resets_at=_epoch(snapshot.get("resets_at")),
        ))

    limits = {}
    for (limit_id, limit_name, minutes), rows in groups.items():
        rows.sort(key=lambda row: row["observed_at"])
        limits.setdefault((limit_id, limit_name), []).append((minutes, rows))

    plans = {}
    for (limit_id, limit_name), window_groups in limits.items():
        all_rows = sorted(
            (row for _, rows in window_groups for row in rows),
            key=lambda row: row["observed_at"], reverse=True,
        )
        plan_type = next(
            (row.get("plan_type") for row in all_rows if row.get("plan_type")), None)
        windows = []
        for minutes, rows in sorted(window_groups, key=lambda item: item[0]):
            latest = rows[-1]
            resets_at = latest.get("resets_at")
            expired = resets_at is not None and resets_at <= now_ts
            used = None if expired else float(latest["used_percent"])
            velocity = None if expired else _velocity(rows, latest, now_ts)
            projection = _codex_projection(used, resets_at, velocity, now_ts)
            windows.append({
                "window_minutes": minutes,
                "window": window_label(minutes),
                "status": "expired" if expired else "current",
                "used_percent": used,
                "resets_at": _iso(resets_at),
                "observed_at": _iso(latest["observed_at"]),
                "velocity_per_hour": None if velocity is None else velocity["rate_per_hour"],
                "projection": {
                    "status": projection["status"],
                    "projected_at": _iso(projection["projected_at"]),
                },
            })
        plans.setdefault(plan_type, []).append({
            "limit_id": limit_id,
            "limit_name": limit_name,
            "windows": windows,
        })

    result = []
    for plan_type in sorted(plans, key=lambda value: (value is not None, value or "")):
        result.append({
            "plan_type": plan_type,
            "limits": sorted(
                plans[plan_type],
                key=lambda limit: (limit["limit_name"] is not None,
                                   limit["limit_name"] or "",
                                   limit["limit_id"] or ""),
            ),
        })
    return result


def _median(values):
    return statistics.median(values) if values else None


def _dedupe_events(events):
    """Drop exact retries; merge no-reset events within 60 seconds."""
    seen = set()
    unique = []
    last_no_reset = {}
    for event in sorted(events, key=lambda row: row.get("at", 0)):
        at = event.get("at")
        if isinstance(at, bool) or not isinstance(at, (int, float)):
            continue
        resets_at = event.get("resets_at")
        kind = event.get("type")
        if resets_at is None:
            previous = last_no_reset.get(kind)
            last_no_reset[kind] = at
            if previous is not None and at - previous < 60:
                continue
        else:
            key = (int(at), kind, int(resets_at))
            if key in seen:
                continue
            seen.add(key)
        unique.append(event)
    return unique


def _claude_windows(direct, until=None):
    """Split direct records into five-hour windows, starting at first record."""
    windows = []
    for row in direct:
        if until is not None and row["at"] > until:
            break
        if not windows or row["at"] >= windows[-1]["end"]:
            windows.append({
                "start": row["at"],
                "end": row["at"] + CLAUDE_WINDOW_SECONDS,
                "rows": [],
            })
        windows[-1]["rows"].append(row)
    return windows


def _window_tokens(window):
    return sum(row["total"] for row in window["rows"])


def _window_has_hit(window, events):
    return any(window["start"] <= event["at"] <= window["end"] for event in events)


def _claude_capacity(events, direct, now_ts):
    """Capacity from hit windows plus a safe floor from ended clean windows."""
    events = _dedupe_events(events)
    by_reset = {}
    for event in events:
        resets_at = event.get("resets_at")
        if resets_at is None:
            continue
        kind = (event.get("type") or "").lower()
        if kind not in ("", "five_hour"):
            continue
        key = int(resets_at)
        if key not in by_reset or event["at"] > by_reset[key]["at"]:
            by_reset[key] = event
    samples = []
    for resets_at, event in sorted(by_reset.items()):
        start = resets_at - CLAUDE_WINDOW_SECONDS
        end = event["at"]
        if end < start:
            continue
        tokens = sum(row["total"] for row in direct if start <= row["at"] <= end)
        if tokens > 0:
            samples.append({
                "at": event["at"],
                "type": event.get("type"),
                "resets_at": resets_at,
                "tokens": tokens,
            })

    safe_windows = [
        window for window in _claude_windows(direct, until=now_ts)
        if window["end"] <= now_ts and not _window_has_hit(window, events)
    ]
    safe_floor = max((_window_tokens(window) for window in safe_windows), default=None)
    values = [sample["tokens"] for sample in samples]
    median = _median(values)
    maximum = max(values) if values else None
    if safe_floor is not None and (median is None or safe_floor > maximum):
        capacity = safe_floor
        basis = "safe_floor"
    elif median is not None:
        capacity = median
        basis = "hits"
    elif safe_floor is not None:
        capacity = safe_floor
        basis = "safe_floor"
    else:
        capacity = None
        basis = "none"
    return samples, {
        "count": len(values),
        "median": median,
        "min": min(values) if values else None,
        "max": maximum,
        "safe_floor": safe_floor,
        "safe_windows": len(safe_windows),
        "basis": basis,
    }


def _claude_current(direct, capacity, events, now_ts):
    windows = _claude_windows(direct, until=now_ts)
    if not windows or windows[-1]["end"] <= now_ts:
        return None
    window = windows[-1]
    start, end = window["start"], window["end"]
    used = _window_tokens(window)
    percent = (used / capacity * 100) if capacity else None
    has_hit = _window_has_hit(window, events)

    hour_rows = [row for row in direct
                 if now_ts - VELOCITY_WINDOW_SECONDS <= row["at"] <= now_ts]
    velocity = None
    if len(hour_rows) >= 2:
        span = hour_rows[-1]["at"] - hour_rows[0]["at"]
        if span >= MIN_VELOCITY_SPAN_SECONDS:
            # Do not divide by a very short burst: cap the denominator at the
            # current-window age as well as at one hour.
            denominator = min(VELOCITY_WINDOW_SECONDS, max(0, now_ts - start))
            if denominator > 0:
                velocity = sum(row["total"] for row in hour_rows) / (denominator / 3600)

    projection = {"status": "no_estimate", "projected_at": None}
    if has_hit:
        projection = {"status": "hit", "projected_at": now_ts}
    elif capacity and used >= capacity:
        projection = {"status": "beyond_estimate", "projected_at": None}
    elif capacity and velocity and velocity > 0:
        projected = now_ts + (capacity - used) / velocity * 3600
        projection = {
            "status": "safe" if projected > end else "hit",
            "projected_at": projected,
        }
    elif velocity is None:
        projection = {"status": "insufficient", "projected_at": None}
    elif velocity <= 0:
        projection = {"status": "flat", "projected_at": None}

    return {
        "start": _iso(start),
        "end": _iso(end),
        "direct_tokens": used,
        "estimated_percent": percent,
        "capacity_tokens": capacity,
        "velocity_per_hour": velocity,
        "has_hit": has_hit,
        "projection": {
            "status": projection["status"],
            "projected_at": _iso(projection["projected_at"]),
        },
    }


def summarize_claude(events, direct, now):
    now_ts = now.timestamp()
    events = _dedupe_events(events)
    samples, capacity = _claude_capacity(events, direct, now_ts)
    capacity_value = capacity["median"]
    if capacity["safe_floor"] is not None and (
            capacity_value is None or capacity["safe_floor"] > capacity_value):
        capacity_value = capacity["safe_floor"]
    current = _claude_current(direct, capacity_value, events, now_ts)
    history = sorted(events, key=lambda event: event["at"], reverse=True)[:RECENT_EVENTS]
    return {
        "kind": "estimate",
        "samples": capacity,
        "current": current,
        "events": [{
            "at": _iso(event["at"]),
            "type": event.get("type"),
            "status": event.get("status"),
            "resets_at": _iso(event.get("resets_at")),
        } for event in history],
    }


# ---------- collection ----------

def collect(sources=None, use_cache=True, now=None):
    selected = list(sources) if sources else list(DEFAULT_SOURCES)
    now = now or datetime.now(config.TZ)
    scan = scan_rate_limits(selected, use_cache=use_cache)

    claude_records = (readers.read_all(sources=["claude"], use_cache=use_cache)
                      if "claude" in selected else [])
    direct = direct_claude_records(claude_records)

    return {
        "generated_at": now.isoformat(),
        "timezone": config.timezone_name(),
        "sources": selected,
        "unsupported": sorted(set(selected) - set(DEFAULT_SOURCES)),
        "codex": {
            "selected": "codex" in selected,
            "kind": "official",
            "snapshot_count": len(scan["codex_snapshots"]),
            "files": scan["codex_files"],
            "plans": (summarize_codex(scan["codex_snapshots"], now)
                      if "codex" in selected else []),
        },
        "claude": {
            "selected": "claude" in selected,
            "files": scan["claude_files"],
            **(summarize_claude(scan["claude_events"], direct, now)
               if "claude" in selected else
               {"kind": "estimate", "samples": {"count": 0, "median": None,
                                                "min": None, "max": None,
                                                "safe_floor": None, "safe_windows": 0,
                                                "basis": "none"},
                "current": None, "events": []}),
        },
        "opencode": {
            "selected": "opencode" in selected,
            "kind": "none",
            "available": False,
            "reason": "no_official_quota_data",
        },
        "parsed_files": scan["parsed_files"],
    }


# ---------- text output ----------

_TEXT = {
    "en": {
        "title": "tokens quota",
        "timezone": "Timezone",
        "generated": "Generated",
        "codex": "Codex · {plan} (official)",
        "unknown_plan": "unknown",
        "window_5h": "5h window",
        "window_week": "week window",
        "window_other": "{window} window",
        "reset": "reset {time}",
        "expired": "window reset; waiting for a new snapshot",
        "no_snapshots": "no official rate-limit snapshots",
        "no_velocity": "velocity: insufficient data",
        "flat": "velocity not increasing",
        "safe": "→ about {time} (after reset; safe this window)",
        "hit": "→ about {time} ⚠",
        "reached": "already at 100%",
        "claude": "Claude (estimate, based on {count} rate-limit windows)",
        "claude_floor": "Claude (estimate, capacity floor from {safe} safe windows)",
        "claude_none": "Claude (estimate): no rate-limit samples yet; cannot estimate",
        "current": "current 5h window {start} → {end}  direct tokens {used} / estimated capacity {capacity} ({low}–{high}) ≈ {percent}%",
        "current_floor": "current 5h window {start} → {end}  direct tokens {used} / capacity at least {capacity} (highest recorded safe window) ≈ {percent}% (hit samples are stale)",
        "current_no_capacity": "current 5h window {start} → {end}  direct tokens {used}",
        "no_current": "no direct Anthropic records in the last 5 hours",
        "velocity": "velocity {rate}%/h",
        "claude_velocity": "velocity {rate}/h",
        "beyond_estimate": "past the estimate without a limit hit (estimate is low)",
        "recent": "recent rate limits:",
        "recent_item": "  {at} {type} (reset {reset})",
        "recent_item_no_reset": "  {at} {type} (reset unknown)",
        "opencode": "OpenCode: no official quota data",
        "unsupported": "{source}: no quota data",
    },
    "zh": {
        "title": "tokens quota",
        "timezone": "时区",
        "generated": "生成于",
        "codex": "Codex · {plan}（官方）",
        "unknown_plan": "未知",
        "window_5h": "5h 窗口",
        "window_week": "周窗口",
        "window_other": "{window} 窗口",
        "reset": "重置 {time}",
        "expired": "窗口已重置，等待新快照",
        "no_snapshots": "没有官方额度快照",
        "no_velocity": "速度：数据不足",
        "flat": "速度未增长",
        "safe": "→ 约 {time} 撞线（晚于重置，本窗口安全）",
        "hit": "→ 约 {time} 撞线 ⚠",
        "reached": "已达 100%",
        "claude": "Claude（估算，依据 {count} 个撞线窗口）",
        "claude_floor": "Claude（估算，容量下限来自 {safe} 个安全窗口）",
        "claude_none": "Claude（估算）：尚无撞线样本，无法估算",
        "current": "当前 5h 窗口 起 {start} → 止 {end}   直连 token {used} / 估算容量 {capacity}（{low}–{high}）≈ {percent}%",
        "current_floor": "当前 5h 窗口 起 {start} → 止 {end}   直连 token {used} / 容量至少 {capacity}（历史最高未撞线用量）≈ {percent}%（撞线样本已过时）",
        "current_no_capacity": "当前 5h 窗口 起 {start} → 止 {end}   直连 token {used}",
        "no_current": "最近 5 小时没有直连 Anthropic 记录",
        "velocity": "速度 {rate}%/h",
        "claude_velocity": "速度 {rate}/h",
        "beyond_estimate": "已超过历史估算，仍未撞线（估算偏低）",
        "recent": "最近撞线：",
        "recent_item": "  {at} {type}（重置 {reset}）",
        "recent_item_no_reset": "  {at} {type}（重置时间未知）",
        "opencode": "OpenCode：无官方额度数据",
        "unsupported": "{source}：无额度数据",
    },
}


def _human(n):
    if n is None:
        return "—"
    if n >= 100_000_000:
        return f"{n / 100_000_000:.2f} 亿"
    if n >= 10_000:
        return f"{n / 10_000:.1f} 万"
    return str(n)


def _human_en(n):
    if n is None:
        return "—"
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.2f}B"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def _fmt_number(value):
    return f"{value:.1f}".rstrip("0").rstrip(".")


def _signed_number(value):
    return f"{value:+.1f}".rstrip("0").rstrip(".")


def _fmt_time(epoch, now, text):
    if epoch is None:
        return "—"
    value = _local(epoch)
    if value.date() == now.date():
        return value.strftime("%H:%M")
    return value.strftime("%m-%d %H:%M")


def _window_text(minutes, text):
    if minutes == SHORT_WINDOW_MINUTES:
        return text["window_5h"]
    if minutes == WEEK_WINDOW_MINUTES:
        return text["window_week"]
    return text["window_other"].format(window=window_label(minutes))


def _print_codex(report, text, lang, now):
    print()
    plans = report["codex"]["plans"]
    if not plans:
        print(f"Codex: {text['no_snapshots']}")
        return
    for plan in plans:
        label = plan.get("plan_type") or text["unknown_plan"]
        print(text["codex"].format(plan=label))
        for limit in plan["limits"]:
            prefix = limit.get("limit_name") or limit.get("limit_id")
            if prefix in (None, "codex"):
                prefix = ""
            else:
                prefix += " "
            for window in limit["windows"]:
                label_window = _window_text(window["window_minutes"], text)
                if window["status"] == "expired":
                    print(f"  {prefix}{label_window}  {text['expired']}")
                    continue
                used = window["used_percent"]
                used_text = "—" if used is None else f"{_fmt_number(used)}%"
                reset = _fmt_time(_epoch(window["resets_at"]), now, text)
                line = f"  {prefix}{label_window}  {used_text}  {text['reset'].format(time=reset)}"
                velocity = window.get("velocity_per_hour")
                if velocity is None:
                    line += f"  {text['no_velocity']}"
                else:
                    line += f"  {text['velocity'].format(rate=_signed_number(velocity))}"
                projection = window["projection"]
                if projection["status"] == "safe":
                    line += "  " + text["safe"].format(
                        time=_fmt_time(_epoch(projection["projected_at"]), now, text))
                elif projection["status"] == "hit":
                    if used is not None and used >= 100:
                        line += "  " + text["reached"]
                    else:
                        line += "  " + text["hit"].format(
                            time=_fmt_time(_epoch(projection["projected_at"]), now, text))
                elif projection["status"] == "flat":
                    line += "  " + text["flat"]
                print(line)


def _print_claude(report, text, lang, now):
    claude = report["claude"]
    print()
    samples = claude["samples"]
    basis = samples.get("basis", "none")
    if basis == "safe_floor":
        print(text["claude_floor"].format(safe=samples.get("safe_windows", 0)))
    elif samples["count"]:
        print(text["claude"].format(count=samples["count"]))
    else:
        print(text["claude_none"])
    current = claude.get("current")
    if not current:
        print(f"  {text['no_current']}")
    else:
        start = _fmt_time(_epoch(current["start"]), now, text)
        end = _fmt_time(_epoch(current["end"]), now, text)
        human = _human if lang == "zh" else _human_en
        if current.get("capacity_tokens"):
            if basis == "safe_floor":
                print("  " + text["current_floor"].format(
                    start=start, end=end, used=human(current["direct_tokens"]),
                    capacity=human(current["capacity_tokens"]),
                    percent=f"{current['estimated_percent']:.0f}",
                ))
            else:
                print("  " + text["current"].format(
                    start=start, end=end, used=human(current["direct_tokens"]),
                    capacity=human(current["capacity_tokens"]),
                    low=human(samples["min"]), high=human(samples["max"]),
                    percent=f"{current['estimated_percent']:.0f}",
                ))
        else:
            print("  " + text["current_no_capacity"].format(
                start=start, end=end, used=human(current["direct_tokens"])))
        velocity = current.get("velocity_per_hour")
        projection = current["projection"]
        if velocity is None:
            print(f"  {text['no_velocity']}")
            if projection["status"] == "hit":
                print("  " + text["hit"].format(
                    time=_fmt_time(_epoch(projection["projected_at"]), now, text)))
            elif projection["status"] == "beyond_estimate":
                print("  " + text["beyond_estimate"])
        else:
            line = "  " + text["claude_velocity"].format(rate=human(velocity))
            if projection["status"] == "hit":
                line += "  " + text["hit"].format(
                    time=_fmt_time(_epoch(projection["projected_at"]), now, text))
            elif projection["status"] == "safe":
                line += "  " + text["safe"].format(
                    time=_fmt_time(_epoch(projection["projected_at"]), now, text))
            elif projection["status"] == "flat":
                line += "  " + text["flat"]
            elif projection["status"] == "insufficient":
                line += "  " + text["no_velocity"]
            elif projection["status"] == "beyond_estimate":
                line += "  " + text["beyond_estimate"]
            print(line)
    events = claude.get("events") or []
    if events:
        print(f"  {text['recent']}")
        for event in events:
            at = _fmt_time(_epoch(event["at"]), now, text)
            kind = event.get("type") or "unknown"
            if event.get("resets_at"):
                print(text["recent_item"].format(
                    at=at, type=kind,
                    reset=_fmt_time(_epoch(event["resets_at"]), now, text)))
            else:
                print(text["recent_item_no_reset"].format(at=at, type=kind))


def print_report(report, lang="en"):
    text = _TEXT.get(lang, _TEXT["en"])
    now = datetime.fromisoformat(report["generated_at"])
    print(text["title"])
    print(f"  {text['timezone']}: {report['timezone']}")
    print(f"  {text['generated']}: {now.strftime('%Y-%m-%d %H:%M')}")
    if report["codex"]["selected"]:
        _print_codex(report, text, lang, now)
    if report["claude"]["selected"]:
        _print_claude(report, text, lang, now)
    if report["opencode"]["selected"]:
        print()
        print(text["opencode"])
    for source in report.get("unsupported", []):
        print()
        print(text["unsupported"].format(source=source.title()))
