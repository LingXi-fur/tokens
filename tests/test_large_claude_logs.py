"""Synthetic-only regression tests for bounded, all-or-fail Claude collection.

No real source discovery, router, title, sidecar, cache, or network is used.
The >64 MiB cases write both ordinary lines and giant projected JSON lines in chunks.
"""
import builtins
from contextlib import ExitStack, contextmanager
from datetime import timezone
import io
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tokens_cli import cli, config, live_dashboard, readers


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def event(mid="one", tokens=7, **overrides):
    value = {
        "type": "assistant", "timestamp": "2026-10-20T10:00:00Z",
        "sessionId": "synthetic-session", "cwd": "/synthetic/project",
        "message": {"id": mid, "model": "synthetic-backend", "usage": {
            "input_tokens": tokens, "output_tokens": 3,
            "cache_read_input_tokens": 2, "cache_creation_input_tokens": 1,
        }},
    }
    value.update(overrides)
    return value


def normalized(value):
    message = value["message"]
    usage = message["usage"]
    return {
        "source": "claude", "ts": value["timestamp"], "date": "2026-10-20",
        "model": message["model"], "input": usage["input_tokens"],
        "output": usage["output_tokens"], "cache_read": usage["cache_read_input_tokens"],
        "cache_write": usage["cache_creation_input_tokens"],
        "total": sum(usage.values()), "session": value.get("sessionId"),
        "cwd": value.get("cwd"),
        # All event() fixtures supply the four valid Claude usage fields.
        # Keep existing schema-1 evidence in both equality and byte accounting.
        "billing": {
            "v": 1,
            "present": {"input": True, "output": True,
                        "cache_read": True, "cache_write": True},
            "raw": {"input": usage["input_tokens"], "output": usage["output_tokens"],
                    "cache_read": usage["cache_read_input_tokens"],
                    "cache_write": usage["cache_creation_input_tokens"]},
            "parts": [usage["input_tokens"], usage["output_tokens"],
                      usage["cache_read_input_tokens"],
                      usage["cache_creation_input_tokens"], 0],
            "uncertain": False,
            "reasons": [],
        },
    }


def retained_cost(value):
    message = value["message"]
    usage = message["usage"]
    key = message.get("id") or (
        value["timestamp"], message["model"], usage["input_tokens"],
        usage["output_tokens"], usage["cache_read_input_tokens"],
        usage["cache_creation_input_tokens"],
    )
    return len(encoded(normalized(value))) + 512 + len(encoded(key)) + 256


class _BoundedReader:
    """Instrument the OS boundary without depending on a parser helper name."""

    def __init__(self, file, testcase, after_first=None, fail_after=None,
                 max_read=None, eof_after=None):
        self.file = file
        self.testcase = testcase
        self.after_first = after_first
        self.fail_after = fail_after
        self.max_read = max_read
        self.eof_after = eof_after
        self.calls = 0
        self.requests = []
        self.bytes_read = 0

    def __getattr__(self, name):
        return getattr(self.file, name)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return self.file.__exit__(*args)

    def __iter__(self):
        raise AssertionError("Claude collection must not iterate unbounded lines")

    def seek(self, *args, **kwargs):
        raise AssertionError("Claude collection must never seek or replay a prefix")

    def _read(self, method, size):
        self.testcase.assertGreater(size, 0, "unbounded read is forbidden")
        self.testcase.assertLessEqual(size, 64 * 1024)
        self.requests.append((method, size))
        if self.fail_after is not None and self.calls >= self.fail_after:
            raise OSError("synthetic-private-read-detail")
        if self.eof_after is not None and self.calls >= self.eof_after:
            return b""
        result = getattr(self.file, method)(min(size, self.max_read) if self.max_read else size)
        self.calls += 1
        self.bytes_read += len(result)
        if self.calls == 1 and self.after_first:
            self.after_first()
        return result

    def read(self, size=-1):
        return self._read("read", size)

    def readline(self, size=-1):
        return self._read("readline", size)


class LargeClaudeLogsTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.projects = self.root / "projects"
        self.projects.mkdir()
        self.cache = self.root / "cache" / "records.json"
        self.output = self.root / "reports"
        self.output.mkdir()
        self.paths = {source: [] for source in ("claude", "gemini", "codex")}
        # Deliberately look up claude_parse at call time, not at fixture creation.
        self.parse = mock.Mock(side_effect=lambda path: readers.claude_parse(path))
        self.other_parsers = {source: mock.Mock(return_value=[])
                              for source in ("gemini", "codex")}
        sources = {
            source: (lambda source=source: list(self.paths[source]),
                     self.parse if source == "claude" else self.other_parsers[source])
            for source in self.paths
        }
        patches = [
            mock.patch.object(config, "CACHE_DIR", str(self.cache.parent)),
            mock.patch.object(config, "CACHE_FILE", str(self.cache)),
            mock.patch.object(config, "CLAUDE_PROJECTS", str(self.projects)),
            mock.patch.object(config, "GEMINI_TMP", str(self.root / "gemini")),
            mock.patch.object(config, "CODEX_SESSIONS", str(self.root / "codex")),
            mock.patch.object(config, "OUT_DIR", str(self.output)),
            mock.patch.object(config, "SESSION_SUMMARY_FILE", str(self.root / "absent-summary.json")),
            mock.patch.object(config, "CCR_ROUTER_FILE", str(self.root / "absent-router.js")),
            mock.patch.object(config, "TZ", timezone.utc),
            mock.patch.object(readers, "_ccr_signature", return_value=""),
            mock.patch.object(readers, "_ccr_rules", return_value=[]),
            mock.patch.object(readers, "load_session_summaries", return_value={}),
            mock.patch.object(readers, "build_session_index", return_value={}),
            mock.patch.object(readers, "session_title", return_value=""),
            mock.patch.dict(readers.SOURCES, sources, clear=True),
            mock.patch.dict(os.environ, {"TOKENS_LANG": "en", "TZ": "UTC"}),
        ]
        for patcher in patches:
            self.stack.enter_context(patcher)

    def write(self, values, name="session.jsonl", source="claude"):
        path = self.projects / name
        path.write_bytes(b"".join(encoded(value) + b"\n" for value in values))
        self.paths[source].append(str(path))
        return path

    def collect(self, use_cache=True):
        if not use_cache:
            return readers.read_all(sources=["claude"], use_cache=False)
        # Production Claude cache entries also retain parser-owned dedup state.
        # Bind the real parser late; the finder remains synthetic. A wrapper
        # parser intentionally cannot attest that state and must not be cached.
        with mock.patch.dict(readers.SOURCES, {
                "claude": (lambda: list(self.paths["claude"]), readers.claude_parse)}):
            return readers.read_all(sources=["claude"], use_cache=True)

    def assert_incomplete(self, action):
        with self.assertRaises(readers.CollectionIncompleteError) as caught:
            action()
        text = str(caught.exception)
        for private in (str(self.root), "synthetic-private", "synthetic-session"):
            self.assertNotIn(private, text)
        return caught.exception

    @contextmanager
    def instrument(self, after_first=None, fail_after=None, max_read=None, eof_after=None):
        real_open, real_fdopen = builtins.open, os.fdopen
        wrapped = []
        source_identities = set()
        for path in self.paths["claude"]:
            try:
                info = os.stat(path)
            except OSError:
                continue
            source_identities.add((info.st_dev, info.st_ino))

        def wrap(file):
            if isinstance(file, _BoundedReader):
                return file
            result = _BoundedReader(file, self, after_first, fail_after, max_read, eof_after)
            wrapped.append(result)
            return result

        def open_file(path, mode="r", *args, **kwargs):
            file = real_open(path, mode, *args, **kwargs)
            return wrap(file) if "r" in mode and str(path) in self.paths["claude"] else file

        def fdopen(fd, mode="r", *args, **kwargs):
            info = os.fstat(fd)
            is_source = (info.st_dev, info.st_ino) in source_identities
            file = real_fdopen(fd, mode, *args, **kwargs)
            return wrap(file) if "r" in mode and is_source else file

        with mock.patch("builtins.open", side_effect=open_file), \
                mock.patch.object(os, "fdopen", side_effect=fdopen):
            yield wrapped

    @contextmanager
    def deny_open(self, path):
        real_open, real_os_open = builtins.open, os.open

        def deny(original):
            def call(candidate, *args, **kwargs):
                if str(candidate) == str(path):
                    raise PermissionError("synthetic-private-open-detail")
                return original(candidate, *args, **kwargs)
            return call

        with mock.patch("builtins.open", side_effect=deny(real_open)), \
                mock.patch.object(os, "open", side_effect=deny(real_os_open)):
            yield

    def test_default_resource_limits_match_the_contract(self):
        expected = {
            "MAX_FILE_BYTES": 64 * 1024 * 1024, "MAX_LINE_BYTES": 4 * 1024 * 1024,
            "MAX_CLAUDE_RECORDS": 100000, "MAX_CLAUDE_RETAINED_BYTES": 64 * 1024 * 1024,
            "MAX_TOTAL_RECORDS": 500000, "MAX_TOTAL_RETAINED_BYTES": 256 * 1024 * 1024,
            "MAX_CACHE_BYTES": 64 * 1024 * 1024, "CLAUDE_READ_CHUNK_BYTES": 64 * 1024,
        }
        for name, value in expected.items():
            with self.subTest(limit=name):
                self.assertEqual(value, getattr(readers, name))
        self.assertEqual(7, readers.CACHE_VERSION)

    def test_growth_past_old_file_gate_keeps_old_and_new_usage(self):
        first, second = event("old"), event("new", 17)
        path = self.write([first])
        with mock.patch.object(readers, "MAX_FILE_BYTES", path.stat().st_size):
            self.assertEqual([normalized(first)], self.collect())
            with path.open("ab") as file:
                file.write(encoded(second) + b"\n")
            self.assertEqual([normalized(first), normalized(second)], self.collect())
            self.assertEqual([normalized(first), normalized(second)], self.collect())

    def test_only_claude_gets_the_large_regular_file_exception(self):
        path = self.write([event()])
        with mock.patch.object(readers, "MAX_FILE_BYTES", 1):
            self.assertFalse(readers._safe_to_parse(str(path), path.stat()))
            self.assertTrue(readers._safe_to_parse(str(path), path.stat(), source="claude"))
            for source in ("gemini", "codex"):
                self.paths[source].append(str(path))
                self.assertFalse(readers._safe_to_parse(str(path), path.stat(), source=source))
            self.assertEqual([], readers.read_all(sources=["gemini", "codex"], use_cache=False))
        for parser in self.other_parsers.values():
            parser.assert_not_called()

    def test_real_file_larger_than_64_mib_retains_both_endpoints(self):
        first, last = event("first"), event("last", 19)
        path = self.write([first])
        # Each physical line is valid JSON surrounded by ordinary whitespace.
        block = (b" " * 4093 + b"{}\n") * 128
        with path.open("ab") as file:
            while file.tell() <= 64 * 1024 * 1024:
                file.write(block)
            file.write(encoded(last) + b"\n")
        self.assertGreater(path.stat().st_size, 64 * 1024 * 1024)
        self.assertEqual([normalized(first), normalized(last)], self.collect(use_cache=False))

    def test_raw_byte_limit_accepts_exact_utf8_crlf_and_unterminated_lines(self):
        # v7: the old byte limit is a buffering threshold, never a rejection gate.
        value = event(cwd="/合成/狐狸")
        for ending in (b"\n", b"\r\n", b""):
            with self.subTest(ending=ending):
                path = self.write([], name="boundary.jsonl")
                raw = b"  " + encoded(value) + b"  " + ending
                path.write_bytes(raw)
                for threshold in (len(raw), len(raw) - 1, 1):
                    with mock.patch.object(readers, "MAX_LINE_BYTES", threshold):
                        self.assertEqual([normalized(value)], readers.claude_parse(str(path)))

    def test_multibyte_line_is_measured_in_bytes_not_characters(self):
        # Crossing the byte threshold, including within UTF-8, must preserve data.
        value = event(cwd="狐" * 100)
        path = self.write([value])
        raw = path.read_bytes()
        with mock.patch.object(readers, "MAX_LINE_BYTES", len(raw.decode("utf-8"))), \
                mock.patch.object(readers, "CLAUDE_READ_CHUNK_BYTES", 7):
            self.assertEqual([normalized(value)], readers.claude_parse(str(path)))

    def test_overlong_line_fails_before_any_tail_fragment_is_parsed(self):
        # Preserve the old anti-tail-fragment guarantee, not its removed length failure.
        first, after = event("head"), event("after")
        path = self.write([first])
        limit = len(encoded(first)) + 1
        fake_tail = encoded(event("must-not-be-parsed"))
        with path.open("ab") as file:
            file.write(b"{bad-json" + b" " * (limit + 20) + fake_tail + b"\n")
            file.write(encoded(after) + b"\n")
        with mock.patch.object(readers, "MAX_LINE_BYTES", limit):
            self.assertEqual([normalized(first), normalized(after)], readers.claude_parse(str(path)))

    def test_streaming_uses_only_bounded_reads_and_closes_the_file(self):
        path = self.write([event("one"), event("two")])
        with self.instrument() as opened:
            self.assertEqual(2, len(readers.claude_parse(str(path))))
        self.assertEqual(1, len(opened), "source must be opened exactly once")
        self.assertEqual(path.stat().st_size, opened[0].bytes_read)
        self.assertTrue(all(method == "read" for method, _ in opened[0].requests))
        self.assertTrue(all(file.closed for file in opened))

    @staticmethod
    def repeat_bytes(file, count, unit=b"x"):
        """Write giant synthetic content without retaining a giant test string."""
        block = unit * max(1, (64 * 1024 // len(unit)))
        while count:
            piece = block[:min(count, len(block))]
            file.write(piece)
            count -= len(piece)

    def append_giant_event(self, file, value, unknown_bytes, position="tail", ending=b"\n",
                           bad_tail=b""):
        fields = [encoded(key) + b":" + encoded(item) for key, item in value.items()]
        before = {"head": 0, "middle": unknown_bytes // 2, "tail": unknown_bytes}[position]
        after = unknown_bytes - before
        file.write(b"{")
        if before:
            file.write(b'"discarded-before":"')
            self.repeat_bytes(file, before)
            file.write(b'",')
        file.write(b",".join(fields))
        if after:
            file.write(b',"discarded-after":"')
            self.repeat_bytes(file, after)
            file.write(b'"')
        file.write(b"}" + bad_tail + ending)

    @contextmanager
    def projection_limits(self, **limits):
        factory = readers._claude_json.ProjectionParser
        with mock.patch.object(readers._claude_json, "ProjectionParser",
                               side_effect=lambda: factory(**limits)):
            yield

    def test_giant_lines_keep_usage_at_head_middle_and_tail(self):
        first, last = event("before"), event("after", 19)
        for position in ("head", "middle", "tail"):
            with self.subTest(position=position):
                value = event("giant-" + position, 23)
                path = self.write([first], name="giant.jsonl")
                with path.open("ab") as file:
                    self.append_giant_event(file, value, 4 * 1024 * 1024 + 17, position)
                    file.write(encoded(last) + b"\n")
                with self.instrument() as opened:
                    self.assertEqual([normalized(first), normalized(value), normalized(last)],
                                     readers.claude_parse(str(path)))
                self.assertEqual(1, len(opened), "giant prefixes must not be reopened")
                self.assertEqual(path.stat().st_size, sum(file.bytes_read for file in opened))
                self.assertTrue(all(file.closed for file in opened))

    def test_single_line_larger_than_64_mib_retains_usage_and_unterminated_tail(self):
        first, value, last = event("before"), event("over-64-mib", 29), event("last", 31)
        path = self.write([first])
        with path.open("ab") as file:
            self.append_giant_event(file, value, 64 * 1024 * 1024 + 1, "tail", ending=b"\r\n")
            file.write(encoded(last))
        self.assertGreater(path.stat().st_size, 64 * 1024 * 1024)
        with self.instrument() as opened:
            self.assertEqual([normalized(first), normalized(value), normalized(last)], self.collect())
        self.assertEqual(1, len(opened))
        self.assertEqual(path.stat().st_size, opened[0].bytes_read)
        with self.instrument() as warm:
            self.assertEqual([normalized(first), normalized(value), normalized(last)], self.collect())
        self.assertEqual(0, sum(file.calls for file in warm))

    def test_unknown_giant_keys_strings_and_float_are_validated_not_retained(self):
        value = event("after-unknown", 13)
        path = self.write([])
        with path.open("wb") as file:
            file.write(b'{"')
            self.repeat_bytes(file, 4 * 1024 * 1024 + 1)
            file.write(b'":true,"huge-float":0.')
            self.repeat_bytes(file, 4 * 1024 * 1024 + 1, b"1")
            file.write(b',"unknown":"')
            self.repeat_bytes(file, 4 * 1024 * 1024 + 1)
            file.write(b'",' + encoded(value)[1:] + b"\n")
        # Selected data is small; unknown key/string/float lengths must not be charged.
        with self.projection_limits(max_projection_bytes=16 * 1024, max_number_bytes=16), \
                self.instrument() as opened:
            self.assertEqual([normalized(value)], readers.claude_parse(str(path)))
        self.assertEqual(path.stat().st_size, opened[0].bytes_read)

    def test_giant_non_assistant_and_unknown_arrays_do_not_drop_next_event(self):
        value = event("after-discarded", 17)
        path = self.write([])
        with path.open("wb") as file:
            file.write(b'{"type":"user","content":"')
            self.repeat_bytes(file, 4 * 1024 * 1024 + 1)
            file.write(b'"}\n{"unknown":[')
            for number in range(8192):
                if number:
                    file.write(b",")
                file.write(b'"' + b"a" * 512 + b'"')
            file.write(b"]}\n" + encoded(value))
        self.assertEqual([normalized(value)], readers.claude_parse(str(path)))

    def test_giant_bad_tail_never_commits_usage_before_full_line_validation(self):
        before, rejected, after = event("before"), event("bad"), event("after", 17)
        path = self.write([before])
        with path.open("ab") as file:
            self.append_giant_event(file, rejected, 4 * 1024 * 1024 + 1,
                                    "head", bad_tail=b"garbage")
            file.write(encoded(after) + b"\n")
        seen = []
        original = readers._claude_event_record
        def observe(value):
            seen.append(value)
            return original(value)
        with mock.patch.object(readers, "_claude_event_record", side_effect=observe):
            self.assertEqual([normalized(before), normalized(after)], readers.claude_parse(str(path)))
        self.assertEqual(["before", "after"], [item["message"]["id"] for item in seen])

    def test_giant_bad_line_is_drained_and_tail_cannot_become_an_event(self):
        before, after = event("before"), event("after", 17)
        path = self.write([before])
        with path.open("ab") as file:
            file.write(b"{bad-json ")
            self.repeat_bytes(file, 4 * 1024 * 1024 + 1)
            file.write(encoded(event("fake-fragment")) + b"\n" + encoded(after) + b"\n")
        with self.instrument() as opened:
            self.assertEqual([normalized(before), normalized(after)], readers.claude_parse(str(path)))
        self.assertEqual(path.stat().st_size, opened[0].bytes_read)

    def test_short_reads_preserve_lf_boundaries_and_initial_remaining(self):
        values = [event("one", cwd="/狐/狸"), event("two", 11)]
        path = self.write(values)
        with self.instrument(max_read=7) as opened:
            self.assertEqual([normalized(value) for value in values], readers.claude_parse(str(path)))
        self.assertEqual(path.stat().st_size, opened[0].bytes_read)
        self.assertEqual(7, max(min(request[1], 7) for request in opened[0].requests))
        self.assertEqual((path.stat().st_size - 1) % 7 + 1, opened[0].requests[-1][1])

    def test_premature_eof_is_incomplete_and_does_not_publish_partial(self):
        path = self.write([event("one"), event("two")])
        with self.instrument(max_read=len(encoded(event("one"))) + 1, eof_after=1) as opened:
            error = self.assert_incomplete(lambda: self.collect())
        self.assertEqual("file_changed", error.reason)
        self.assertFalse(self.cache.exists())
        self.assertTrue(all(file.closed for file in opened))

    def test_io_fault_after_streaming_prefix_is_incomplete_and_closes_once(self):
        value = event("long")
        path = self.write([event("before")])
        with path.open("ab") as file:
            self.append_giant_event(file, value, 4 * 1024 * 1024 + 128 * 1024, "head")
        with self.instrument(fail_after=65) as opened:
            error = self.assert_incomplete(lambda: self.collect())
        self.assertEqual("read_failed", error.reason)
        self.assertEqual(1, len(opened))
        self.assertEqual(65, opened[0].calls)
        self.assertTrue(opened[0].closed)
        self.assertFalse(self.cache.exists())

    def test_projection_limit_reasons_are_controlled_and_not_swallowed_as_bad_json(self):
        cases = (
            ({"max_depth": 1}, b'{"unknown":{"nested":{}}}', "json_depth_limit"),
            ({"max_tokens": 1}, encoded(event()), "json_token_limit"),
            ({"max_projection_bytes": 128}, encoded(event()), "json_projection_limit"),
            ({"max_projection_nodes": 1}, encoded(event()), "json_projection_limit"),
            ({"max_number_bytes": 1}, encoded(event(tokens=12)), "json_number_limit"),
        )
        path = self.write([])
        for limits, raw, reason in cases:
            for threshold in (len(raw) + 1, 1):
                with self.subTest(limits=limits, threshold=threshold):
                    path.write_bytes(raw + b"\n")
                    with self.projection_limits(**limits), \
                            mock.patch.object(readers, "MAX_LINE_BYTES", threshold), \
                            mock.patch.object(readers, "CLAUDE_READ_CHUNK_BYTES", 7):
                        error = self.assert_incomplete(lambda: self.collect())
                    self.assertEqual(reason, error.reason)
                    self.assertFalse(self.cache.exists())

    def test_giant_selected_value_failure_preserves_cache_and_cli_reports(self):
        path = self.write([event("good")])
        self.collect()
        original_cache = self.cache.read_bytes()
        with path.open("ab") as file:
            file.write(b'{"sessionId":"')
            self.repeat_bytes(file, 4 * 1024 * 1024 + 1)
            file.write(b'",' + encoded({key: value for key, value in event("oversized").items()
                                          if key != "sessionId"})[1:] + b"\n")
        report = self.output / "dashboard.html"
        report.write_text("existing-report", encoding="utf-8")
        with self.projection_limits(max_projection_bytes=16 * 1024):
            error = self.assert_incomplete(self.collect)
            self.assertEqual("json_projection_limit", error.reason)
            for argv in (["dashboard"], ["day", "--html"]):
                stderr = io.StringIO()
                with self.subTest(argv=argv), mock.patch("sys.stderr", stderr), \
                        mock.patch.object(cli, "_no_records_message") as no_records, \
                        mock.patch.object(cli.report_dashboard, "write_dashboard") as dashboard, \
                        mock.patch.object(cli.report_html, "write_report") as html:
                    result = cli.main(argv + ["--source", "claude", "--lang", "en"])
                self.assertNotEqual(0, result)
                # The CLI keeps its fixed public wording; no internal reason leaks.
                self.assertIn("Local log collection is incomplete", stderr.getvalue())
                for private in (str(self.root), "synthetic-session", "oversized",
                                "json_projection_limit"):
                    self.assertNotIn(private, stderr.getvalue())
                no_records.assert_not_called()
                dashboard.assert_not_called()
                html.assert_not_called()
        self.assertEqual(original_cache, self.cache.read_bytes())
        self.assertEqual("existing-report", report.read_text(encoding="utf-8"))

    def test_giant_selected_value_live_failure_keeps_snapshot_and_retries_same_signature(self):
        path = self.write([event("good")])
        with path.open("ab") as file:
            file.write(b'{"type":"')
            self.repeat_bytes(file, 4 * 1024 * 1024 + 1)
            file.write(b'",' + encoded({key: value for key, value in event("oversized").items()
                                          if key != "type"})[1:] + b"\n")
        dashboard = live_dashboard.LiveDashboard(["claude"], use_cache=False)
        # First failure must not fabricate a snapshot. Raising the injected budget
        # fixes capacity without changing file/signature and must really retry.
        with self.projection_limits(max_projection_bytes=16 * 1024):
            self.assertFalse(dashboard.refresh())
        failed = dashboard.response()
        self.assertFalse(failed["has_snapshot"])
        self.assertIsNone(failed["snapshot"])
        self.assertIsNone(failed["checked_at"])
        self.assertEqual(live_dashboard._SCAN_FAILED_ERROR, failed["error"])
        self.parse.reset_mock()
        self.assertTrue(dashboard.refresh())
        self.parse.assert_called_once()
        before = dashboard.response()
        with self.projection_limits(max_projection_bytes=16 * 1024):
            self.assertFalse(dashboard.refresh(force=True))
        failed = dashboard.response()
        for key in ("wire", "snapshot", "checked_at"):
            self.assertEqual(before[key], failed[key])
        self.assertTrue(failed["has_snapshot"])
        self.assertEqual(live_dashboard._SCAN_FAILED_ERROR, failed["error"])
        for private in (str(self.root), "synthetic-session", "oversized",
                        "json_projection_limit"):
            self.assertNotIn(private, failed["error"])
        self.parse.reset_mock()
        dashboard.refresh()
        self.parse.assert_called_once()
        self.assertIsNone(dashboard.response()["error"])

    def test_malformed_and_non_usage_events_keep_legacy_tolerance(self):
        value = event()
        path = self.write([])
        path.write_bytes(b'\n{bad json\n[]\nnull\n{"type":"user"}\n' + encoded(value) + b"\n")
        self.assertEqual([normalized(value)], readers.claude_parse(str(path)))

    def test_message_id_is_first_wins(self):
        first, duplicate = event("same", 5), event("same", 900)
        path = self.write([first, duplicate])
        self.assertEqual([normalized(first)], readers.claude_parse(str(path)))

    def test_missing_id_fallback_deduplicates_only_matching_usage(self):
        first, different = event(None, 5), event(None, 6)
        path = self.write([first, first, different])
        self.assertEqual([normalized(first), normalized(different)], readers.claude_parse(str(path)))

    def test_message_ids_are_not_deduplicated_across_files(self):
        self.write([event("same")], "first.jsonl")
        self.write([event("same")], "second.jsonl")
        self.assertEqual(2, len(self.collect(use_cache=False)))

    def test_file_record_limit_counts_unique_items_and_fails_before_the_next(self):
        first, second = event("one"), event("two")
        path = self.write([first] * 20 + [second])
        with mock.patch.object(readers, "MAX_CLAUDE_RECORDS", 2):
            self.assertEqual([normalized(first), normalized(second)], readers.claude_parse(str(path)))
            with path.open("ab") as file:
                file.write(encoded(event("three")) + b"\n")
            self.assert_incomplete(lambda: readers.claude_parse(str(path)))

    def test_file_byte_budget_includes_all_record_fields_and_complete_dedup_key(self):
        for value in (event("标识" * 40, cwd="/狐狸" * 30, sessionId="会话" * 20),
                      event(None, cwd="/狐狸" * 30)):
            with self.subTest(has_id=bool(value["message"]["id"])):
                path = self.write([value], name="budget.jsonl")
                cost = retained_cost(value)
                with mock.patch.object(readers, "MAX_CLAUDE_RETAINED_BYTES", cost):
                    self.assertEqual([normalized(value)], readers.claude_parse(str(path)))
                with mock.patch.object(readers, "MAX_CLAUDE_RETAINED_BYTES", cost - 1):
                    self.assert_incomplete(lambda: readers.claude_parse(str(path)))

    def test_dedup_bytes_are_not_charged_twice_for_duplicates(self):
        value = event("same")
        path = self.write([value] * 30)
        with mock.patch.object(readers, "MAX_CLAUDE_RETAINED_BYTES", retained_cost(value)):
            self.assertEqual([normalized(value)], readers.claude_parse(str(path)))

    def test_zero_file_budgets_allow_empty_but_not_a_retained_record(self):
        path = self.write([{"type": "user"}])
        with mock.patch.object(readers, "MAX_CLAUDE_RECORDS", 0), \
                mock.patch.object(readers, "MAX_CLAUDE_RETAINED_BYTES", 0):
            self.assertEqual([], readers.claude_parse(str(path)))
            path.write_bytes(encoded(event()) + b"\n")
            self.assert_incomplete(lambda: readers.claude_parse(str(path)))

    def test_total_record_limit_is_exact_on_cold_and_warm_paths(self):
        self.write([event("one")], "one.jsonl")
        self.write([event("two")], "two.jsonl")
        for warm in (False, True):
            with self.subTest(warm=warm):
                if warm:
                    self.collect()
                with mock.patch.object(readers, "MAX_TOTAL_RECORDS", 2):
                    self.assertEqual(2, len(self.collect(use_cache=warm)))
                with mock.patch.object(readers, "MAX_TOTAL_RECORDS", 1):
                    self.assert_incomplete(lambda: self.collect(use_cache=warm))

    def test_total_byte_budget_counts_records_but_not_file_dedup_keys(self):
        values = [event("very-long-id" * 40), event("other", cwd="/狐狸")]
        for number, value in enumerate(values):
            self.write([value], name=f"{number}.jsonl")
        cost = sum(len(encoded(normalized(value))) + 512 for value in values)
        self.collect()
        for warm in (False, True):
            with self.subTest(warm=warm):
                with mock.patch.object(readers, "MAX_TOTAL_RETAINED_BYTES", cost):
                    self.assertEqual(2, len(self.collect(use_cache=warm)))
                with mock.patch.object(readers, "MAX_TOTAL_RETAINED_BYTES", cost - 1):
                    self.assert_incomplete(lambda: self.collect(use_cache=warm))

    def test_total_limit_also_counts_other_source_records(self):
        value = event()
        self.write([value])
        path = self.write([], name="other.log", source="gemini")
        self.other_parsers["gemini"].return_value = [dict(normalized(value), source="gemini")]
        self.assertTrue(path.is_file())
        with mock.patch.object(readers, "MAX_TOTAL_RECORDS", 1):
            self.assert_incomplete(lambda: readers.read_all(sources=["claude", "gemini"], use_cache=False))

    def test_warm_cache_cannot_bypass_the_file_record_budget(self):
        self.write([event("one"), event("two")])
        self.assertEqual(2, len(self.collect()))
        with mock.patch.object(readers, "MAX_CLAUDE_RECORDS", 1):
            self.assert_incomplete(self.collect)

    def test_warm_cache_cannot_bypass_complete_dedup_byte_budget(self):
        value = event("long-id" * 100)
        self.write([value])
        self.collect()
        with mock.patch.object(readers, "MAX_CLAUDE_RETAINED_BYTES", retained_cost(value) - 1):
            self.assert_incomplete(self.collect)

    def test_malformed_warm_cache_records_are_a_miss_not_successful_empty_usage(self):
        value = event()
        self.write([value])
        self.collect()
        pristine = json.loads(self.cache.read_bytes())
        for records in ({}, ["not-a-record"], [{"source": "claude"}]):
            with self.subTest(records=records):
                cache = json.loads(encoded(pristine))
                for key, entry in cache.items():
                    if key.startswith("claude::"):
                        entry["records"] = records
                self.cache.write_bytes(encoded(cache))
                with self.instrument() as opened:
                    self.assertEqual([normalized(value)], self.collect())
                self.assertGreater(sum(file.calls for file in opened), 0,
                                   "malformed cached records must trigger a real read")

    def test_cache_hit_is_equivalent_and_does_not_reparse(self):
        self.write([event()])
        cold = self.collect()
        with self.instrument() as opened:
            self.assertEqual(cold, self.collect())
        self.assertEqual(0, sum(file.calls for file in opened),
                         "warm cache may open/fstat the source but must not read it")
        if os.name == "posix":
            self.assertEqual(0o600, stat.S_IMODE(self.cache.stat().st_mode))

    def test_old_cache_version_is_a_miss(self):
        value = event()
        self.write([value])
        self.collect()
        original = json.loads(self.cache.read_bytes())
        for version in (5, 6):
            with self.subTest(version=version):
                cache = dict(original, _v=version)
                for key, entry in original.items():
                    if key.startswith("claude::"):
                        cache[key] = dict(entry, records=[])
                self.cache.write_bytes(encoded(cache))
                with self.instrument() as opened:
                    self.assertEqual([normalized(value)], self.collect())
                self.assertGreater(sum(file.calls for file in opened), 0,
                                   "old cache versions must trigger a real read")

    def test_cache_input_limit_accepts_exact_bytes_and_rejects_the_next_byte(self):
        self.write([event()])
        self.collect()
        size = self.cache.stat().st_size
        with mock.patch.object(readers, "MAX_CACHE_BYTES", size), \
                self.instrument() as opened:
            self.assertEqual(1, len(self.collect()))
        self.assertEqual(0, sum(file.calls for file in opened),
                         "exact-limit warm cache must not read the source")
        with mock.patch.object(readers, "MAX_CACHE_BYTES", size - 1), \
                self.instrument() as opened:
            self.assertEqual(1, len(self.collect()))
        self.assertGreater(sum(file.calls for file in opened), 0,
                           "oversized cache input must trigger a real read")

    def test_oversized_cache_input_is_rejected_before_json_load(self):
        self.cache.parent.mkdir()
        self.cache.write_bytes(b"{" + b" " * 100 + b"}")
        with mock.patch.object(readers, "MAX_CACHE_BYTES", 16), \
                mock.patch.object(readers.json, "load", side_effect=AssertionError("must size-check first")):
            self.assertEqual({}, readers._load_cache())

    def test_corrupt_or_oversized_cache_is_a_miss_not_empty_usage(self):
        value = event()
        self.write([value])
        self.collect()
        original = self.cache.read_bytes()
        for content in (b"{broken", original + b" " * 100):
            with self.subTest(corrupt=content.startswith(b"{broken")):
                self.cache.write_bytes(content)
                with mock.patch.object(readers, "MAX_CACHE_BYTES", len(original)), \
                        self.instrument() as opened:
                    self.assertEqual([normalized(value)], self.collect())
                self.assertGreater(sum(file.calls for file in opened), 0,
                                   "unusable cache must trigger a real read")

    def test_cache_output_over_limit_preserves_old_cache_and_valid_results(self):
        first, second = event("one"), event("two")
        path = self.write([first])
        self.collect()
        old = self.cache.read_bytes()
        with path.open("ab") as file:
            file.write(encoded(second) + b"\n")
        with mock.patch.object(readers, "MAX_CACHE_BYTES", len(old)):
            self.assertEqual([normalized(first), normalized(second)], self.collect())
        self.assertEqual(old, self.cache.read_bytes())

    def test_uncached_collection_never_loads_or_saves_a_cache(self):
        self.write([event()])
        with mock.patch.object(readers, "_load_cache", side_effect=AssertionError("cache read")), \
                mock.patch.object(readers, "_save_cache", side_effect=AssertionError("cache write")):
            self.assertEqual(1, len(self.collect(use_cache=False)))
        self.assertFalse(self.cache.exists())

    def test_failure_after_good_file_does_not_commit_partial_cache_or_empty_entry(self):
        first = self.write([event("one")], name="good.jsonl")
        self.collect()
        old = self.cache.read_bytes()
        bad = self.write([event("two")], name="bad.jsonl")
        with self.deny_open(bad):
            self.assert_incomplete(self.collect)
        self.assertEqual(old, self.cache.read_bytes())
        self.assertEqual(2, len(self.collect()))
        self.assertTrue(first.exists())

    def test_cold_read_failure_does_not_create_success_cache(self):
        path = self.write([event()])
        with self.deny_open(path):
            self.assert_incomplete(self.collect)
        self.assertFalse(self.cache.exists())
        self.assertEqual(1, len(self.collect()))

    def test_direct_parser_rejects_symlink_and_directory(self):
        target = self.write([event()])
        link = self.projects / "link.jsonl"
        link.symlink_to(target)
        for path in (link, self.projects):
            with self.subTest(kind=path.name):
                error = self.assert_incomplete(lambda: readers.claude_parse(str(path)))
                self.assertEqual("unsafe_file", error.reason)

    @unittest.skipUnless(callable(getattr(os, "mkfifo", None)), "requires mkfifo")
    def test_direct_parser_rejects_fifo_without_blocking(self):
        fifo = self.projects / "pipe.jsonl"
        os.mkfifo(fifo)
        real_open, real_os_open = builtins.open, os.open
        def safe_open(candidate, *args, **kwargs):
            if str(candidate) == str(fifo) and kwargs.get("opener") is None:
                raise AssertionError("opening FIFO without a safe opener would block")
            return real_open(candidate, *args, **kwargs)
        def safe_os_open(candidate, flags, *args, **kwargs):
            if str(candidate) == str(fifo):
                self.assertTrue(flags & os.O_NONBLOCK, "FIFO open must not block")
            return real_os_open(candidate, flags, *args, **kwargs)
        with mock.patch("builtins.open", side_effect=safe_open), \
                mock.patch.object(os, "open", side_effect=safe_os_open):
            error = self.assert_incomplete(lambda: readers.claude_parse(str(fifo)))
        self.assertEqual("unsafe_file", error.reason)

    def test_direct_parser_rejects_mock_nonregular_lstat_before_open(self):
        path = self.projects / "synthetic-nonregular.jsonl"
        for mode in (stat.S_IFDIR, stat.S_IFIFO, stat.S_IFLNK):
            with self.subTest(mode=mode), \
                    mock.patch.object(os, "lstat", return_value=mock.Mock(st_mode=mode)), \
                    mock.patch.object(os, "open") as opening, \
                    mock.patch("builtins.open") as builtin_open:
                error = self.assert_incomplete(lambda: readers.claude_parse(str(path)))
                self.assertEqual("unsafe_file", error.reason)
                opening.assert_not_called()
                builtin_open.assert_not_called()

    def test_discovered_unsafe_claude_object_is_failure_not_an_empty_source(self):
        target = self.write([event()])
        link = self.projects / "link.jsonl"
        link.symlink_to(target)
        self.paths["claude"] = [str(link)]
        self.assert_incomplete(lambda: self.collect(use_cache=False))

    def test_discovered_missing_file_is_failure_not_silent_disappearance(self):
        path = self.write([event()])
        path.unlink()
        self.assert_incomplete(lambda: self.collect(use_cache=False))

    def test_claude_enumeration_io_failure_is_not_a_normal_empty_source(self):
        parser = self.parse
        def denied():
            raise PermissionError("synthetic-private-enumeration-detail")
        with mock.patch.dict(readers.SOURCES, {"claude": (denied, parser)}):
            self.assert_incomplete(lambda: self.collect(use_cache=False))
        parser.assert_not_called()

    def test_genuinely_absent_default_directory_remains_an_empty_source(self):
        with mock.patch.object(config, "CLAUDE_PROJECTS", str(self.root / "absent")), \
                mock.patch.dict(readers.SOURCES, {"claude": (readers.claude_files, self.parse)}):
            self.assertEqual([], self.collect(use_cache=False))

    def test_io_failure_mid_read_closes_file_and_does_not_return_partial(self):
        path = self.write([event("one"), event("two")])
        # v7 can read both tiny lines in one block; place the injected I/O fault
        # after the first complete event rather than after an old readline call.
        with mock.patch.object(readers, "CLAUDE_READ_CHUNK_BYTES", len(encoded(event("one"))) + 1), \
                self.instrument(fail_after=1) as opened:
            self.assert_incomplete(lambda: readers.claude_parse(str(path)))
        self.assertTrue(opened)
        self.assertTrue(all(file.closed for file in opened))

    def test_append_is_bounded_to_opening_length_and_retried_next_collection(self):
        first, second = event("one"), event("two")
        path = self.write([first])
        def append():
            with path.open("ab") as file:
                file.write(encoded(second) + b"\n")
        with self.instrument(after_first=append):
            self.assertEqual([normalized(first)], self.collect())
        self.assertEqual([normalized(first), normalized(second)], self.collect())

    def test_truncation_mid_read_is_detected_even_with_buffered_data(self):
        first = event("one")
        path = self.write([first, event("two")])
        def truncate():
            with path.open("r+b") as file:
                file.truncate(len(encoded(first)) + 1)
        with self.instrument(after_first=truncate):
            self.assert_incomplete(lambda: readers.claude_parse(str(path)))

    def test_replacement_mid_read_is_detected_without_publishing_old_inode(self):
        path = self.write([event("one"), event("two")])
        replacement = self.projects / "replacement.tmp"
        replacement.write_bytes(path.read_bytes())
        original_stat = path.stat()
        os.utime(replacement, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
        with self.instrument(after_first=lambda: os.replace(replacement, path)):
            self.assert_incomplete(lambda: readers.claude_parse(str(path)))

    def test_cli_real_reader_failure_is_nonzero_private_and_preserves_reports(self):
        path = self.write([event()])
        report = self.output / "dashboard.html"
        report.write_text("existing-report", encoding="utf-8")
        for argv in (["dashboard"], ["day", "--html"]):
            with self.subTest(argv=argv):
                stderr = io.StringIO()
                with self.deny_open(path), mock.patch("sys.stderr", stderr), \
                        mock.patch.object(cli, "_no_records_message") as no_records, \
                        mock.patch.object(cli.report_dashboard, "write_dashboard") as dashboard, \
                        mock.patch.object(cli.report_html, "write_report") as html:
                    result = cli.main(argv + ["--source", "claude", "--lang", "en"])
                self.assertIsInstance(result, int)
                self.assertNotEqual(0, result)
                self.assertTrue(stderr.getvalue().strip())
                for private in (str(self.root), "synthetic-private", "synthetic-session"):
                    self.assertNotIn(private, stderr.getvalue())
                self.assertNotIn("No supported token logs", stderr.getvalue())
                no_records.assert_not_called()
                dashboard.assert_not_called()
                html.assert_not_called()
                self.assertEqual("existing-report", report.read_text(encoding="utf-8"))

    def test_live_first_real_read_failure_keeps_no_snapshot_then_recovers(self):
        path = self.write([event()])
        dashboard = live_dashboard.LiveDashboard(["claude"], use_cache=False)
        with self.deny_open(path):
            self.assertFalse(dashboard.refresh())
        failed = dashboard.response()
        self.assertFalse(failed["has_snapshot"])
        self.assertIsNone(failed["snapshot"])
        self.assertIsNone(failed["checked_at"])
        self.assertTrue(failed["error"])
        self.assertNotIn(str(self.root), json.dumps(failed))
        self.assertTrue(dashboard.refresh())
        self.assertTrue(dashboard.response()["has_snapshot"])
        self.assertIsNone(dashboard.response()["error"])

    def test_live_same_success_signature_must_retry_real_reader_after_failure(self):
        path = self.write([event()])
        dashboard = live_dashboard.LiveDashboard(["claude"], use_cache=False)
        self.assertTrue(dashboard.refresh())
        before = dashboard.response()
        with self.deny_open(path):
            self.assertFalse(dashboard.refresh(force=True))
        failed = dashboard.response()
        for key in ("wire", "snapshot", "checked_at"):
            self.assertEqual(before[key], failed[key])
        self.assertTrue(failed["has_snapshot"])
        self.assertTrue(failed["error"])
        self.assertNotIn(str(self.root), json.dumps(failed))
        self.parse.reset_mock()
        dashboard.refresh()
        self.parse.assert_called_once()
        self.assertIsNone(dashboard.response()["error"])

    def test_live_growth_beyond_old_gate_changes_signature_and_publishes_usage(self):
        path = self.write([event("one")])
        dashboard = live_dashboard.LiveDashboard(["claude"], use_cache=False)
        with mock.patch.object(readers, "MAX_FILE_BYTES", path.stat().st_size):
            self.assertTrue(dashboard.refresh())
            before = dashboard.response()["snapshot"]
            with path.open("ab") as file:
                file.write(encoded(event("two", 20)) + b"\n")
            self.assertTrue(dashboard.refresh())
            self.assertNotEqual(before, dashboard.response()["snapshot"])
        self.assertIsNone(dashboard.response()["error"])

    def test_live_new_unsafe_object_cannot_hide_behind_unchanged_signature(self):
        path = self.write([event()])
        dashboard = live_dashboard.LiveDashboard(["claude"], use_cache=False)
        self.assertTrue(dashboard.refresh())
        before = dashboard.response()
        link = self.projects / "new-link.jsonl"
        link.symlink_to(path)
        self.paths["claude"].append(str(link))
        self.assertFalse(dashboard.refresh())
        failed = dashboard.response()
        self.assertTrue(failed["error"])
        for key in ("wire", "snapshot", "checked_at"):
            self.assertEqual(before[key], failed[key])
        self.paths["claude"].remove(str(link))
        self.parse.reset_mock()
        dashboard.refresh()
        self.parse.assert_called_once()
        self.assertIsNone(dashboard.response()["error"])

    @contextmanager
    def synthetic_home(self):
        with mock.patch.object(config, "HOME", str(self.root)), \
                mock.patch.dict(os.environ, {"HOME": str(self.root)}):
            yield

    @contextmanager
    def controlled_ctime(self, path, version):
        """Give lstat/fstat one consistent synthetic version, without sleeps."""
        real_lstat, real_fstat = os.lstat, os.fstat
        identity = path.stat()

        class StatVersion:
            def __init__(self, actual):
                self.actual = actual
                self.st_ctime_ns = version["ctime_ns"]
                self.st_ctime = self.st_ctime_ns / 1_000_000_000

            def __getattr__(self, name):
                return getattr(self.actual, name)

        def lstat(candidate, *args, **kwargs):
            actual = real_lstat(candidate, *args, **kwargs)
            return StatVersion(actual) if str(candidate) == str(path) else actual

        def fstat(fd):
            actual = real_fstat(fd)
            if (actual.st_dev, actual.st_ino) == (identity.st_dev, identity.st_ino):
                return StatVersion(actual)
            return actual

        with mock.patch.object(os, "lstat", side_effect=lstat), \
                mock.patch.object(os, "fstat", side_effect=fstat):
            yield

    def test_discovery_follows_directory_symlink_to_legal_jsonl(self):
        external = self.root / "external-project"
        external.mkdir()
        value = event("through-directory-link")
        (external / "session.jsonl").write_bytes(encoded(value) + b"\n")
        link = self.projects / "linked-project"
        link.symlink_to(external, target_is_directory=True)
        visible = str(link / "session.jsonl")
        with self.synthetic_home(), mock.patch.dict(readers.SOURCES, {
                "claude": (readers.claude_files, readers.claude_parse)}):
            self.assertIn(visible, readers.claude_files())
            self.assertEqual([normalized(value)],
                             readers.read_all(sources=["claude"], use_cache=False))

    def test_discovery_ancestor_directory_cycle_reports_controlled_failure(self):
        child = self.projects / "child"
        child.mkdir()
        (child / "back-to-root").symlink_to(self.projects, target_is_directory=True)
        with self.synthetic_home(), mock.patch.dict(readers.SOURCES, {
                "claude": (readers.claude_files, readers.claude_parse)}):
            error = self.assert_incomplete(
                lambda: readers.read_all(sources=["claude"], use_cache=False))
        self.assertEqual("claude", error.source)
        self.assertEqual("discovery_failed", error.reason)
        self.assertFalse(self.cache.exists())

    def assert_discovered_nonregular_is_rejected(self, kind):
        path = self.projects / (kind + ".jsonl")
        if kind == "directory":
            path.mkdir()
        elif kind == "fifo":
            os.mkfifo(path)
        else:
            target = self.root / "synthetic-target.jsonl"
            target.write_bytes(encoded(event()) + b"\n")
            path.symlink_to(target)
        real_open = os.open

        def nonblocking_open(candidate, flags, *args, **kwargs):
            if kind == "fifo" and str(candidate) == str(path):
                self.assertTrue(flags & os.O_NONBLOCK,
                                "a rejected FIFO must never be opened blocking")
            return real_open(candidate, flags, *args, **kwargs)

        with self.synthetic_home(), mock.patch.dict(readers.SOURCES, {
                "claude": (readers.claude_files, readers.claude_parse)}), \
                mock.patch.object(os, "open", side_effect=nonblocking_open):
            self.assertIn(str(path), readers.claude_files())
            error = self.assert_incomplete(
                lambda: readers.read_all(sources=["claude"], use_cache=False))
        self.assertEqual("claude", error.source)
        self.assertEqual("unsafe_file", error.reason)
        self.assertFalse(self.cache.exists())

    def test_discovery_does_not_drop_jsonl_named_directory(self):
        self.assert_discovered_nonregular_is_rejected("directory")

    @unittest.skipUnless(callable(getattr(os, "mkfifo", None)), "requires mkfifo")
    def test_discovery_does_not_drop_jsonl_named_fifo(self):
        self.assert_discovered_nonregular_is_rejected("fifo")

    def test_discovery_does_not_drop_jsonl_named_file_symlink(self):
        self.assert_discovered_nonregular_is_rejected("symlink")

    def test_live_ctime_only_change_really_reads_and_publishes_same_length_edit(self):
        first, changed = event("same-id", 7), event("same-id", 8)
        path = self.write([first])
        initial = path.stat()
        replacement = encoded(changed) + b"\n"
        self.assertEqual(initial.st_size, len(replacement))
        version = {"ctime_ns": initial.st_ctime_ns}
        with self.synthetic_home(), self.controlled_ctime(path, version):
            dashboard = live_dashboard.LiveDashboard(["claude"], use_cache=False)
            self.assertTrue(dashboard.refresh())
            before = dashboard.response()
            path.write_bytes(replacement)
            os.utime(path, ns=(initial.st_atime_ns, initial.st_mtime_ns))
            version["ctime_ns"] += 1
            self.assertEqual(initial.st_size, path.stat().st_size)
            self.assertEqual(initial.st_mtime_ns, path.stat().st_mtime_ns)
            self.parse.reset_mock()
            with self.instrument() as opened:
                self.assertTrue(dashboard.refresh())
            self.parse.assert_called_once()
            self.assertGreater(sum(file.calls for file in opened), 0,
                               "ctime-only change must not take unchanged shortcut")
            after = dashboard.response()
        self.assertTrue(after["has_snapshot"])
        self.assertIsNone(after["error"])
        self.assertNotEqual(before["snapshot"], after["snapshot"])
        self.assertNotEqual(before["wire"], after["wire"])

    def test_same_size_mtime_but_changed_ctime_mid_read_is_incomplete(self):
        first, second = event("one", 7), event("two", 7)
        path = self.write([first, second])
        initial = path.stat()
        replacement = encoded(first) + b"\n" + encoded(event("two", 8)) + b"\n"
        self.assertEqual(initial.st_size, len(replacement))
        version = {"ctime_ns": initial.st_ctime_ns}

        def edit_without_size_or_mtime_change():
            path.write_bytes(replacement)
            os.utime(path, ns=(initial.st_atime_ns, initial.st_mtime_ns))
            version["ctime_ns"] += 1

        with self.synthetic_home(), self.controlled_ctime(path, version), \
                self.instrument(after_first=edit_without_size_or_mtime_change) as opened:
            error = self.assert_incomplete(lambda: readers.claude_parse(str(path)))
        self.assertEqual("claude", error.source)
        self.assertEqual("file_changed", error.reason)
        self.assertEqual(initial.st_size, path.stat().st_size)
        self.assertEqual(initial.st_mtime_ns, path.stat().st_mtime_ns)
        self.assertTrue(opened)
        self.assertTrue(all(file.closed for file in opened))


_STAT_PROBE_PREFIX = "TOKENS_WINDOWS_STAT_PROBE="
_STAT_PROBE_LIMIT = 8 * 1024


def _stat_probe_line(report):
    """Keep diagnostics extractable even if an unusual runtime adds large values."""
    bounded = dict(report, phases=list(report.get("phases", ())))
    omitted = 0
    while True:
        line = _STAT_PROBE_PREFIX + json.dumps(
            bounded, ensure_ascii=True, separators=(",", ":"), allow_nan=False)
        if len(line.encode("utf-8")) + 1 <= _STAT_PROBE_LIMIT:
            return line
        if bounded["phases"]:
            bounded["phases"].pop()
            omitted += 1
            bounded["omitted_phases"] = omitted
        else:
            return _STAT_PROBE_PREFIX + '{"status":"size_limited"}'


class StatProbeOutputTests(unittest.TestCase):
    def test_probe_line_preserves_small_report_as_one_prefixed_json_line(self):
        report = {"runtime": {"python": [3, 13], "platform": "win32"},
                  "phases": [{"name": "original", "status": "ok"}]}
        line = _stat_probe_line(report)
        self.assertTrue(line.startswith(_STAT_PROBE_PREFIX))
        self.assertEqual(report, json.loads(line[len(_STAT_PROBE_PREFIX):]))
        self.assertNotIn("\n", line)
        self.assertLessEqual(len(line.encode("utf-8")), _STAT_PROBE_LIMIT)

    def test_probe_line_bounds_oversized_diagnostics_without_mutating_report(self):
        report = {"phases": [{"name": "synthetic", "value": "x" * 16384}]}
        line = _stat_probe_line(report)
        self.assertLessEqual(len(line.encode("utf-8")), _STAT_PROBE_LIMIT)
        self.assertEqual({"phases": [], "omitted_phases": 1},
                         json.loads(line[len(_STAT_PROBE_PREFIX):]))
        self.assertEqual(1, len(report["phases"]))
        oversized_header = _stat_probe_line({"synthetic": "x" * 16384})
        self.assertEqual({"status": "size_limited"},
                         json.loads(oversized_header[len(_STAT_PROBE_PREFIX):]))


class WindowsStatDiagnosticTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform == "win32", "Windows-only raw stat diagnostic")
    def test_raw_stat_diagnostic(self):
        # No SafeReader, business config, or LargeClaudeLogsTests fixture is used.
        # v rows follow apis/fields; t indexes shared type rows. diff contains
        # differing field names for each pair named in diff_pairs.
        fields = ["mode", "dev", "ino", "size", "mtime_ns", "ctime_ns"]
        report = {
            "runtime": {"python": list(sys.version_info[:2]), "platform": sys.platform,
                        "fchmod": callable(getattr(os, "fchmod", None)),
                        "mkfifo": callable(getattr(os, "mkfifo", None))},
            "fields": fields, "apis": ["stat", "lstat", "fstat"], "types": [],
            "diff_pairs": ["stat:lstat", "stat:fstat", "lstat:fstat"], "phases": [],
        }

        def capture(name, path, fd):
            phase = {"name": name, "samples": []}
            report["phases"].append(phase)
            try:
                for _ in range(2):
                    snapshots = [os.stat(path), os.lstat(path), os.fstat(fd)]
                    values, types = [], []
                    for snapshot in snapshots:
                        row = [getattr(snapshot, "st_" + field, None) for field in fields]
                        type_row = [type(value).__name__ for value in row]
                        if type_row not in report["types"]:
                            report["types"].append(type_row)
                        values.append(row)
                        types.append(report["types"].index(type_row))
                    phase["samples"].append({
                        "v": values, "t": types,
                        "diff": [[field for i, field in enumerate(fields)
                                  if values[left][i] != values[right][i]
                                  or type(values[left][i]) is not type(values[right][i])]
                                 for left, right in ((0, 1), (0, 2), (1, 2))],
                    })
                phase["status"] = "ok"
            except OSError:
                phase["status"] = "os_error"

        def mutate(name, path, file, operation):
            try:
                operation()
                file.flush()
            except OSError:
                report["phases"].append({"name": name, "status": "os_error"})
            else:
                capture(name, path, file.fileno())

        try:
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "synthetic.bin"
                path.write_bytes(b"abcdefgh")
                if hasattr(os.stat(path), "st_birthtime_ns"):
                    fields.append("birthtime_ns")
                with path.open("r+b") as file:
                    capture("original", path, file.fileno())

                    def append():
                        file.seek(0, os.SEEK_END)
                        file.write(b"ijkl")

                    mutate("append", path, file, append)
                    mutate("truncate", path, file, lambda: file.truncate(4))

                    def rewrite():
                        before = os.stat(path)
                        file.seek(0)
                        file.write(b"wxyz")
                        file.flush()
                        os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))

                    mutate("same_length_rewrite_restore_mtime", path, file, rewrite)
                # Replacement is an independent stage: Windows may deny replacing
                # an open file, which must not suppress the mutation observations.
                try:
                    original = Path(tmp) / "replacement-target.bin"
                    replacement = Path(tmp) / "replacement-source.bin"
                    original.write_bytes(b"abcd")
                    replacement.write_bytes(b"wxyz")
                    with original.open("rb") as file:
                        capture("replacement_before", original, file.fileno())
                        try:
                            os.replace(replacement, original)
                        except OSError:
                            report["phases"].append({"name": "replacement", "status": "os_error"})
                        else:
                            capture("replacement_after_old_fd", original, file.fileno())
                except OSError:
                    report["phases"].append({"name": "replacement_setup", "status": "os_error"})
        except OSError:
            report["status"] = "os_error"
        print(_stat_probe_line(report), flush=True)


if __name__ == "__main__":
    unittest.main()
