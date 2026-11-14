"""Auto-discovery and source-registry contracts with synthetic roots only."""
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tokens_cli import cli, config, doctor, sources  # noqa: E402


class AutoSourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.claude = self.root / "claude"
        self.gemini = self.root / "gemini"
        self.codex = self.root / "codex"
        self.opencode = self.root / "opencode" / "opencode.db"
        self.patches = [
            mock.patch.object(config, "CLAUDE_PROJECTS", str(self.claude)),
            mock.patch.object(config, "GEMINI_TMP", str(self.gemini)),
            mock.patch.object(config, "CODEX_SESSIONS", str(self.codex)),
            mock.patch.object(config, "CODEX_ARCHIVED_SESSIONS",
                              str(self.root / "codex-archive")),
            mock.patch.object(config, "OPENCODE_DB", str(self.opencode)),
        ]
        for patcher in self.patches:
            patcher.start()

    def tearDown(self):
        for patcher in reversed(self.patches):
            patcher.stop()
        self.tmp.cleanup()

    def test_only_codex_present_detects_only_codex(self):
        self.codex.mkdir()
        detected, skipped = sources.detect()
        self.assertEqual(["codex"], [source.name for source in detected])
        self.assertEqual({"claude", "gemini", "opencode"},
                         {row["name"] for row in skipped})

    def test_all_four_present_detects_all(self):
        for directory in (self.claude, self.gemini, self.codex):
            directory.mkdir()
        self.opencode.parent.mkdir()
        self.opencode.write_bytes(b"")
        detected, skipped = sources.detect()
        self.assertEqual(["claude", "gemini", "codex", "opencode"],
                         [source.name for source in detected])
        self.assertEqual([], skipped)

    def test_detection_never_opens_a_file(self):
        self.codex.mkdir()
        with mock.patch("builtins.open", side_effect=AssertionError("opened")), \
                mock.patch("os.open", side_effect=AssertionError("opened")):
            detected, skipped = sources.detect()
        self.assertEqual(["codex"], [source.name for source in detected])
        self.assertTrue(skipped)

    def test_auto_and_explicit_sources_are_unioned(self):
        self.codex.mkdir()
        enabled, detected, skipped, auto = sources.resolve(["auto", "gemini"])
        self.assertTrue(auto)
        self.assertEqual(["gemini", "codex"], enabled)
        self.assertEqual(["codex"], [source.name for source in detected])

    def test_explicit_source_does_not_auto_detect(self):
        enabled, detected, skipped, auto = sources.resolve(["opencode"])
        self.assertFalse(auto)
        self.assertEqual(["opencode"], enabled)
        self.assertEqual([], detected)
        self.assertEqual([], skipped)

    def test_detection_text_matches_language(self):
        self.codex.mkdir()
        detected, skipped = sources.detect()
        zh = sources.format_detection(detected, skipped, "zh")
        en = sources.format_detection(detected, skipped, "en")
        self.assertIn("自动发现来源：Codex", zh)
        self.assertIn("Gemini CLI，未找到 ~/.gemini", zh)
        self.assertIn("Auto-detected sources: Codex", en)
        self.assertIn("Gemini CLI, ~/.gemini not found", en)

    def test_no_sources_returns_nonzero_with_existing_guidance(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch("tokens_cli.cli.readers.read_all") as read_all, \
                mock.patch("sys.stdout", stdout), mock.patch("sys.stderr", stderr):
            result = cli.main(["day"])
        self.assertEqual(1, result)
        read_all.assert_not_called()
        self.assertIn("Auto-detected sources: none", stdout.getvalue())
        self.assertIn("No supported token logs were found.", stderr.getvalue())
        self.assertIn("tokens doctor", stderr.getvalue())

    def test_cli_auto_passes_only_detected_sources(self):
        self.codex.mkdir()
        stdout = io.StringIO()
        with mock.patch("tokens_cli.cli.readers.read_all", return_value=[]) as read_all, \
                mock.patch("sys.stdout", stdout):
            result = cli.main(["day"])
        self.assertEqual(1, result)
        read_all.assert_called_once_with(sources=["codex"], use_cache=True)
        self.assertIn("Auto-detected sources: Codex", stdout.getvalue())

    def test_static_html_subtitle_includes_detection(self):
        from tokens_cli import report_html
        rows = [("2026-07-01", {"total": 10, "calls": 1,
                                "by_model": [("m", 10)],
                                "by_source": [("codex", 10)]})]
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(config, "OUT_DIR", tmp):
            path = report_html.write_report(
                "day", rows, "2026-07-01", "Today", ["codex"], lang="en",
                discovery="Auto-detected sources: Codex")
            html = Path(path).read_text(encoding="utf-8")
        self.assertIn("Auto-detected sources: Codex", html)

    def test_doctor_reports_discovery_for_every_registered_source(self):
        self.codex.mkdir()
        (self.codex / "rollout-a.jsonl").write_text("{}\n", encoding="utf-8")
        report = doctor.collect(sources=["codex"])
        rows = {row["source"]: row for row in report["discovery"]}
        self.assertEqual({"claude", "gemini", "codex", "opencode"}, set(rows))
        self.assertTrue(rows["codex"]["exists"])
        self.assertEqual(1, rows["codex"]["files"])
        self.assertFalse(rows["claude"]["exists"])
        stdout = io.StringIO()
        with mock.patch("sys.stdout", stdout):
            doctor.print_report(report)
        text = stdout.getvalue()
        self.assertIn("Source discovery:", text)
        self.assertIn("Codex", text)
        self.assertIn("1 candidates", text)

    def test_json_reports_include_detection_fields(self):
        self.codex.mkdir()
        report = {
            "generated_at": "2026-11-10T18:00:00+08:00",
            "timezone": "Asia/Shanghai", "sources": ["codex"], "unsupported": [],
            "codex": {"selected": True, "kind": "official", "snapshot_count": 0,
                      "files": 0, "plans": []},
            "claude": {"selected": False, "kind": "estimate",
                       "samples": {"count": 0, "median": None, "min": None,
                                   "max": None, "safe_floor": None,
                                   "safe_windows": 0, "basis": "none"},
                       "current": None, "events": [], "files": 0},
            "opencode": {"selected": False, "kind": "none", "available": False,
                         "reason": "no_official_quota_data"},
            "parsed_files": 0,
        }
        stdout = io.StringIO()
        with mock.patch("tokens_cli.cli.quota.collect", return_value=report), \
                mock.patch("sys.stdout", stdout):
            self.assertEqual(0, cli.main(["quota", "--json"]))
        payload = json.loads(stdout.getvalue())
        self.assertEqual(["codex"], payload["sources_detected"])
        self.assertIn("gemini", {row["name"] for row in payload["sources_skipped"]})

        doctor_report = {"groups": [], "totals": {"groups": 0, "records": 0, "tokens": 0},
                         "router": {"path": "", "exists": False, "rules": []},
                         "timezone": "Asia/Shanghai", "since": None, "until": None,
                         "sources": ["codex"], "source_totals": {}}
        stdout = io.StringIO()
        with mock.patch("tokens_cli.cli.doctor.collect_models",
                        return_value=doctor_report), mock.patch("sys.stdout", stdout):
            self.assertEqual(0, cli.main(["doctor", "--models", "--json"]))
        payload = json.loads(stdout.getvalue())
        self.assertEqual(["codex"], payload["sources_detected"])
        self.assertIn("gemini", {row["name"] for row in payload["sources_skipped"]})


if __name__ == "__main__":
    unittest.main()
