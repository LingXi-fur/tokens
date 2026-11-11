"""Synthetic contracts for the OpenCode (sst/opencode) SQLite reader.

The reader opens the database read-only and projects only tokens/model/time
through SQL ``json_extract``; message bodies never enter Python. These tests
build a throwaway database with the v2 schema subset the reader touches.
"""
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
sys.path.insert(0, str(ROOT / "src"))

from tokens_cli import readers  # noqa: E402

SCHEMA = """
CREATE TABLE session_v2 (id text PRIMARY KEY, project_id text NOT NULL, slug text NOT NULL,
  directory text NOT NULL, time_created integer NOT NULL);
CREATE TABLE session_message (id text PRIMARY KEY, session_id text NOT NULL, type text NOT NULL,
  seq integer NOT NULL, time_created integer NOT NULL, time_updated integer NOT NULL, data text NOT NULL);
"""

# 2026-11-10T15:30:00Z = 2026-11-10 23:30 Asia/Shanghai; +1h crosses into 11-11 locally.
T0 = 1794324600000


def assistant(tokens, model="deepseek-v4.1-flash", created=T0, **extra):
    data = {"agent": "build", "content": [{"type": "text", "text": "SECRET BODY"}],
            "model": {"id": model, "providerID": "opencode-go"},
            "time": {"created": created}}
    if tokens is not None:
        data["tokens"] = tokens
    data.update(extra)
    return data


def build_db(path, messages, wal=False):
    con = sqlite3.connect(path)
    if wal:
        con.execute("PRAGMA journal_mode=WAL")
    con.executescript(SCHEMA)
    con.execute("INSERT INTO session_v2 VALUES ('ses_1','prj','slug','/synthetic/project',0)")
    for index, (kind, data) in enumerate(messages):
        body = data if isinstance(data, str) else json.dumps(data)
        con.execute("INSERT INTO session_message VALUES (?,?,?,?,?,?,?)",
                    (f"msg_{index:03d}", "ses_1", kind, index, T0 + index, T0 + index, body))
    con.commit()
    return con


TOKENS = {"input": 100, "output": 20, "reasoning": 30, "cache": {"read": 1000, "write": 5}}


class OpenCodeReaderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "opencode.db")
        patcher = mock.patch.object(readers.config, "TZ", ZoneInfo("Asia/Shanghai"))
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def test_token_semantics_billing_and_privacy(self):
        build_db(self.db, [
            ("user", {"text": "hello"}),
            ("assistant", assistant(TOKENS)),
            ("assistant", assistant(None, error={"message": "boom"})),   # aborted, no tokens
            ("assistant", "{not json"),
            ("assistant", assistant({"input": 7, "output": 3, "reasoning": 0})),  # no cache block
        ]).close()
        records = readers.opencode_parse(self.db)
        self.assertEqual(2, len(records))
        first, second = records
        # output 不含 reasoning：总量把 reasoning 单独加上，记录 output 为生成侧合计。
        self.assertEqual(100 + 20 + 30 + 1000 + 5, first["total"])
        self.assertEqual(50, first["output"])
        self.assertEqual((100, 1000, 5), (first["input"], first["cache_read"], first["cache_write"]))
        self.assertEqual([100, 20, 1000, 5, 30], first["billing"]["parts"])
        self.assertFalse(first["billing"]["uncertain"])
        self.assertEqual("deepseek-v4.1-flash", first["model"])
        self.assertEqual("opencode", first["source"])
        self.assertEqual("ses_1", first["session"])
        self.assertEqual("/synthetic/project", first["cwd"])
        self.assertEqual("2026-11-10", first["date"])
        self.assertEqual(10, second["total"])
        self.assertEqual([7, 3, 0, 0, 0], second["billing"]["parts"])
        self.assertNotIn("SECRET BODY", json.dumps(records))

    def test_missing_required_component_is_uncertain_not_billed(self):
        build_db(self.db, [("assistant", assistant({"input": 5, "output": 2}))]).close()
        (record,) = readers.opencode_parse(self.db)
        self.assertTrue(record["billing"]["uncertain"])
        self.assertIn("missing_thoughts", record["billing"]["reasons"])
        self.assertEqual([0, 0, 0, 0, 0], record["billing"]["parts"])
        self.assertEqual(7, record["total"])

    def test_negative_or_bogus_tokens_are_skipped(self):
        build_db(self.db, [
            ("assistant", assistant({"input": -1, "output": 2, "reasoning": 0})),
            ("assistant", assistant({"input": "9", "output": 2, "reasoning": 0})),
            ("assistant", assistant(TOKENS, created="yesterday")),
        ]).close()
        self.assertEqual([], readers.opencode_parse(self.db))

    def test_reporting_timezone_drives_the_date(self):
        build_db(self.db, [("assistant", assistant(TOKENS, created=T0 + 3600 * 1000))]).close()
        self.assertEqual("2026-11-11", readers.opencode_parse(self.db)[0]["date"])
        with mock.patch.object(readers.config, "TZ", ZoneInfo("UTC")):
            self.assertEqual("2026-11-10", readers.opencode_parse(self.db)[0]["date"])

    def test_missing_or_foreign_database_yields_nothing(self):
        self.assertEqual([], readers.opencode_parse(os.path.join(self.tmp.name, "absent.db")))
        Path(self.db).write_text("not sqlite", encoding="utf-8")
        self.assertEqual([], readers.opencode_parse(self.db))
        os.remove(self.db)
        sqlite3.connect(self.db).close()  # valid sqlite, no OpenCode tables
        self.assertEqual([], readers.opencode_parse(self.db))

    def test_reader_never_writes_to_the_database(self):
        build_db(self.db, [("assistant", assistant(TOKENS))]).close()
        before = Path(self.db).read_bytes()
        os.chmod(self.db, 0o444)
        try:
            self.assertEqual(1, len(readers.opencode_parse(self.db)))
        finally:
            os.chmod(self.db, 0o644)
        self.assertEqual(before, Path(self.db).read_bytes())

    def test_files_follow_config_path(self):
        with mock.patch.object(readers.config, "OPENCODE_DB", self.db):
            self.assertEqual([], readers.opencode_files())
            build_db(self.db, []).close()
            self.assertEqual([self.db], readers.opencode_files())

    def test_large_database_is_not_rejected_by_the_single_file_ceiling(self):
        build_db(self.db, []).close()
        st = os.stat(self.db)
        big = os.stat_result(st[:6] + (readers.MAX_FILE_BYTES + 1,) + st[7:])
        self.assertTrue(readers._safe_to_parse(self.db, big, source="opencode"))
        self.assertFalse(readers._safe_to_parse(self.db, big, source="gemini"))

    def test_read_all_caches_and_sees_uncheckpointed_wal_writes(self):
        writer = build_db(self.db, [("assistant", assistant(TOKENS))], wal=True)
        writer.execute("PRAGMA wal_autocheckpoint=0")
        cache_file = Path(self.tmp.name) / "records.json"
        with mock.patch.object(readers.config, "OPENCODE_DB", self.db), \
                mock.patch.object(readers.config, "CACHE_DIR", self.tmp.name), \
                mock.patch.object(readers.config, "CACHE_FILE", str(cache_file)), \
                mock.patch.object(readers, "_ccr_signature", return_value=None):
            first = readers.read_all(["opencode"])
            self.assertEqual(1, len(first))
            with mock.patch.object(readers, "opencode_parse", wraps=readers.opencode_parse) as spy:
                self.assertEqual(first, readers.read_all(["opencode"]))
                spy.assert_not_called()  # warm cache hit
            main_before = os.stat(self.db)
            writer.execute("INSERT INTO session_message VALUES (?,?,?,?,?,?,?)",
                           ("msg_new", "ses_1", "assistant", 99, T0 + 99, T0 + 99,
                            json.dumps(assistant(TOKENS))))
            writer.commit()
            # 新写入只落在 -wal：主库签名不变，读取器仍须重析并看到它。
            self.assertEqual(main_before.st_size, os.stat(self.db).st_size)
            self.assertEqual(2, len(readers.read_all(["opencode"])))
        writer.close()

    def test_source_is_registered_everywhere_it_is_enumerated(self):
        from tokens_cli import cli, live_snapshot
        self.assertIn("opencode", readers.SOURCES)
        self.assertIn("opencode", readers._BILLING_VALIDATORS)
        self.assertIn("opencode", readers.CollectionIncompleteError.SOURCES)
        self.assertEqual(["opencode"], cli.build_parser().parse_args(["--source", "opencode"]).source)
        self.assertTrue(live_snapshot.SnapshotStore(["opencode"], directory=self.tmp.name)._valid)


if __name__ == "__main__":
    unittest.main()
