#!/usr/bin/env python3
"""Build a self-contained 3D prototype using synthetic records only."""
import argparse
from datetime import date
import hashlib
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from tokens_cli import config, demo, dashboard_payload  # noqa: E402
from tokens_cli.report_dashboard import _embed_json  # noqa: E402


def synthetic_records(records):
    """Copy and relabel only this prototype's fixture; never alter public demo data."""
    aliases = {
        "claude-opus-4-1": "gpt-6.1-sol",
        "claude-sonnet-4-5": "gpt-5.6-luna",
        "gpt-5-codex": "gpt-6-sol",
        "gemini-2.5-pro": "deepseek-v4-pro",
    }
    result = []
    for original in records:
        row = dict(original)
        row["model"] = aliases.get(row["model"], row["model"])
        fresh = row["input"] - (row["cache_read"] if row["source"] == "codex" else 0)
        parts = [fresh, row["output"], row["cache_read"], row["cache_write"], 0]
        assert all(isinstance(value, int) and 0 <= value <= 2**53 - 1 for value in parts)
        assert sum(parts) == row["total"], "Synthetic billing must conserve reported total"
        if row["date"] != "2026-10-02":
            components = ("input", "output", "cache_read", "cache_write", "thoughts")
            row["billing"] = {"v": 1, "present": dict.fromkeys(components, True),
                              "raw": dict(zip(components, parts)), "parts": parts,
                              "uncertain": False, "reasons": []}
        result.append(row)
    return result


def synthetic_payload():
    old_timezone = config.TZ
    try:
        config.set_timezone("UTC")
        bundle = demo.build_demo(today=date(2026, 10, 13))
        records = synthetic_records([row for row in bundle["records"] if row["date"] >= "2026-10-01"])
        # Explicit titles and guards ensure no fallback can touch private logs.
        with patch("tokens_cli.dashboard_payload.readers.load_session_summaries", side_effect=AssertionError("Private readers forbidden")), \
             patch("tokens_cli.dashboard_payload.readers.build_session_index", side_effect=AssertionError("Private readers forbidden")):
            return dashboard_payload.build_payload(
                records, since="2026-10-01", until=bundle["until"],
                sources=bundle["sources"], generated_at=bundle["generated_at"],
                session_titles=bundle["session_titles"],
            )
    finally:
        config.TZ = old_timezone


def build_html(payload=None):
    asset = ROOT / "ui" / "world"
    script_path = asset / "generated" / "world.bundle.js"
    if not script_path.is_file():
        raise RuntimeError("Run npm --prefix ui/world run build first")
    template = (asset / "prototype.html").read_text(encoding="utf-8")
    script = script_path.read_text(encoding="utf-8")
    style = (asset / "prototype.css").read_text(encoding="utf-8")
    core = (ROOT / "src/tokens_cli/dashboard_assets/cost_core.js").read_text(encoding="utf-8")
    if "</script" in script.lower() or "</script" in core.lower() or "</style" in style.lower():
        raise ValueError("Unsafe inline asset")
    substitutions = {"__STYLE__": style, "__SCRIPT__": script, "__COST_CORE__": core,
                     "__DATA__": _embed_json(synthetic_payload() if payload is None else payload)}
    # Single-pass substitution: user labels cannot become accidental placeholders.
    import re
    html = re.sub(r"__STYLE__|__SCRIPT__|__DATA__|__COST_CORE__", lambda match: substitutions[match[0]], template)
    if len(html.encode("utf-8")) > 8 * 1024 * 1024:
        raise ValueError("Prototype exceeds the 8 MiB inline budget")
    return html


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="New HTML path; existing files are never overwritten")
    args = parser.parse_args()
    destination = args.output or Path(tempfile.mkdtemp(prefix="tokens-world-prototype-")) / "index.html"
    html = build_html()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8") as output:
        output.write(html)
    print("prototype=" + str(destination))
    print("bytes=" + str(len(html.encode("utf-8"))))
    print("sha256=" + hashlib.sha256(html.encode("utf-8")).hexdigest())


if __name__ == "__main__":
    main()
