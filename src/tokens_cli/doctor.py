"""Environment diagnostics without reading log contents.

`collect` stays content-free. `collect_models`, used only by
`tokens doctor --models`, reuses the normal reader/cache path to explain how
each Claude request name was attributed to a model.
"""
import os
import shutil
import unicodedata

from . import aggregate, config, readers

BASIS_HEX_ALIAS = "hex_alias"
BASIS_LOGGED = "logged"
BASIS_NATIVE_DIRECT = "native_direct"
BASIS_ROUTER_RULE = "router_rule"


def collect(sources=None):
    selected = sources or list(readers.SOURCES)
    source_rows = []
    for source in selected:
        files_fn, _ = readers.SOURCES[source]
        root = {
            "claude": config.CLAUDE_PROJECTS,
            "gemini": config.GEMINI_TMP,
            "codex": config.CODEX_SESSIONS,
            "opencode": config.OPENCODE_DB,
        }[source]
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
            "exists": os.path.isfile(root) if source == "opencode" else os.path.isdir(root),
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
    }


def collect_models(sources=None, since=None, until=None, use_cache=True):
    """Group Claude records by (request_model, model) and explain attribution.

    Uses the normal reader entry point so the existing cache, completeness
    checks, and timezone semantics apply. Only aggregated fields are returned;
    cwd, session ids, and project labels never leave the reader.
    """
    selected = list(sources) if sources else list(config.DEFAULT_SOURCES)
    records = readers.read_all(sources=selected, use_cache=use_cache)
    claude = [record for record in records
              if isinstance(record, dict) and record.get("source") == "claude"]
    if since or until:
        claude = aggregate.filter_range(claude, since=since, until=until)

    groups = {}
    for record in claude:
        model = record.get("model")
        request = record.get("request_model", model)
        day = record.get("date")
        if not isinstance(request, str) or not isinstance(model, str) or not isinstance(day, str):
            continue
        group = groups.get((request, model))
        if group is None:
            group = groups[(request, model)] = {
                "request": request,
                "model": model,
                "basis": _basis(request, model),
                "records": 0,
                "tokens": 0,
                "first": day,
                "last": day,
            }
        group["records"] += 1
        group["tokens"] += record.get("total", 0)
        group["first"] = min(group["first"], day)
        group["last"] = max(group["last"], day)

    rows = sorted(groups.values(),
                  key=lambda row: (-row["tokens"], row["model"], row["request"]))
    return {
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
        "groups": rows,
    }


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

    rows = report["groups"]
    if not rows:
        print(f"  {text['empty']}")
    else:
        labels = [f"{row['request']} → {row['model']}" for row in rows]
        request_width = max([_display_width(text["request"])]
                            + [_display_width(label) for label in labels])
        basis_width = max([_display_width(text["basis"])]
                          + [_display_width(row["basis"]) for row in rows])
        records_width = max(_display_width(text["records"]),
                            len(str(max(row["records"] for row in rows))))
        tokens_width = max(_display_width(text["tokens"]),
                           len(str(max(row["tokens"] for row in rows))))
        print()
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
    totals = report["totals"]
    print()
    print("  " + text["summary"].format(
        groups=totals["groups"], records=totals["records"],
        tokens=f"{totals['tokens']:,}"))


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


def _status(ok):
    return "writable" if ok else "not writable"
