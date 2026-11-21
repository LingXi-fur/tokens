#!/usr/bin/env python3
"""Repeatable synthetic cold-scan benchmark for Claude logs.

Generates only synthetic JSONL under a temporary directory, points every cache
path at that directory, then measures cold, warm, and incremental reads.
No real logs or user cache files are read.
"""
from __future__ import annotations

import argparse
import cProfile
import json
import os
import pstats
import resource
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tokens_cli import config, readers  # noqa: E402


def _assistant_line(index: int, tokens: int = 100) -> str:
    return json.dumps({
        "type": "assistant",
        "timestamp": "2026-11-10T10:00:00Z",
        "sessionId": f"bench-{index % 100:03d}",
        "cwd": "/synthetic/bench",
        "message": {
            "id": f"msg_{index:024d}",
            "model": "claude-opus-5.5",
            "usage": {
                "input_tokens": tokens,
                "output_tokens": tokens // 2,
                "cache_read_input_tokens": tokens * 2,
                "cache_creation_input_tokens": 1,
            },
        },
    }) + "\n"


def _user_line(index: int, size: int = 80) -> str:
    return json.dumps({
        "type": "user",
        "timestamp": "2026-11-10T10:00:01Z",
        "sessionId": f"bench-{index % 100:03d}",
        "cwd": "/synthetic/bench",
        "message": {"role": "user", "content": "synthetic non-usage line " + ("x" * size)},
    }) + "\n"


def _write_file(path: Path, target_bytes: int, start_index: int) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    index = start_index
    with path.open("w", encoding="utf-8") as handle:
        while written < target_bytes:
            user = _user_line(index, size=1000)
            handle.write(user)
            written += len(user)
            if index % 10 == 0:
                assistant = _assistant_line(index)
                handle.write(assistant)
                written += len(assistant)
            index += 1
    return index


def generate(root: Path, small_files: int, small_lines: int, big_mb: list[int]) -> None:
    index = 0
    for number in range(small_files):
        path = root / f"project-{number % 50:02d}" / f"small-{number:04d}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            for _ in range(small_lines):
                handle.write(_assistant_line(index))
                index += 1
    for number, megabytes in enumerate(big_mb, 1):
        path = root / "big" / f"big-{number}.jsonl"
        index = _write_file(path, megabytes * 1024 * 1024, index)


def _peak_mb() -> float:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        return value / (1024 * 1024)
    return value / 1024


def _measure(label: str, *, profile: bool = False) -> dict:
    profiler = cProfile.Profile() if profile else None
    if profiler is not None:
        profiler.enable()
    started = time.perf_counter()
    records = readers.read_all(sources=["claude"], use_cache=True)
    elapsed = time.perf_counter() - started
    if profiler is not None:
        profiler.disable()
    result = {
        "label": label,
        "seconds": elapsed,
        "records": len(records),
        "tokens": sum(record["total"] for record in records),
        "peak_rss_mb": _peak_mb(),
    }
    if profiler is not None:
        stats = pstats.Stats(profiler)
        ranked = sorted(stats.stats.items(), key=lambda item: item[1][3], reverse=True)
        result["profile"] = "\n".join(
            f"{key[2]}  cumulative={entry[3]:.3f}s  calls={entry[1]}"
            for key, entry in ranked[:10]
        )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--small-files", type=int, default=3000)
    parser.add_argument("--small-lines", type=int, default=20)
    parser.add_argument("--big-mb", type=int, nargs="+", default=[30, 60, 120])
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args(argv)

    sandbox = Path(tempfile.mkdtemp(prefix="tokens-cold-scan-"))
    root = sandbox / "claude"
    cache_dir = sandbox / "cache"
    root.mkdir()
    cache_dir.mkdir()
    old = (config.CLAUDE_PROJECTS, config.CACHE_DIR, config.CACHE_FILE,
           config.CCR_ROUTER_FILE, readers._ccr_rules_cache)
    try:
        config.CLAUDE_PROJECTS = str(root)
        config.CACHE_DIR = str(cache_dir)
        config.CACHE_FILE = str(cache_dir / "records-v8.json")
        config.CCR_ROUTER_FILE = str(sandbox / "missing-router.js")
        readers._ccr_rules_cache = ("", [])
        generate(root, args.small_files, args.small_lines, args.big_mb)

        cold = _measure("cold", profile=True)
        warm = _measure("warm")
        big = sorted((root / "big").glob("*.jsonl"))[0]
        with big.open("a", encoding="utf-8") as handle:
            handle.write(_assistant_line(10_000_000))
        incremental = _measure("incremental")

        for item in (cold, warm, incremental):
            print(f"{item['label']}: {item['seconds']:.3f}s "
                  f"records={item['records']} tokens={item['tokens']} "
                  f"peak_rss_mb={item['peak_rss_mb']:.1f}")
        print("\ntop functions (cold, cumulative):")
        print(cold.get("profile", ""))
    finally:
        config.CLAUDE_PROJECTS, config.CACHE_DIR, config.CACHE_FILE, \
            config.CCR_ROUTER_FILE, readers._ccr_rules_cache = old
        if args.keep:
            print(f"kept synthetic sandbox: {sandbox}")
        else:
            shutil.rmtree(sandbox, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
