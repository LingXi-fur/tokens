"""Synthetic-only collection/cache integrity regressions.

Authoring does not run these tests.  All source, HOME, router, sidecar, cache,
output and title-discovery paths below belong to one TemporaryDirectory.  The
real parsers/read_all/CLI/dashboard/title-index implementations remain in use;
only source finders and explicitly injected boundary failures are substituted.
No helpers from test_large_claude_logs are imported: the authoring worktree may
have an older HEAD than the checkout against which this candidate is validated.
"""
import builtins
from contextlib import ExitStack, contextmanager
from copy import deepcopy
from datetime import timezone
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# Avoid host timezone-file probing when this test is imported on its own.
with mock.patch.dict(os.environ, {"TOKENS_TIMEZONE": "UTC", "TZ": "UTC"}):
    from tokens_cli import cli, config, dashboard_wire, readers, report_dashboard


SOURCES = ("claude", "gemini", "codex")
TOKEN_FIELDS = ("input", "output", "cache_read", "cache_write", "total")
STAMP = "2026-10-20T10:00:00Z"
TITLE = "Explain synthetic cache validation"
_UNSET = object()
_DELETE = object()


def encoded(value, *, allow_nan=False):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"),
                      allow_nan=allow_nan).encode("utf-8")


def replace_nested(record, path, value):
    container = record
    for name in path[:-1]:
        container = container[name]
    if value is _DELETE:
        del container[path[-1]]
    else:
        container[path[-1]] = deepcopy(value)


class _SourceReader:
    """Count actual source reads, not opens/stat/fstat or cache/HTML reads."""

    def __init__(self, file, note_read):
        self.file = file
        self.note_read = note_read

    def __getattr__(self, name):
        return getattr(self.file, name)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return self.file.__exit__(*args)

    def __iter__(self):
        return self

    def __next__(self):
        self.note_read()
        return next(self.file)

    def read(self, *args, **kwargs):
        self.note_read()
        return self.file.read(*args, **kwargs)

    def readline(self, *args, **kwargs):
        self.note_read()
        return self.file.readline(*args, **kwargs)

    def readlines(self, *args, **kwargs):
        self.note_read()
        return self.file.readlines(*args, **kwargs)

    def readinto(self, *args, **kwargs):
        self.note_read()
        return self.file.readinto(*args, **kwargs)

    def read1(self, *args, **kwargs):
        self.note_read()
        return self.file.read1(*args, **kwargs)

    def readinto1(self, *args, **kwargs):
        self.note_read()
        return self.file.readinto1(*args, **kwargs)


class CollectionIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.home = self.root / "home"
        self.projects = self.home / ".claude" / "projects"
        self.gemini = self.home / ".gemini" / "tmp"
        self.codex = self.home / ".codex" / "sessions"
        self.output = self.root / "output"
        self.cache = self.root / "cache" / "records-v7.json"
        for directory in (self.projects, self.gemini, self.codex, self.output):
            directory.mkdir(parents=True)
        self.paths = {source: [] for source in SOURCES}
        self.parsers = {"claude": readers.claude_parse,
                        "gemini": readers.gemini_parse,
                        "codex": readers.codex_parse}
        finders = {
            source: (lambda source=source: list(self.paths[source]), self.parsers[source])
            for source in SOURCES
        }
        patches = [
            mock.patch.object(config, "HOME", str(self.home)),
            mock.patch.object(config, "CLAUDE_PROJECTS", str(self.projects)),
            mock.patch.object(config, "GEMINI_TMP", str(self.gemini)),
            mock.patch.object(config, "CODEX_SESSIONS", str(self.codex)),
            mock.patch.object(config, "CACHE_DIR", str(self.cache.parent)),
            mock.patch.object(config, "CACHE_FILE", str(self.cache)),
            mock.patch.object(config, "OUT_DIR", str(self.output)),
            mock.patch.object(config, "SESSION_SUMMARY_FILE",
                              str(self.root / "absent-synthetic-sidecar.json")),
            mock.patch.object(config, "CCR_ROUTER_FILE",
                              str(self.home / "absent-synthetic-router.js")),
            mock.patch.object(config, "TZ", timezone.utc),
            mock.patch.object(readers, "_ccr_rules_cache", ("", [])),
            mock.patch.dict(readers.SOURCES, finders, clear=True),
            mock.patch.dict(os.environ, {
                "HOME": str(self.home), "TZ": "UTC", "TOKENS_TIMEZONE": "UTC",
                "TOKENS_LANG": "en", "XDG_CACHE_HOME": str(self.cache.parent),
                "LOCALAPPDATA": str(self.root / "local-app-data"),
            }),
            # Collection uses only the fixed synthetic finders.  Title lookups
            # must receive the real index, never fall back to broad globbing.
            mock.patch.object(readers.glob, "glob", side_effect=AssertionError(
                "unexpected file discovery outside the synthetic finders")),
        ]
        for patcher in patches:
            self.stack.enter_context(patcher)
        # Deliberately do NOT patch build_session_index, session_title,
        # load_session_summaries, read_all, billing_view or dashboard builders.
        for source in SOURCES:
            self.write_source(source)

    def write_source(self, source, *, input_value=_UNSET, cache_value=_UNSET):
        """Write two genuine source events, including complete billing evidence."""
        if source == "claude":
            path = self.projects / "synthetic-claude-session.jsonl"
            events = [{"type": "user", "message": {"content": [
                {"type": "text", "text": TITLE}]}}]
            for index, amount in enumerate((7, 19)):
                usage = {"input_tokens": amount, "output_tokens": 3,
                         "cache_read_input_tokens": 2,
                         "cache_creation_input_tokens": 1}
                if index == 0:
                    if input_value is not _UNSET:
                        usage["input_tokens"] = input_value
                    if cache_value is not _UNSET:
                        usage["cache_read_input_tokens"] = cache_value
                events.append({
                    "type": "assistant", "timestamp": STAMP,
                    "sessionId": "synthetic-claude-session", "cwd": "/synthetic/project",
                    "message": {"id": f"synthetic-message-{index}",
                                "model": "synthetic-claude-backend", "usage": usage},
                })
            raw = b"".join(encoded(event) + b"\n" for event in events)
        elif source == "gemini":
            path = self.gemini / "synthetic-project" / "chats" / "session-synthetic.json"
            messages = []
            for index, amount in enumerate((11, 23)):
                tokens = {"input": amount, "output": 4, "cached": 2,
                          "thoughts": 1, "tool": 0, "total": amount + 7}
                if index == 0:
                    if input_value is not _UNSET:
                        tokens["input"] = input_value
                    if cache_value is not _UNSET:
                        tokens["cached"] = cache_value
                messages.append({"type": "gemini", "timestamp": STAMP,
                                 "model": "synthetic-gemini-model", "tokens": tokens})
            raw = encoded({"sessionId": "synthetic-gemini-session", "messages": messages})
        else:
            self.assertEqual("codex", source)
            path = self.codex / "rollout-synthetic.jsonl"
            events = [{"type": "event_msg", "timestamp": STAMP,
                       "payload": {"type": "turn_context", "model": "synthetic-codex-model"}}]
            for index, amount in enumerate((17, 29)):
                usage = {"input_tokens": amount, "cached_input_tokens": 3,
                         "output_tokens": 6, "reasoning_output_tokens": 2,
                         "total_tokens": amount + 6}
                if index == 0:
                    if input_value is not _UNSET:
                        usage["input_tokens"] = input_value
                    if cache_value is not _UNSET:
                        usage["cached_input_tokens"] = cache_value
                events.append({"type": "event_msg", "timestamp": STAMP,
                               "payload": {"type": "token_count", "info": {
                                   "last_token_usage": usage}}})
            raw = b"".join(encoded(event) + b"\n" for event in events)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        if str(path) not in self.paths[source]:
            self.paths[source].append(str(path))
        return path

    def collect(self, sources=SOURCES, *, use_cache=True):
        return readers.read_all(sources=list(sources), use_cache=use_cache)

    def cache_data(self):
        # This is a small JSON fixture generated by the real cache writer.
        return json.loads(self.cache.read_bytes())

    def prime(self, sources=SOURCES):
        cold = self.collect(sources, use_cache=False)
        self.assertEqual(2 * len(sources), len(cold))
        self.assertEqual(cold, self.collect(sources))
        pristine = self.cache_data()
        self.assertEqual(7, pristine["_v"])
        for source in sources:
            record = pristine[self.entry_key(source)]["records"][0]
            self.assertEqual({"v", "present", "raw", "parts", "uncertain", "reasons"},
                             set(record["billing"]))
        return cold, pristine

    def entry_key(self, source):
        return source + "::" + self.paths[source][0]

    def corrupt(self, pristine, source, path, value):
        bad = deepcopy(pristine)
        replace_nested(bad[self.entry_key(source)]["records"][0], path, value)
        # NaN/Infinity are deliberately injected only into corrupt cache bytes,
        # never generated as a legal source fixture or by the real writer.
        raw = encoded(bad, allow_nan=True)
        self.cache.write_bytes(raw)
        return raw

    @contextmanager
    def source_reads(self, *, fail_source=None):
        real_open, real_io_open = builtins.open, io.open
        real_fdopen, real_fstat, real_read = os.fdopen, os.fstat, os.read
        counts = {source: 0 for source in SOURCES}
        path_sources = {path: source for source in SOURCES for path in self.paths[source]}
        identities = {}
        for path, source in path_sources.items():
            info = os.stat(path)
            identities[(info.st_dev, info.st_ino)] = source

        def source_for_fd(fd):
            info = real_fstat(fd)
            return identities.get((info.st_dev, info.st_ino))

        def note(source):
            counts[source] += 1
            if source == fail_source:
                raise OSError("synthetic-private-source-read-detail")

        def wrap(file, source, mode):
            if source is None or ("r" not in mode and "+" not in mode):
                return file
            return _SourceReader(file, lambda: note(source))

        def opening(original):
            def call(path, mode="r", *args, **kwargs):
                file = original(path, mode, *args, **kwargs)
                source = source_for_fd(path) if isinstance(path, int) else path_sources.get(str(path))
                return wrap(file, source, mode)
            return call

        def fdopen(fd, mode="r", *args, **kwargs):
            source = source_for_fd(fd)
            return wrap(real_fdopen(fd, mode, *args, **kwargs), source, mode)

        def read(fd, size):
            source = source_for_fd(fd)
            if source is not None:
                note(source)
            return real_read(fd, size)

        with mock.patch("builtins.open", side_effect=opening(real_open)), \
                mock.patch.object(io, "open", side_effect=opening(real_io_open)), \
                mock.patch.object(os, "fdopen", side_effect=fdopen), \
                mock.patch.object(os, "read", side_effect=read):
            yield counts

    def assert_recovered(self, cold, pristine, source, path, value):
        self.corrupt(pristine, source, path, value)
        with self.source_reads() as counts:
            actual = self.collect()
        self.assertGreater(counts[source], 0,
                           "bad cache must trigger actual reads of the affected source")
        self.assertEqual(cold, actual)
        # Complete cache equality catches discarded sibling records, partial
        # repaired entries, stale malformed billing and loss of other sources.
        self.assertEqual(pristine, self.cache_data())
        with self.source_reads() as warm_counts:
            self.assertEqual(cold, self.collect())
        self.assertEqual(dict.fromkeys(SOURCES, 0), warm_counts)

    def dashboard_payload_from_output(self):
        html = (self.output / "dashboard.html").read_text(encoding="utf-8")
        marker = "const WIRE = "
        self.assertIn(marker, html)
        wire, _ = json.JSONDecoder().raw_decode(html.split(marker, 1)[1])
        return dashboard_wire.decode_payload(wire)

    def run_dashboard(self, sources):
        argv = ["dashboard", "--lang", "en"]
        for source in sources:
            argv.extend(("--source", source))
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch("sys.stdout", stdout), mock.patch("sys.stderr", stderr):
            status = cli.main(argv)
        self.assertEqual(0, status)
        self.assertEqual("", stderr.getvalue(), "successful recovery must not leak private diagnostics")
        self.assertIn("Dashboard:", stdout.getvalue())
        return self.dashboard_payload_from_output()

    def make_directory_cycle(self):
        child = self.projects / "synthetic-cycle"
        child.mkdir()
        (child / "back-to-projects").symlink_to(self.projects, target_is_directory=True)

    def test_three_source_cold_and_warm_results_match_without_warm_source_reads(self):
        with self.source_reads() as cold_counts:
            cold = self.collect()
        self.assertEqual(6, len(cold))
        self.assertEqual(set(SOURCES), {record["source"] for record in cold})
        self.assertTrue(all(cold_counts[source] > 0 for source in SOURCES))
        self.assertEqual(7, self.cache_data()["_v"])
        with self.source_reads() as warm_counts:
            warm = self.collect()
        self.assertEqual(cold, warm)
        self.assertEqual(dict.fromkeys(SOURCES, 0), warm_counts,
                         "safe source open/fstat is allowed; reading source content is not")

    def test_cold_numeric_compatibility_values_are_preserved_on_warm_reads(self):
        # These are existing normalization behavior, not new billing rules:
        # bool, finite float and negative tokens survive cold parsing but carry
        # uncertain billing evidence.  Do not silently coerce or reject them.
        for source in SOURCES:
            for field, argument in (("input", "input_value"), ("cache_read", "cache_value")):
                for value in (True, False, 2.5, -3):
                    with self.subTest(source=source, field=field, value=value):
                        if self.cache.exists():
                            self.cache.unlink()
                        self.write_source(source, **{argument: value})
                        cold, _ = self.prime((source,))
                        self.assertIs(type(value), type(cold[0][field]))
                        self.assertEqual(value, cold[0][field])
                        self.assertTrue(cold[0]["billing"]["uncertain"])
                        with self.source_reads() as counts:
                            warm = self.collect((source,))
                        self.assertEqual(encoded(cold), encoded(warm))
                        self.assertIs(type(value), type(warm[0][field]))
                        self.assertEqual(0, counts[source])

    def test_cold_nullable_gemini_and_codex_values_are_preserved_on_warm_reads(self):
        # Nonzero explicit reported totals avoid the legacy fallback addition;
        # input/cache_read can then legitimately remain None in these parsers.
        for source in ("gemini", "codex"):
            for field, argument in (("input", "input_value"), ("cache_read", "cache_value")):
                with self.subTest(source=source, field=field):
                    if self.cache.exists():
                        self.cache.unlink()
                    self.write_source(source, **{argument: None})
                    cold, _ = self.prime((source,))
                    self.assertIsNone(cold[0][field])
                    self.assertTrue(cold[0]["billing"]["uncertain"])
                    self.assertEqual([0] * 5, cold[0]["billing"]["parts"])
                    with self.source_reads() as counts:
                        warm = self.collect((source,))
                    self.assertEqual(encoded(cold), encoded(warm))
                    self.assertIsNone(warm[0][field])
                    self.assertEqual(0, counts[source])

    def test_invalid_cached_token_types_and_nonfinite_values_force_real_recollection(self):
        cold, pristine = self.prime()
        invalid = ({}, [], [1], "synthetic-private-token", float("nan"),
                   float("inf"), float("-inf"))
        for source in SOURCES:
            for field in TOKEN_FIELDS:
                values = list(invalid)
                # Nullable input/cache_read from the other two cold parsers are
                # covered above, rather than incorrectly declared corrupt here.
                if source == "claude" or field not in ("input", "cache_read"):
                    values.append(None)
                for value in values:
                    with self.subTest(source=source, field=field, value=repr(value)):
                        self.assert_recovered(cold, pristine, source, (field,), value)

    def test_missing_record_fields_and_bad_string_fields_force_real_recollection(self):
        cold, pristine = self.prime()
        for source in SOURCES:
            original = pristine[self.entry_key(source)]["records"][0]
            cases = [((field,), _DELETE) for field in original]
            cases.extend(((field,), value) for field in ("ts", "date", "model")
                         for value in (None, [], {}, 42))
            cases.extend([(("unexpected_cache_field",), 1),
                          (("source",), "not-the-selected-source")])
            for path, value in cases:
                with self.subTest(source=source, path=path, value=repr(value)):
                    self.assert_recovered(cold, pristine, source, path, value)

    def test_missing_billing_schema_fields_and_billing_containers_force_recollection(self):
        cold, pristine = self.prime()
        cases = [(("billing",), value) for value in ({}, [], "billing", None)]
        cases.extend((("billing", field), _DELETE)
                     for field in ("v", "present", "raw", "parts", "uncertain", "reasons"))
        for source in SOURCES:
            for path, value in cases:
                with self.subTest(source=source, path=path, value=repr(value)):
                    self.assert_recovered(cold, pristine, source, path, value)

    def test_invalid_billing_version_and_parts_force_real_recollection(self):
        cold, pristine = self.prime()
        cases = [(("billing", "v"), value)
                 for value in (True, False, 0, 2, 1.0, "1", None, [], {})]
        cases.extend((("billing", "parts"), value)
                     for value in ({}, "0,0,0,0,0", None, [], [0] * 4, [0] * 6))
        for value in (True, 1.0, -1, "1", None, {}, [], float("nan"),
                      float("inf"), float("-inf"), 2 ** 53):
            parts = [0] * 5
            parts[0] = value
            cases.append((("billing", "parts"), parts))
        for source in SOURCES:
            for path, value in cases:
                with self.subTest(source=source, path=path, value=repr(value)):
                    self.assert_recovered(cold, pristine, source, path, value)

    def test_invalid_billing_uncertain_and_reasons_force_real_recollection(self):
        cold, pristine = self.prime()
        cases = [(("billing", "uncertain"), value)
                 for value in (0, 1, "false", None, [], {})]
        cases.extend((("billing", "reasons"), value)
                     for value in ({}, "invalid_input", None, 0, [None], [1],
                                   [True], [{}], [[]]))
        for source in SOURCES:
            for path, value in cases:
                with self.subTest(source=source, path=path, value=repr(value)):
                    self.assert_recovered(cold, pristine, source, path, value)

    def test_invalid_billing_presence_and_raw_evidence_force_real_recollection(self):
        cold, pristine = self.prime()
        cases = [(("billing", field), value)
                 for field in ("present", "raw") for value in (None, [], "evidence")]
        cases.extend([(("billing", "present", "input"), _DELETE),
                      (("billing", "raw", "input"), _DELETE)])
        cases.extend((("billing", "present", "input"), value)
                     for value in (0, 1, "true", None, [], {}))
        cases.extend((("billing", "raw", "input"), value)
                     for value in (True, 1.5, -1, "1", [], {}, float("nan"),
                                   float("inf"), float("-inf"), 2 ** 53))
        for source in SOURCES:
            for path, value in cases:
                with self.subTest(source=source, path=path, value=repr(value)):
                    self.assert_recovered(cold, pristine, source, path, value)

    def test_failure_after_one_cache_repair_does_not_save_partial_collection(self):
        _, pristine = self.prime()
        bad = deepcopy(pristine)
        bad[self.entry_key("gemini")]["records"][0]["input"] = []
        bad[self.entry_key("claude")]["records"][0]["total"] = {}
        before = encoded(bad)
        self.cache.write_bytes(before)
        with self.source_reads(fail_source="claude") as counts:
            with self.assertRaises(readers.CollectionIncompleteError) as caught:
                self.collect(("gemini", "claude", "codex"))
        self.assertEqual("claude", caught.exception.source)
        self.assertEqual("read_failed", caught.exception.reason)
        self.assertGreater(counts["gemini"], 0, "repair the first source before the next fails")
        self.assertGreater(counts["claude"], 0)
        self.assertEqual(before, self.cache.read_bytes(),
                         "no repaired subset or empty-success entry may replace the old cache")
        self.assertEqual([], list(self.output.iterdir()))

    def test_cli_real_read_all_repairs_bad_warm_cache_and_writes_correct_dashboard(self):
        cold, pristine = self.prime()
        expected = report_dashboard.build_payload(cold, sources=list(SOURCES))
        for source in SOURCES:
            for path, value in ((("total",), {}), (("input",), []),
                                (("input",), [1]), (("billing",), {})):
                with self.subTest(source=source, path=path, value=repr(value)):
                    self.corrupt(pristine, source, path, value)
                    with self.source_reads() as counts:
                        actual = self.run_dashboard(SOURCES)
                    self.assertGreater(counts[source], 0)
                    self.assertFalse(actual["anonymized"])
                    # Compare substantive data, not time-of-generation fields.
                    for key in ("source", "models", "provenance", "day", "week", "month",
                                "reuse", "cache_read", "achievement_stats", "cost"):
                        self.assertEqual(expected[key], actual[key], key)
                    self.assertEqual(pristine, self.cache_data())

    def test_healthy_session_index_and_title_use_only_the_synthetic_claude_directory(self):
        index = readers.build_session_index()
        self.assertEqual({"synthetic-claude-session": self.paths["claude"][0]}, index)
        self.assertEqual(TITLE, readers.session_title("synthetic-claude-session", session_index=index))

    def test_session_index_treats_controlled_optional_discovery_failure_as_empty(self):
        error = readers.CollectionIncompleteError("claude", "discovery_failed")
        with mock.patch.object(readers, "claude_files", side_effect=error) as finder:
            self.assertEqual({}, readers.build_session_index())
        finder.assert_called_once_with()

    def test_nonanonymous_single_source_dashboards_survive_optional_claude_discovery_failure(self):
        for source in ("gemini", "codex"):
            with self.subTest(source=source):
                error = readers.CollectionIncompleteError("claude", "discovery_failed")
                with mock.patch.object(readers, "claude_files", side_effect=error) as finder:
                    actual = self.run_dashboard((source,))
                finder.assert_called_once_with()
                self.assertFalse(actual["anonymized"])
                self.assertEqual([source], actual["source"])
                self.assertEqual(2, actual["provenance"]["records"])
                self.assertEqual({source}, set(actual["provenance"]["sources"]))
                self.assertGreater(actual["provenance"]["total"], 0)

    def test_nonanonymous_gemini_codex_dashboard_survives_real_optional_claude_directory_cycle(self):
        self.make_directory_cycle()
        real_finder = readers.claude_files
        # Wrap the genuine finder, rather than replacing its cycle detection or
        # the index/dashboard builders with successful empty stubs.
        with mock.patch.object(readers, "claude_files", wraps=real_finder) as finder, \
                self.source_reads() as counts:
            actual = self.run_dashboard(("gemini", "codex"))
        finder.assert_called_once_with()
        self.assertFalse(actual["anonymized"])
        self.assertEqual(["gemini", "codex"], actual["source"])
        self.assertEqual(4, actual["provenance"]["records"])
        self.assertEqual({"gemini", "codex"}, set(actual["provenance"]["sources"]))
        self.assertEqual(18 + 30 + 23 + 35, actual["provenance"]["total"])
        self.assertEqual(0, counts["claude"])
        self.assertGreater(counts["gemini"], 0)
        self.assertGreater(counts["codex"], 0)

    def test_selected_claude_real_directory_cycle_still_propagates_and_preserves_cache(self):
        self.prime()
        before = self.cache.read_bytes()
        self.make_directory_cycle()
        with mock.patch.dict(readers.SOURCES, {
                "claude": (readers.claude_files, readers.claude_parse)}):
            with self.assertRaises(readers.CollectionIncompleteError) as caught:
                self.collect(("claude",))
        self.assertEqual("claude", caught.exception.source)
        self.assertEqual("discovery_failed", caught.exception.reason)
        self.assertEqual(before, self.cache.read_bytes())
        self.assertEqual([], list(self.output.iterdir()))

    def test_selected_sources_do_not_swallow_other_controlled_collection_errors(self):
        self.prime()
        before = self.cache.read_bytes()
        for source in SOURCES:
            for reason in ("discovery_failed", "read_failed", "unsafe_file", "record_limit"):
                with self.subTest(source=source, reason=reason):
                    error = readers.CollectionIncompleteError(source, reason)
                    finder = mock.Mock(side_effect=error)
                    with mock.patch.dict(readers.SOURCES, {
                            source: (finder, self.parsers[source])}):
                        with self.assertRaises(readers.CollectionIncompleteError) as caught:
                            self.collect((source,))
                    self.assertIs(error, caught.exception)
                    finder.assert_called_once_with()
                    self.assertEqual(before, self.cache.read_bytes())

    def test_optional_session_index_does_not_hide_unrelated_programming_errors(self):
        for error in (RuntimeError("synthetic-index-programming-error"),
                      ValueError("synthetic-index-invalid-state")):
            with self.subTest(error=type(error).__name__):
                with mock.patch.object(readers, "claude_files", side_effect=error):
                    with self.assertRaises(type(error)) as caught:
                        readers.build_session_index()
                self.assertIs(error, caught.exception)


if __name__ == "__main__":
    unittest.main()
