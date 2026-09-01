import os
import re
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

import sys
sys.path.insert(0, str(SRC))

from tokens_cli import __version__, config, doctor


class ConfigDoctorTests(unittest.TestCase):
    def setUp(self):
        self.output = config.OUT_DIR
        self.summary = config.SESSION_SUMMARY_FILE
        self.timezone = config.TZ

    def tearDown(self):
        config.OUT_DIR = self.output
        config.SESSION_SUMMARY_FILE = self.summary
        config.TZ = self.timezone

    def test_package_version_matches_project_metadata(self):
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        match = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.MULTILINE)
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), __version__)

    def test_default_output_is_current_working_directory_not_package(self):
        package_dir = Path(config.__file__).resolve().parent
        self.assertEqual((Path.cwd() / "out").resolve(), Path(config.OUT_DIR))
        self.assertFalse(Path(config.OUT_DIR).is_relative_to(package_dir))

    def test_system_zone_name_reads_zoneinfo_link_and_timezone_file(self):
        with mock.patch.object(config.os.path, "realpath", side_effect=[
                "/var/db/timezone/tz/2026c.1.0/zoneinfo/America/New_York",
        ]):
            self.assertEqual("America/New_York", config._system_zone_name())

        timezone_file = mock.mock_open(read_data="Europe/Berlin\n")
        with mock.patch.object(config.os.path, "realpath", return_value="/not-zoneinfo"), \
                mock.patch("builtins.open", timezone_file):
            self.assertEqual("Europe/Berlin", config._system_zone_name())

    def test_system_timezone_prefers_iana_name_and_preserves_dst(self):
        with mock.patch.dict(config.os.environ, {}, clear=True), \
                mock.patch.object(config, "_system_zone_name", return_value="America/New_York"):
            timezone_value = config._system_timezone()
        self.assertEqual("America/New_York", timezone_value.key)
        winter = datetime(2026, 1, 1, 12, tzinfo=timezone_value).utcoffset()
        summer = datetime(2026, 7, 1, 12, tzinfo=timezone_value).utcoffset()
        self.assertNotEqual(winter, summer)

    def test_system_timezone_falls_back_to_dynamic_local_rules(self):
        with mock.patch.dict(config.os.environ, {}, clear=True), \
                mock.patch.object(config, "_system_zone_name", return_value=None):
            self.assertIs(config._SYSTEM_LOCAL_TIMEZONE, config._system_timezone())

    @unittest.skipUnless(hasattr(time, "tzset"), "requires time.tzset")
    def test_dynamic_local_timezone_preserves_dst_and_utc_conversion(self):
        original = os.environ.get("TZ")
        try:
            os.environ["TZ"] = "America/New_York"
            time.tzset()
            timezone_value = config._SystemLocalTimezone()
            winter = datetime(2026, 1, 1, 12, tzinfo=timezone_value)
            summer = datetime(2026, 7, 1, 12, tzinfo=timezone_value)
            self.assertNotEqual(winter.utcoffset(), summer.utcoffset())
            converted = datetime(2026, 7, 1, 16, tzinfo=timezone.utc).astimezone(timezone_value)
            self.assertEqual((2026, 7, 1, 12), (
                converted.year, converted.month, converted.day, converted.hour,
            ))
        finally:
            if original is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = original
            time.tzset()

    def test_set_output_dir_updates_summary_sidecar(self):
        with tempfile.TemporaryDirectory() as tmp:
            config.set_output_dir(Path(tmp) / "reports")
            self.assertEqual((Path(tmp) / "reports").resolve(), Path(config.OUT_DIR).resolve())
            self.assertEqual(Path(config.OUT_DIR) / "session_summaries.json", Path(config.SESSION_SUMMARY_FILE))

    def test_set_timezone_accepts_iana_and_rejects_unknown(self):
        config.set_timezone("UTC")
        self.assertEqual("UTC", config.timezone_name())
        with self.assertRaises(ValueError):
            config.set_timezone("Mars/Olympus")

    def test_doctor_counts_candidates_without_parsing_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "one.jsonl"
            log.write_text("private message content", encoding="utf-8")
            source_map = {"claude": (mock.Mock(return_value=[str(log)]), mock.Mock())}
            roots = {
                "CLAUDE_PROJECTS": tmp,
                "OUT_DIR": str(Path(tmp) / "out"),
                "CACHE_FILE": str(Path(tmp) / "cache" / "records.json"),
            }
            with mock.patch.object(doctor.readers, "SOURCES", source_map), \
                    mock.patch.object(config, "CLAUDE_PROJECTS", roots["CLAUDE_PROJECTS"]), \
                    mock.patch.object(config, "OUT_DIR", roots["OUT_DIR"]), \
                    mock.patch.object(config, "CACHE_FILE", roots["CACHE_FILE"]):
                report = doctor.collect(["claude"])
            self.assertEqual(1, report["sources"][0]["files"])
            self.assertEqual(1, report["sources"][0]["readable"])
            source_map["claude"][1].assert_not_called()


if __name__ == "__main__":
    unittest.main()
