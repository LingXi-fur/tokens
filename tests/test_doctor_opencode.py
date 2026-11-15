"""Synthetic contracts for `tokens doctor --models` OpenCode coverage.

Every test builds a throwaway SQLite database with the OpenCode v2 schema
subset and never reads a real log or database. Message bodies contain a
sentinel string so leaks are detectable.
"""
import io
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from tokens_cli import cli, doctor, readers  # noqa: E402

SCHEMA = """
CREATE TABLE session_v2 (id text PRIMARY KEY, project_id text NOT NULL, slug text NOT NULL,
  directory text NOT NULL, time_created integer NOT NULL);
CREATE TABLE session_message (id text PRIMARY KEY, session_id text NOT NULL, type text NOT NULL,
  seq integer NOT NULL, time_created integer NOT NULL, time_updated integer NOT NULL, data text NOT NULL);
"""

T0 = 1794324600000
SECRET = "SECRET BODY SENTINEL"
TOKENS = {"input": 100, "output": 20, "reasoning": 30,
          "cache": {"read": 1000, "write": 5}}


def assistant(tokens, model="deepseek-v4.1-flash", created=T0):
    data = {
        "agent": "build",
        "content": [{"type": "text", "text": SECRET}],
        "model": {"id": model, "providerID": "opencode-go"},
        "time": {"created": created},
    }
    if tokens is not None:
        data["tokens"] = tokens
    return data


def build_db(path, messages):
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    con.execute("INSERT INTO session_v2 VALUES ('ses_1','prj','slug','/synthetic/project',0)")
    for index, (kind, data) in enumerate(messages):
        body = data if isinstance(data, str) else json.dumps(data)
        con.execute("INSERT INTO session_message VALUES (?,?,?,?,?,?,?)",
                    (f"msg_{index:03d}", "ses_1", kind, index, T0 + index, T0 + index, body))
    con.commit()
    con.close()
    return path


def claude_record():
    return {
        "source": "claude",
        "request_model": "claude-opus-5-5",
        "model": "claude-opus-5.5",
        "date": "2026-11-10",
        "total": 100,
    }


class DoctorOpenCodeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "opencode.db")
        self.missing_router = os.path.join(self.tmp.name, "missing-router.js")
        self.router_cache = readers._ccr_rules_cache
        readers._ccr_rules_cache = ("", [])
        patcher = mock.patch.object(readers.config, "TZ", ZoneInfo("Asia/Shanghai"))
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        readers._ccr_rules_cache = self.router_cache
        self.tmp.cleanup()

    def _patches(self):
        return (
            mock.patch.object(readers.config, "OPENCODE_DB", self.db),
            mock.patch.object(readers.config, "CCR_ROUTER_FILE", self.missing_router),
        )

    def test_opencode_groups_health_and_privacy(self):
        build_db(self.db, [
            ("user", {"text": SECRET}),
            ("assistant", assistant(TOKENS)),
            ("assistant", assistant(TOKENS, model="kimi-k2.6")),
            ("assistant", assistant(None)),          # aborted: valid JSON, no tokens
            ("assistant", "{not json"),              # invalid JSON
        ])
        db_patch, router_patch = self._patches()
        with db_patch, router_patch:
            report = doctor.collect_models(sources=["opencode"], use_cache=False)
            stdout = io.StringIO()
            with mock.patch("sys.stdout", stdout):
                doctor.print_models(report, lang="en")

        self.assertEqual(["opencode"], report["sources"])
        self.assertEqual(2, report["totals"]["groups"])
        self.assertEqual(2, report["totals"]["records"])
        self.assertEqual(2310, report["totals"]["tokens"])
        self.assertEqual(report["totals"], report["source_totals"]["opencode"])
        for row in report["groups"]:
            self.assertEqual("opencode", row["source"])
            self.assertEqual("-", row["request"])
            self.assertEqual("opencode_logged", row["basis"])
        self.assertEqual({"deepseek-v4.1-flash", "kimi-k2.6"},
                         {row["model"] for row in report["groups"]})

        health = report["opencode_health"]
        self.assertEqual("ok", health["status"])
        self.assertEqual(4, health["assistant_messages"])
        self.assertEqual(1, health["invalid_json"])
        self.assertEqual(1, health["no_tokens"])
        self.assertEqual(2, health["records"])

        text = stdout.getvalue()
        self.assertIn("OpenCode:", text)
        self.assertIn("opencode_logged", text)
        self.assertIn("4 assistant messages → 2 records", text)
        self.assertIn("1 no tokens", text)
        self.assertIn("1 invalid json", text)
        self.assertNotIn(SECRET, text)
        self.assertNotIn(SECRET, json.dumps(report))
        self.assertNotIn("/synthetic/project", text)
        self.assertNotIn("ses_1", text)
        self.assertNotIn("/synthetic/project", json.dumps(report))
        self.assertNotIn("ses_1", json.dumps(report))

    def test_mixed_sources_print_blocks_with_their_own_totals(self):
        build_db(self.db, [("assistant", assistant(TOKENS))])
        with mock.patch.object(readers.config, "OPENCODE_DB", self.db), \
                mock.patch.object(readers.config, "CCR_ROUTER_FILE", self.missing_router):
            opencode_records = readers.opencode_parse(self.db)
            with mock.patch.object(doctor.readers, "read_all",
                                   return_value=[claude_record()] + opencode_records):
                report = doctor.collect_models(
                    sources=["claude", "opencode"], use_cache=False)
        stdout = io.StringIO()
        with mock.patch("sys.stdout", stdout):
            doctor.print_models(report, lang="en")
        text = stdout.getvalue()

        self.assertEqual(100, report["source_totals"]["claude"]["tokens"])
        self.assertEqual(1155, report["source_totals"]["opencode"]["tokens"])
        self.assertEqual(1255, report["totals"]["tokens"])
        self.assertLess(text.index("Claude:"), text.index("OpenCode:"))
        self.assertEqual(2, text.count("1 groups, 1 records"))
        self.assertIn("opencode: 1 assistant messages → 1 records", text)
        self.assertEqual({"claude", "opencode"},
                         {row["source"] for row in report["groups"]})

    def test_json_keeps_legacy_keys_and_adds_source_and_health(self):
        # Claude-only reports keep the original top-level shape plus source_totals.
        with mock.patch.object(readers.config, "CCR_ROUTER_FILE", self.missing_router), \
                mock.patch.object(doctor.readers, "read_all",
                                  return_value=[claude_record()]):
            claude_report = doctor.collect_models(sources=["claude"], use_cache=False)
        payload = json.loads(json.dumps(claude_report))
        legacy_top = {"timezone", "since", "until", "sources", "router",
                      "totals", "groups"}
        self.assertTrue(legacy_top <= set(payload))
        self.assertEqual(legacy_top | {"source_totals"}, set(payload))
        self.assertNotIn("opencode_health", payload)
        legacy_group = {"request", "model", "basis", "records", "tokens",
                        "first", "last"}
        self.assertTrue(legacy_group <= set(payload["groups"][0]))
        self.assertEqual(legacy_group | {"source"}, set(payload["groups"][0]))
        self.assertEqual("claude", payload["groups"][0]["source"])

        # OpenCode adds a stable health object without removing old keys.
        build_db(self.db, [("assistant", assistant(TOKENS))])
        db_patch, router_patch = self._patches()
        with db_patch, router_patch:
            opencode_report = doctor.collect_models(
                sources=["opencode"], use_cache=False)
        health = json.loads(json.dumps(opencode_report))["opencode_health"]
        self.assertEqual({"path", "exists", "status", "assistant_messages",
                          "invalid_json", "no_tokens", "records"}, set(health))
        self.assertTrue(health["exists"])

    def test_health_status_for_missing_foreign_and_tableless_databases(self):
        with mock.patch.object(readers.config, "OPENCODE_DB", self.db), \
                mock.patch.object(readers.config, "CCR_ROUTER_FILE", self.missing_router):
            missing = doctor.collect_models(sources=["opencode"], use_cache=False)
        self.assertEqual("missing", missing["opencode_health"]["status"])
        self.assertFalse(missing["opencode_health"]["exists"])

        Path(self.db).write_text("not sqlite", encoding="utf-8")
        with mock.patch.object(readers.config, "OPENCODE_DB", self.db), \
                mock.patch.object(readers.config, "CCR_ROUTER_FILE", self.missing_router):
            foreign = doctor.collect_models(sources=["opencode"], use_cache=False)
            stdout = io.StringIO()
            with mock.patch("sys.stdout", stdout):
                doctor.print_models(foreign, lang="en")
        self.assertEqual("invalid_database", foreign["opencode_health"]["status"])
        self.assertIn("not a SQLite database", stdout.getvalue())

        os.remove(self.db)
        sqlite3.connect(self.db).close()  # valid SQLite, no OpenCode tables
        with mock.patch.object(readers.config, "OPENCODE_DB", self.db), \
                mock.patch.object(readers.config, "CCR_ROUTER_FILE", self.missing_router):
            tableless = doctor.collect_models(sources=["opencode"], use_cache=False)
            stdout = io.StringIO()
            with mock.patch("sys.stdout", stdout):
                doctor.print_models(tableless, lang="en")
        self.assertEqual("missing_table", tableless["opencode_health"]["status"])
        self.assertIn("missing session_message table", stdout.getvalue())

    def test_date_filter_does_not_change_health_record_count(self):
        build_db(self.db, [
            ("assistant", assistant(TOKENS)),
            ("assistant", assistant(TOKENS, created=T0 + 24 * 3600 * 1000)),
        ])
        db_patch, router_patch = self._patches()
        with db_patch, router_patch:
            report = doctor.collect_models(
                sources=["opencode"], since="2026-11-10", until="2026-11-10",
                use_cache=False)
        self.assertEqual(1, report["totals"]["records"])
        self.assertEqual(2, report["opencode_health"]["records"])
        self.assertEqual(2, report["opencode_health"]["assistant_messages"])

    def test_cli_forwards_opencode_source(self):
        build_db(self.db, [("assistant", assistant(TOKENS))])
        stdout = io.StringIO()
        db_patch, router_patch = self._patches()
        with db_patch, router_patch, mock.patch("sys.stdout", stdout):
            result = cli.main(
                ["doctor", "--models", "--source", "opencode", "--json",
                 "--no-cache"])
        self.assertEqual(0, result)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(["opencode"], payload["sources"])
        self.assertEqual("ok", payload["opencode_health"]["status"])


if __name__ == "__main__":
    unittest.main()
