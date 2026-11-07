"""Synthetic-only, actual source-I/O tests for the private per-reader memo."""
from collections import Counter
from contextlib import ExitStack, contextmanager
from copy import deepcopy
from datetime import timezone, timedelta, tzinfo
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
with mock.patch.dict(os.environ, {"TOKENS_TIMEZONE": "UTC", "TZ": "UTC"}):
    from tokens_cli import config, readers, codex_usage, _claude_json
if __package__:
    from .test_collection_integrity import _SourceReader
else:
    from test_collection_integrity import _SourceReader

STAMP = "2026-10-20T10:00:00Z"


def codex_event(response="one", amount=7):
    return {"type": "token_usage_record", "timestamp": STAMP, "payload": {
        "thread_id": "synthetic-thread", "response_id": response,
        "usage": {"input_tokens": amount, "output_tokens": 3,
                  "cached_input_tokens": 2, "reasoning_output_tokens": 1,
                  "total_tokens": amount + 3 if type(amount) is int else 10}}}


def claude_event(model="claude-sonnet-4", amount=7):
    return {"type": "assistant", "timestamp": STAMP,
            "sessionId": "synthetic-session", "cwd": "/synthetic",
            "message": {"id": "synthetic-message", "model": model,
                        "usage": {"input_tokens": amount, "output_tokens": 3}}}


class ReaderMemoTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.home = self.root / "home"
        self.home.mkdir()
        self.cache = self.root / "cache" / "records.json"
        self.router = self.home / "router.js"
        self.paths = {"claude": [], "codex": [], "gemini": []}
        for source in self.paths:
            (self.root / source).mkdir()
        for name, value in {
            "HOME": str(self.home), "CLAUDE_PROJECTS": str(self.root / "claude"),
            "GEMINI_TMP": str(self.root / "gemini"),
            "CODEX_SESSIONS": str(self.root / "codex"),
            "CODEX_ARCHIVED_SESSIONS": str(self.root / "archived"),
            "CACHE_DIR": str(self.cache.parent), "CACHE_FILE": str(self.cache),
            "OUT_DIR": str(self.root / "out"),
            "SESSION_SUMMARY_FILE": str(self.root / "titles.json"),
            "CCR_ROUTER_FILE": str(self.router), "TZ": timezone.utc,
        }.items():
            self.stack.enter_context(mock.patch.object(config, name, value))
        self.stack.enter_context(mock.patch.dict(os.environ, {
            "HOME": str(self.home), "TZ": "UTC", "TOKENS_TIMEZONE": "UTC",
            "XDG_CACHE_HOME": str(self.root / "cache"),
            "LOCALAPPDATA": str(self.root / "local"),
        }))
        self.stack.enter_context(mock.patch.object(readers, "_ccr_rules_cache", ("", [])))
        finders = {src: (lambda src=src: list(self.paths[src]), readers.SOURCES[src][1])
                   for src in self.paths}
        self.stack.enter_context(mock.patch.dict(readers.SOURCES, finders, clear=True))
        self.stack.enter_context(mock.patch.object(readers.glob, "glob", side_effect=
                                                  AssertionError("non-synthetic discovery")))
        self.stack.enter_context(mock.patch.object(readers, "build_session_index", side_effect=
                                                  AssertionError("unexpected title discovery")))
        self.events = []

    def write(self, source, name, events):
        path = self.root / source / name
        path.write_bytes(b"".join(json.dumps(e, separators=(",", ":")).encode() + b"\n"
                                 for e in events))
        if str(path) not in self.paths[source]:
            self.paths[source].append(str(path))
        return path

    def test_zero_update_sequence_matches_no_cache_cold_and_warm(self):
        usage = {"input_tokens": 7, "output_tokens": 3, "cached_input_tokens": 2,
                 "reasoning_output_tokens": 1, "total_tokens": 10}
        header = [{"type": "session_meta", "payload": {"id": "synthetic-thread"}},
                  {"type": "turn_context", "payload": {"model": "synthetic-model"}}]
        events = header + [{"type": "event_msg", "timestamp": STAMP, "payload": {
            "type": "token_count", "info": {"last_token_usage": last,
                                             "total_token_usage": usage}}}
            for last in (usage, dict.fromkeys(usage, 0))]
        good = self.write("codex", "a-zero.jsonl", events)
        bad = self.bad()
        memo = readers._ParseMemo()
        for warm in (False, True):
            with self.subTest(warm=warm), self.io_counts() as (reads, opens, fstats):
                self.failure(memo)
                self.assertEqual(not warm, reads[str(good)] > 0)
                self.assertGreater(opens[str(good)], 0)
                self.assertGreater(fstats[str(good)], 0)
                self.assertGreater(reads[str(bad)], 0)
        self.paths["codex"].remove(str(bad))
        expected = self.collect(use_cache=False, sources=("codex",))
        self.assertEqual([10], [record["total"] for record in expected])
        self.assertEqual(expected, self.collect(memo, sources=("codex",)))
        with self.io_counts() as (reads, _, _):
            self.assertEqual(expected, self.collect(memo, sources=("codex",)))
            self.assertEqual(0, reads[str(good)])

    def test_context_estimate_sequence_matches_no_cache_cold_and_warm(self):
        usage = {"input_tokens": 7, "output_tokens": 3, "cached_input_tokens": 2,
                 "reasoning_output_tokens": 1, "total_tokens": 10}
        estimate = dict(dict.fromkeys(usage, 0), total_tokens=5)
        header = [{"type": "session_meta", "payload": {"id": "synthetic-thread"}},
                  {"type": "turn_context", "payload": {"model": "synthetic-model"}}]
        def token(last):
            return {"type": "event_msg", "timestamp": STAMP, "payload": {
                "type": "token_count", "info": {"last_token_usage": last,
                                                 "total_token_usage": usage}}}
        good = self.write("codex", "a-estimate.jsonl", header + [token(usage), token(estimate)])
        # The failing shape is a modern response identity with differing
        # usage: identity conflicts still fail under first-sight accounting.
        changed = dict(usage, output_tokens=4, total_tokens=11)
        def record(response, last):
            return {"type": "token_usage_record", "timestamp": STAMP, "payload": {
                "thread_id": "synthetic-thread", "session_id": "synthetic-thread",
                "response_id": response, "usage": last}}
        bad = self.write("codex", "z-conflict.jsonl", header + [
            token(usage), token(estimate), record("one", usage), record("one", changed)])
        memo = readers._ParseMemo()
        for warm in (False, True):
            with self.subTest(warm=warm), self.io_counts() as (reads, opens, fstats):
                self.assertEqual(("codex", "usage_conflict", "modern_response_mismatch"), self.failure(memo))
                self.assertEqual(not warm, reads[str(good)] > 0)
                self.assertGreater(opens[str(good)], 0)
                self.assertGreater(fstats[str(good)], 0)
                self.assertGreater(reads[str(bad)], 0)
        self.paths["codex"].remove(str(bad))
        expected = self.collect(use_cache=False, sources=("codex",))
        self.assertEqual([10], [record["total"] for record in expected])
        self.assertEqual(expected, self.collect(memo, sources=("codex",)))
        with self.io_counts() as (reads, _, _):
            self.assertEqual(expected, self.collect(memo, sources=("codex",)))
            self.assertEqual(0, reads[str(good)])

    def test_interleaved_mixed_estimate_matches_no_cache_cold_and_warm(self):
        usage = {"input_tokens": 7, "output_tokens": 3, "cached_input_tokens": 2,
                 "reasoning_output_tokens": 1, "total_tokens": 10}
        estimate = dict(dict.fromkeys(usage, 0), total_tokens=5)
        header = [{"type": "session_meta", "payload": {"id": "synthetic-thread"}},
                  {"type": "turn_context", "payload": {"model": "synthetic-model"}}]
        def token(last, cumulative):
            return {"type": "event_msg", "timestamp": STAMP, "payload": {
                "type": "token_count", "info": {"last_token_usage": last,
                                                 "total_token_usage": cumulative}}}
        def record(response):
            return {"type": "token_usage_record", "timestamp": STAMP, "payload": {
                "thread_id": "synthetic-thread", "session_id": "synthetic-thread",
                "response_id": response, "usage": usage}}
        events = header + [token(usage, usage), record("one"), token(estimate, usage),
                           record("two"), token(usage, dict(usage, total_tokens=20))]
        good = self.write("codex", "a-mixed.jsonl", events)
        # Union accounting explains any modern surplus, so the failing shape
        # here is a same-response identity carrying different usage.
        extra = dict(usage, output_tokens=4, total_tokens=11)
        bad = self.write("codex", "z-mixed-conflict.jsonl",
                         events + [{"type": "token_usage_record", "timestamp": STAMP,
                                    "payload": {"thread_id": "synthetic-thread",
                                                "session_id": "synthetic-thread",
                                                "response_id": "one", "usage": extra}}])
        memo = readers._ParseMemo()
        for warm in (False, True):
            with self.subTest(warm=warm), self.io_counts() as (reads, opens, fstats):
                self.assertEqual(("codex", "usage_conflict", "modern_response_mismatch"), self.failure(memo))
                self.assertEqual(not warm, reads[str(good)] > 0)
                self.assertGreater(opens[str(good)], 0)
                self.assertGreater(fstats[str(good)], 0)
                self.assertGreater(reads[str(bad)], 0)
        self.paths["codex"].remove(str(bad))
        expected = self.collect(use_cache=False, sources=("codex",))
        self.assertEqual([10, 10], [item["total"] for item in expected])
        self.assertEqual(expected, self.collect(memo, sources=("codex",)))
        with self.io_counts() as (reads, _, _):
            self.assertEqual(expected, self.collect(memo, sources=("codex",)))
            self.assertEqual(0, reads[str(good)])

    def test_modern_response_mismatch_detail_survives_memo_failure_retries(self):
        good = self.write("claude", "a-good.jsonl", [claude_event()])
        usage = {"input_tokens": 7, "output_tokens": 3, "total_tokens": 10}
        def record(response, last):
            return {"type": "token_usage_record", "timestamp": STAMP, "payload": {
                "thread_id": "synthetic-thread", "session_id": "synthetic-thread",
                "response_id": response, "usage": last}}
        header = [{"type": "session_meta", "payload": {"id": "synthetic-thread"}},
                  {"type": "turn_context", "payload": {"model": "first"}}]
        bad = self.write("codex", "z-anchor.jsonl",
                         header + [record("one", usage), record("one", dict(usage, total_tokens=11))])
        memo = readers._ParseMemo()
        for warm in (False, True):
            with self.subTest(warm=warm), self.io_counts() as (reads, opens, fstats):
                with self.assertRaises(readers.CollectionIncompleteError) as caught:
                    self.collect(memo)
                self.assertEqual("modern_response_mismatch", caught.exception.conflict_kind)
                self.assertIsNone(caught.exception.mismatch_kind)
                self.assertGreater(reads[str(bad)], 0)
                self.assertEqual(0 if warm else 1, int(reads[str(good)] > 0))
                self.assertGreater(opens[str(good)], 0)
                self.assertGreater(fstats[str(good)], 0)
        self.write("codex", "z-anchor.jsonl", header + [record("one", usage)])
        self.assertEqual(self.collect(memo), self.collect(use_cache=False))

    def bad(self):
        return self.write("codex", "z-bad.jsonl", [codex_event(amount="invalid")])

    def collect(self, memo=None, *, sources=("claude", "codex"), use_cache=True):
        return readers.read_all(list(sources), use_cache, self.observe, parse_memo=memo)

    def observe(self, event, source):
        self.events.append((event, source))

    def failure(self, memo, **kwargs):
        self.events.clear()
        with self.assertRaises(readers.CollectionIncompleteError) as caught:
            self.collect(memo, **kwargs)
        err = caught.exception
        return err.source, err.reason, err.conflict_kind

    @contextmanager
    def io_counts(self):
        """Wrap real fd-backed source reads without replacing any parser/helper."""
        actual_fdopen, actual_open, actual_fstat = os.fdopen, os.open, os.fstat
        identities = {}
        for paths in self.paths.values():
            for path in paths:
                try:
                    st = os.stat(path)
                    identities[(st.st_dev, st.st_ino)] = path
                except OSError:
                    pass
        reads, opens, fstats = Counter(), Counter(), Counter()

        def wrap(fd, *args, **kwargs):
            file = actual_fdopen(fd, *args, **kwargs)
            st = actual_fstat(fd)
            path = identities.get((st.st_dev, st.st_ino))
            return _SourceReader(file, lambda: reads.update([path])) if path else file

        def opened(path, *args, **kwargs):
            fd = actual_open(path, *args, **kwargs)
            if os.fspath(path) in {p for ps in self.paths.values() for p in ps}:
                opens.update([os.fspath(path)])
            return fd

        def fstat(fd):
            st = actual_fstat(fd)
            path = identities.get((st.st_dev, st.st_ino))
            if path:
                fstats.update([path])
            return st

        with mock.patch.object(os, "fdopen", side_effect=wrap), \
                mock.patch.object(os, "open", side_effect=opened), \
                mock.patch.object(os, "fstat", side_effect=fstat):
            yield reads, opens, fstats

    def test_failure_retains_prefix_but_retries_bad_file_without_content_read(self):
        a = self.write("codex", "a.jsonl", [codex_event()])
        b = self.bad()
        memo = readers._ParseMemo()
        with self.io_counts() as (reads, opens, fstats):
            cold = self.failure(memo)
            self.assertGreater(reads[str(a)], 0)
            self.assertGreater(reads[str(b)], 0)
            reads.clear(); opens.clear(); fstats.clear()
            self.assertEqual(cold, self.failure(memo))
            self.assertEqual(0, reads[str(a)])
            self.assertGreater(reads[str(b)], 0)
            self.assertGreater(opens[str(a)], 0)
            self.assertGreaterEqual(fstats[str(a)], 2)
        self.assertEqual([("discovered", "codex"), ("processed_cached", "codex"),
                          ("discovered", "codex")], self.events)
        self.assertFalse(self.cache.exists())

    def test_claude_success_prefix_is_reused_after_codex_failure(self):
        a = self.write("claude", "a.jsonl", [claude_event()])
        self.bad()
        memo = readers._ParseMemo()
        expected = self.failure(memo)
        with self.io_counts() as (reads, opens, _):
            self.assertEqual(expected, self.failure(memo))
            self.assertEqual(0, reads[str(a)])
            self.assertEqual(1, opens[str(a)])
        self.assertIn(("processed_cached", "claude"), self.events)

    def test_cross_file_conflict_is_not_registered_and_repair_matches_no_memo(self):
        a = self.write("codex", "a.jsonl", [codex_event()])
        b = self.write("codex", "b.jsonl", [codex_event(amount=8)])
        memo = readers._ParseMemo()
        expected = ("codex", "usage_conflict", "cross_file_identity_mismatch")
        self.assertEqual(expected, self.failure(memo))
        with self.io_counts() as (reads, _, _):
            self.assertEqual(expected, self.failure(memo))
            self.assertEqual(0, reads[str(a)])
            self.assertGreater(reads[str(b)], 0)
        self.assertNotIn(("processed_cached", "codex"), self.events[2:])
        self.write("codex", "b.jsonl", [codex_event(), codex_event("two", 13)])
        baseline = self.collect(use_cache=False)
        actual = self.collect(memo)
        self.assertEqual(baseline, actual)
        self.assertEqual(2, len(actual))

    def test_raw_preselection_records_are_restored_when_predecessor_disappears(self):
        a = self.write("codex", "a.jsonl", [codex_event()])
        b = self.write("codex", "b.jsonl", [codex_event(), codex_event("two", 13)])
        self.bad()
        memo = readers._ParseMemo()
        self.failure(memo)
        a.unlink(); self.paths["codex"].remove(str(a))
        with self.io_counts() as (reads, _, _):
            self.failure(memo)
            self.assertEqual(0, reads[str(b)])
        self.paths["codex"] = [str(b)]
        self.assertEqual(self.collect(use_cache=False), self.collect(memo))
        self.assertEqual(2, len(self.collect(memo)))

    def test_disk_cache_unchanged_on_failure_and_original_schema_on_success(self):
        a = self.write("codex", "a.jsonl", [codex_event()])
        original = self.collect()
        raw = self.cache.read_bytes()
        self.write("codex", "a.jsonl", [codex_event(amount=11)])
        b = self.bad(); memo = readers._ParseMemo()
        self.failure(memo); self.failure(memo)
        self.assertEqual(raw, self.cache.read_bytes())
        self.paths["codex"].remove(str(b))
        result = self.collect(memo)
        self.assertNotEqual(original, result)
        data = json.loads(self.cache.read_bytes())
        self.assertEqual(readers.CACHE_VERSION, data["_v"])
        self.assertEqual({"key", "records", "identity", "version", "dedup"},
                         set(data["codex::" + str(a)]))
        self.assertEqual(result, self.collect())

    def test_nested_return_and_disk_objects_cannot_mutate_memo(self):
        a = self.write("claude", "a.jsonl", [claude_event()])
        memo = readers._ParseMemo()
        expected = self.collect(use_cache=False)
        returned = self.collect(memo)
        returned[0]["billing"]["parts"][0] = 999
        returned[0]["billing"]["present"]["input"] = False
        self.cache.unlink()
        self.assertEqual(expected, self.collect(memo))
        self.cache.unlink()
        returned = self.collect(memo)
        returned[0]["billing"]["reasons"].append("caller mutation")
        self.cache.unlink()
        self.assertEqual(expected, self.collect(memo))
        self.assertEqual(1, len(expected))

    def test_append_truncate_replace_same_size_ctime_and_delete_invalidate(self):
        for change in ("append", "truncate", "replace", "ctime", "delete"):
            with self.subTest(change=change):
                self.paths["codex"] = []
                a = self.write("codex", "a.jsonl", [codex_event()])
                self.bad(); memo = readers._ParseMemo(); self.failure(memo)
                before = a.stat()
                if change == "append":
                    with a.open("ab") as fh:
                        fh.write(json.dumps(codex_event("two")).encode() + b"\n")
                elif change == "truncate":
                    a.write_bytes(b"{}\n")
                elif change == "replace":
                    other = a.with_suffix(".new"); other.write_bytes(a.read_bytes()); other.replace(a)
                elif change == "ctime":
                    raw = a.read_bytes().replace(b'"input_tokens":7', b'"input_tokens":8')
                    self.assertEqual(before.st_size, len(raw)); a.write_bytes(raw)
                    os.utime(a, ns=(before.st_atime_ns, before.st_mtime_ns))
                    self.assertNotEqual(before.st_ctime_ns, a.stat().st_ctime_ns)
                else:
                    a.unlink()
                with self.io_counts() as (reads, _, _):
                    error = self.failure(memo)
                    if change == "delete":
                        self.assertEqual("stat_failed", error[1])
                    else:
                        self.assertGreater(reads[str(a)], 0)

    def test_symlink_and_fifo_never_reuse(self):
        for kind in ("symlink", "fifo"):
            with self.subTest(kind=kind):
                self.paths["codex"] = []
                a = self.write("codex", "a.jsonl", [codex_event()]); self.bad()
                memo = readers._ParseMemo(); self.failure(memo); a.unlink()
                if kind == "symlink":
                    target = self.root / "target"; target.write_bytes(b"{}\n"); a.symlink_to(target)
                else:
                    if not hasattr(os, "mkfifo"):
                        continue
                    os.mkfifo(a)
                self.assertEqual(("codex", "unsafe_file", None), self.failure(memo))
                a.unlink()

    def test_no_cache_is_zero_disk_and_memo_access(self):
        a = self.write("codex", "a.jsonl", [codex_event()])
        memo = readers._ParseMemo()
        with mock.patch.object(readers, "_load_cache", side_effect=AssertionError("disk read")), \
                mock.patch.object(readers, "_save_cache", side_effect=AssertionError("disk write")), \
                mock.patch.object(memo, "get", side_effect=AssertionError("memo read")), \
                mock.patch.object(memo, "put", side_effect=AssertionError("memo write")), \
                self.io_counts() as (reads, _, _):
            first = self.collect(memo, use_cache=False)
            self.assertEqual(first, self.collect(memo, use_cache=False))
            self.assertGreaterEqual(reads[str(a)], 2)
        self.assertFalse(self.cache.exists())

    def test_unknown_parser_and_patched_helper_disable_reuse_not_fake_io_pass(self):
        a = self.write("codex", "a.jsonl", [codex_event()]); self.bad()
        for owner, name in ((codex_usage, "parse_state"), (readers, "_to_local_date"),
                            (codex_usage, "identity"), (codex_usage, "_complete_usage"),
                            (_claude_json.ProjectionParser, "feed")):
            with self.subTest(helper=name):
                memo = readers._ParseMemo(); self.failure(memo)
                original = getattr(owner, name)
                with mock.patch.object(owner, name, new=lambda *a, _fn=original, **k: _fn(*a, **k)), \
                        self.io_counts() as (reads, _, _):
                    self.failure(memo); self.failure(memo)
                    self.assertGreaterEqual(reads[str(a)], 2)
        parser = readers.SOURCES["codex"][1]
        with mock.patch.dict(readers.SOURCES, {"codex": (readers.SOURCES["codex"][0],
                                                        lambda p: parser(p))}):
            memo = readers._ParseMemo()
            with self.io_counts() as (reads, _, _):
                self.failure(memo); self.failure(memo)
                self.assertGreaterEqual(reads[str(a)], 2)

    def test_namespace_timezone_roots_normalization_and_budgets_invalidate(self):
        a = self.write("codex", "a.jsonl", [codex_event()]); self.bad()
        cases = [(config, "TZ", timezone(timedelta(hours=3))),
                 (config, "CODEX_ARCHIVED_SESSIONS", str(self.root / "other")),
                 (readers, "CACHE_VERSION", readers.CACHE_VERSION + 1),
                 (readers, "MAX_TOTAL_RECORDS", readers.MAX_TOTAL_RECORDS - 1),
                 (codex_usage, "MAX_RECORDS", codex_usage.MAX_RECORDS - 1),
                 (codex_usage, "ANCHOR_FIELDS", codex_usage.ANCHOR_FIELDS[:-1]),
                 (readers, "BILLING_COMPONENTS", tuple(reversed(readers.BILLING_COMPONENTS)))]
        for owner, name, value in cases:
            with self.subTest(name=name):
                memo = readers._ParseMemo(); self.failure(memo)
                with mock.patch.object(owner, name, value), self.io_counts() as (reads, _, _):
                    self.failure(memo)
                    self.assertGreater(reads[str(a)], 0)

    def test_unknown_timezone_never_reuses(self):
        class MutableTZ(tzinfo):
            def utcoffset(self, dt): return timedelta(0)
            def dst(self, dt): return timedelta(0)
            def tzname(self, dt): return "UTC"
        a = self.write("codex", "a.jsonl", [codex_event()]); self.bad()
        with mock.patch.object(config, "TZ", MutableTZ()):
            memo = readers._ParseMemo()
            with self.io_counts() as (reads, _, _):
                self.failure(memo); self.failure(memo)
                self.assertGreaterEqual(reads[str(a)], 2)

    def test_initial_unheated_router_settles_after_parse_and_reuses(self):
        a = self.write("claude", "a.jsonl", [claude_event()]); self.bad()
        self.router.write_text("if (model.includes('sonnet')) return 'p,backend-one';\n")
        memo = readers._ParseMemo(); self.failure(memo)
        self.assertNotEqual("", readers._ccr_rules_cache[0])
        with self.io_counts() as (reads, _, _):
            self.failure(memo)
            self.assertEqual(0, reads[str(a)])
        self.router.write_text("if (model.includes('sonnet')) return 'p,backend-two';\n")
        with self.io_counts() as (reads, _, _):
            self.failure(memo)
            self.assertGreater(reads[str(a)], 0)
        self.paths["codex"] = []
        self.assertEqual("backend-two", self.collect(memo)[0]["model"])

    def test_total_budget_rechecked_and_failing_file_removed(self):
        a = self.write("codex", "a.jsonl", [codex_event()]); b = self.bad()
        memo = readers._ParseMemo(); self.failure(memo)
        self.write("codex", b.name, [codex_event("two")])
        with mock.patch.object(readers, "MAX_TOTAL_RECORDS", 1):
            self.assertEqual(("all", "total_record_limit", None), self.failure(memo))
            self.assertEqual(("all", "total_record_limit", None), self.failure(memo))
        self.assertEqual(self.collect(use_cache=False), self.collect(memo))

    def test_empty_files_are_entries_but_only_after_success(self):
        a = self.write("codex", "a.jsonl", []); self.bad()
        memo = readers._ParseMemo(max_entries=1)
        self.failure(memo)
        self.assertEqual(1, len(memo._entries))
        with self.io_counts() as (reads, opens, _):
            self.failure(memo)
            self.assertEqual(0, reads[str(a)])
            self.assertEqual(1, opens[str(a)])

    def test_lru_and_entry_record_byte_limits_are_nonfatal(self):
        a = self.write("codex", "a.jsonl", [codex_event()]); self.bad()
        for settings in ({"max_entries": 0}, {"max_records": 0}, {"max_bytes": 1},
                         {"max_entry_records": 0}, {"max_entry_bytes": 1}):
            with self.subTest(settings=settings):
                memo = readers._ParseMemo(**settings)
                with self.io_counts() as (reads, _, _):
                    expected = self.failure(memo)
                    self.assertEqual(expected, self.failure(memo))
                    self.assertGreaterEqual(reads[str(a)], 2)
                self.assertEqual(0, len(memo._entries))

    def test_over_capacity_sequential_scans_report_actual_thrash(self):
        for index in range(4):
            self.write("codex", f"{index}.jsonl", [codex_event(str(index))])
        b = self.bad(); memo = readers._ParseMemo(max_entries=3)
        with self.io_counts() as (reads, _, _):
            expected = self.failure(memo)
            cold_reads = sum(reads.values()); reads.clear()
            self.assertEqual(expected, self.failure(memo))
            warm_reads = sum(reads.values())
            hits = self.events.count(("processed_cached", "codex"))
        self.assertEqual(5, cold_reads)
        self.assertEqual(5, warm_reads)
        self.assertEqual(0, hits)
        self.assertEqual(3, len(memo._entries))
        self.assertNotIn(("codex", str(b)), memo._entries)

    def test_lru_touch_aggregate_capacity_and_oversize_before_copy(self):
        a = self.write("codex", "a.jsonl", [codex_event()])
        records, dedup, opened, stable = codex_usage.parse_state(str(a))
        self.assertTrue(stable)
        version = readers._stat_version(opened)
        keys = [("codex", str(a) + suffix) for suffix in ("", "-b", "-c")]
        memo = readers._ParseMemo(max_entries=2)
        memo.put(keys[0], version, records, dedup)
        saved_dedup = deepcopy(dedup)
        dedup[0] = "0" * 64
        self.assertEqual(saved_dedup, memo.get(keys[0], version)[1])
        memo.put(keys[1], version, records, saved_dedup)
        memo.get(keys[0], version)
        memo.put(keys[2], version, records, saved_dedup)
        self.assertEqual([keys[0], keys[2]], list(memo._entries))
        measured = memo._entries[keys[0]][3]
        for settings in ({"max_records": 1}, {"max_bytes": measured * 2 - 1}):
            constrained = readers._ParseMemo(**settings)
            constrained.put(keys[0], version, records, saved_dedup)
            constrained.put(keys[1], version, records, saved_dedup)
            self.assertEqual([keys[1]], list(constrained._entries))
            self.assertLessEqual(constrained._records, constrained.max_records)
            self.assertLessEqual(constrained._bytes, constrained.max_bytes)
        oversized = deepcopy(records)
        oversized[0]["model"] = "x" * (memo.max_entry_bytes + 1)
        before = list(memo._entries)
        with mock.patch.object(readers, "deepcopy", side_effect=AssertionError("copy before bounded measure")):
            memo.put(("codex", "oversized"), version, oversized, saved_dedup)
        self.assertEqual(before, list(memo._entries))
        pair = memo.get(keys[0], version)
        pair[0][0]["billing"]["parts"][0] = 1000
        pair[1][0] = "f" * 64
        self.assertEqual((records, saved_dedup), memo.get(keys[0], version))

    def test_read_time_append_is_successful_but_not_admitted(self):
        a = self.write("codex", "a.jsonl", [codex_event()]); self.bad()
        memo = readers._ParseMemo()
        actual_fdopen, actual_fstat = os.fdopen, os.fstat
        identity = (a.stat().st_dev, a.stat().st_ino)
        changed = []

        def wrap(fd, *args, **kwargs):
            file = actual_fdopen(fd, *args, **kwargs)
            info = actual_fstat(fd)
            if (info.st_dev, info.st_ino) != identity:
                return file

            def append_once():
                if not changed:
                    changed.append(True)
                    with a.open("ab") as output:
                        output.write(json.dumps(codex_event("two")).encode() + b"\n")
            return _SourceReader(file, append_once)

        with mock.patch.object(os, "fdopen", side_effect=wrap):
            self.assertEqual(("codex", "usage_invalid", None), self.failure(memo))
        self.assertNotIn(("codex", str(a)), memo._entries)
        with self.io_counts() as (reads, _, _):
            self.failure(memo)
            self.assertGreater(reads[str(a)], 0)
        self.assertIn(("codex", str(a)), memo._entries)

    def test_namespace_changed_during_parse_does_not_register(self):
        a = self.write("codex", "a.jsonl", [codex_event()]); self.bad()
        memo = readers._ParseMemo()
        actual_fdopen, actual_fstat = os.fdopen, os.fstat
        identity = (a.stat().st_dev, a.stat().st_ino)
        old_root = config.CODEX_ARCHIVED_SESSIONS

        def wrap(fd, *args, **kwargs):
            file = actual_fdopen(fd, *args, **kwargs)
            info = actual_fstat(fd)
            if (info.st_dev, info.st_ino) != identity:
                return file
            return _SourceReader(file, lambda: setattr(config, "CODEX_ARCHIVED_SESSIONS",
                                                       str(self.root / "changed")))
        try:
            with mock.patch.object(os, "fdopen", side_effect=wrap):
                self.failure(memo)
            self.assertNotIn(("codex", str(a)), memo._entries)
        finally:
            config.CODEX_ARCHIVED_SESSIONS = old_root

    def test_router_own_symlink_and_target_identity_invalidate(self):
        a = self.write("claude", "a.jsonl", [claude_event()]); self.bad()
        target = self.root / "router-target.js"
        rule = "if (model.includes('sonnet')) return 'p,backend-one';\n"
        target.write_text(rule); self.router.symlink_to(target)
        memo = readers._ParseMemo(); self.failure(memo)
        for kind in ("target", "own"):
            with self.subTest(kind=kind):
                if kind == "target":
                    replacement = target.with_suffix(".new")
                    replacement.write_text(rule)
                    before = target.stat()
                    os.utime(replacement, ns=(before.st_atime_ns, before.st_mtime_ns))
                    replacement.replace(target)
                else:
                    self.router.unlink(); self.router.symlink_to(target)
                with self.io_counts() as (reads, _, _):
                    self.failure(memo)
                    self.assertGreater(reads[str(a)], 0)
        # The existing rules are the parser's actual rules; memo never invents a
        # stronger claim about same-size/same-mtime rule-cache invalidation.

    def test_observer_failure_cannot_change_success_or_memo(self):
        self.write("codex", "a.jsonl", [codex_event()])
        memo = readers._ParseMemo()
        baseline = self.collect(use_cache=False)
        with mock.patch.object(self, "observe", side_effect=RuntimeError("observer only")):
            self.assertEqual(baseline, self.collect(memo))
            self.cache.unlink()
            self.assertEqual(baseline, self.collect(memo))

    def test_valid_disk_cache_precedes_memo_without_get_or_put(self):
        self.write("claude", "a.jsonl", [claude_event()])
        self.write("codex", "a.jsonl", [codex_event()])
        memo = readers._ParseMemo()
        expected = self.collect(memo)
        with mock.patch.object(memo, "get", side_effect=AssertionError("disk must win before RAM lookup")), \
                mock.patch.object(memo, "put", side_effect=AssertionError("valid disk needs no RAM admission")), \
                self.io_counts() as (reads, opens, fstats):
            self.assertEqual(expected, self.collect(memo))
            self.assertEqual(0, sum(reads.values()))
            self.assertEqual(2, sum(opens.values()))
            self.assertGreaterEqual(sum(fstats.values()), 4)

    def test_disk_warm_security_error_is_not_hidden_by_memo_fallback(self):
        a = self.write("codex", "a.jsonl", [codex_event()])
        memo = readers._ParseMemo()
        self.collect(memo)
        actual_open = os.open

        def denied(path, *args, **kwargs):
            if os.fspath(path) == str(a):
                raise PermissionError("synthetic disk warm open denied")
            return actual_open(path, *args, **kwargs)

        with mock.patch.object(os, "open", side_effect=denied), \
                mock.patch.object(memo, "get", side_effect=AssertionError("security errors must propagate")):
            self.assertEqual(("codex", "open_failed", None), self.failure(memo))
        self.assertNotIn(("codex", str(a)), memo._entries)

    @unittest.skipUnless(hasattr(time, "tzset"), "requires process-local timezone control")
    def test_naive_timestamps_do_not_reuse_across_process_local_timezone_change(self):
        original_tz = os.environ.get("TZ")
        try:
            for source, make_event in (("claude", claude_event), ("codex", codex_event)):
                with self.subTest(source=source):
                    self.paths["claude"] = []; self.paths["codex"] = []
                    event = make_event()
                    event["timestamp"] = "2026-11-01T18:00:00"
                    a = self.write(source, "naive.jsonl", [event]); self.bad()
                    kwargs = {"sources": (source,)}
                    memo = readers._ParseMemo()
                    os.environ["TZ"] = "UTC"; time.tzset()
                    bad_path = self.paths["codex"].pop()
                    cold = self.collect(use_cache=False, **kwargs)
                    self.paths["codex"].append(bad_path)
                    self.assertEqual("2026-11-01", cold[0]["date"])
                    self.failure(memo)
                    os.environ["TZ"] = "Etc/GMT+12"; time.tzset()
                    with self.io_counts() as (reads, _, _):
                        self.failure(memo)
                        self.assertGreater(reads[str(a)], 0)
                    self.assertNotIn((source, str(a)), memo._entries)
                    self.paths["codex"] = ([str(a)] if source == "codex" else [])
                    expected = self.collect(use_cache=False, **kwargs)
                    self.assertEqual("2026-11-02", expected[0]["date"])
                    self.assertEqual(expected, self.collect(memo, **kwargs))
                    self.assertNotIn((source, str(a)), memo._entries)
                    self.cache.unlink()
                    # Explicit-offset timestamps remain eligible across the
                    # same process-local timezone switch (config.TZ is UTC).
                    aware_event = make_event()
                    aware_event["timestamp"] = "2026-11-01T18:00:00Z"
                    self.write(source, a.name, [aware_event]); self.bad()
                    os.environ["TZ"] = "UTC"; time.tzset()
                    aware_memo = readers._ParseMemo(); self.failure(aware_memo)
                    self.assertIn((source, str(a)), aware_memo._entries)
                    os.environ["TZ"] = "Etc/GMT+12"; time.tzset()
                    with self.io_counts() as (reads, _, _):
                        self.failure(aware_memo)
                        self.assertEqual(0, reads[str(a)])
                    self.paths["codex"] = ([str(a)] if source == "codex" else [])
                    self.assertEqual("2026-11-01", self.collect(aware_memo, **kwargs)[0]["date"])
                    self.cache.unlink()
        finally:
            if original_tz is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = original_tz
            time.tzset()

    def test_naive_or_unprovable_admission_removes_old_key_but_offset_is_reusable(self):
        for source, make_event in (("claude", claude_event), ("codex", codex_event)):
            with self.subTest(source=source):
                a = self.write(source, "aware.jsonl", [make_event()])
                if source == "claude":
                    records, dedup, opened, _ = readers._claude_parse_state(str(a))
                else:
                    records, dedup, opened, _ = codex_usage.parse_state(str(a))
                self.assertEqual(STAMP, records[0]["ts"])
                version = readers._stat_version(opened)
                key = source, str(a)
                memo = readers._ParseMemo()
                for bad_ts in ("2026-11-01T18:00:00", "unparseable"):
                    memo.put(key, version, records, dedup)
                    self.assertIn(key, memo._entries)
                    naive = deepcopy(records)
                    naive[0]["ts"] = bad_ts
                    memo.put(key, version, naive, dedup)
                    self.assertNotIn(key, memo._entries)
                memo.put(key, version, records, dedup)
                self.assertEqual((records, dedup), memo.get(key, version))

    @unittest.skipUnless(hasattr(time, "tzset"), "requires process-local timezone control")
    def test_claude_skipped_naive_overflow_candidate_prevents_empty_or_mixed_reuse(self):
        original_tz = os.environ.get("TZ")
        try:
            for mixed in (False, True):
                with self.subTest(mixed=mixed):
                    self.paths["claude"] = []; self.paths["codex"] = []
                    extreme = claude_event()
                    extreme["timestamp"] = "9999-12-31T18:00:00"
                    extreme["message"]["id"] = "naive-extreme"
                    events = [extreme]
                    if mixed:
                        regular = claude_event()
                        regular["message"]["id"] = "aware-regular"
                        events.append(regular)
                    a = self.write("claude", "overflow.jsonl", events); self.bad()
                    memo = readers._ParseMemo()
                    os.environ["TZ"] = "Etc/GMT+12"; time.tzset()
                    cold = readers.claude_parse(str(a))
                    self.assertEqual(int(mixed), len(cold))
                    self.failure(memo)
                    os.environ["TZ"] = "UTC"; time.tzset()
                    with self.io_counts() as (reads, _, _):
                        self.failure(memo)
                        self.assertGreater(reads[str(a)], 0)
                    self.assertNotIn(("claude", str(a)), memo._entries)
                    self.paths["codex"] = []
                    expected = self.collect(use_cache=False)
                    self.assertEqual(1 + int(mixed), len(expected))
                    self.assertEqual("9999-12-31", expected[0]["date"])
                    self.assertEqual(expected, self.collect(memo))
                    self.cache.unlink()
        finally:
            if original_tz is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = original_tz
            time.tzset()

    def test_claude_date_proof_is_local_optional_and_preserves_return_and_exception(self):
        self.assertIsNone(readers._claude_parse_state.__kwdefaults__["_memo_proof"])
        event = claude_event(); event["timestamp"] = "2026-11-01T18:00:00"
        # Direct helper calls retain exactly the old record or exception shape;
        # proof is an opt-in local argument, not module/instance ambient state.
        proof = [True]
        self.assertEqual(readers._claude_event_record(event),
                         readers._claude_event_record(event, _memo_proof=proof))
        self.assertEqual([False], proof)
        aware_proof = [True]
        self.assertEqual(readers._claude_event_record(claude_event()),
                         readers._claude_event_record(claude_event(), _memo_proof=aware_proof))
        self.assertEqual([True], aware_proof)
        self.assertIsNone(readers._to_local_date("bad", _memo_proof=[True]))

    def test_default_interface_and_instance_isolation(self):
        a = self.write("codex", "a.jsonl", [codex_event()]); self.bad()
        first, second = readers._ParseMemo(), readers._ParseMemo()
        self.failure(first)
        with self.io_counts() as (reads, _, _):
            self.failure(second)
            self.assertGreater(reads[str(a)], 0)
        with self.assertRaises(readers.CollectionIncompleteError):
            readers.read_all(["codex"], True, self.observe)
        self.assertEqual(4096, first.max_entries)
        self.assertEqual(100000, first.max_records)
        self.assertEqual(64 * 1024 * 1024, first.max_bytes)


if __name__ == "__main__":
    unittest.main()
