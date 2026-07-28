"""Single-pass data aggregation for the interactive Dashboard."""
import base64
import hashlib
import heapq
import hmac
import secrets
from collections import defaultdict
from datetime import date, datetime, timedelta

import aggregate
import config
import readers
import report_term


PALETTE = ["#5b8def", "#14b8a6", "#f59e0b", "#a78bfa",
           "#f472b6", "#38bdf8", "#fb923c", "#94a3b8"]


class _ReportAliases:
    """Report-scoped keyed aliases; the random key never enters the payload."""

    def __init__(self):
        self.key = secrets.token_bytes(32)
        self.aliases = {"project": {}, "session": {}}
        self.reverse = {"project": {}, "session": {}}

    def get(self, kind, value):
        if not value:
            return value
        value = str(value)
        cached = self.aliases[kind].get(value)
        if cached:
            return cached

        digest = hmac.new(
            self.key,
            f"tokens/{kind}/v1\0{value}".encode("utf-8"),
            hashlib.sha256,
        ).digest()
        token = base64.b32encode(digest).decode("ascii").rstrip("=")
        prefix = "Project" if kind == "project" else "Session"
        length = 10
        while True:
            alias = f"{prefix}-{token[:length]}"
            owner = self.reverse[kind].get(alias)
            if owner is None or owner == value:
                break
            length += 2
        self.aliases[kind][value] = alias
        self.reverse[kind][alias] = value
        return alias


def _short_cwd(path):
    parts = str(path).replace("\\", "/").rstrip("/").split("/")
    return "/".join(parts[-2:]) or str(path)


def _entity_add(buckets, ident, model, total):
    if not ident:
        return
    item = buckets.get(ident)
    if item is None:
        item = [0, {}]
        buckets[ident] = item
    item[0] += total
    item[1][model] = item[1].get(model, 0) + total


def _top_entities(buckets, limit=6):
    return sorted(buckets.items(), key=lambda item: item[1][0], reverse=True)[:limit]


def _flow_add(buckets, left, right, total):
    if left and right:
        key = (left, right)
        buckets[key] = buckets.get(key, 0) + total


def _reuse_parts(source, total, input_value, output_value, cache_read, cache_write):
    total = max(0, total)
    fresh_input = max(0, input_value - cache_read) if source == "codex" else max(0, input_value)
    candidates = [fresh_input, max(0, output_value), max(0, cache_read), max(0, cache_write)]
    parts = []
    remaining = total
    for value in candidates:
        shown = min(value, remaining)
        parts.append(shown)
        remaining -= shown
    parts.append(remaining)
    return parts


def _period_add(buckets, period, model, total, input_value=0, output_value=0,
                cache_read=0, cache_write=0, source="unknown"):
    item = buckets.get(period)
    if item is None:
        item = {
            "total": 0,
            "calls": 0,
            "models": {},
            "model_calls": {},
            "reuse_models": {},
        }
        buckets[period] = item
    item["total"] += total
    item["calls"] += 1
    item["models"][model] = item["models"].get(model, 0) + total
    item["model_calls"][model] = item["model_calls"].get(model, 0) + 1
    parts = item["reuse_models"].setdefault(model, [0, 0, 0, 0, 0])
    for index, value in enumerate(_reuse_parts(
            source, total, input_value, output_value, cache_read, cache_write)):
        parts[index] += value



def _pack_periods(buckets):
    packed = []
    for period, stats in sorted(buckets.items()):
        models = dict(sorted(stats["models"].items(), key=lambda item: item[1], reverse=True))
        packed.append({
            "period": period,
            "total": stats["total"],
            "calls": stats["calls"],
            "models": models,
            "model_calls": dict(stats["model_calls"]),
        })
    return packed


def _reuse_periods(buckets):
    return [
        [period, stats["reuse_models"]]
        for period, stats in sorted(buckets.items())
    ]


def _new_day():
    return {
        "hourly": [0] * 24,
        "hourly_models": {},
        "cache_read": 0,
        "cache_read_models": {},
        "achievement": {
            "input": 0,
            "output": 0,
            "cache_write": 0,
            "sources": {},
            "sessions": {},
        },
        "cwds": {},
        "sessions": {},
        "project_model": {},
        "model_session": {},
    }


def _flow_payload(project_model, model_session, title_for_session):
    session_ids = {sid for _, sid in model_session}
    labels = {
        sid: title_for_session(sid) or str(sid)[:8]
        for sid in session_ids
    }
    return {
        "project_model": [
            [_short_cwd(cwd), cwd, model, total]
            for (cwd, model), total in sorted(
                project_model.items(), key=lambda item: item[1], reverse=True
            )
        ],
        "model_session": [
            [model, labels[sid], sid, total]
            for (model, sid), total in sorted(
                model_session.items(), key=lambda item: item[1], reverse=True
            )
        ],
    }


def _entity_payload(buckets, label_for_ident):
    return [
        [label_for_ident(ident), stats[0], ident, dict(stats[1])]
        for ident, stats in sorted(
            buckets.items(), key=lambda item: item[1][0], reverse=True
        )
    ]


def _top_cwds(buckets):
    return _entity_payload(
        dict(_top_entities(buckets)),
        _short_cwd,
    )


def _top_sessions(buckets, title_for_session):
    return _entity_payload(
        dict(_top_entities(buckets)),
        lambda sid: title_for_session(sid) or str(sid)[:8],
    )


def build_payload(records, since=None, until=None, sources=None, anonymize=False):
    generated_at = datetime.now(config.TZ)
    aliases = _ReportAliases() if anonymize else None
    model_totals = {}
    hourly = [0] * 24
    hour_buckets = {}
    day_acc = {}
    day_periods = {}
    week_periods = {}
    month_periods = {}
    global_cwds = {}
    global_sessions = {}
    global_project_model = {}
    global_model_session = {}
    replay_heaps = defaultdict(list)
    session_counts = defaultdict(int)
    session_totals = defaultdict(int)
    cwd_totals = defaultdict(int)
    source_totals = defaultdict(int)
    model_stats = {}
    cache_read = 0
    input_total = 0
    output_total = 0
    cache_write_total = 0
    first_day = None
    last_day = None
    provenance = {
        "records": 0,
        "total": 0,
        "valid_ts": 0,
        "with_cwd": 0,
        "with_session": 0,
        "replay_eligible": 0,
        "replay_retained": 0,
        "with_input": 0,
        "with_output": 0,
        "with_cache_read": 0,
        "with_cache_write": 0,
        "with_components": 0,
        "first_day": None,
        "last_day": None,
        "sources": {},
    }
    record_counter = 0

    for record in records:
        day = record["date"]
        if since and day < since:
            continue
        if until and day > until:
            continue

        total = record.get("total", 0) or 0
        model = record.get("model") or "unknown"
        source = record.get("source") or "unknown"
        raw_cwd = record.get("cwd")
        raw_sid = record.get("session")
        cwd = raw_cwd
        sid = raw_sid
        if aliases:
            cwd = aliases.get("project", cwd)
            sid = aliases.get("session", sid)
        cache_value = record.get("cache_read", 0) or 0
        input_value = record.get("input", 0) or 0
        output_value = record.get("output", 0) or 0
        cache_write = record.get("cache_write", 0) or 0

        local_dt = readers.parse_local_dt(record.get("ts"))
        source_provenance = provenance["sources"].setdefault(source, {
            "records": 0,
            "total": 0,
            "valid_ts": 0,
            "with_cwd": 0,
            "with_session": 0,
            "with_input": 0,
            "with_output": 0,
            "with_cache_read": 0,
            "with_cache_write": 0,
            "with_components": 0,
        })
        provenance["records"] += 1
        provenance["total"] += total
        provenance["first_day"] = day if provenance["first_day"] is None or day < provenance["first_day"] else provenance["first_day"]
        provenance["last_day"] = day if provenance["last_day"] is None or day > provenance["last_day"] else provenance["last_day"]
        source_provenance["records"] += 1
        source_provenance["total"] += total
        component_keys = ("input", "output", "cache_read", "cache_write")
        coverage = (
            ("valid_ts", local_dt is not None),
            ("with_cwd", bool(raw_cwd)),
            ("with_session", bool(raw_sid)),
            ("with_input", "input" in record and record.get("input") is not None),
            ("with_output", "output" in record and record.get("output") is not None),
            ("with_cache_read", "cache_read" in record and record.get("cache_read") is not None),
            ("with_cache_write", "cache_write" in record and record.get("cache_write") is not None),
            ("with_components", all(key in record and record.get(key) is not None for key in component_keys)),
        )
        for key, present in coverage:
            if present:
                provenance[key] += 1
                source_provenance[key] += 1
        if raw_sid:
            provenance["replay_eligible"] += 1

        model_totals[model] = model_totals.get(model, 0) + total
        cache_read += cache_value
        input_total += input_value
        output_total += output_value
        cache_write_total += cache_write
        first_day = day if first_day is None or day < first_day else first_day
        last_day = day if last_day is None or day > last_day else last_day

        parsed_day = date.fromisoformat(day)
        week = aggregate.week_start(parsed_day).isoformat()
        month = aggregate.month_start(parsed_day).isoformat()
        _period_add(day_periods, day, model, total, input_value, output_value, cache_value, cache_write, source)
        _period_add(week_periods, week, model, total, input_value, output_value, cache_value, cache_write, source)
        _period_add(month_periods, month, model, total, input_value, output_value, cache_value, cache_write, source)

        detail = day_acc.get(day)
        if detail is None:
            detail = _new_day()
            day_acc[day] = detail
        detail["cache_read"] += cache_value
        detail["cache_read_models"][model] = detail["cache_read_models"].get(model, 0) + cache_value
        achievement = detail["achievement"]
        achievement["input"] += input_value
        achievement["output"] += output_value
        achievement["cache_write"] += cache_write
        achievement["sources"][source] = achievement["sources"].get(source, 0) + total
        if sid:
            achievement["sessions"][sid] = achievement["sessions"].get(sid, 0) + 1
        _entity_add(detail["cwds"], cwd, model, total)
        _entity_add(detail["sessions"], sid, model, total)
        _flow_add(detail["project_model"], cwd, model, total)
        _flow_add(detail["model_session"], model, sid, total)

        if local_dt is not None:
            hour = local_dt.hour
            hourly[hour] += total
            detail["hourly"][hour] += total
            model_hours = detail["hourly_models"].setdefault(model, [0] * 24)
            model_hours[hour] += total
            hour_key = (local_dt.date().isoformat(), hour)
            hour_buckets[hour_key] = hour_buckets.get(hour_key, 0) + total

        _entity_add(global_cwds, cwd, model, total)
        _entity_add(global_sessions, sid, model, total)
        _flow_add(global_project_model, cwd, model, total)
        _flow_add(global_model_session, model, sid, total)

        if cwd:
            cwd_totals[cwd] += total
        source_totals[source] += total
        stats = model_stats.setdefault(model, {
            "input": 0,
            "output": 0,
            "cache_read": 0,
            "cache_write": 0,
            "calls": 0,
        })
        stats["input"] += input_value
        stats["output"] += output_value
        stats["cache_read"] += cache_value
        stats["cache_write"] += cache_write
        stats["calls"] += 1

        if sid:
            session_counts[sid] += 1
            session_totals[sid] += total
            replay_item = (record.get("ts") or "", record_counter, total)
            heap = replay_heaps[sid]
            if len(heap) < 200:
                heapq.heappush(heap, replay_item)
            elif replay_item > heap[0]:
                heapq.heapreplace(heap, replay_item)
        record_counter += 1

    models = []
    for model in report_term.PRIORITY_MODELS:
        if model in model_totals:
            models.append(model)
    for model, _ in sorted(model_totals.items(), key=lambda item: item[1], reverse=True):
        if model not in models:
            models.append(model)
    pretty = {model: config.pretty_model(model) for model in models}
    colors = {model: PALETTE[i % len(PALETTE)] for i, model in enumerate(models)}

    if anonymize:
        def title_for_session(sid):
            return sid or ""
    else:
        summaries = readers.load_session_summaries()
        session_index = readers.build_session_index()
        title_cache = {}

        def title_for_session(sid):
            if sid not in title_cache:
                title_cache[sid] = (
                    summaries.get(sid)
                    or readers.session_title(sid, session_index=session_index)
                    or ""
                )
            return title_cache[sid]

    day_details = {}
    achievement_daily = []
    cumulative_session_turns = defaultdict(int)
    for day, detail in sorted(day_acc.items()):
        achievement = detail["achievement"]
        for sid, turns in achievement["sessions"].items():
            cumulative_session_turns[sid] += turns
        achievement_daily.append({
            "day": day,
            "input": achievement["input"],
            "output": achievement["output"],
            "cache_write": achievement["cache_write"],
            "sources": dict(achievement["sources"]),
            "max_turns": max(cumulative_session_turns.values(), default=0),
        })
        day_details[day] = {
            "hourly": detail["hourly"],
            "hourly_models": detail["hourly_models"],
            "cache_read": detail["cache_read"],
            "cache_read_models": detail["cache_read_models"],
            "cwds": _entity_payload(detail["cwds"], _short_cwd),
            "sessions": _entity_payload(
                detail["sessions"],
                lambda sid: title_for_session(sid) or str(sid)[:8],
            ),
            "top_cwds": _top_cwds(detail["cwds"]),
            "top_sessions": _top_sessions(detail["sessions"], title_for_session),
            "flow": _flow_payload(
                detail["project_model"],
                detail["model_session"],
                title_for_session,
            ),
        }

    session_series = {
        sid: [item[2] for item in sorted(heap)]
        for sid, heap in replay_heaps.items()
    }
    provenance["replay_retained"] = sum(len(values) for values in session_series.values())
    buckets = []
    for offset in range(5, -1, -1):
        point = generated_at - timedelta(hours=offset)
        buckets.append({
            "h": point.hour,
            "total": hour_buckets.get((point.date().isoformat(), point.hour), 0),
        })

    achievement_stats = {
        "input": input_total,
        "output": output_total,
        "cache_write": cache_write_total,
        "session_totals": sorted(session_totals.values(), reverse=True),
        "cwd_totals": sorted(cwd_totals.values(), reverse=True),
        "source_totals": dict(source_totals),
        "model_stats": model_stats,
        "first_day": first_day,
        "last_day": last_day,
    }

    return {
        "anonymized": anonymize,
        "generated": generated_at.strftime("%Y-%m-%d %H:%M"),
        "source": sources or [],
        "range": {"since": since, "until": until},
        "models": models,
        "pretty": pretty,
        "colors": colors,
        "cache_read": cache_read,
        "hourly": hourly,
        "day_details": day_details,
        "block": {"total": sum(item["total"] for item in buckets), "buckets": buckets},
        "top_cwds": _top_cwds(global_cwds),
        "top_sessions": _top_sessions(global_sessions, title_for_session),
        "session_series": session_series,
        "flow": _flow_payload(global_project_model, global_model_session, title_for_session),
        "n_cwds": len(global_cwds),
        "n_sessions": len(session_counts),
        "max_turns": max(session_counts.values(), default=0),
        "provenance": provenance,
        "achievement_stats": achievement_stats,
        "achievement_daily": achievement_daily,
        "reuse": {
            "day": _reuse_periods(day_periods),
            "week": _reuse_periods(week_periods),
            "month": _reuse_periods(month_periods),
        },
        "day": _pack_periods(day_periods),
        "week": _pack_periods(week_periods),
        "month": _pack_periods(month_periods),
    }
