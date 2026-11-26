"""Corrupt, partial, and empty source files are distinguished, for real.

(a) a legal file with no usage stays a cacheable empty result;
(b) a whole-file failure (invalid JSON, non-SQLite, foreign schema) raises
    CorruptSourceFile, is counted as parse_error by read_all, is never cached,
    and is retried on the next read;
(c) a usable file with damaged rows keeps the good records and reports the
    damaged-row count as partial_records.

Transient SQLite failures (locks, WAL, availability) stay retryable read
failures and are never labeled corrupt.
"""
from tests import _hermetic  # noqa: F401
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

from tokens_cli import antigravity_usage, config, readers

from tests.test_antigravity_usage import _create_db, _make_gen_data, _make_step_metadata
from tests.test_opencode_reader import TOKENS, assistant, build_db


class ParserCorruptSignalTests(unittest.TestCase):
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

    # ---------- Gemini ----------

    def _gemini_file(self, body):
        root = self.root / "gemini"
        path = root / "p1" / "chats" / "session-1.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        return root, path

    def test_gemini_empty_file_is_cacheable_and_reported_clean(self):
        root, path = self._gemini_file(json.dumps({"sessionId": "s"}).encode())
        with mock.patch.object(config, "GEMINI_TMP", str(root)):
            collection = {}
            records = readers.read_all(sources=["gemini"], use_cache=True,
                                       collection_report=collection)
        self.assertEqual([], records)
        self.assertEqual({"skipped": {}}, collection)
        self.assertIn("gemini::" + str(path), self.cache_entries())

    def test_gemini_invalid_json_is_corrupt_skip_retried_and_not_cached(self):
        bad = b'{"sessionId": "synthetic-session", "messages": [{"type": "gemini"'
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
        root, path = self._gemini_file(bad + b" " * (size - len(bad)))
        with mock.patch.object(config, "GEMINI_TMP", str(root)):
            collection = {}
            records = readers.read_all(sources=["gemini"], use_cache=True,
                                       collection_report=collection)
        self.assertEqual([], records)
        self.assertEqual({"skipped": {"gemini": {"parse_error": 1}}}, collection)
        self.assertNotIn("gemini::" + str(path), self.cache_entries())

        before = path.stat()
        path.write_bytes(good + b" " * (size - len(good)))
        os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
        with mock.patch.object(config, "GEMINI_TMP", str(root)):
            collection = {}
            records = readers.read_all(sources=["gemini"], use_cache=True,
                                       collection_report=collection)
        self.assertEqual(1, len(records))
        self.assertEqual({"skipped": {}}, collection)
        self.assertIn("gemini::" + str(path), self.cache_entries())

    def test_gemini_damaged_message_counts_partial_and_keeps_good_records(self):
        body = json.dumps({
            "sessionId": "synthetic-session",
            "messages": [
                {"type": "gemini", "timestamp": "2026-11-01T00:00:00Z",
                 "model": "synthetic-model",
                 "tokens": {"input": 3, "output": 4, "cached": 0, "total": 7}},
                {"type": "gemini", "timestamp": "2026-11-01T01:00:00Z",
                 "model": "synthetic-model", "tokens": [1]},
                {"type": "gemini", "timestamp": None,
                 "model": "synthetic-model",
                 "tokens": {"input": 1, "output": 1, "cached": 0, "total": 2}},
            ],
        }).encode()
        root, path = self._gemini_file(body)
        with mock.patch.object(config, "GEMINI_TMP", str(root)):
            collection = {}
            records = readers.read_all(sources=["gemini"], use_cache=True,
                                       collection_report=collection)
        self.assertEqual(1, len(records))
        self.assertEqual({"skipped": {"gemini": {"partial_records": 2}}}, collection)
        entry = self.cache_entries()["gemini::" + str(path)]
        self.assertEqual({"key", "records", "partial"}, set(entry))
        self.assertEqual(2, entry["partial"])
        with mock.patch.object(config, "GEMINI_TMP", str(root)):
            collection = {}
            warm = readers.read_all(sources=["gemini"], use_cache=True,
                                    collection_report=collection)
        self.assertEqual(records, warm)
        self.assertEqual({"skipped": {"gemini": {"partial_records": 2}}}, collection)

    # ---------- OpenCode ----------

    def test_opencode_empty_database_is_cacheable_and_reported_clean(self):
        build_db(self.root / "opencode.db", []).close()
        path = str(self.root / "opencode.db")
        with mock.patch.object(config, "OPENCODE_DB", path):
            collection = {}
            records = readers.read_all(sources=["opencode"], use_cache=True,
                                       collection_report=collection)
        self.assertEqual([], records)
        self.assertEqual({"skipped": {}}, collection)
        self.assertIn("opencode::" + path, self.cache_entries())

    def test_opencode_non_sqlite_and_foreign_schema_are_corrupt(self):
        for content in (b"not sqlite at all", None):
            with self.subTest(kind="bytes" if content else "foreign-schema"):
                self.cache.unlink(missing_ok=True)
                target = self.root / "opencode.db"
                if content is not None:
                    target.write_bytes(content)
                else:
                    if target.exists():
                        target.unlink()
                    sqlite3.connect(str(target)).close()
                with mock.patch.object(config, "OPENCODE_DB", str(target)):
                    collection = {}
                    records = readers.read_all(sources=["opencode"], use_cache=True,
                                               collection_report=collection)
                self.assertEqual([], records)
                self.assertEqual({"skipped": {"opencode": {"parse_error": 1}}},
                                 collection)
                self.assertNotIn("opencode::" + str(target), self.cache_entries())

    def test_opencode_damaged_rows_count_partial_and_keep_good_records(self):
        build_db(self.root / "opencode.db", [
            ("assistant", assistant(TOKENS)),
            ("assistant", "{not json"),
            ("assistant", assistant(TOKENS, created="yesterday")),
        ]).close()
        path = str(self.root / "opencode.db")
        with mock.patch.object(config, "OPENCODE_DB", path):
            collection = {}
            records = readers.read_all(sources=["opencode"], use_cache=True,
                                       collection_report=collection)
        self.assertEqual(1, len(records))
        self.assertEqual({"skipped": {"opencode": {"partial_records": 2}}}, collection)
        entry = self.cache_entries()["opencode::" + path]
        self.assertEqual(2, entry["partial"])
        with mock.patch.object(config, "OPENCODE_DB", path):
            collection = {}
            warm = readers.read_all(sources=["opencode"], use_cache=True,
                                    collection_report=collection)
        self.assertEqual(records, warm)
        self.assertEqual({"skipped": {"opencode": {"partial_records": 2}}}, collection)

    # ---------- Antigravity ----------

    def _antigravity_dir(self):
        root = self.root / "ag"
        root.mkdir(exist_ok=True)
        return root

    def test_antigravity_empty_database_is_cacheable_and_reported_clean(self):
        root = self._antigravity_dir()
        _create_db(str(root / "conv.db"), steps=[], gens=[]).close()
        path = str(root / "conv.db")
        with mock.patch.dict(os.environ, {"TOKENS_ANTIGRAVITY_DIR": str(root)}):
            collection = {}
            records = readers.read_all(sources=["antigravity"], use_cache=True,
                                       collection_report=collection)
        self.assertEqual([], records)
        self.assertEqual({"skipped": {}}, collection)
        self.assertIn("antigravity::" + path, self.cache_entries())

    def test_antigravity_non_sqlite_and_foreign_schema_are_corrupt(self):
        for content in (b"not sqlite at all", None):
            with self.subTest(kind="bytes" if content else "foreign-schema"):
                self.cache.unlink(missing_ok=True)
                root = self._antigravity_dir()
                target = root / "conv.db"
                if target.exists():
                    target.unlink()
                if content is not None:
                    target.write_bytes(content)
                else:
                    sqlite3.connect(str(target)).close()
                with mock.patch.dict(os.environ, {"TOKENS_ANTIGRAVITY_DIR": str(root)}):
                    collection = {}
                    records = readers.read_all(sources=["antigravity"], use_cache=True,
                                               collection_report=collection)
                self.assertEqual([], records)
                self.assertEqual({"skipped": {"antigravity": {"parse_error": 1}}},
                                 collection)
                self.assertNotIn("antigravity::" + str(target), self.cache_entries())

    def test_antigravity_damaged_protobuf_counts_partial_and_keeps_good_records(self):
        root = self._antigravity_dir()
        unknown_wire = bytes([(1 << 3) | 3])          # unsupported wire type
        truncated_varint = bytes([(1 << 3) | 0, 0x80])  # truncated varint
        truncated_bytes = bytes([(1 << 3) | 2, 0x20, 0x01, 0x02])
        field_zero = bytes([0x00, 0x01])
        bad_metadata = bytes([(1 << 3) | 2, 0x05]) + b"ab"  # truncated length
        con = _create_db(
            str(root / "conv.db"),
            steps=[(0, _make_step_metadata(1794600000)),
                   (1, bad_metadata)],
            gens=[
                (0, unknown_wire),
                (1, truncated_varint),
                (2, truncated_bytes),
                (3, field_zero),
                (4, _make_gen_data(request_id="r-ok", last_step_index="0")),
                (5, _make_gen_data(request_id="r-ok2", last_step_index="9")),
            ],
        )
        con.close()
        path = str(root / "conv.db")
        with mock.patch.dict(os.environ, {"TOKENS_ANTIGRAVITY_DIR": str(root)}):
            collection = {}
            records = readers.read_all(sources=["antigravity"], use_cache=True,
                                       collection_report=collection)
        # r-ok has a valid step timestamp; r-ok2 points at the damaged step and
        # is dropped by the existing missing-time rule, not by corruption.
        self.assertEqual(1, len(records))
        self.assertEqual({"skipped": {"antigravity": {"partial_records": 5}}}, collection)
        entry = self.cache_entries()["antigravity::" + path]
        self.assertEqual(5, entry["partial"])
        with mock.patch.dict(os.environ, {"TOKENS_ANTIGRAVITY_DIR": str(root)}):
            collection = {}
            warm = readers.read_all(sources=["antigravity"], use_cache=True,
                                    collection_report=collection)
        self.assertEqual(records, warm)
        self.assertEqual({"skipped": {"antigravity": {"partial_records": 5}}}, collection)

    # ---------- shared: strictness unchanged ----------

    def test_claude_and_codex_do_not_swallow_corrupt_source_file(self):
        for source in ("claude", "codex"):
            with self.subTest(source=source):
                path = self.root / source / "bad.dat"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"not sqlite at all")

                def parse(target):
                    raise readers.CorruptSourceFile(source)

                with mock.patch.dict(readers.SOURCES, {
                        source: (lambda: [str(path)], parse)}):
                    with self.assertRaises(readers.CollectionIncompleteError) as caught:
                        readers.read_all(sources=[source], use_cache=True,
                                         collection_report={})
                self.assertEqual("read_failed", caught.exception.reason)


if __name__ == "__main__":
    unittest.main()
