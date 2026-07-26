"""Single-pass data aggregation for the interactive Dashboard."""
import heapq
from collections import defaultdict
from datetime import date, datetime, timedelta

import aggregate
import config
import readers
import report_term


PALETTE = ["#5b8def", "#14b8a6", "#f59e0b", "#a78bfa",
           "#f472b6", "#38bdf8", "#fb923c", "#94a3b8"]


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


def _period_add(buckets, period, model, total, input_value=0, output_value=0,
                cache_read=0, cache_write=0, source="unknown"):
    item = buckets.get(period)
    if item is None:
        item = {
            "total": 0,
            "calls": 0,
            "models": {},
            "reuse_models": {},
        }
        buckets[period] = item
    item["total"] += total
    item["calls"] += 1
    item["models"][model] = item["models"].get(model, 0) + total
    parts = item["reuse_models"].setdefault(model, [0, 0, 0, 0, 0])
    # Values are mutually exclusive for visualization and always sum to total.
    if source == "claude":
        parts[0] += input_value
        parts[1] += output_value
        parts[2] += cache_read
        parts[3] += cache_write
        parts[4] += max(0, total - input_value - output_value - cache_read - cache_write)
    elif source == "gemini":
        # Gemini CLI versions disagree on whether cached tokens are already in input/total.
        # Preserve output first, then reserve cache and fit fresh input into the remainder.
        shown_output = min(output_value, total)
        remaining = total - shown_output
        cached = min(cache_read, remaining)
        remaining -= cached
        fresh_input = min(max(0, input_value - cache_read), remaining)
        remaining -= fresh_input
        parts[0] += fresh_input
        parts[1] += shown_output
        parts[2] += cached
        parts[4] += remaining
    elif source == "codex":
        # Codex input includes cached input; fit every component to total defensively.
        cached = min(cache_read, total)
        remaining = total - cached
        fresh_input = min(max(0, input_value - cache_read), remaining)
        remaining -= fresh_input
        shown_output = min(output_value, remaining)
        remaining -= shown_output
        parts[0] += fresh_input
        parts[1] += shown_output
        parts[2] += cached
        parts[4] += remaining
    else:
        parts[0] += min(total, input_value)
        parts[1] += min(max(0, total - parts[0]), output_value)
        parts[4] += max(0, total - input_value - output_value)



def _pack_periods(buckets):
    packed = []
    for period, stats in sorted(buckets.items()):
        models = dict(sorted(stats["models"].items(), key=lambda item: item[1], reverse=True))
        packed.append({
            "period": period,
            "total": stats["total"],
            "calls": stats["calls"],
            "models": models,
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


def _top_cwds(buckets):
    return [
        [_short_cwd(path), stats[0], path, dict(stats[1])]
        for path, stats in _top_entities(buckets)
    ]


def _top_sessions(buckets, title_for_session):
    return [
        [title_for_session(sid) or str(sid)[:8], stats[0], sid, dict(stats[1])]
        for sid, stats in _top_entities(buckets)
    ]


def build_payload(records, since=None, until=None, sources=None):
    generated_at = datetime.now(config.TZ)
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
        cwd = record.get("cwd")
        sid = record.get("session")
        cache_value = record.get("cache_read", 0) or 0
        input_value = record.get("input", 0) or 0
        output_value = record.get("output", 0) or 0
        cache_write = record.get("cache_write", 0) or 0

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
        _entity_add(detail["cwds"], cwd, model, total)
        _entity_add(detail["sessions"], sid, model, total)
        _flow_add(detail["project_model"], cwd, model, total)
        _flow_add(detail["model_session"], model, sid, total)

        local_dt = readers.parse_local_dt(record.get("ts"))
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
    for day, detail in day_acc.items():
        day_details[day] = {
            "hourly": detail["hourly"],
            "hourly_models": detail["hourly_models"],
            "cache_read": detail["cache_read"],
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
        "achievement_stats": achievement_stats,
        "reuse": {
            "day": _reuse_periods(day_periods),
            "week": _reuse_periods(week_periods),
            "month": _reuse_periods(month_periods),
        },
        "day": _pack_periods(day_periods),
        "week": _pack_periods(week_periods),
        "month": _pack_periods(month_periods),
    }
