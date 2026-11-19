"""Skipped source files stay visible, are retried, and are never cached empty.

Claude/Codex remain fail-closed.  Gemini, OpenCode, and Antigravity skip a bad
file so the rest of the Dashboard still loads, but the skip must be reported in
data health and the failed parse must not be stored as an empty cache entry.
"""
from tests import _hermetic  # noqa: F401
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

from tokens_cli import cli, config, dashboard_payload, dashboard_wire, readers, report_dashboard


def _billing():
    return readers._antigravity_billing({"input": 3, "output": 4, "cache_read": 0})


def _record(source):
    return {
        "source": source,
        "ts": "2026-11-01T00:00:00Z",
        "date": "2026-11-01",
        "model": "synthetic-model",
        "input": 3,
        "output": 4,
        "cache_read": 0,
        "cache_write": 0,
        "total": 7,
        "session": "synthetic-session",
        "billing": _billing(),
    }


class ParseSkipVisibilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        cache_dir = self.root / "cache"
        cache_dir.mkdir()
        self.cache = cache_dir / "records.json"
        for patch in (
            mock.patch.object(config, "CACHE_DIR", str(cache_dir)),
            mock.patch.object(config, "CACHE_FILE", str(self.cache)),
            mock.patch.object(config, "TZ", ZoneInfo("UTC")),
        ):
            patch.start()
            self.addCleanup(patch.stop)

    def cache_entries(self):
        if not self.cache.exists():
            return {}
        return json.loads(self.cache.read_text(encoding="utf-8"))

    def payload(self, records, source, report):
        return dashboard_payload.build_payload(
            records, sources=[source], collection_report=report,
        )

    def assert_skip_reported(self, source, reason):
        report = {}
        records = readers.read_all(sources=[source], use_cache=True,
                                   collection_report=report)
        self.assertEqual([], records)
        self.assertEqual({"skipped": {source: {reason: 1}}}, report)
        payload = self.payload(records, source, report)
        self.assertEqual({source: {reason: 1}}, payload["provenance"]["skipped"])
        return report

    def assert_not_cached(self, source, path):
        self.assertNotIn(source + "::" + str(path), self.cache_entries())

    def assert_retried_after_fix(self, source, path, write_good):
        before = path.stat()
        write_good(path, before.st_size)
        os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
        after = path.stat()
        # Same size and mtime: only the absence of an empty cache entry can
        # make the reader try the repaired file again.
        self.assertEqual(before.st_size, after.st_size)
        self.assertEqual(before.st_mtime_ns, after.st_mtime_ns)
        report = {}
        records = readers.read_all(sources=[source], use_cache=True,
                                   collection_report=report)
        self.assertEqual(1, len(records))
        self.assertEqual({"skipped": {}}, report)
        self.assertIn(source + "::" + str(path), self.cache_entries())

    def test_gemini_malformed_file_is_reported_retried_and_not_cached(self):
        root = self.root / "gemini"
        path = root / "p1" / "chats" / "session-1.json"
        path.parent.mkdir(parents=True)
        bad = json.dumps({
            "sessionId": "synthetic-session",
            "messages": [{
                "type": "gemini",
                "timestamp": "2026-11-01T00:00:00Z",
                "model": "synthetic-model",
                "tokens": [1],
            }],
        }).encode()
        good = json.dumps({
            "sessionId": "synthetic-session",
            "messages": [{
                "type": "gemini",
                "timestamp": "2026-11-01T00:00:00Z",
                "model": "synthetic-model",
                "tokens": {"input": 3, "output": 4, "cached": 0, "total": 7},
            }],
        }).encode()
        size = max(len(bad), len(good))
        path.write_bytes(bad + b" " * (size - len(bad)))
        with mock.patch.object(config, "GEMINI_TMP", str(root)):
            self.assert_skip_reported("gemini", "parse_error")
            self.assert_not_cached("gemini", path)

            def write_good(target, size):
                self.assertGreaterEqual(size, len(good))
                target.write_bytes(good + b" " * (size - len(good)))

            self.assert_retried_after_fix("gemini", path, write_good)

    def _synthetic_source(self, source, failure):
        path = self.root / source / "bad.dat"
        path.parent.mkdir(parents=True)

        def parse(target):
            if Path(target).read_bytes().strip() == b"bad":
                raise failure("synthetic parse failure")
            return [_record(source)]

        return path, parse

    def _exercise_synthetic(self, source, failure, reason):
        path, parse = self._synthetic_source(source, failure)
        path.write_bytes(b"bad")
        files = lambda: [str(path)]
        with mock.patch.dict(readers.SOURCES, {source: (files, parse)}):
            self.assert_skip_reported(source, reason)
            self.assert_not_cached(source, path)

            def write_good(target, size):
                self.assertEqual(3, size)
                target.write_bytes(b"yes")

            self.assert_retried_after_fix(source, path, write_good)

    def test_opencode_read_failure_is_reported_retried_and_not_cached(self):
        self._exercise_synthetic("opencode", OSError, "read_failed")

    def test_antigravity_parse_failure_is_reported_retried_and_not_cached(self):
        self._exercise_synthetic("antigravity", ValueError, "parse_error")

    def test_mixed_good_and_bad_files_keep_good_records_and_count_skips(self):
        root = self.root / "gemini"
        good = root / "p1" / "chats" / "session-1.json"
        bad = root / "p2" / "chats" / "session-2.json"
        good.parent.mkdir(parents=True)
        bad.parent.mkdir(parents=True)
        good.write_text(json.dumps({
            "sessionId": "synthetic-session",
            "messages": [{
                "type": "gemini",
                "timestamp": "2026-11-01T00:00:00Z",
                "model": "synthetic-model",
                "tokens": {"input": 3, "output": 4, "cached": 0, "total": 7},
            }],
        }), encoding="utf-8")
        bad.write_text(json.dumps({
            "sessionId": "synthetic-session",
            "messages": [{
                "type": "gemini",
                "timestamp": "2026-11-01T00:00:00Z",
                "model": "synthetic-model",
                "tokens": [1],
            }],
        }), encoding="utf-8")
        with mock.patch.object(config, "GEMINI_TMP", str(root)):
            report = {}
            records = readers.read_all(sources=["gemini"], use_cache=True,
                                       collection_report=report)
        self.assertEqual(1, len(records))
        self.assertEqual({"skipped": {"gemini": {"parse_error": 1}}}, report)
        entries = self.cache_entries()
        self.assertIn("gemini::" + str(good), entries)
        self.assertNotIn("gemini::" + str(bad), entries)
        self.assertNotIn(b"session-2", self.cache.read_bytes())

    def test_skipped_summary_drops_paths_and_unknown_shapes(self):
        payload = dashboard_payload.build_payload([], sources=["gemini"],
                                                  collection_report={"skipped": {
            "gemini": {"parse_error": 1, "read_failed": 0, "path": 5},
            "unknown": {"parse_error": 1},
            "/synthetic/private/path": {"parse_error": 1},
        }})
        self.assertEqual({"gemini": {"parse_error": 1}},
                         payload["provenance"]["skipped"])
        self.assertNotIn("/synthetic/private/path",
                         json.dumps(payload, ensure_ascii=False))

    def test_generated_dashboard_embeds_skipped_health_without_paths(self):
        report = {"skipped": {"antigravity": {"parse_error": 1}}}
        html = report_dashboard.build_dashboard_html(
            [], sources=["antigravity"], collection_report=report,
        )
        marker = "const WIRE = "
        wire, _ = json.JSONDecoder().raw_decode(html.split(marker, 1)[1])
        payload = dashboard_wire.decode_payload(wire)
        self.assertEqual({"antigravity": {"parse_error": 1}},
                         payload["provenance"]["skipped"])
        self.assertNotIn(str(self.root), html)
        self.assertIn("prov-skips", html)

    def test_claude_and_codex_still_fail_closed(self):
        for source in ("claude", "codex"):
            with self.subTest(source=source):
                path = self.root / source / "bad.dat"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"bad")

                def parse(target):
                    raise ValueError("synthetic parse failure")

                with mock.patch.dict(readers.SOURCES, {
                        source: (lambda: [str(path)], parse)}):
                    with self.assertRaises(readers.CollectionIncompleteError) as caught:
                        readers.read_all(sources=[source], use_cache=True,
                                         collection_report={})
                self.assertEqual(source, caught.exception.source)
                self.assertEqual("read_failed", caught.exception.reason)

    def test_cli_dashboard_reports_a_source_whose_only_file_was_skipped(self):
        root = self.root / "gemini"
        path = root / "p1" / "chats" / "session-1.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({
            "sessionId": "synthetic-session",
            "messages": [{
                "type": "gemini",
                "timestamp": "2026-11-01T00:00:00Z",
                "model": "synthetic-model",
                "tokens": [1],
            }],
        }), encoding="utf-8")
        out = self.root / "out"
        with mock.patch.object(config, "GEMINI_TMP", str(root)), \
                mock.patch.object(config, "OUT_DIR", str(out)), \
                mock.patch.object(config, "SESSION_SUMMARY_FILE", str(out / "titles.json")), \
                mock.patch("tokens_cli.cli.report_dashboard.open_path"), \
                mock.patch("sys.stdout", io.StringIO()):
            status = cli.main(["dashboard", "--no-cache", "--source", "gemini"])
        self.assertEqual(0, status)
        html = (out / "dashboard.html").read_text(encoding="utf-8")
        wire, _ = json.JSONDecoder().raw_decode(html.split("const WIRE = ", 1)[1])
        payload = dashboard_wire.decode_payload(wire)
        self.assertEqual({"gemini": {"parse_error": 1}},
                         payload["provenance"]["skipped"])
        self.assertEqual(0, payload["provenance"]["records"])

    def test_read_all_without_report_keeps_the_old_list_contract(self):
        path, parse = self._synthetic_source("antigravity", ValueError)
        path.write_bytes(b"bad")
        with mock.patch.dict(readers.SOURCES, {
                "antigravity": (lambda: [str(path)], parse)}):
            self.assertEqual([], readers.read_all(sources=["antigravity"], use_cache=True))
        self.assertNotIn("antigravity::" + str(path), self.cache_entries())


if __name__ == "__main__":
    unittest.main()
