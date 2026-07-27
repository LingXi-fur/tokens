import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]

import sys
sys.path.insert(0, str(ROOT))

import cli


class CliTests(unittest.TestCase):
    @mock.patch("cli.readers.read_all", return_value=[{"date": "2026-07-01"}])
    @mock.patch("cli.report_dashboard.write_dashboard", return_value="/tmp/dashboard-anonymized.html")
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

    @mock.patch("cli.readers.read_all", return_value=[{"date": "2026-07-01"}])
    @mock.patch("cli.report_dashboard.open_path")
    @mock.patch("cli.report_dashboard.write_dashboard", return_value="/tmp/dashboard-anonymized.html")
    def test_dashboard_flag_anonymize_opens_returned_path(self, write_dashboard, open_path, _read_all):
        result = cli.main(["--dashboard", "--anonymize", "--open"])
        self.assertEqual(0, result)
        self.assertTrue(write_dashboard.call_args.kwargs["anonymize"])
        open_path.assert_called_once_with("/tmp/dashboard-anonymized.html")

    @mock.patch("cli.readers.read_all", return_value=[{"date": "2026-07-01"}])
    @mock.patch("cli.report_dashboard.write_dashboard", return_value="/tmp/dashboard.html")
    def test_dashboard_default_keeps_anonymize_disabled(self, write_dashboard, _read_all):
        result = cli.main(["dashboard"])
        self.assertEqual(0, result)
        self.assertFalse(write_dashboard.call_args.kwargs["anonymize"])

    def test_anonymize_rejects_non_dashboard_modes(self):
        with self.assertRaises(SystemExit) as caught:
            cli.main(["month", "--html", "--anonymize"])
        self.assertEqual(2, caught.exception.code)


if __name__ == "__main__":
    unittest.main()
