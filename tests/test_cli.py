import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

import sys
sys.path.insert(0, str(SRC))

from tokens_cli import cli, config


class CliTests(unittest.TestCase):
    def setUp(self):
        self.output = config.OUT_DIR
        self.summary = config.SESSION_SUMMARY_FILE
        self.timezone = config.TZ

    def tearDown(self):
        config.OUT_DIR = self.output
        config.SESSION_SUMMARY_FILE = self.summary
        config.TZ = self.timezone

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
        self.assertIn(config.CLAUDE_PROJECTS, stderr.getvalue())

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
