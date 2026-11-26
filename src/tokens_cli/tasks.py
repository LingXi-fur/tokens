"""Optional agent-taskboard (atb) task cost join.

Reads `atb export --json` through a subprocess only (never imports atb),
matches each native session segment to tokens records, and prices the segment
with the same official reference rates as the cost ledger.  No atb install,
no `.taskboard/`, or a failed export simply disables the block.

Privacy: the payload carries task ids, agent names, statuses, counts and
money.  Task titles are local-only and dropped when the report is anonymized.
Segment ids, session ids and paths never enter the payload.
"""
from __future__ import annotations

import json
import os
import shlex
import shutil
import statistics
import subprocess
import threading
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from . import config, outcomes, sources as source_registry

TASKS_SCHEMA = 1
ATB_TIMEOUT_SECONDS = 120
CACHE_TTL_SECONDS = 600
CACHE_SCHEMA = 1
# atb adapter names -> tokens source names.  Unknown/plugin adapters stay
# unmatched instead of being guessed.
ADAPTER_SOURCES = {
    "claude-code": "claude",
    "codex": "codex",
    "gemini-cli": "gemini",
    "opencode": "opencode",
}
BASIS_KINDS = ("worktree", "command", "time_window")

_RUNNING = set()
_LOCK = threading.Lock()


def _cache_path():
    return os.path.join(config.CACHE_DIR, "atb-tasks-v1.json")


def _load_cache():
    try:
        with open(_cache_path(), "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {"v": CACHE_SCHEMA, "repos": {}}
    if (not isinstance(data, dict) or data.get("v") != CACHE_SCHEMA
            or not isinstance(data.get("repos"), dict)):
        return {"v": CACHE_SCHEMA, "repos": {}}
    return data


def _save_cache(data):
    try:
        os.makedirs(config.CACHE_DIR, exist_ok=True)
        temp = _cache_path() + ".tmp"
        with open(temp, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, separators=(",", ":"))
        os.replace(temp, _cache_path())
    except (OSError, ValueError):
        pass


def _epoch(value):
    if not isinstance(value, str):
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.timestamp()


def _split_command(raw, windows=None):
    """Split ``TOKENS_ATB_CMD`` into argv.

    POSIX shell rules would treat the backslashes of a Windows path such as
    ``C:\\Python\\python.exe`` as escapes and drop them, so on Windows split
    without escapes and strip one pair of surrounding quotes per argument.
    """
    if windows is None:
        windows = os.name == "nt"
    if not windows:
        return shlex.split(raw)
    parts = []
    for part in shlex.split(raw, posix=False):
        if len(part) >= 2 and part[0] == part[-1] and part[0] in "\"'":
            part = part[1:-1]
        parts.append(part)
    return parts


def _command():
    raw = os.environ.get("TOKENS_ATB_CMD", "").strip()
    if raw:
        try:
            parts = _split_command(raw)
        except ValueError:
            return None
        return parts or None
    found = shutil.which("atb")
    return [found] if found else None


def _taskboard_signature(repo):
    try:
        return os.stat(os.path.join(repo, ".taskboard")).st_mtime_ns
    except OSError:
        return None


def _candidate_repos(repos):
    candidates, seen = [], set()
    for repo in repos:
        try:
            path = os.path.realpath(repo)
        except (OSError, ValueError):
            continue
        if path in seen:
            continue
        seen.add(path)
        if _taskboard_signature(path) is not None:
            candidates.append(path)
    raw = os.environ.get("TOKENS_ATB_REPOS", "")
    for item in raw.split(os.pathsep):
        item = item.strip()
        if not item or not os.path.isabs(item):
            continue
        path = os.path.realpath(item)
        if path in seen:
            continue
        seen.add(path)
        if _taskboard_signature(path) is not None:
            candidates.append(path)
    return candidates


def _run_export(repo):
    """(export, error) for one repository; never raises."""
    command = _command()
    if command is None:
        return None, "atb_missing"
    try:
        completed = subprocess.run(
            [*command, "export", "--json"],
            cwd=repo, timeout=ATB_TIMEOUT_SECONDS, capture_output=True,
            text=True, encoding="utf-8", errors="replace",
        )
    except subprocess.TimeoutExpired:
        return None, "atb_failed"
    except (OSError, ValueError):
        return None, "atb_failed"
    if completed.returncode != 0:
        return None, "atb_failed"
    try:
        export = json.loads(completed.stdout)
    except (ValueError, RecursionError):
        return None, "atb_failed"
    if not isinstance(export, dict):
        return None, "atb_failed"
    if export.get("schema") != 1:
        return None, "atb_schema"
    if not isinstance(export.get("tasks"), list):
        return None, "atb_failed"
    return export, None


def _cache_fresh(entry, signature, now_ts):
    return (isinstance(entry, dict) and entry.get("signature") == signature
            and isinstance(entry.get("fetched_at"), (int, float))
            and now_ts - entry["fetched_at"] < CACHE_TTL_SECONDS)


def _ensure_export(repo, background, reasons, cache, now_ts):
    """Export for repo, spawning a worker when background=True.

    Returns (export, loading).  A fresh cache wins; a stale cached export is
    still shown while a background refresh runs.  Failures keep the stale data
    when present and record a reason.
    """
    entry = cache["repos"].get(repo)
    signature = _taskboard_signature(repo)
    if _cache_fresh(entry, signature, now_ts):
        if entry.get("error"):
            if entry["error"] in ("atb_missing", "atb_failed", "atb_schema"):
                reasons[entry["error"]] += 1
            return None, False
        return entry.get("export"), False
    if not background:
        export, error = _run_export(repo)
        cache["repos"][repo] = {
            "signature": signature, "fetched_at": now_ts,
            "export": export, "error": error,
        }
        if error:
            reasons[error] += 1
            stale = entry.get("export") if isinstance(entry, dict) else None
            return stale, False
        return export, False
    with _LOCK:
        if repo not in _RUNNING:
            _RUNNING.add(repo)

            def work():
                export, error = _run_export(repo)
                data = _load_cache()
                data["repos"][repo] = {
                    "signature": _taskboard_signature(repo),
                    "fetched_at": time.time(), "export": export, "error": error,
                }
                _save_cache(data)
                with _LOCK:
                    _RUNNING.discard(repo)

            threading.Thread(target=work, daemon=True).start()
    stale = entry.get("export") if isinstance(entry, dict) else None
    if stale is None:
        return None, True
    if isinstance(entry, dict) and entry.get("error") in (
            "atb_missing", "atb_failed", "atb_schema"):
        reasons[entry["error"]] += 1
    return stale, True


def _record_index(records):
    """(tokens source, native session id) -> [(epoch, record)] sorted."""
    index = defaultdict(list)
    for record in records:
        if not isinstance(record, dict):
            continue
        source = record.get("source")
        # Codex keeps its rollout id in ``native_session`` so the dashboard's
        # historical session shape/privacy contract is unchanged.
        session = record.get("native_session") or record.get("session")
        at = _epoch(record.get("ts"))
        total = record.get("total")
        if (source not in ADAPTER_SOURCES.values() or not session
                or at is None or isinstance(total, bool)
                or not isinstance(total, int) or total < 0):
            continue
        index[(source, session)].append((at, record))
    for rows in index.values():
        rows.sort(key=lambda item: item[0])
    return index


def _segment_bounds(segment):
    start = _epoch(segment.get("from"))
    if start is None:
        start = _epoch(segment.get("started_at"))
    end = _epoch(segment.get("to"))
    if end is None:
        end = _epoch(segment.get("last_active_at"))
    return start, end


def _price(record, rates_table):
    parts, rates = outcomes._model_rates(record, rates_table)
    if parts is None:
        return None
    return sum((Decimal(part) * rate for part, rate in zip(parts, rates)
                if rate is not None and part), Decimal(0)) / Decimal(1_000_000)


def _segments_for_session(segments):
    """Map records to at most one segment: [from, to), last segment includes to.

    ``segments`` is a list of (task, segment, from, to, final).  Records at a
    boundary go to the segment that starts there (the next one); only the last
    segment of a session may include its own ``to``.
    """
    ordered = sorted(segments, key=lambda item: (item[2] is None, item[2] or 0.0))
    starts = [item[2] if item[2] is not None else float("-inf")
              for item in ordered]
    return ordered, starts


def _assign_segment(at, ordered, starts):
    import bisect
    index = bisect.bisect_right(starts, at) - 1
    if index < 0:
        return None
    task, segment, start, end, final = ordered[index]
    if end is None:
        return None
    if at < end or (at == end and final):
        return ordered[index]
    return None


def _match(exports, index, rates_table):
    tasks_by_id, evidence = [], Counter()
    mismatch = 0
    segment_groups = defaultdict(list)
    for repo, export in exports:
        for task in export.get("tasks", []):
            if not isinstance(task, dict):
                continue
            segments = []
            for segment in task.get("sessions") or []:
                if not isinstance(segment, dict):
                    continue
                source = ADAPTER_SOURCES.get(segment.get("adapter"))
                session = segment.get("id")
                start, end = _segment_bounds(segment)
                if source and session:
                    segment_groups[(source, session)].append(
                        (task, segment, start, end))
                basis = segment.get("basis")
                if basis in BASIS_KINDS:
                    evidence[basis] += 1
            tasks_by_id.append((repo, task, segments))
    # Determine the final segment of each native session after all tasks are
    # known: its ``to`` equals the session's last activity and no other segment
    # starts at that exact time.
    finals = {}
    for key, rows in segment_groups.items():
        ends = [end for _, segment, _, end in rows
                if end is not None]
        starts_at = {start for _, _, start, _ in rows if start is not None}
        last = max(ends) if ends else None
        if last is None:
            continue
        for row in rows:
            _, segment, _, end = row
            activity = _epoch(segment.get("last_active_at"))
            final = (end == last and (activity is None or end == activity)
                     and end not in starts_at)
            if final:
                finals[(key, id(segment))] = True

    assigned = defaultdict(list)
    for key, rows in segment_groups.items():
        prepared = [(task, segment, start, end,
                     finals.get((key, id(segment)), False))
                    for task, segment, start, end in rows]
        ordered, starts = _segments_for_session(prepared)
        for at, record in index.get(key, ()):
            hit = _assign_segment(at, ordered, starts)
            if hit is not None:
                assigned[id(hit[1])].append(record)

    tasks = []
    for repo, task, _ in tasks_by_id:
        cost = Decimal(0)
        tokens = matched_segments = segments_total = 0
        segment_rows = task.get("sessions") or []
        for segment in segment_rows:
            if not isinstance(segment, dict):
                continue
            segments_total += 1
            rows = assigned.get(id(segment), ())
            if not rows:
                continue
            matched_segments += 1
            segment_total = 0
            components = Counter()
            for record in rows:
                tokens += record.get("total", 0) or 0
                segment_total += record.get("total", 0) or 0
                for part in ("input", "output", "cache_read", "cache_write"):
                    value = record.get(part)
                    if isinstance(value, int) and not isinstance(value, bool) \
                            and value >= 0:
                        components[part] += value
                priced = _price(record, rates_table)
                if priced is not None:
                    cost += priced
            usage = segment.get("usage")
            expected = usage.get("total") if isinstance(usage, dict) else None
            if isinstance(expected, int) and expected > 0:
                # atb adapters expose different component sets (for example
                # OpenCode omits cache reads).  Compare like for like against
                # the components atb actually reported, instead of treating a
                # definitional difference as a usage mismatch.
                reported = [part for part in ("input", "output", "cache_read",
                                              "cache_write")
                            if part in usage]
                comparable = (sum(components[part] for part in reported)
                              if reported else segment_total)
                if abs(comparable - expected) > 0.05 * max(1, expected):
                    mismatch += 1
        tasks.append({
            "repo": repo,
            "id": task.get("id"),
            "title": task.get("title"),
            "agent": task.get("agent") or "unknown",
            "status": task.get("status") or "unknown",
            "merged": bool(task.get("merged")),
            "rework_count": int(task.get("rework_count") or 0),
            "cost": cost,
            "tokens": tokens,
            "segments": segments_total,
            "matched_segments": matched_segments,
        })
    return tasks, evidence, mismatch


def _agent_rows(tasks):
    grouped = defaultdict(list)
    for task in tasks:
        grouped[task["agent"]].append(task)
    rows = []
    for agent, items in grouped.items():
        merged = [task for task in items if task["merged"]]
        costs = sorted(float(task["cost"]) for task in merged)
        avg = (sum(costs) / len(costs)) if costs else 0.0
        median = statistics.median(costs) if costs else 0.0
        reworked = sum(1 for task in items if task["rework_count"] >= 1)
        rows.append({
            "agent": agent,
            "tasks": len(items),
            "merged_tasks": len(merged),
            "avg_cost_merged": round(avg, 2),
            "median_cost_merged": round(median, 2),
            "rework_rate": round(reworked / len(items), 3) if items else 0.0,
            "avg_tokens": round(sum(task["tokens"] for task in items)
                                / len(items), 1) if items else 0.0,
            "avg_rework": round(sum(task["rework_count"] for task in items)
                                / len(items), 3) if items else 0.0,
            "unmatched_tasks": sum(1 for task in items
                                   if task["matched_segments"] == 0),
        })
    rows.sort(key=lambda row: (-row["merged_tasks"], row["agent"]))
    return rows


def build_tasks(*, records, repos, rates_table, now, anonymize=False,
                background=False):
    """(tasks block or None, reasons Counter) for the outcomes build."""
    reasons = Counter()
    candidates = _candidate_repos(repos)
    if not candidates:
        return None, reasons
    cache = _load_cache()
    now_ts = now.timestamp()
    exports = []
    loading = False
    for repo in candidates:
        export, running = _ensure_export(repo, background, reasons, cache,
                                         now_ts)
        loading = loading or running
        if export is not None:
            exports.append((repo, export))
    if not background:
        _save_cache(cache)
    if not exports:
        if loading:
            return {
                "schema": TASKS_SCHEMA, "available": False, "loading": True,
                "generated_at": now.isoformat(), "timezone": config.timezone_name(),
                "repos": len(candidates), "evidence": {kind: 0 for kind in BASIS_KINDS},
                "agents": [], "tasks": [], "top_tasks": [],
                "reasons": dict(reasons),
            }, reasons
        return None, reasons

    matched, evidence, mismatch = _match(exports, _record_index(records),
                                         rates_table)
    if mismatch:
        reasons["atb_usage_mismatch"] += mismatch
    tasks = sorted(matched, key=lambda task: (-float(task["cost"]), task["id"] or ""))
    for task in tasks:
        task["cost"] = outcomes._money(task["cost"])
        task.pop("repo", None)
        if anonymize:
            task.pop("title", None)
    agents = _agent_rows(tasks)
    top = [dict(task) for task in tasks[:5]]
    return {
        "schema": TASKS_SCHEMA,
        "available": True,
        "loading": loading,
        "generated_at": now.isoformat(),
        "timezone": config.timezone_name(),
        "repos": len(candidates),
        "evidence": {kind: evidence.get(kind, 0) for kind in BASIS_KINDS},
        "agents": agents,
        "tasks": tasks,
        "top_tasks": top,
        "reasons": dict(reasons),
    }, reasons
