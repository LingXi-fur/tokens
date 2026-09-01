#!/usr/bin/env python3
"""可重复的 tokens Dashboard 性能基准。

默认只跑合成数据，避免读取或输出任何本机标识。传入 --real 才测本地日志。
输出 JSON，便于保存 before/after 结果。
"""
import argparse
import json
import os
import sys
import time
import tracemalloc
from contextlib import nullcontext
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from tokens_cli import config, dashboard_wire, readers, report_dashboard


def synthetic_records(count, days=365, models=6, sessions=500, projects=100):
    records = []
    for i in range(count):
        day_index = i % days
        month = min(12, 1 + day_index // 31)
        day = 1 + day_index % 28
        hour = i % 24
        records.append({
            "source": "claude",
            "ts": f"2025-{month:02d}-{day:02d}T{hour:02d}:00:00+08:00",
            "date": f"2025-{month:02d}-{day:02d}",
            "model": f"model-{i % models}",
            "input": 70,
            "output": 20,
            "cache_read": 10,
            "cache_write": 0,
            "total": 100,
            "session": f"session-{i % sessions}",
            "cwd": f"/synthetic/project-{i % projects}",
        })
    return records


def measure_payload(records, suppress_titles=True):
    title_patch = mock.patch(
        "tokens_cli.dashboard_payload.readers.session_title", return_value=""
    ) if suppress_titles else nullcontext()
    with title_patch:
        tracemalloc.start()
        started = time.perf_counter()
        payload = report_dashboard.build_payload(records, sources=["claude"])
        elapsed = time.perf_counter() - started
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    wire = json.dumps(
        dashboard_wire.encode_payload(payload),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode()
    return {
        "records": len(records),
        "seconds": round(elapsed, 6),
        "peak_bytes": peak,
        "payload_bytes": len(encoded),
        "wire_bytes": len(wire),
        "days": len(payload.get("day_details", {})),
        "sessions": len(payload.get("session_series", {})),
    }


def measure_real(use_cache):
    tracemalloc.start()
    started = time.perf_counter()
    records = readers.read_all(
        sources=config.DEFAULT_SOURCES,
        use_cache=use_cache,
    )
    read_seconds = time.perf_counter() - started
    started = time.perf_counter()
    payload = report_dashboard.build_payload(
        records,
        sources=config.DEFAULT_SOURCES,
    )
    build_seconds = time.perf_counter() - started
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    wire = json.dumps(
        dashboard_wire.encode_payload(payload),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode()
    return {
        "cached": use_cache,
        "records": len(records),
        "read_seconds": round(read_seconds, 6),
        "build_seconds": round(build_seconds, 6),
        "peak_bytes": peak,
        "payload_bytes": len(encoded),
        "wire_bytes": len(wire),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--sizes",
        default="1000,10000,50000,100000",
        help="逗号分隔的合成 record 数量",
    )
    parser.add_argument("--real", action="store_true", help="测量本机真实日志")
    parser.add_argument("--output", help="写入 JSON 文件")
    args = parser.parse_args()

    result = {
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "pid": os.getpid(),
        "synthetic": [],
    }
    for raw in args.sizes.split(","):
        count = int(raw.strip())
        result["synthetic"].append(measure_payload(synthetic_records(count)))
    if args.real:
        result["real"] = [measure_real(True), measure_real(False)]

    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
