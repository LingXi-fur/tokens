#!/usr/bin/env python3
"""Per-test timing for the full unittest suite.

Python 3.11's unittest has no ``--durations``, so this wraps ``TestResult``:
every test is timed from ``startTest`` to ``stopTest`` (setUp + method +
tearDown), and per-class wall spans reveal fixture time that no single test
owns (setUpClass browser launches, one-off HTML builds). Prints the slowest
test classes and test methods with their share of the run, so speed-up work
targets the real hotspots.

Usage:
    HOME=$(mktemp -d) PLAYWRIGHT_BROWSERS_PATH=... \\
        python3 scripts/test_durations.py [--top 30] [--json PATH]

The suite itself is discovered exactly like ``python3 -m unittest discover
-s tests``; measurements therefore match a normal full run.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import unittest
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))


class TimingResult(unittest.TextTestResult):
    """Record wall-clock seconds per test (setUp + method + tearDown)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.durations = {}

    def startTest(self, test):
        self._started = time.perf_counter()
        super().startTest(test)

    def stopTest(self, test):
        if self._started is not None:
            stop = time.perf_counter()
            self.durations[test.id()] = (
                self.durations.get(test.id(), 0.0) + stop - self._started)
            self._started = None
        super().stopTest(test)


def class_of(test_id):
    """tests.module.Class.method -> tests.module.Class."""
    return test_id.rsplit(".", 1)[0]


class ClassTimedSuite(unittest.TestSuite):
    """Time a whole class-suite run, setUpClass/tearDownClass included.

    unittest runs class fixtures outside every single test, so per-test
    timing alone cannot see browser launches or one-off HTML builds. The
    wrapper records the wall span of the class suite; the report derives
    fixture time as span minus the sum of the class's own test times.
    """

    def __init__(self, tests, label, class_spans):
        super().__init__(tests)
        self._label = label
        self._class_spans = class_spans

    def run(self, result, debug=False):
        start = time.perf_counter()
        try:
            return super().run(result, debug=debug)
        finally:
            stop = time.perf_counter()
            prev = self._class_spans.get(self._label, 0.0)
            self._class_spans[self._label] = max(prev, stop - start)


def _wrap_class_suites(suite, class_spans):
    """Rebuild the discovered suite tree, timing every class-level suite."""
    tests = list(getattr(suite, "_tests", []))
    if not tests:
        return suite
    if all(isinstance(t, unittest.TestCase) for t in tests):
        labels = {class_of(t.id()) for t in tests}
        if len(labels) == 1:
            return ClassTimedSuite(tests, labels.pop(), class_spans)
        return suite
    return unittest.TestSuite([_wrap_class_suites(t, class_spans) for t in tests])


def measure():
    class_spans = {}
    suite = unittest.defaultTestLoader.discover(
        str(ROOT / "tests"), top_level_dir=str(ROOT))
    suite = _wrap_class_suites(suite, class_spans)
    runner = unittest.TextTestRunner(verbosity=1, resultclass=TimingResult)
    run_start = time.perf_counter()
    result = runner.run(suite)
    result.run_span = time.perf_counter() - run_start
    if not result.durations:
        raise SystemExit("no tests ran; check the discovery configuration")
    result.class_spans = class_spans
    return result


def report(result, top):
    durations = result.durations
    class_spans = result.class_spans

    per_class = defaultdict(lambda: {"total": 0.0, "tests": 0})
    for tid, secs in durations.items():
        row = per_class[class_of(tid)]
        row["total"] += secs
        row["tests"] += 1
    for cls, span in class_spans.items():
        row = per_class.setdefault(cls, {"total": 0.0, "tests": 0})
        # setUpClass/tearDownClass/gap: class wall span minus its own tests.
        row["fixture"] = max(0.0, span - row["total"])

    grand = sum(row["total"] + row.get("fixture", 0.0) for row in per_class.values())
    methods = sorted(durations.items(), key=lambda kv: -kv[1])[:top]
    classes = sorted(
        per_class.items(),
        key=lambda kv: -(kv[1]["total"] + kv[1]["fixture"]))[:top]

    lines = []
    lines.append(f"tests run: {result.testsRun}   "
                 f"sum of test+fixture time: {grand:.2f}s   "
                 f"(unittest total {getattr(result, 'run_span', grand):.2f}s)")
    lines.append("")
    lines.append(f"slowest {min(top, len(classes))} test classes")
    lines.append(f"{'class':<62} {'tests':>6} {'tests(s)':>9} {'fixture(s)':>10} "
                 f"{'total(s)':>9} {'share':>7}")
    for cls, row in classes:
        whole = row["total"] + row.get("fixture", 0.0)
        lines.append(f"{cls:<62.62} {row['tests']:>6} {row['total']:>9.2f} "
                     f"{row.get('fixture', 0.0):>10.2f} {whole:>9.2f} "
                     f"{100 * whole / grand:>6.1f}%")
    lines.append("")
    lines.append(f"slowest {min(top, len(methods))} test methods")
    lines.append(f"{'test':<86} {'seconds':>9} {'share':>7}")
    for tid, secs in methods:
        lines.append(f"{tid:<86.86} {secs:>9.2f} {100 * secs / grand:>6.1f}%")
    return "\n".join(lines), {
        "tests_run": result.testsRun,
        "grand_seconds": round(grand, 3),
        "classes": [
            {"class": cls, "tests": row["tests"],
             "test_seconds": round(row["total"], 3),
             "fixture_seconds": round(row.get("fixture", 0.0), 3),
             "total_seconds": round(row["total"] + row.get("fixture", 0.0), 3)}
            for cls, row in classes],
        "methods": [
            {"test": tid, "seconds": round(secs, 3)} for tid, secs in methods],
        "all_class_seconds": {
            cls: round(row["total"] + row.get("fixture", 0.0), 3)
            for cls, row in sorted(per_class.items())},
        "all_method_seconds": {tid: round(secs, 3) for tid, secs in durations.items()},
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--top", type=int, default=30,
                        help="how many slowest classes/methods to list")
    parser.add_argument("--json", type=str, default=None,
                        help="also write the full measurement as JSON")
    args = parser.parse_args(argv)

    result = measure()
    text, data = report(result, args.top)
    print(text)
    if args.json:
        Path(args.json).write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8")
    failures = len(result.failures) + len(result.errors)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
