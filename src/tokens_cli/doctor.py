"""Environment diagnostics without reading log contents.

`collect` stays content-free. `collect_models`, used only by
`tokens doctor --models`, reuses the normal reader/cache path to explain how
each Claude request name was attributed to a model and to summarize OpenCode
records without exposing message bodies.
"""
import os
import shutil
import sqlite3
import unicodedata

from . import aggregate, config, readers, sources as source_registry

BASIS_HEX_ALIAS = "hex_alias"
BASIS_LOGGED = "logged"
BASIS_NATIVE_DIRECT = "native_direct"
BASIS_ROUTER_RULE = "router_rule"
BASIS_OPENCODE_LOGGED = "opencode_logged"

# OpenCode records have no request_model; the request column stays explicit.
OPENCODE_REQUEST = "-"
_MODEL_SOURCES = ("claude", "opencode")


def collect(sources=None):
    selected = list(sources) if sources is not None else list(readers.SOURCES)
    source_rows = []
    for source in selected:
        files_fn, _ = readers.SOURCES[source]
        root = source_registry.BY_NAME[source].root()
        error = None
        try:
            files = files_fn()
        except readers.CollectionIncompleteError as exc:
            files, error = [], exc.reason
        except OSError:
            files, error = [], "discovery_failed"
        readable = sum(os.path.isfile(path) and os.access(path, os.R_OK) for path in files)
        source_rows.append({
            "source": source,
            "root": root,
            "exists": os.path.isfile(root) if source_registry.BY_NAME[source].root_kind == "file"
            else os.path.isdir(root),
            "files": len(files),
            "readable": readable,
            **({"error": error} if error else {}),
            **({"archive_exists": os.path.isdir(config.CODEX_ARCHIVED_SESSIONS),
                "compressed_files": sum(path.endswith(".zst") for path in files),
                "decompressor_available": bool(shutil.which("zstd"))}
               if source == "codex" else {}),
        })
    return {
        "timezone": config.timezone_name(),
        "output": config.OUT_DIR,
        "output_parent_writable": _parent_writable(config.OUT_DIR),
        "cache": config.CACHE_FILE,
        "cache_parent_writable": _parent_writable(config.CACHE_FILE),
        "sources": source_rows,
        "discovery": _discovery_rows(),
    }


def _discovery_rows():
    rows = []
    for source in source_registry.SOURCES:
        root = source.root()
        exists = (os.path.isfile(root) if source.root_kind == "file"
                  else os.path.isdir(root))
        readable = exists and os.access(root, os.R_OK)
        files = 0
        if exists:
            try:
                files = len(source.files())
            except (readers.CollectionIncompleteError, OSError):
                files = 0
        rows.append({
            "source": source.name,
            "label": source.label,
            "root": root,
            "exists": exists,
            "readable": readable,
            "files": files,
        })
    return rows


def collect_models(sources=None, since=None, until=None, use_cache=True):
    """Group model attribution for Claude and, when enabled, OpenCode.

    Uses the normal reader entry point so the existing cache, completeness
    checks, and timezone semantics apply. Only aggregated fields are returned;
    cwd, session ids, message bodies, and project labels never leave the
    reader. The default selection stays Claude-only.
    """
    selected = (list(sources) if sources is not None
                else [source.name for source in source_registry.SOURCES])
    enabled = {source: source in selected for source in _MODEL_SOURCES}
    records = readers.read_all(sources=selected, use_cache=use_cache) if selected else []

    claude = ([record for record in records
               if isinstance(record, dict) and record.get("source") == "claude"]
              if enabled["claude"] else [])
    opencode = ([record for record in records
                 if isinstance(record, dict) and record.get("source") == "opencode"]
                if enabled["opencode"] else [])
    opencode_produced = len(opencode)
    if since or until:
        claude = aggregate.filter_range(claude, since=since, until=until)
        opencode = aggregate.filter_range(opencode, since=since, until=until)

    groups = {}
    for record in claude:
        model = record.get("model")
        request = record.get("request_model", model)
        day = record.get("date")
        if not isinstance(request, str) or not isinstance(model, str) or not isinstance(day, str):
            continue
        _add_group(groups, "claude", request, model, day,
                   record.get("total", 0), _basis(request, model))
    for record in opencode:
        model = record.get("model")
        day = record.get("date")
        if not isinstance(model, str) or not isinstance(day, str):
            continue
        _add_group(groups, "opencode", OPENCODE_REQUEST, model, day,
                   record.get("total", 0), BASIS_OPENCODE_LOGGED)

    source_rank = {source: index for index, source in enumerate(_MODEL_SOURCES)}
    rows = sorted(groups.values(),
                  key=lambda row: (source_rank.get(row["source"], len(source_rank)),
                                   -row["tokens"], row["model"], row["request"]))

    source_totals = {}
    for source in _MODEL_SOURCES:
        if not enabled[source]:
            continue
        source_rows = [row for row in rows if row["source"] == source]
        source_totals[source] = {
            "groups": len(source_rows),
            "records": sum(row["records"] for row in source_rows),
            "tokens": sum(row["tokens"] for row in source_rows),
        }

    report = {
        "timezone": config.timezone_name(),
        "since": since,
        "until": until,
        "sources": selected,
        "router": {
            "path": config.CCR_ROUTER_FILE,
            "exists": os.path.isfile(config.CCR_ROUTER_FILE),
            "rules": [[needle, backend] for needle, backend in readers._ccr_rules()],
        },
        "totals": {
            "groups": len(rows),
            "records": sum(row["records"] for row in rows),
            "tokens": sum(row["tokens"] for row in rows),
        },
        "source_totals": source_totals,
        "groups": rows,
    }
    if enabled["opencode"]:
        report["opencode_health"] = _opencode_health(config.OPENCODE_DB, opencode_produced)
    return report


def _add_group(groups, source, request, model, day, total, basis):
    group = groups.get((source, request, model))
    if group is None:
        group = groups[(source, request, model)] = {
            "source": source,
            "request": request,
            "model": model,
            "basis": basis,
            "records": 0,
            "tokens": 0,
            "first": day,
            "last": day,
        }
    group["records"] += 1
    group["tokens"] += total
    group["first"] = min(group["first"], day)
    group["last"] = max(group["last"], day)


def _opencode_health(path, records):
    """Count assistant messages and skipped reasons through a read-only query.

    Only aggregate counts are returned. Message bodies are never selected, and
    missing/foreign databases become an explicit status instead of an error.
    """
    health = {
        "path": path,
        "exists": os.path.isfile(path),
        "status": "ok",
        "assistant_messages": 0,
        "invalid_json": 0,
        "no_tokens": 0,
        "records": records,
    }
    if not health["exists"]:
        health["status"] = "missing"
        return health
    connection = None
    try:
        connection = readers._opencode_connect(path)
        row = connection.execute(
            "SELECT COUNT(*), "
            "COALESCE(SUM(CASE WHEN json_valid(data)=0 THEN 1 ELSE 0 END),0), "
            "COALESCE(SUM(CASE WHEN json_valid(data) THEN "
            "CASE WHEN json_type(data,'$.tokens') IS NOT 'object' THEN 1 ELSE 0 END "
            "ELSE 0 END),0) "
            "FROM session_message WHERE type='assistant'"
        ).fetchone()
    except sqlite3.Error as exc:
        message = str(exc).lower()
        if "no such table" in message:
            health["status"] = "missing_table"
        elif "not a database" in message or "encrypted" in message:
            health["status"] = "invalid_database"
        else:
            health["status"] = "unreadable"
        return health
    finally:
        if connection is not None:
            connection.close()
    health["assistant_messages"], health["invalid_json"], health["no_tokens"] = row
    return health


def _basis(request, model):
    """Explain one attribution using the reader's actual precedence."""
    if readers._CCR_HEX_ALIAS_RE.fullmatch(request):
        return BASIS_HEX_ALIAS
    if request == model:
        return BASIS_LOGGED
    if model == readers._native_model_identity(request):
        return BASIS_NATIVE_DIRECT
    return BASIS_ROUTER_RULE


_MODELS_TEXT = {
    "en": {
        "timezone": "Timezone",
        "window": "Window",
        "all_dates": "all dates",
        "router": "Router",
        "rules": "{n} rules",
        "not_found": "not found; no routing rules applied",
        "request": "request → model",
        "basis": "basis",
        "records": "records",
        "tokens": "tokens",
        "span": "first..last",
        "summary": "{groups} groups, {records} records, {tokens} tokens",
        "empty": "No Claude records matched.",
        "empty_source": "No records matched for {source}.",
        "source_header": "{source}:",
        "source_labels": {"claude": "Claude", "opencode": "OpenCode"},
        "opencode_health": (
            "opencode: {messages:,} assistant messages → {records:,} records "
            "(skipped: {no_tokens:,} no tokens, {invalid_json:,} invalid json)"
        ),
        "opencode_missing": "opencode: database not found — {path}",
        "opencode_invalid_database": "opencode: not a SQLite database — {path}",
        "opencode_missing_table": "opencode: missing session_message table — {path}",
        "opencode_unreadable": "opencode: database unreadable — {path}",
    },
    "zh": {
        "timezone": "时区",
        "window": "日期范围",
        "all_dates": "全部日期",
        "router": "路由文件",
        "rules": "{n} 条规则",
        "not_found": "不存在；未应用任何路由规则",
        "request": "请求 → 归属",
        "basis": "依据",
        "records": "记录",
        "tokens": "token",
        "span": "首次..最近",
        "summary": "{groups} 组，{records} 条记录，{tokens} token",
        "empty": "没有匹配的 Claude 记录。",
        "empty_source": "{source} 没有匹配的记录。",
        "source_header": "{source}：",
        "source_labels": {"claude": "Claude", "opencode": "OpenCode"},
        "opencode_health": (
            "opencode：{messages:,} 条 assistant 消息 → {records:,} 条记录"
            "（跳过：{no_tokens:,} 条无 tokens，{invalid_json:,} 条非法 JSON）"
        ),
        "opencode_missing": "opencode：数据库不存在 — {path}",
        "opencode_invalid_database": "opencode：不是 SQLite 数据库 — {path}",
        "opencode_missing_table": "opencode：缺少 session_message 表 — {path}",
        "opencode_unreadable": "opencode：数据库无法读取 — {path}",
    },
}


def print_models(report, lang="en"):
    """Print the attribution table; columns stay obvious in either language."""
    text = _MODELS_TEXT.get(lang, _MODELS_TEXT["en"])
    print("tokens doctor --models")
    print(f"  {text['timezone']}: {report['timezone']}")
    print(f"  {text['window']}: {_window(report, text)}")
    router = report["router"]
    status = (text["rules"].format(n=len(router["rules"]))
              if router["exists"] else text["not_found"])
    print(f"  {text['router']}: {router['path']} ({status})")
    for needle, backend in router["rules"]:
        print(f"    {needle} → {backend}")

    source_totals = report.get("source_totals")
    if not isinstance(source_totals, dict) or not source_totals:
        # Backward-compatible fallback for reports collected before sources.
        source_totals = {"claude": report["totals"]}
    blocks = [source for source in _MODEL_SOURCES if source in source_totals]

    if blocks == ["claude"]:
        # Keep the original single-source layout unchanged.
        print()
        _print_table(report["groups"], text, text["empty"])
        print()
        print("  " + _summary_line(report["totals"], text))
    else:
        for source in blocks:
            label = text["source_labels"].get(source, source)
            rows = [row for row in report["groups"] if row.get("source") == source]
            print()
            print(f"  {text['source_header'].format(source=label)}")
            _print_table(rows, text, text["empty_source"].format(source=label))
            print("  " + _summary_line(source_totals[source], text))
        health = report.get("opencode_health")
        if health is not None:
            print()
            print("  " + _opencode_health_line(health, text))


def _print_table(rows, text, empty_message):
    if not rows:
        print(f"  {empty_message}")
        return
    labels = [f"{row['request']} → {row['model']}" for row in rows]
    request_width = max([_display_width(text["request"])]
                        + [_display_width(label) for label in labels])
    basis_width = max([_display_width(text["basis"])]
                      + [_display_width(row["basis"]) for row in rows])
    records_width = max(_display_width(text["records"]),
                        len(str(max(row["records"] for row in rows))))
    tokens_width = max(_display_width(text["tokens"]),
                       len(str(max(row["tokens"] for row in rows))))
    print(f"  {_pad(text['request'], request_width)}  "
          f"{_pad(text['basis'], basis_width)}  "
          f"{_rpad(text['records'], records_width)}  "
          f"{_rpad(text['tokens'], tokens_width)}  {text['span']}")
    for label, row in zip(labels, rows):
        print(f"  {_pad(label, request_width)}  "
              f"{_pad(row['basis'], basis_width)}  "
              f"{row['records']:>{records_width}}  "
              f"{row['tokens']:>{tokens_width}}  "
              f"{row['first']}..{row['last']}")


def _summary_line(totals, text):
    return text["summary"].format(
        groups=totals["groups"], records=totals["records"],
        tokens=f"{totals['tokens']:,}")


def _opencode_health_line(health, text):
    status = health.get("status")
    if status == "ok":
        return text["opencode_health"].format(
            messages=health["assistant_messages"],
            records=health["records"],
            no_tokens=health["no_tokens"],
            invalid_json=health["invalid_json"],
        )
    key = {
        "missing": "opencode_missing",
        "invalid_database": "opencode_invalid_database",
        "missing_table": "opencode_missing_table",
    }.get(status, "opencode_unreadable")
    return text[key].format(path=health["path"])


def _window(report, text):
    if report["since"] and report["until"]:
        return f"{report['since']}..{report['until']}"
    if report["since"]:
        return f"{report['since']}.."
    if report["until"]:
        return f"..{report['until']}"
    return text["all_dates"]


def _display_width(value):
    return sum(2 if unicodedata.east_asian_width(char) in "WF" else 1 for char in value)


def _pad(value, width):
    return value + " " * max(0, width - _display_width(value))


def _rpad(value, width):
    return " " * max(0, width - _display_width(value)) + value


def _parent_writable(path):
    parent = os.path.abspath(os.path.dirname(path))
    probe = parent
    while not os.path.exists(probe):
        next_probe = os.path.dirname(probe)
        if next_probe == probe:
            return False
        probe = next_probe
    return os.path.isdir(probe) and os.access(probe, os.W_OK)


def print_report(report):
    print("tokens doctor")
    print(f"  Timezone: {report['timezone']}")
    print(f"  Output:   {report['output']} ({_status(report['output_parent_writable'])})")
    print(f"  Cache:    {report['cache']} ({_status(report['cache_parent_writable'])})")
    print("  Sources:")
    for row in report["sources"]:
        if row.get("error"):
            status = "incomplete discovery (" + row["error"] + ")"
        elif not row["exists"] and not row.get("archive_exists"):
            status = "not found"
        elif not row["files"]:
            status = "no log files"
        else:
            status = f"{row['readable']}/{row['files']} readable files"
        print(f"    {row['source']:<7} {status} — {row['root']}")
        if row["source"] == "codex":
            support = "available" if row["decompressor_available"] else "unavailable"
            print(f"            {row['compressed_files']} compressed archives; zstd {support}")
    print("  Source discovery:")
    for row in report.get("discovery", []):
        state = "found" if row["exists"] else "not found"
        if row["exists"] and not row["readable"]:
            state = "unreadable"
        print(f"    {row['label']:<12} {state:<9} {row['root']} ({row['files']} candidates)")


def _status(ok):
    return "writable" if ok else "not writable"
