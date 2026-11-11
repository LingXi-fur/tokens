import io
import json
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

from tokens_cli import __version__, cli, config, doctor, readers


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


ROUTER_JS = """module.exports = async function router(req, config) {
  const model = req.body.model || '';
  if (model.includes('opus')) {
    return 'zhipu,glm-5.3';
  }
  if (model.includes('sonnet')) {
    return 'zhipu,glm-5.3-flash';
  }
}
"""

NATIVE_MID = "msg_01AbCdEfGhIjKlMnOpQrStUv"
NATIVE_REQUEST = "req_011CVsyntheticRequest01"


def _event(model, *, request_id=None, mid=NATIVE_MID,
           timestamp="2026-11-10T02:00:00Z", tokens=10):
    """Synthetic Claude assistant event; no real log content is involved."""
    event = {
        "type": "assistant",
        "timestamp": timestamp,
        "sessionId": "synthetic-session",
        "cwd": "/synthetic/private-project",
        "message": {
            "model": model,
            "usage": {
                "input_tokens": tokens,
                "output_tokens": 3,
                "cache_read_input_tokens": 2,
                "cache_creation_input_tokens": 1,
            },
        },
    }
    if mid is not None:
        event["message"]["id"] = mid
    if request_id is not None:
        event["requestId"] = request_id
    return event


def _record(request, model, day, tokens):
    """Minimal reader-shaped record for grouping/filter tests."""
    return {
        "source": "claude",
        "request_model": request,
        "model": model,
        "date": day,
        "total": tokens,
    }


class DoctorModelsTests(unittest.TestCase):
    def setUp(self):
        self.router_cache = readers._ccr_rules_cache
        readers._ccr_rules_cache = ("", [])

    def tearDown(self):
        readers._ccr_rules_cache = self.router_cache

    def _router_at(self, tmp, text=ROUTER_JS):
        path = Path(tmp) / "custom-router.js"
        path.write_text(text, encoding="utf-8")
        return mock.patch.object(readers.config, "CCR_ROUTER_FILE", str(path))

    def _parse(self, event):
        parsed = readers._claude_event_record(event)
        self.assertIsNotNone(parsed)
        return parsed[0]

    def _collect(self, records, **kwargs):
        with mock.patch.object(doctor.readers, "read_all", return_value=records) as read_all:
            report = doctor.collect_models(**kwargs)
        return report, read_all

    def test_four_bases_from_synthetic_records(self):
        hex_alias = "anthropic/claude-ccr-h" + "zhipu/glm-5.3-flash".encode().hex()
        with tempfile.TemporaryDirectory() as tmp, self._router_at(tmp):
            records = [
                # Native Anthropic evidence wins over the current router rule.
                self._parse(_event("claude-opus-5-5", request_id=NATIVE_REQUEST)),
                # CCR hex alias decodes independently of router rules.
                self._parse(_event(hex_alias, mid=None)),
                # Backend name logged as-is.
                self._parse(_event("glm-5.3", mid=None)),
                # Tier alias without native evidence follows the router rule.
                self._parse(_event("claude-opus-5", mid=None)),
                # Non-Claude sources are ignored even when requested.
                {"source": "gemini", "model": "gem", "date": "2026-11-10", "total": 99},
            ]
            report, read_all = self._collect(records, sources=["claude"])

        bases = {(row["request"], row["model"]): row["basis"] for row in report["groups"]}
        self.assertEqual("native_direct", bases[("claude-opus-5-5", "claude-opus-5.5")])
        self.assertEqual("hex_alias", bases[(hex_alias, "glm-5.3-flash")])
        self.assertEqual("logged", bases[("glm-5.3", "glm-5.3")])
        self.assertEqual("router_rule", bases[("claude-opus-5", "glm-5.3")])
        self.assertNotIn("gemini", {row["model"] for row in report["groups"]})
        self.assertEqual(4, report["totals"]["groups"])
        self.assertEqual(4, report["totals"]["records"])
        self.assertEqual(64, report["totals"]["tokens"])
        read_all.assert_called_once_with(sources=["claude"], use_cache=True)
        self.assertTrue(report["router"]["exists"])
        self.assertEqual([["opus", "glm-5.3"], ["sonnet", "glm-5.3-flash"]],
                         report["router"]["rules"])

    def test_basis_precedence_follows_documented_order(self):
        hex_alias = "anthropic/claude-ccr-h0a"
        self.assertEqual("hex_alias", doctor._basis(hex_alias, hex_alias))
        self.assertEqual("logged", doctor._basis("glm-5.3", "glm-5.3"))
        self.assertEqual("native_direct",
                         doctor._basis("claude-opus-5-5", "claude-opus-5.5"))
        self.assertEqual("router_rule", doctor._basis("claude-opus-5", "glm-5.3"))

    def test_missing_router_is_reported_without_rules(self):
        records = [_record("glm-5.3", "glm-5.3", "2026-11-10", 7)]
        with tempfile.TemporaryDirectory() as tmp:
            missing = str(Path(tmp) / "missing-router.js")
            with mock.patch.object(readers.config, "CCR_ROUTER_FILE", missing):
                report, _ = self._collect(records)
                stdout = io.StringIO()
                with mock.patch("sys.stdout", stdout):
                    doctor.print_models(report)
        self.assertFalse(report["router"]["exists"])
        self.assertEqual([], report["router"]["rules"])
        self.assertEqual(missing, report["router"]["path"])
        self.assertIn(missing, stdout.getvalue())
        self.assertIn("not found", stdout.getvalue())

    def test_json_shape_is_stable(self):
        records = [_record("claude-opus-5-5", "claude-opus-5.5", "2026-11-10", 12)]
        with tempfile.TemporaryDirectory() as tmp:
            missing = str(Path(tmp) / "missing-router.js")
            with mock.patch.object(readers.config, "CCR_ROUTER_FILE", missing):
                report, _ = self._collect(records, since="2026-11-10",
                                          until="2026-11-10")
        payload = json.loads(json.dumps(report))
        self.assertEqual({"timezone", "since", "until", "sources", "router",
                          "totals", "groups"}, set(payload))
        self.assertEqual({"path", "exists", "rules"}, set(payload["router"]))
        self.assertEqual({"groups", "records", "tokens"}, set(payload["totals"]))
        self.assertEqual({"request", "model", "basis", "records", "tokens",
                          "first", "last"}, set(payload["groups"][0]))
        self.assertEqual("2026-11-10", payload["since"])
        self.assertEqual("2026-11-10", payload["until"])
        self.assertEqual(12, payload["groups"][0]["tokens"])

    def test_since_and_until_filter_records(self):
        records = [
            _record("glm-5.3", "glm-5.3", "2026-11-09", 1),
            _record("glm-5.3", "glm-5.3", "2026-11-10", 2),
            _record("glm-5.3", "glm-5.3", "2026-11-11", 4),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            missing = str(Path(tmp) / "missing-router.js")
            with mock.patch.object(readers.config, "CCR_ROUTER_FILE", missing):
                today, _ = self._collect(records, since="2026-11-10",
                                         until="2026-11-10")
                open_ended, _ = self._collect(records, since="2026-11-10")
                all_dates, _ = self._collect(records)
        self.assertEqual(1, today["totals"]["records"])
        self.assertEqual(2, today["totals"]["tokens"])
        self.assertEqual(("2026-11-10", "2026-11-10"),
                         (today["groups"][0]["first"], today["groups"][0]["last"]))
        self.assertEqual(6, open_ended["totals"]["tokens"])
        self.assertEqual(("2026-11-10", "2026-11-11"),
                         (open_ended["groups"][0]["first"], open_ended["groups"][0]["last"]))
        self.assertEqual(7, all_dates["totals"]["tokens"])
        self.assertEqual(("2026-11-09", "2026-11-11"),
                         (all_dates["groups"][0]["first"], all_dates["groups"][0]["last"]))

    def test_output_never_contains_cwd_session_or_project(self):
        with tempfile.TemporaryDirectory() as tmp, self._router_at(tmp):
            record = self._parse(_event("claude-opus-5-5", request_id=NATIVE_REQUEST))
        self.assertEqual("/synthetic/private-project", record["cwd"])
        self.assertEqual("synthetic-session", record["session"])
        report, _ = self._collect([record])
        stdout = io.StringIO()
        with mock.patch("sys.stdout", stdout):
            doctor.print_models(report, lang="en")
        text = stdout.getvalue()
        self.assertIn("claude-opus-5-5 → claude-opus-5.5", text)
        self.assertIn("native_direct", text)
        self.assertIn("request → model", text)
        for private in ("/synthetic/private-project", "synthetic-session", "private-project"):
            self.assertNotIn(private, text)
            self.assertNotIn(private, json.dumps(report))

    def test_chinese_output_follows_lang(self):
        records = [_record("glm-5.3", "glm-5.3", "2026-11-10", 7)]
        report, _ = self._collect(records)
        stdout = io.StringIO()
        with mock.patch("sys.stdout", stdout):
            doctor.print_models(report, lang="zh")
        text = stdout.getvalue()
        self.assertIn("依据", text)
        self.assertIn("记录", text)
        self.assertIn("glm-5.3", text)

    def test_cli_models_json_forwards_filters_and_cache(self):
        report = {
            "timezone": "UTC", "since": "2026-11-10", "until": None,
            "sources": ["claude"],
            "router": {"path": "/synthetic/router.js", "exists": False, "rules": []},
            "totals": {"groups": 0, "records": 0, "tokens": 0},
            "groups": [],
        }
        stdout = io.StringIO()
        with mock.patch("tokens_cli.cli.doctor.collect_models", return_value=report) as collect, \
                mock.patch("tokens_cli.cli.doctor.collect") as env_collect, \
                mock.patch("sys.stdout", stdout):
            result = cli.main(["doctor", "--models", "--json",
                               "--since", "2026-11-10", "--no-cache"])
        self.assertEqual(0, result)
        env_collect.assert_not_called()
        self.assertEqual("2026-11-10", collect.call_args.kwargs["since"])
        self.assertIsNone(collect.call_args.kwargs["until"])
        self.assertFalse(collect.call_args.kwargs["use_cache"])
        self.assertEqual([], json.loads(stdout.getvalue())["groups"])

    def test_json_requires_models_mode(self):
        with mock.patch("sys.stderr", io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                cli.main(["doctor", "--json"])
        self.assertEqual(2, caught.exception.code)


if __name__ == "__main__":
    unittest.main()
