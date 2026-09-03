"""Environment diagnostics without reading log contents."""
import os

from . import config, readers


def collect(sources=None):
    selected = sources or list(readers.SOURCES)
    source_rows = []
    for source in selected:
        files_fn, _ = readers.SOURCES[source]
        root = {
            "claude": config.CLAUDE_PROJECTS,
            "gemini": config.GEMINI_TMP,
            "codex": config.CODEX_SESSIONS,
        }[source]
        try:
            files = files_fn()
        except OSError:
            files = []
        readable = sum(os.path.isfile(path) and os.access(path, os.R_OK) for path in files)
        source_rows.append({
            "source": source,
            "root": root,
            "exists": os.path.isdir(root),
            "files": len(files),
            "readable": readable,
        })
    return {
        "timezone": config.timezone_name(),
        "output": config.OUT_DIR,
        "output_parent_writable": _parent_writable(config.OUT_DIR),
        "cache": config.CACHE_FILE,
        "cache_parent_writable": _parent_writable(config.CACHE_FILE),
        "sources": source_rows,
    }


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
        if not row["exists"]:
            status = "not found"
        elif not row["files"]:
            status = "no log files"
        else:
            status = f"{row['readable']}/{row['files']} readable files"
        print(f"    {row['source']:<7} {status} — {row['root']}")


def _status(ok):
    return "writable" if ok else "not writable"
