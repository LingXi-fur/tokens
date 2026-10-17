"""Single-pass data aggregation for the interactive Dashboard."""
import base64
import hashlib
import heapq
import hmac
import json
import secrets
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from . import aggregate, config, readers


LIGHT_PALETTE = [
    "#2a78d6", "#eb6834", "#1baf7a", "#eda100",
    "#e87ba4", "#008300", "#4a3aa7", "#e34948",
]
DARK_PALETTE = [
    "#3987e5", "#d95926", "#199e70", "#c98500",
    "#d55181", "#008300", "#9085e9", "#e66767",
]
MODEL_IDENTITY_CAPACITY = 7
# Keep explicitly compared GLM variants independently filterable when present.
COMPARISON_MODELS = ("glm-5.3", "glm-5.3-flash")
OTHER_MODEL = "other"
SNAPSHOT_SCHEMA = 1
METRIC_SCHEMA = 1
# 费用账本（cost block）contract：schema 1，分量顺序固定，与 readers 计费证据一致。
COST_SCHEMA = 1
COST_COMPONENTS = ("input", "output", "cache_read", "cache_write", "thoughts")
# JS Number 安全整数上限：单条记录分量已由 readers.billing_view 校验；聚合桶
# 累加若将超出该上限，结束当前 row、另起同 key row，保证每个 row 的 parts/
# reportedTotal/calls 仍是安全整数（不截断、不降级、不改字符串）。
COST_MAX_SAFE = 2 ** 53 - 1


def _record_model(record):
    return record.get("model") or "unknown"


def _model_first_seen_key(record):
    """Return an orderable, input-order-independent identity key."""
    raw_ts = record.get("ts")
    if isinstance(raw_ts, str):
        try:
            parsed = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            normalized = parsed.astimezone(timezone.utc).isoformat()
            return 0, normalized
        except ValueError:
            pass
    raw_day = record.get("date")
    if isinstance(raw_day, str):
        try:
            return 1, date.fromisoformat(raw_day).isoformat()
        except ValueError:
            pass
    return 2, ""


def _model_last_seen_key(record):
    """Order activity by report day, then timestamp when available."""
    raw_day = record.get("date")
    try:
        day = date.fromisoformat(raw_day).isoformat() if isinstance(raw_day, str) else ""
    except ValueError:
        day = ""
    raw_ts = record.get("ts")
    if isinstance(raw_ts, str):
        try:
            parsed = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            normalized = parsed.astimezone(timezone.utc).isoformat()
            return day or normalized[:10], 1, normalized
        except ValueError:
            pass
    return day, 0, ""


def _model_registry(records):
    """Select major identities from all records, then assign first-seen color slots."""
    first_seen = {}
    last_seen = {}
    token_totals = defaultdict(int)
    saw_other = False
    for record in records:
        model = _record_model(record)
        if model == OTHER_MODEL:
            saw_other = True
            continue
        first_key = _model_first_seen_key(record)
        if model not in first_seen or first_key < first_seen[model]:
            first_seen[model] = first_key
        last_key = _model_last_seen_key(record)
        if model not in last_seen or last_key > last_seen[model]:
            last_seen[model] = last_key
        token_totals[model] += record.get("total", 0) or 0

    # Stable passes keep activity and first-seen order as usage tie-breakers.
    ranked = sorted(first_seen, key=lambda model: (first_seen[model], model))
    ranked.sort(key=lambda model: last_seen[model], reverse=True)
    ranked.sort(key=lambda model: token_totals[model], reverse=True)
    retained = ranked[:MODEL_IDENTITY_CAPACITY]
    if len(ranked) > MODEL_IDENTITY_CAPACITY:
        # Reserve comparison identities and the latest backend, then fill by usage.
        recent = max(ranked, key=lambda model: (last_seen[model], model))
        required = {model for model in COMPARISON_MODELS if model in first_seen}
        required.add(recent)
        retained = [model for model in ranked if model in required]
        retained += [model for model in ranked if model not in required][
            :MODEL_IDENTITY_CAPACITY - len(retained)
        ]
    retained.sort(key=lambda model: (first_seen[model], model))
    overflow = [model for model in ranked if model not in retained]
    aliases = {model: model for model in retained}
    aliases.update({model: OTHER_MODEL for model in overflow})
    if saw_other:
        aliases[OTHER_MODEL] = OTHER_MODEL

    slots = {model: index for index, model in enumerate(retained)}
    if overflow or saw_other:
        slots[OTHER_MODEL] = MODEL_IDENTITY_CAPACITY
    return aliases, slots


def _canonical_model(record, registry):
    model = _record_model(record)
    return registry.get(model, OTHER_MODEL)


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
        sid: title_for_session(sid) or ""
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
        lambda sid: title_for_session(sid) or "",
    )


def _snapshot_identity(payload):
    """Return a deterministic ID for the complete generated data payload."""
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:24]


def build_payload(records, since=None, until=None, sources=None, anonymize=False,
                  aliases=None, generated_at=None, session_titles=None):
    records = tuple(records)
    model_registry, model_slots = _model_registry(records)
    overflow_names = {
        name for name, canonical in model_registry.items()
        if canonical == OTHER_MODEL and name != OTHER_MODEL
    }
    other_model_days = defaultdict(lambda: defaultdict(int))
    generated_at = generated_at or datetime.now(config.TZ)
    aliases = aliases or (_ReportAliases() if anonymize else None)
    model_totals = {}
    hourly = [0] * 24
    hour_buckets = {}
    day_acc = {}
    day_periods = {}
    week_periods = {}
    month_periods = {}
    global_cwds = {}
    replay_heaps = defaultdict(list)
    session_counts = defaultdict(int)
    session_totals = defaultdict(int)
    # 会话背景（报告范围内聚合）：主导项目 Token 贡献、来源类别、首末活动日。
    session_project_tokens = defaultdict(lambda: defaultdict(int))
    session_sources = defaultdict(set)
    session_days = defaultdict(lambda: [None, None])
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
    latest_backend = None
    latest_backend_key = None
    latest_backend_grouped = False
    # 费用账本：桶按 日期 × source × 未折叠模型 聚合；source 是日志来源而非渠道；
    # 目录条目只有 source/model/identity/hidden，不含 session/cwd。
    cost_catalog = {}
    cost_groups = {}
    cost_total_incomplete = False

    for record in records:
        day = record["date"]
        if since and day < since:
            continue
        if until and day > until:
            continue

        total = record.get("total", 0) or 0
        raw_model = _record_model(record)
        model = _canonical_model(record, model_registry)
        if not anonymize and raw_model in overflow_names:
            other_model_days[day][raw_model] += total
        latest_key = (_model_last_seen_key(record), raw_model)
        if latest_backend_key is None or latest_key > latest_backend_key:
            latest_backend_key = latest_key
            latest_backend = model
            latest_backend_grouped = model != _record_model(record)
        source = record.get("source") or "unknown"
        # 费用账本聚合（schema 1）：不可信记录整条排除计费分量（全 0），
        # uncertain=true，原 total/calls 仍保留；不复用 _reuse_parts 截断。
        if anonymize and (raw_model in overflow_names or raw_model == OTHER_MODEL):
            # 匿名 overflow / 字面 other：按 source 合并成隐藏 'other'，不暴露原名，
            # 无法定价 → 整条 uncertain 且分量全 0（不得用统一 Other 单价强行合计）。
            cost_model = OTHER_MODEL
            catalog_key = (source, cost_model)
            if catalog_key not in cost_catalog:
                cost_catalog[catalog_key] = {
                    "source": source,
                    "model": OTHER_MODEL,
                    "identity": OTHER_MODEL,
                    "hidden": True,
                }
            cost_parts = [0] * len(COST_COMPONENTS)
            cost_uncertain = True
        else:
            cost_model = raw_model
            catalog_key = (source, cost_model)
            if catalog_key not in cost_catalog:
                cost_catalog[catalog_key] = {
                    "source": source,
                    "model": cost_model,
                    "identity": model_registry.get(cost_model, OTHER_MODEL),
                    "hidden": False,
                }
            cost_parts, cost_uncertain = readers.billing_view(record)
        # 源 reportedTotal 检测读原始 record.get("total")（不经过上面
        # `or 0` 的 legacy 变量，避免 None/False 被吞成合法 0）。
        # 异常（缺失/None/bool/负数/非 int）：保守 0 + 整条 uncertain 并置
        # total_incomplete；超 MAX_SAFE 且 ≤ 64 个安全整数 chunk：拆 chunk row
        # （parts 全 0、calls 只计首 chunk），sum 精确保留原 total，绝不把超界
        # 无损 JSON 数字直接送 JS Number；超出 64 chunk：不再截断冒充数值，
        # 置 total_incomplete 并按 unknown 计 0。旧 token 统计不受影响。
        raw_total = record.get("total")
        chunk_cap = 64  # 防恶意天文数字撑爆 payload；正常数据 1-2 个 chunk。
        if (
            isinstance(raw_total, bool)
            or not isinstance(raw_total, int)
            or raw_total < 0
        ):
            cost_totals = (0,)
            cost_uncertain = True
            cost_total_incomplete = True
        elif raw_total <= COST_MAX_SAFE:
            cost_totals = (raw_total,)
        elif raw_total <= chunk_cap * COST_MAX_SAFE:
            full, rest = divmod(raw_total, COST_MAX_SAFE)
            cost_totals = [COST_MAX_SAFE] * full
            if rest:
                cost_totals.append(rest)
            cost_uncertain = True
        else:
            cost_totals = (0,)
            cost_uncertain = True
            cost_total_incomplete = True
        cost_mask = 0
        for part_index, part_value in enumerate(cost_parts):
            if part_value:
                cost_mask |= 1 << part_index
        cost_group_key = (day, source, cost_model, cost_uncertain, cost_mask)
        cost_rows = cost_groups.setdefault(cost_group_key, [])
        for chunk_index, cost_total in enumerate(cost_totals):
            row = cost_rows[-1] if cost_rows else None
            if row is None or any(
                row[0][i] + cost_parts[i] > COST_MAX_SAFE
                for i in range(len(cost_parts))
            ) or row[1] + cost_total > COST_MAX_SAFE or row[2] + 1 > COST_MAX_SAFE:
                # 累加将超出安全整数：结束当前 row，本 chunk 另起同 key row。
                row = [[0] * len(COST_COMPONENTS), 0, 0]
                cost_rows.append(row)
            for part_index, part_value in enumerate(cost_parts):
                row[0][part_index] += part_value
            row[1] += cost_total
            row[2] += 1 if chunk_index == 0 else 0
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
            if cwd:
                session_project_tokens[sid][_short_cwd(cwd)] += total
            session_sources[sid].add(source)
            span = session_days[sid]
            if span[0] is None or day < span[0]:
                span[0] = day
            if span[1] is None or day > span[1]:
                span[1] = day
            replay_item = (record.get("ts") or "", record_counter, total)
            heap = replay_heaps[sid]
            if len(heap) < 200:
                heapq.heappush(heap, replay_item)
            elif replay_item > heap[0]:
                heapq.heapreplace(heap, replay_item)
        record_counter += 1

    models = [
        model
        for model, _ in sorted(
            model_totals.items(),
            key=lambda item: (-item[1], item[0]),
        )
    ]
    pretty = {model: config.pretty_model(model) for model in models}
    if OTHER_MODEL in pretty:
        pretty[OTHER_MODEL] = "Other"
    colors = {
        "light": {
            model: LIGHT_PALETTE[model_slots[model]]
            for model in models
        },
        "dark": {
            model: DARK_PALETTE[model_slots[model]]
            for model in models
        },
    }

    if anonymize:
        # 匿名优先：只回显会话别名，绝不读取/清洗真实标题。
        def title_for_session(sid):
            return sid or ""
    elif session_titles is not None:
        # 显式注入路径：只清洗给定标题，不再读取日志（离线安全重建契约）。
        def title_for_session(sid):
            return readers.sanitize_session_title(session_titles.get(sid, ""))
    else:
        summaries = readers.load_session_summaries()
        session_index = readers.build_session_index()
        title_cache = {}

        def title_for_session(sid):
            if sid not in title_cache:
                title_cache[sid] = (
                    readers.sanitize_session_title(summaries.get(sid) or "")
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
                lambda sid: title_for_session(sid) or "",
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

    session_context = {}
    for sid, span in session_days.items():
        projects = session_project_tokens.get(sid) or {}
        # 主导项目：Token 贡献最大；平局按显示名稳定排序。
        dominant = ""
        multi = False
        if projects:
            ranked = sorted(projects.items(), key=lambda item: (-item[1], item[0]))
            dominant = ranked[0][0]
            multi = len(ranked) > 1
        session_source_list = sorted(session_sources.get(sid, ()))
        session_context[sid] = {
            "p": dominant,
            "pm": multi,
            "s": session_source_list,
            "d0": span[0],
            "d1": span[1],
        }

    # 费用账本收尾：目录按 (source, model) 确定性排序、索引稳定；rows 按
    # (day, modelIndex, uncertain, 非零分量 bitmask) 聚合并确定性排序，
    # 前端可据此精确判断各组 calls 的全部活跃分量是否均已定价。
    cost_models_list = [
        entry for _, entry in sorted(
            cost_catalog.items(),
            key=lambda item: (item[1]["source"], item[1]["model"]),
        )
    ]
    cost_model_index = {
        (entry["source"], entry["model"]): index
        for index, entry in enumerate(cost_models_list)
    }
    cost_sorted_groups = sorted(
        (
            (day, cost_model_index[(source, cost_model)], uncertain, cost_mask, row)
            for (day, source, cost_model, uncertain, cost_mask), rows
            in cost_groups.items()
            for row in rows
        ),
        key=lambda group: (group[0], group[1], group[2], group[3]),
    )
    cost = {
        "schema": COST_SCHEMA,
        # 可选 bool：存在异常/超界 total（无法安全精确表示）时 true，前端应
        # 禁用 Token 覆盖百分比类派生指标，只保留 calls 口径说明。
        "total_incomplete": cost_total_incomplete,
        "components": list(COST_COMPONENTS),
        "models": cost_models_list,
        "rows": [
            [day, model_index, parts, reported_total, calls, uncertain]
            for day, model_index, uncertain, _cost_mask, (parts, reported_total, calls)
            in cost_sorted_groups
        ],
    }

    dashboard_data = {
        "anonymized": anonymize,
        "source": sources or [],
        "range": {
            "since": since,
            "until": until,
            "latest_backend": latest_backend,
            "latest_backend_folded": latest_backend_grouped,
        },
        "models": models,
        "other_models": [
            {"day": day, "models": dict(sorted(values.items()))}
            for day, values in sorted(other_model_days.items())
        ],
        "pretty": pretty,
        "colors": colors,
        "cache_read": cache_read,
        "hourly": hourly,
        "day_details": day_details,
        "block": {"total": sum(item["total"] for item in buckets), "buckets": buckets},
        "top_cwds": _top_cwds(global_cwds),
        "session_series": session_series,
        "session_context": session_context,
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
        "cost": cost,
    }
    snapshot_data = {
        "snapshot_schema": SNAPSHOT_SCHEMA,
        "metric_schema": METRIC_SCHEMA,
        "timezone": getattr(config.TZ, "key", str(config.TZ)),
        "coverage": {"first_day": first_day, "last_day": last_day},
    }
    snapshot = {
        **snapshot_data,
        "id": _snapshot_identity({
            "snapshot": snapshot_data,
            **dashboard_data,
        }),
    }

    return {
        "generated": generated_at.strftime("%Y-%m-%d %H:%M"),
        "snapshot": snapshot,
        **dashboard_data,
    }
