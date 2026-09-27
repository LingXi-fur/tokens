#!/usr/bin/env python3
"""Build the deterministic synthetic Dashboard published with the docs."""
import argparse
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from tokens_cli import config, demo, report_dashboard


DEMO_DATE = date(2026, 9, 24)
DEMO_URL = "https://lingxi-fur.github.io/tokens/demo/"
DEMO_IMAGE_URL = "https://lingxi-fur.github.io/tokens/assets/readme-preview.png"
DEMO_META = "\n".join((
    '<meta name="description" content="Explore local-first AI CLI token analytics with generated sample data. No install, account, or log upload required.">',
    '<meta name="color-scheme" content="light dark">',
    '<meta property="og:type" content="website">',
    '<meta property="og:site_name" content="tokens">',
    '<meta property="og:title" content="tokens — Local-first AI CLI Token Dashboard">',
    '<meta property="og:description" content="Try the real tokens Dashboard with synthetic Claude Code, Gemini CLI, and Codex usage data.">',
    f'<meta property="og:url" content="{DEMO_URL}">',
    f'<meta property="og:image" content="{DEMO_IMAGE_URL}">',
    '<meta property="og:image:width" content="1440">',
    '<meta property="og:image:height" content="920">',
    '<meta name="twitter:card" content="summary_large_image">',
    '<meta name="twitter:title" content="tokens — Local-first AI CLI Token Dashboard">',
    '<meta name="twitter:description" content="Try the real Dashboard with generated sample data — no install or log upload.">',
    f'<meta name="twitter:image" content="{DEMO_IMAGE_URL}">',
))
DEFAULT_DOCS_ROOT = ROOT / "docs"
DEFAULT_OUTPUT = Path("demo/index.html")


def _safe_output(docs_root, output):
    root = Path(docs_root).expanduser().resolve()
    target = Path(output).expanduser()
    if not target.is_absolute():
        target = root / target
    target = target.resolve()
    try:
        common = Path(os.path.commonpath((root, target)))
    except ValueError as exc:
        raise ValueError("demo output must stay inside the docs root") from exc
    if common != root or target == root:
        raise ValueError("demo output must stay inside the docs root")
    return target


def _atomic_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def build_docs_demo(output=DEFAULT_OUTPUT, docs_root=DEFAULT_DOCS_ROOT):
    target = _safe_output(docs_root, output)
    previous_timezone = config.TZ
    try:
        config.set_timezone("UTC")
        bundle = demo.build_demo(today=DEMO_DATE)
        html = report_dashboard.build_dashboard_html(
            bundle["records"],
            since=bundle["since"],
            until=bundle["until"],
            sources=bundle["sources"],
            generated_at=bundle["generated_at"],
            session_titles=bundle["session_titles"],
            demo=True,
            language="en",
            head_meta=DEMO_META,
        )
    finally:
        config.TZ = previous_timezone
    _atomic_write(target, html)
    return target


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Build the deterministic synthetic Dashboard for GitHub Pages.",
    )
    parser.add_argument(
        "--docs-root",
        type=Path,
        default=DEFAULT_DOCS_ROOT,
        help="Root that must contain the generated file.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Output HTML path, absolute or relative to --docs-root.",
    )
    args = parser.parse_args(argv)
    target = build_docs_demo(args.output, args.docs_root)
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
