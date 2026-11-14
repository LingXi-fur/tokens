import os
import sqlite3
import tempfile
import unittest
from unittest import mock

from tokens_cli import antigravity_usage


def _encode_varint(value: int) -> bytes:
    parts = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            parts.append(byte | 0x80)
        else:
            parts.append(byte)
            break
    return bytes(parts)


def _pb_varint(field_num: int, value: int) -> bytes:
    return _encode_varint((field_num << 3) | 0) + _encode_varint(value)


def _pb_bytes(field_num: int, payload: bytes) -> bytes:
    return _encode_varint((field_num << 3) | 2) + _encode_varint(len(payload)) + payload


def _pb_str(field_num: int, text: str) -> bytes:
    return _pb_bytes(field_num, text.encode("utf-8"))


def _make_step_metadata(unix_sec: int) -> bytes:
    return _pb_bytes(1, _pb_varint(1, unix_sec))


def _make_gen_data(
    *,
    model: str | None = "gemini-4-hydrogen",
    inp: int = 100,
    outp: int = 40,
    cache_read: int = 500,
    thought_split: int = 15,
    text_split: int = 25,
    include_usage: bool = True,
    request_id: str | None = "req-1",
    cascade_id: str | None = "cas-1",
    last_step_index: str | None = "0",
) -> bytes:
    inner = bytearray()
    if include_usage:
        usage = bytearray()
        usage.extend(_pb_varint(1, 7))  # model enum
        usage.extend(_pb_varint(2, inp))
        usage.extend(_pb_varint(3, outp))
        usage.extend(_pb_varint(5, cache_read))
        usage.extend(_pb_varint(6, 24))
        usage.extend(_pb_varint(9, thought_split))
        usage.extend(_pb_varint(10, text_split))
        inner.extend(_pb_bytes(4, bytes(usage)))
    if model is not None:
        inner.extend(_pb_str(19, model))
    kvs = []
    if request_id is not None:
        kvs.append(("request_id", request_id))
    if cascade_id is not None:
        kvs.append(("cascade_id", cascade_id))
    if last_step_index is not None:
        kvs.append(("last_step_index", last_step_index))
    for k, v in kvs:
        inner.extend(_pb_bytes(20, _pb_str(1, k) + _pb_str(2, v)))
    return _pb_bytes(1, bytes(inner))


def _create_db(path: str, steps: list[tuple[int, bytes]], gens: list[tuple[int, bytes]], wal: bool = False):
    con = sqlite3.connect(path)
    if wal:
        con.execute("PRAGMA journal_mode=WAL")
    con.execute("CREATE TABLE steps (idx INTEGER, step_payload BLOB, metadata BLOB, render_info BLOB)")
    con.execute("CREATE TABLE gen_metadata (idx INTEGER, data BLOB, size INTEGER)")
    for idx, meta in steps:
        con.execute(
            "INSERT INTO steps (idx, step_payload, metadata, render_info) VALUES (?, ?, ?, ?)",
            (idx, b"secret-payload", meta, b"secret-render"),
        )
    for idx, data in gens:
        con.execute(
            "INSERT INTO gen_metadata (idx, data, size) VALUES (?, ?, ?)",
            (idx, data, len(data)),
        )
    con.commit()
    return con


class AntigravityUsageTests(unittest.TestCase):
    def setUp(self):
        self._orig_missing = antigravity_usage.MISSING_TIME_COUNT
        antigravity_usage.MISSING_TIME_COUNT = 0

    def tearDown(self):
        antigravity_usage.MISSING_TIME_COUNT = self._orig_missing

    def test_parse_normal_record_and_no_double_count_subfields(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "conv-1.db")
            con = _create_db(
                db_path,
                steps=[(0, _make_step_metadata(1794600000))],
                gens=[(0, _make_gen_data(
                    model="gemini-4-hydrogen",
                    inp=120,
                    outp=45,
                    cache_read=800,
                    thought_split=20,
                    text_split=25,
                    request_id="req-a",
                    cascade_id="cas-xyz",
                    last_step_index="0",
                ))],
            )
            con.close()

            records = antigravity_usage.parse(db_path)
            self.assertEqual(len(records), 1)
            rec = records[0]
            self.assertEqual(rec["source"], "antigravity")
            self.assertEqual(rec["model"], "gemini-4-hydrogen")
            self.assertEqual(rec["input"], 120)
            self.assertEqual(rec["output"], 45)  # 1.4.9/1.4.10 not double-counted
            self.assertEqual(rec["cache_read"], 800)
            self.assertEqual(rec["cache_write"], 0)
            self.assertEqual(rec["total"], 120 + 45 + 800)
            self.assertEqual(rec["session"], "cas-xyz")
            self.assertIsNone(rec["cwd"])
            self.assertIsNone(rec["billing"])
            self.assertEqual(rec["ts"], "2026-11-13T20:00:00Z")
            self.assertRegex(rec["date"], r"^\d{4}-\d{2}-\d{2}$")
            self.assertEqual(antigravity_usage.MISSING_TIME_COUNT, 0)

    def test_missing_model_falls_back_to_antigravity_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "conv.db")
            con = _create_db(
                db_path,
                steps=[(2, _make_step_metadata(1794600000))],
                gens=[(0, _make_gen_data(model=None, last_step_index="2"))],
            )
            con.close()
            records = antigravity_usage.parse(db_path)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["model"], "antigravity-unknown")

    def test_skips_missing_usage_corrupt_unknown_wire_and_truncated_blobs(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "bad.db")
            no_usage = _make_gen_data(include_usage=False, request_id="r0", last_step_index="0")
            unknown_wire = bytes([(1 << 3) | 3])  # wire type 3 (start group, unsupported)
            truncated_varint = bytes([(1 << 3) | 0, 0x80])
            truncated_bytes = bytes([(1 << 3) | 2, 0x20, 0x01, 0x02])
            field_zero = bytes([0x00, 0x01])
            valid = _make_gen_data(request_id="r-ok", last_step_index="0")

            con = _create_db(
                db_path,
                steps=[(0, _make_step_metadata(1794600000))],
                gens=[
                    (0, no_usage),
                    (1, unknown_wire),
                    (2, truncated_varint),
                    (3, truncated_bytes),
                    (4, field_zero),
                    (5, valid),
                ],
            )
            con.close()
            records = antigravity_usage.parse(db_path)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["input"], 100)

    def test_deduplicates_by_request_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "dedup.db")
            row1 = _make_gen_data(inp=111, request_id="dup-1", last_step_index="0")
            row2 = _make_gen_data(inp=222, request_id="dup-1", last_step_index="0")
            row3 = _make_gen_data(inp=333, request_id="uniq-2", last_step_index="0")
            con = _create_db(
                db_path,
                steps=[(0, _make_step_metadata(1794600000))],
                gens=[(0, row1), (1, row2), (2, row3)],
            )
            con.close()
            records = antigravity_usage.parse(db_path)
            self.assertEqual([r["input"] for r in records], [111, 333])

    def test_skips_and_counts_missing_step_timestamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "notime.db")
            gens = [
                (0, _make_gen_data(request_id="r1", last_step_index="99")),  # unmatched idx
                (1, _make_gen_data(request_id="r2", last_step_index=None)),  # missing key
                (2, _make_gen_data(request_id="r3", last_step_index="abc")),  # non-int
                (3, _make_gen_data(request_id="r4", last_step_index="0")),  # valid
            ]
            con = _create_db(
                db_path,
                steps=[(0, _make_step_metadata(1794600000))],
                gens=gens,
            )
            con.close()
            records = antigravity_usage.parse(db_path)
            self.assertEqual(len(records), 1)
            self.assertEqual(antigravity_usage.MISSING_TIME_COUNT, 3)

    def test_reads_wal_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "wal.db")
            con = _create_db(
                db_path,
                steps=[(0, _make_step_metadata(1794600000))],
                gens=[(0, _make_gen_data(inp=77, request_id="wal-req", last_step_index="0"))],
                wal=True,
            )
            try:
                # Keep writer connection open with active WAL/-shm files
                records = antigravity_usage.parse(db_path)
                self.assertEqual(len(records), 1)
                self.assertEqual(records[0]["input"], 77)
            finally:
                con.close()

    def test_discover_does_not_open_files_and_skips_summaries(self):
        with tempfile.TemporaryDirectory() as tmp:
            open(os.path.join(tmp, "a.db"), "wb").close()
            open(os.path.join(tmp, "b.db-wal"), "wb").close()
            open(os.path.join(tmp, "conversation_summaries.db"), "wb").close()
            open(os.path.join(tmp, "notes.txt"), "wb").close()

            with mock.patch.dict(os.environ, {"TOKENS_ANTIGRAVITY_DIR": tmp}):
                with mock.patch("builtins.open", side_effect=AssertionError("open called")), \
                     mock.patch("sqlite3.connect", side_effect=AssertionError("connect called")):
                    found = antigravity_usage.discover()

            self.assertEqual(found, [os.path.join(tmp, "a.db")])

    def test_sql_queries_never_reference_forbidden_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "sqlcheck.db")
            con = _create_db(
                db_path,
                steps=[(0, _make_step_metadata(1794600000))],
                gens=[(0, _make_gen_data())],
            )
            con.close()

            executed_sql: list[str] = []
            real_connect = sqlite3.connect

            def spy_connect(*args, **kwargs):
                real_con = real_connect(*args, **kwargs)

                class SpyCon:
                    def execute(self, sql, *a, **kw):
                        executed_sql.append(sql)
                        return real_con.execute(sql, *a, **kw)

                    def close(self):
                        return real_con.close()

                return SpyCon()

            with mock.patch("tokens_cli.antigravity_usage.sqlite3.connect", side_effect=spy_connect):
                records = antigravity_usage.parse(db_path)

            self.assertEqual(len(records), 1)
            self.assertTrue(executed_sql)
            joined = " ".join(executed_sql).lower()
            for forbidden in ("step_payload", "render_info", "task_details", "select *"):
                self.assertNotIn(forbidden, joined)


if __name__ == "__main__":
    unittest.main()
