#!/usr/bin/env python3
"""Run the full unittest suite across N parallel worker processes.

The serial run is one Python interpreter driving every browser and server
test; wall time is bounded by that single pipeline even though most of it is
I/O and browser waiting. This script splits the test *modules* across N
workers so the same test set finishes in a fraction of the wall time.

Isolation contract:
- every worker gets its own fresh ``HOME`` and ``TMPDIR`` (and its own
  hermetic cache redirect from ``tests/_hermetic``), so workers cannot see
  each other's files, caches, or browser profiles;
- everything else in the environment (TZ, PLAYWRIGHT_BROWSERS_PATH, PATH,
  TOKENS_*) is inherited, so results match the serial run;
- every child is reaped: the runner waits for each worker, and any straggler
  past the deadline is terminated, then killed, then waited on — no
  background process survives the script and ``pkill`` is never used.

Usage:
    PLAYWRIGHT_BROWSERS_PATH=... python3 scripts/run_tests_parallel.py \
        [--workers 8] [--durations-json PATH]

``--durations-json`` accepts the JSON emitted by ``scripts/test_durations.py``
so shards are balanced by measured seconds instead of raw module counts.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_RAN_RE = re.compile(r"^Ran (\d+) tests?", re.MULTILINE)
_RESULT_RE = re.compile(r"^(OK|FAILED)(?: \(.*\))?$", re.MULTILINE)


def discover_modules():
    modules = []
    for path in sorted((ROOT / "tests").glob("test_*.py")):
        modules.append("tests." + path.stem)
    return modules


def module_weights(durations_json, modules):
    """Aggregate measured class seconds per module; 0.0 when unknown."""
    weights = {module: 0.0 for module in modules}
    if not durations_json:
        return weights
    data = json.loads(Path(durations_json).read_text(encoding="utf-8"))
    for cls, secs in data.get("all_class_seconds", {}).items():
        name = cls.rsplit(".", 1)[0]
        if name in weights:
            weights[name] += float(secs)
    return weights


def shard(modules, weights, workers):
    """Longest-processing-time first over measured weights."""
    bins = [[] for _ in range(workers)]
    loads = [0.0] * workers
    for module in sorted(modules, key=lambda m: (-weights[m], m)):
        target = loads.index(min(loads))
        bins[target].append(module)
        loads[target] += max(weights[module], 0.001)
    return [b for b in bins if b]


def run_worker(modules, log_path, extra_env):
    env = dict(os.environ)
    home = tempfile.mkdtemp(prefix="tokens-ptest-home-")
    tmp = tempfile.mkdtemp(prefix="tokens-ptest-tmp-")
    env["HOME"] = home
    env["TMPDIR"] = tmp
    env.update(extra_env)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT / "src"), env.get("PYTHONPATH", "")]).rstrip(os.pathsep)
    proc = subprocess.Popen(
        [sys.executable, "-m", "unittest", *modules],
        cwd=str(ROOT), env=env,
        stdout=open(log_path, "w", encoding="utf-8"),
        stderr=subprocess.STDOUT,
    )
    return proc, home, tmp


def reap(proc, deadline):
    """Wait past the deadline, then terminate and kill — always reaped."""
    try:
        return proc.wait(timeout=max(1.0, deadline - time.monotonic()))
    except subprocess.TimeoutExpired:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)
        return proc.returncode


def cleanup_dir(path):
    shutil.rmtree(path, ignore_errors=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workers", type=int,
                        default=min(8, os.cpu_count() or 4))
    parser.add_argument("--durations-json", type=str, default=None,
                        help="JSON from scripts/test_durations.py for balancing")
    parser.add_argument("--deadline", type=float, default=900.0,
                        help="per-worker wall deadline in seconds")
    args = parser.parse_args(argv)

    modules = discover_modules()
    if not modules:
        raise SystemExit("no test modules found under tests/")
    weights = module_weights(args.durations_json, modules)
    bins = shard(modules, weights, max(1, args.workers))

    tmp_root = tempfile.mkdtemp(prefix="tokens-ptest-logs-")
    started = time.monotonic()
    workers = []
    homes, tmps = [], []
    for index, shard_modules in enumerate(bins):
        log_path = Path(tmp_root) / f"worker-{index}.log"
        proc, home, tmp = run_worker(shard_modules, log_path, {})
        workers.append((index, shard_modules, proc, log_path))
        homes.append(home)
        tmps.append(tmp)
        print(f"worker {index}: {len(shard_modules)} modules, pid {proc.pid}",
              flush=True)

    deadline = started + args.deadline
    results = []
    for index, shard_modules, proc, log_path in workers:
        code = reap(proc, deadline)
        results.append((index, shard_modules, proc.returncode, code, log_path))

    wall = time.monotonic() - started

    # The children are reaped above (wait/terminate/kill/wait); their scratch
    # directories are private to each worker and are removed here.
    for home, tmp in zip(homes, tmps):
        cleanup_dir(home)
        cleanup_dir(tmp)

    failed = False
    total_tests = 0
    for index, shard_modules, returncode, code, log_path in results:
        text = Path(log_path).read_text(encoding="utf-8", errors="replace")
        ran = _RAN_RE.findall(text)
        verdict = _RESULT_RE.findall(text)
        count = int(ran[-1]) if ran else 0
        total_tests += count
        ok = (returncode == 0 and code == 0 and verdict and verdict[-1] == "OK")
        failed |= not ok
        print(f"worker {index}: {'OK' if ok else 'FAILED'} "
              f"(exit={returncode}) ran {count} tests in {shard_modules}")
        if not ok:
            tail = text.strip().splitlines()[-30:]
            print("\n".join(tail))

    print(f"combined: ran {total_tests} tests across {len(bins)} workers "
          f"in {wall:.1f}s wall time")
    cleanup_dir(tmp_root)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
