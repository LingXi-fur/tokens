import io
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

import sys
sys.path.insert(0, str(SRC))

from tokens_cli import cli, config, demo, lang as lang_module, report_html, report_term


class CliTests(unittest.TestCase):
    def setUp(self):
        self.output = config.OUT_DIR
        self.summary = config.SESSION_SUMMARY_FILE
        self.timezone = config.TZ

    def tearDown(self):
        config.OUT_DIR = self.output
        config.SESSION_SUMMARY_FILE = self.summary
        config.TZ = self.timezone

    def test_language_resolution_precedence_and_invalid_override(self):
        with mock.patch.dict("os.environ", {"LANG": "zh_CN.UTF-8", "TOKENS_LANG": "en"}, clear=True):
            self.assertEqual("en", lang_module.resolve_lang())
            self.assertEqual("zh", lang_module.resolve_lang("zh"))
        with mock.patch.dict("os.environ", {"LANG": "fr_FR.UTF-8"}, clear=True):
            self.assertEqual("en", lang_module.resolve_lang())
        with mock.patch.dict("os.environ", {"LC_ALL": "zh_TW.UTF-8", "LC_MESSAGES": "en_US", "LANG": "en_US"}, clear=True):
            self.assertEqual("zh", lang_module.resolve_lang())
        with mock.patch.dict("os.environ", {"LANG": "zh_CN.UTF-8", "TOKENS_LANG": "  "}, clear=True):
            self.assertEqual("zh", lang_module.resolve_lang())
            self.assertEqual("en", lang_module.resolve_lang("en"))
        with mock.patch.dict("os.environ", {"LANG": "C"}, clear=True):
            self.assertEqual("en", lang_module.resolve_lang())
        with mock.patch.dict("os.environ", {"TOKENS_LANG": "fr"}, clear=True):
            with self.assertRaises(ValueError):
                lang_module.resolve_lang()
            with self.assertRaises(SystemExit) as caught:
                cli.main(["day"])
            self.assertEqual(2, caught.exception.code)

    def test_terminal_and_static_html_use_selected_language(self):
        rows = [("2026-07-01", {"total": 1234, "calls": 2,
                                  "by_model": [("model-a", 1234)],
                                  "by_source": [("claude", 1234)]})]
        stdout = io.StringIO()
        with mock.patch("sys.stdout", stdout):
            report_term.print_report("day", rows, "2026-07-01", "Today", lang="en")
        self.assertIn("Total tokens", stdout.getvalue())
        self.assertIn("Trend history (Date)", stdout.getvalue())
        self.assertNotIn("总 token", stdout.getvalue())
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(config, "OUT_DIR", tmp):
                path = report_html.write_report("week", rows, "2026-07-01", "This week",
                                                ["claude"], lang="en")
            html = Path(path).read_text(encoding="utf-8")
        self.assertIn("<html lang=en>", html)
        self.assertIn("Weekly total token trend", html)
        self.assertIn("Source mix this period", html)
        self.assertNotIn("本期来源分布", html)

    @mock.patch("tokens_cli.cli.readers.read_all", return_value=[{"date": "2026-07-01", "source": "claude"}])
    @mock.patch("tokens_cli.cli.aggregate.by_day", return_value=[])
    def test_language_flag_reaches_terminal_report(self, _by_day, _read_all):
        with mock.patch("tokens_cli.cli.report_term.print_report") as print_report:
            self.assertEqual(0, cli.main(["day", "--lang", "zh"]))
        self.assertEqual("zh", print_report.call_args.kwargs["lang"])
        self.assertEqual("今天", print_report.call_args.args[3])

    @mock.patch("tokens_cli.cli.readers.read_all", return_value=[{"date": "2026-07-01"}])
    @mock.patch("tokens_cli.cli.report_dashboard.write_dashboard", return_value="/tmp/dashboard-anonymized.html")
    def test_dashboard_anonymize_is_forwarded(self, write_dashboard, _read_all):
        result = cli.main([
            "dashboard", "--anonymize",
            "--since", "2026-07-01", "--until", "2026-07-31",
            "--source", "claude", "--source", "gemini",
        ])
        self.assertEqual(0, result)
        write_dashboard.assert_called_once_with(
            [{"date": "2026-07-01"}],
            since="2026-07-01",
            until="2026-07-31",
            sources=["claude", "gemini"],
            anonymize=True,
        )

    @mock.patch("tokens_cli.cli.readers.read_all", return_value=[{"date": "2026-07-01"}])
    @mock.patch("tokens_cli.cli.report_dashboard.open_path")
    @mock.patch("tokens_cli.cli.report_dashboard.write_dashboard", return_value="/tmp/dashboard-anonymized.html")
    def test_dashboard_flag_anonymize_opens_returned_path(self, write_dashboard, open_path, _read_all):
        result = cli.main(["--dashboard", "--anonymize", "--open"])
        self.assertEqual(0, result)
        self.assertTrue(write_dashboard.call_args.kwargs["anonymize"])
        open_path.assert_called_once_with("/tmp/dashboard-anonymized.html")

    @mock.patch("tokens_cli.cli.readers.read_all", return_value=[{"date": "2026-07-01"}])
    @mock.patch("tokens_cli.cli.report_dashboard.write_dashboard", return_value="/tmp/dashboard.html")
    def test_output_and_timezone_are_applied_before_generation(self, write_dashboard, _read_all):
        with tempfile.TemporaryDirectory() as tmp:
            result = cli.main(["dashboard", "--output", tmp, "--timezone", "UTC"])
        self.assertEqual(0, result)
        self.assertEqual(Path(tmp).resolve(), Path(config.OUT_DIR).resolve())
        self.assertEqual("UTC", config.timezone_name())
        write_dashboard.assert_called_once()

    def test_doctor_does_not_read_log_contents(self):
        report = {"sources": []}
        with mock.patch("tokens_cli.cli.doctor.collect", return_value=report) as collect, \
                mock.patch("tokens_cli.cli.doctor.print_report") as print_report, \
                mock.patch("tokens_cli.cli.readers.read_all") as read_all:
            result = cli.main(["doctor"])
        self.assertEqual(0, result)
        collect.assert_called_once_with(sources=None)
        print_report.assert_called_once_with(report)
        read_all.assert_not_called()

    @mock.patch("tokens_cli.cli.readers.read_all", return_value=[])
    def test_no_logs_points_to_doctor(self, _read_all):
        stderr = io.StringIO()
        with mock.patch("sys.stderr", stderr):
            result = cli.main(["day"])
        self.assertEqual(1, result)
        self.assertIn("tokens doctor", stderr.getvalue())
        self.assertIn("./run doctor", stderr.getvalue())
        self.assertIn("tokens demo --open", stderr.getvalue())
        self.assertIn("./run demo --open", stderr.getvalue())
        self.assertIn(config.CLAUDE_PROJECTS, stderr.getvalue())

    @mock.patch("tokens_cli.cli.report_dashboard.open_path")
    @mock.patch("tokens_cli.cli.report_dashboard.write_dashboard", return_value="/tmp/dashboard-demo.html")
    @mock.patch("tokens_cli.cli.readers.build_session_index")
    @mock.patch("tokens_cli.cli.readers.load_session_summaries")
    @mock.patch("tokens_cli.cli.readers.read_all")
    def test_demo_uses_synthetic_data_without_reading_local_logs(
            self, read_all, summaries, session_index, write_dashboard, open_path):
        result = cli.main(["demo", "--open", "--source", "claude"])
        self.assertEqual(0, result)
        read_all.assert_not_called()
        summaries.assert_not_called()
        session_index.assert_not_called()
        open_path.assert_called_once_with("/tmp/dashboard-demo.html")
        kwargs = write_dashboard.call_args.kwargs
        self.assertEqual("dashboard-demo.html", kwargs["filename"])
        self.assertEqual(["claude"], kwargs["sources"])
        self.assertFalse(kwargs["anonymize"])
        self.assertTrue(kwargs["session_titles"])
        self.assertTrue(kwargs["demo"])
        self.assertTrue(write_dashboard.call_args.args[0])

    @mock.patch("tokens_cli.cli.report_dashboard.write_dashboard", return_value="/tmp/dashboard-demo.html")
    @mock.patch("tokens_cli.cli.readers.read_all")
    def test_demo_output_and_timezone_are_applied_before_generation(
            self, read_all, write_dashboard):
        with tempfile.TemporaryDirectory() as tmp:
            result = cli.main(["demo", "--output", tmp, "--timezone", "UTC"])
        self.assertEqual(0, result)
        read_all.assert_not_called()
        self.assertEqual(Path(tmp).resolve(), Path(config.OUT_DIR).resolve())
        self.assertEqual("UTC", config.timezone_name())
        generated_at = write_dashboard.call_args.kwargs["generated_at"]
        self.assertIsNotNone(generated_at.tzinfo)

    @mock.patch("tokens_cli.cli.report_dashboard.open_path", return_value=False)
    def test_demo_browser_failure_does_not_fail_generation(self, _open_path):
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp, mock.patch("sys.stderr", stderr):
            result = cli.main(["demo", "--output", tmp, "--open"])
        self.assertEqual(0, result)
        self.assertIn("Open this file", stderr.getvalue())

    def test_demo_records_are_stable_rich_and_synthetic(self):
        first = demo.build_demo(today=date(2026, 9, 24))
        second = demo.build_demo(today=date(2026, 9, 24))
        self.assertEqual(first, second)
        records = first["records"]
        self.assertGreater(len(records), 250)
        self.assertEqual({"claude", "gemini", "codex"}, {row["source"] for row in records})
        self.assertGreater(len({row["model"] for row in records}), 4)
        self.assertGreater(len({row["cwd"] for row in records}), 4)
        self.assertGreater(len({row["session"] for row in records}), 10)
        self.assertTrue(all(row["cwd"].startswith("/synthetic/") for row in records))
        self.assertTrue(all(row["ts"][-6] in ("+", "-") for row in records))
        self.assertGreater(sum(row["cache_read"] for row in records), 0)

    @mock.patch("tokens_cli.cli.readers.read_all", return_value=[{"date": "2026-07-01"}])
    @mock.patch("tokens_cli.cli.report_dashboard.open_path", return_value=False)
    @mock.patch("tokens_cli.cli.report_dashboard.write_dashboard", return_value="/tmp/dashboard.html")
    def test_browser_failure_does_not_fail_generation(self, _write, _open, _read):
        stderr = io.StringIO()
        with mock.patch("sys.stderr", stderr):
            result = cli.main(["dashboard", "--open"])
        self.assertEqual(0, result)
        self.assertIn("Open this file", stderr.getvalue())

    @mock.patch("tokens_cli.cli.open_url", return_value=True)
    @mock.patch("tokens_cli.cli.live_dashboard.create_server")
    def test_live_dashboard_forwards_options_and_opens_loopback_url(self, create_server, open_url):
        server = mock.Mock()
        server.server_address = ("127.0.0.1", 43123)
        server.serve_forever.side_effect = KeyboardInterrupt
        create_server.return_value = server
        result = cli.main([
            "serve", "--port", "0", "--interval", "2", "--open",
            "--source", "claude", "--anonymize", "--since", "2026-07-01",
        ])
        self.assertEqual(0, result)
        create_server.assert_called_once_with(
            0,
            ["claude"],
            since="2026-07-01",
            until=None,
            anonymize=True,
            use_cache=True,
            interval=2.0,
        )
        open_url.assert_called_once_with("http://127.0.0.1:43123/")
        server.serve_forever.assert_called_once_with(poll_interval=0.25)
        server.server_close.assert_called_once()

    def test_live_dashboard_rejects_invalid_interval_and_port(self):
        for args in (["serve", "--interval", "0"], ["serve", "--port", "65536"]):
            with self.subTest(args=args), self.assertRaises(SystemExit) as caught:
                cli.main(args)
            self.assertEqual(2, caught.exception.code)

    def test_invalid_dates_and_timezone_are_rejected(self):
        for args in (
            ["day", "--since", "not-a-date"],
            ["day", "--since", "2026-08-02", "--until", "2026-08-01"],
            ["day", "--timezone", "Mars/Olympus"],
            ["day", "--days", "0"],
        ):
            with self.subTest(args=args), self.assertRaises(SystemExit) as caught:
                cli.main(args)
            self.assertEqual(2, caught.exception.code)

    def test_anonymize_rejects_non_dashboard_modes(self):
        with self.assertRaises(SystemExit) as caught:
            cli.main(["month", "--html", "--anonymize"])
        self.assertEqual(2, caught.exception.code)


if __name__ == "__main__":
    unittest.main()
