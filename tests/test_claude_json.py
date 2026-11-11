"""Pure, synthetic contract tests for the incremental Claude JSON projector.

The oracle deliberately does not import readers, config, or the implementation's
projection helpers.  Only json.loads and the three fixed projection levels below
specify which values survive.  No source logs, filesystem fixtures, or services
are needed by this module.
"""

import json
import math
import os
from pathlib import Path
import random
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tokens_cli._claude_json import BadJSON, ProjectionLimit, ProjectionParser


_FIELDS = {
    "root": {"type", "timestamp", "sessionId", "cwd", "message"},
    "message": {"model", "id", "usage"},
    "usage": {
        "input_tokens", "output_tokens", "cache_read_input_tokens",
        "cache_creation_input_tokens",
    },
}
_NEXT_LEVEL = {("root", "message"): "message", ("message", "usage"): "usage"}


def _project(value, level="root"):
    """Project only designated objects; selected leaves retain their full value."""
    if not isinstance(value, dict):
        return value
    return {
        key: _project(item, _NEXT_LEVEL[(level, key)])
        if (level, key) in _NEXT_LEVEL else item
        for key, item in value.items() if key in _FIELDS[level]
    }


def _oracle(raw):
    value = json.loads(raw.decode("utf-8", "replace").strip())
    # Non-object roots are syntactically validated but cannot be Claude events.
    return _project(value) if isinstance(value, dict) else None


def _wire(value):
    return json.dumps(value, ensure_ascii=True, separators=(",", ":")).encode("ascii")


def _chunks(raw, width):
    return [raw[index:index + width] for index in range(0, len(raw), width)]


class ProjectionAssertions(unittest.TestCase):
    def assertJSONValueEqual(self, expected, actual, path="root"):
        """Equality also checks bool/int/float distinctions, NaNs, and -0.0."""
        self.assertIs(type(actual), type(expected), path)
        if isinstance(expected, dict):
            self.assertEqual(set(expected), set(actual), path)
            for key in expected:
                self.assertJSONValueEqual(expected[key], actual[key], path + "." + key)
        elif isinstance(expected, list):
            self.assertEqual(len(expected), len(actual), path)
            for index, (left, right) in enumerate(zip(expected, actual)):
                self.assertJSONValueEqual(left, right, path + "[" + str(index) + "]")
        elif isinstance(expected, float):
            if math.isnan(expected):
                self.assertTrue(math.isnan(actual), path)
            else:
                self.assertEqual(expected, actual, path)
                if expected == 0.0:
                    self.assertEqual(math.copysign(1.0, expected), math.copysign(1.0, actual), path)
        else:
            self.assertEqual(expected, actual, path)

    def parseChunks(self, chunks, **limits):
        parser = ProjectionParser(**limits)
        for chunk in chunks:
            self.assertIsNone(parser.feed(chunk), "feed must not publish a projected record")
        return parser.finish_line()

    def assertMatchesOracle(self, raw, *, every_split=True):
        expected = _oracle(raw)
        self.assertJSONValueEqual(expected, self.parseChunks([raw]))
        self.assertJSONValueEqual(expected, self.parseChunks(_chunks(raw, 1)))
        if every_split:
            for cut in range(len(raw) + 1):
                with self.subTest(cut=cut):
                    self.assertJSONValueEqual(expected, self.parseChunks([raw[:cut], raw[cut:]]))

    def assertBadJSON(self, raw, *, every_split=True):
        with self.assertRaises(ValueError, msg="the stdlib oracle must reject the fixture"):
            _oracle(raw)
        chunkings = [[raw], _chunks(raw, 1)]
        if every_split:
            chunkings.extend([raw[:cut], raw[cut:]] for cut in range(len(raw) + 1))
        for index, chunks in enumerate(chunkings):
            with self.subTest(chunking=index):
                with self.assertRaises(BadJSON):
                    self.parseChunks(chunks)


class ProjectionSemanticsTests(ProjectionAssertions):
    def test_bad_json_is_a_value_error(self):
        self.assertTrue(issubclass(BadJSON, ValueError))
        self.assertIsNot(BadJSON, ProjectionLimit)

    def test_non_object_roots_are_validated_but_do_not_project_an_event(self):
        for raw in (b"null", b"false", b"true", b"0", b"1.25", b"NaN", b"Infinity", b'"text"', b"[]", b'[1,{"message":2}]'):
            with self.subTest(raw=raw):
                self.assertMatchesOracle(raw)
        for raw in (b"nullx", b"true false", b"[1,]", b'"text"x'):
            with self.subTest(raw=raw):
                self.assertBadJSON(raw)

    def test_nonfinite_numbers_inside_complete_leaf_metadata_preserve_types(self):
        raw = (
            b'{"sessionId":{"extra":[NaN,Infinity,-Infinity,-0.0]},'
            b'"cwd":[{"nested":NaN}],"message":{"id":{"nested":Infinity},'
            b'"usage":{"input_tokens":[NaN,{"nested":-Infinity}]}}}'
        )
        self.assertMatchesOracle(raw)

    def test_feed_releases_derived_memoryviews_before_propagating_parse_and_limit_errors(self):
        fixtures = (
            (b"x", {}, BadJSON),
            (b"[[", {"max_depth": 1}, ProjectionLimit),
        )
        for raw, limits, exception_type in fixtures:
            with self.subTest(raw=raw, exception_type=exception_type.__name__):
                buffer = bytearray(raw)
                source_view = memoryview(buffer)
                parser = ProjectionParser(**limits)
                try:
                    parser.feed(source_view)
                except exception_type:
                    # Keep the exception traceback alive while checking cleanup.
                    # Release the caller's export so only an unreleased derived
                    # view inside feed could prevent resizing the bytearray.
                    source_view.release()
                    buffer.clear()
                    self.assertEqual(bytearray(), buffer)
                else:
                    self.fail("feed must raise before the buffer cleanup check")
                finally:
                    source_view.release()

    def test_selected_fields_and_missing_fields_match_the_independent_oracle(self):
        values = [
            {},
            {"type": "assistant"},
            {"message": {}},
            {"message": {"usage": {}}},
            {
                "type": "assistant", "timestamp": "2026-10-22T00:00:00Z",
                "sessionId": "full-session", "cwd": "/synthetic/project",
                "message": {
                    "model": "synthetic-model", "id": "full-message-id",
                    "usage": {
                        "input_tokens": 11, "output_tokens": 7,
                        "cache_read_input_tokens": 13,
                        "cache_creation_input_tokens": 17,
                        "not_usage": {"output_tokens": 999},
                    },
                    "content": [{"type": "text", "text": "not retained"}],
                },
                "usage": {"input_tokens": 999},
                "nested": {"message": {"usage": {"input_tokens": 888}}},
            },
        ]
        for value in values:
            with self.subTest(value=value):
                self.assertMatchesOracle(_wire(value))

    def test_selected_leaves_preserve_truthiness_type_and_complete_nested_metadata(self):
        values = [
            None, False, True, 0, -1, 0.0, -0.0, "", "kept", [], {},
            [False, None, {"not_selected": [1, {"usage": "literal metadata"}]}],
            {"not_selected": {"message": {"arbitrary": [False, 0, ""]}}},
        ]
        for value in values:
            event = {
                "type": value, "timestamp": value, "sessionId": value, "cwd": value,
                "message": {
                    "model": value, "id": value,
                    "usage": {key: value for key in _FIELDS["usage"]},
                },
            }
            with self.subTest(value=value):
                self.assertMatchesOracle(_wire(event), every_split=False)

    def test_non_object_message_and_usage_are_not_coerced_to_empty_objects(self):
        for value in (None, False, True, 0, -1, "", "wrong type", [], [1, {"arbitrary": 2}]):
            for event in ({"message": value}, {"message": {"usage": value}}):
                with self.subTest(event=event):
                    self.assertMatchesOracle(_wire(event))

    def test_selected_metadata_is_not_shortened_or_hashed(self):
        value = "prefix-" + "雪/" * 4096 + "-distinct-suffix"
        event = {"sessionId": value, "cwd": value, "message": {"id": value, "model": value}}
        self.assertMatchesOracle(_wire(event), every_split=False)

    def test_duplicate_keys_replace_whole_message_and_usage_instead_of_merging(self):
        fixtures = [
            b'{"message":{"id":"old","usage":{"input_tokens":9}},"message":{"model":"new"}}',
            b'{"message":{"usage":{"input_tokens":9,"output_tokens":8},"usage":{"output_tokens":2}}}',
            b'{"message":{"id":"old"},"message":null}',
            b'{"message":false,"message":{"usage":{}}}',
            b'{"message":{"usage":{"input_tokens":1},"usage":false}}',
            b'{"message":{"usage":false,"usage":{"input_tokens":0}}}',
            b'{"sessionId":{"old":true},"sessionId":[],"cwd":"old","cwd":false}',
            b'{"message":{"id":{"a":1,"a":2},"id":[{"arbitrary":3}]}}',
            b'{"message":{"usage":{"input_tokens":1,"input_tokens":{"all":[2,3]}}}}',
            b'{"message":{"id":"old"},"mess\\u0061ge":{"id":"new"}}',
            b'{"message":{"usage":{"input_tokens":1},"us\\u0061ge":{"output_tokens":2}}}',
            b'{"sessionId":"old","session\\u0049d":"new"}',
        ]
        for raw in fixtures:
            with self.subTest(raw=raw):
                self.assertMatchesOracle(raw)

    def test_recognized_keys_are_exact_decoded_keys_not_prefixes_or_nested_matches(self):
        fixtures = [
            b'{"mess\\u0061ge":{"\\u0069d":"escaped","us\\u0061ge":{"input_\\u0074okens":3}}}',
            b'{"Message":{"id":"wrong"},"message!":{"id":"wrong"},"message":{"id!":9,"id":2}}',
            b'{"message":{"usage":{"input_tokensX":9,"input_tokens":3,"output_tokens\\u0000":8}}}',
            b'{"unknown":{"message":{"id":"fake","usage":{"input_tokens":999}}},"message":{"id":"real"}}',
            b'{"text":"\\\"message\\\":{\\\"usage\\\":{\\\"input_tokens\\\":999}}","message":{"usage":{"input_tokens":1}}}',
            b'{"message":{"unknown":[{"usage":{"input_tokens":999}}],"usage":{"input_tokens":4}}}',
            b'{"\\ud800message":9,"message":{"id":1}}',
        ]
        for raw in fixtures:
            with self.subTest(raw=raw):
                self.assertMatchesOracle(raw)

    def test_feed_does_not_publish_even_after_a_complete_root_and_trailing_whitespace(self):
        raw = b'{"type":"assistant","message":{"usage":{"input_tokens":1}}}'
        parser = ProjectionParser()
        self.assertIsNone(parser.feed(raw))
        self.assertIsNone(parser.feed(b" \r\n\t"))
        self.assertJSONValueEqual(_oracle(raw), parser.finish_line())

    def test_late_trailing_garbage_invalidates_a_previously_complete_candidate(self):
        raw = b'{"message":{"usage":{"input_tokens":1}}}'
        self.assertBadJSON(raw + b" garbage")
        self.assertBadJSON(raw + b" {}")
        self.assertBadJSON(raw + b"\xc2\xa0x")

    def test_synthetic_randomized_events_match_stdlib_without_internal_helper_mocks(self):
        rng = random.Random(0xC1A0DE)
        atoms = [None, False, True, 0, -1, 2.5, "", "雪", "\\\"/", "\ud800"]

        def leaf(depth=0):
            if depth == 2 or rng.randrange(3) == 0:
                return rng.choice(atoms)
            if rng.randrange(2):
                return [leaf(depth + 1) for _ in range(rng.randrange(4))]
            return {key: leaf(depth + 1) for key in rng.sample(["other", "id", "usage"], rng.randrange(4))}

        for index in range(80):
            event = {
                "type": leaf(), "sessionId": leaf(), "cwd": leaf(), "timestamp": leaf(),
                "message": {
                    "model": leaf(), "id": leaf(),
                    "usage": {key: leaf() for key in sorted(_FIELDS["usage"])},
                    "discard": leaf(),
                },
                "discard": leaf(),
            }
            raw = _wire(event)
            width = rng.randrange(1, 29)
            with self.subTest(case=index, width=width):
                self.assertJSONValueEqual(_oracle(raw), self.parseChunks(_chunks(raw, width)))


class ProjectionLexicalTests(ProjectionAssertions):
    def test_utf8_decoder_replacement_matches_whole_line_decode_at_every_byte_cut(self):
        strings = [
            "雪🌈é".encode("utf-8"), b"\xff", b"\xc0\xaf", b"\xed\xa0\x80",
            b"\xe2\x82", b"\xf0\x9f", b"\xe2(\xa1", b"\xf4\x90\x80\x80",
            b"\x80\xbf\xfe", b"a\xe2\x82b", b"\xf0\x90\x80\x80",
        ]
        for text in strings:
            for raw in (
                b'{"sessionId":"' + text + b'","message":{"id":"ok"}}',
                b'{"unknown":"' + text + b'","message":{"id":"ok"}}',
                b'{"' + text + b'":"unknown key","message":{"id":"ok"}}',
            ):
                with self.subTest(text=text):
                    self.assertMatchesOracle(raw)

    def test_incomplete_utf8_at_eof_is_flushed_and_cannot_hide_trailing_garbage(self):
        for raw in (b'{"message":{}}\xe2\x82', b'{"sessionId":"\xf0\x9f', b'\xff{}'):
            with self.subTest(raw=raw):
                self.assertBadJSON(raw)

    def test_unicode_strip_whitespace_is_accepted_only_at_the_outer_edges(self):
        whitespace = (
            " \t\n\r\v\f\x1c\x1d\x1e\x1f\x85\xa0\u1680"
            "\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a"
            "\u2028\u2029\u202f\u205f\u3000"
        )
        for char in whitespace:
            raw = (char + '{"message":{}}' + char).encode("utf-8")
            with self.subTest(codepoint=ord(char)):
                self.assertMatchesOracle(raw)
                if char not in " \t\r\n":
                    for text in ('{' + char + '"message":{}}', '{"message":' + char + '{}}'):
                        self.assertBadJSON(text.encode("utf-8"))
        self.assertMatchesOracle(b'{ \t\r\n"message" \t:\r {"usage": [ true, null, 1 ]} }')

    def test_bom_and_non_strip_unicode_are_not_treated_as_outer_whitespace(self):
        for char in ("\ufeff", "\u200b", "\u180e"):
            for text in (char + "{}", "{}" + char):
                with self.subTest(codepoint=ord(char), text=text):
                    self.assertBadJSON(text.encode("utf-8"))

    def test_string_escapes_surrogate_pairs_and_lone_surrogates_match_json_loads(self):
        values = [
            br'"\\\"\/\b\f\n\r\t"', br'"\u0000\u001f\u007f"',
            br'"\ud834\udd1e"', br'"\uD834\uDD1E"', br'"\ud800"',
            br'"\udfff"', br'"\ud800x\udc00"', br'"\ud800\ud800\udc00"',
            br'"\udc00\ud800"', br'"\ud800\u0041"', br'"\u2028\u2029"',
        ]
        for value in values:
            with self.subTest(value=value):
                self.assertMatchesOracle(b'{"sessionId":' + value + b',"unknown":' + value + b'}')

    def test_raw_control_characters_and_invalid_escapes_are_rejected_even_when_discarded(self):
        bad_strings = [b'"a' + bytes([number]) + b'b"' for number in range(32)]
        bad_strings += [
            br'"\x00"', br'"\a"', br'"\v"', br'"\U00000041"',
            br'"\u"', br'"\u0"', br'"\u00"', br'"\u000"', br'"\u00xz"',
            b'"trailing\\', b'"unterminated',
        ]
        for value in bad_strings:
            for key in (b"sessionId", b"discard"):
                raw = b'{"' + key + b'":' + value + b'}'
                with self.subTest(value=value, key=key):
                    self.assertBadJSON(raw)
        self.assertBadJSON(b'{"bad\x00key":0}')
        self.assertBadJSON(br'{"bad\xkey":0}')

    def test_valid_number_types_negative_zero_and_stdlib_nonfinite_constants_match(self):
        numbers = [
            b"0", b"-0", b"1", b"-123", b"12345678901234567890",
            b"0.0", b"-0.0", b"1.25", b"-0.01", b"1e2", b"1E+2", b"1e-2",
            b"-0e0", b"1e400", b"-1e400", b"1e-4000", b"-1e-4000",
            b"NaN", b"Infinity", b"-Infinity",
        ]
        for number in numbers:
            raw = b'{"message":{"usage":{"input_tokens":' + number + b'}},"discard":' + number + b'}'
            with self.subTest(number=number):
                self.assertMatchesOracle(raw)

    def test_invalid_number_and_constant_grammar_is_rejected_in_unknown_values_too(self):
        invalid = [
            b"+1", b"01", b"-01", b"00", b".1", b"1.", b"-.1", b"1e", b"1e+",
            b"1e-", b"1e1.0", b"--1", b"0x10", b"1_0", b"+Infinity", b"Inf",
            b"nan", b"NAN", b"infinity", b"-NaN", b"NaNx", b"Infinity0",
            b"True", b"FALSE", b"None", b"undefined", b"tru", b"nullx", b"false1",
        ]
        for value in invalid:
            for key in (b"sessionId", b"discard"):
                with self.subTest(value=value, key=key):
                    self.assertBadJSON(b'{"' + key + b'":' + value + b'}')

    def test_invalid_container_syntax_and_truncation_are_checked_in_discarded_subtrees(self):
        invalid_values = [
            b"[1,]", b"[,1]", b"[1 2]", b"[1,,2]", b"{,}", b'{"a":1,}',
            b'{"a" 1}', b'{"a":}', b'{a:1}', b'{"a":1 "b":2}', b'{"a":1,,"b":2}',
            b"[}", b"{]", b"[1", b'{"a":', b'"x', b"/*comment*/0", b"(0)",
        ]
        for value in invalid_values:
            with self.subTest(value=value):
                self.assertBadJSON(b'{"discard":' + value + b'}')
        for raw in (b"", b" \t\r\n", "\u3000".encode("utf-8"), b"{}{}", b"{},", b"{}:", b"[]x"):
            with self.subTest(raw=raw):
                self.assertBadJSON(raw)

    def test_current_interpreter_integer_digit_limit_is_preserved_for_selected_and_unknown_values(self):
        getter = getattr(sys, "get_int_max_str_digits", None)
        if getter is None or getter() == 0:
            self.skipTest("the interpreter has no active decimal integer digit ceiling")
        limit = getter()
        if limit > 10000:
            self.skipTest("custom integer ceiling is too large for this bounded unit fixture")
        try:
            for key in (b"sessionId", b"discard"):
                raw = b'{"' + key + b'":' + b"1" * limit + b'}'
                with self.subTest(key=key, digits=limit):
                    self.assertMatchesOracle(raw, every_split=False)
                raw = b'{"' + key + b'":' + b"1" * (limit + 1) + b'}'
                with self.subTest(key=key, digits=limit + 1):
                    self.assertBadJSON(raw, every_split=False)
            # A large integer part is legal for float tokens, not a decimal int conversion.
            self.assertMatchesOracle(b'{"discard":' + b"1" * (limit + 1) + b'.0}', every_split=False)
        finally:
            self.assertEqual(limit, getter(), "the parser must never change the global int ceiling")

    def test_a_failed_or_incomplete_parser_does_not_leak_state_into_the_next_line(self):
        self.assertBadJSON(b'{"sessionId":"\xe2\x82', every_split=False)
        self.assertBadJSON(b'{"message":{"usage":{"input_tokens":7}}}x', every_split=False)
        self.assertMatchesOracle(b'{"message":{"usage":{"output_tokens":3}}}')


class ProjectionLargeUnknownTests(ProjectionAssertions):
    def test_line_larger_than_four_mib_keeps_usage_before_and_after_discarded_string(self):
        discarded = b"x" * (4 * 1024 * 1024 + 1)
        fixtures = [
            b'{"message":{"usage":{"input_tokens":13}},"discard":"' + discarded + b'"}',
            b'{"discard":"' + discarded + b'","message":{"usage":{"input_tokens":17}}}',
        ]
        for raw in fixtures:
            with self.subTest(usage_at_end=raw.startswith(b'{"discard"')):
                self.assertJSONValueEqual(_oracle(raw), self.parseChunks(_chunks(raw, 64 * 1024)))

    def test_unknown_giant_keys_strings_and_float_tokens_are_validated_without_false_selection(self):
        giant = b"x" * (128 * 1024)
        raw = (
            b'{"message' + giant + b'":{"usage":{"input_tokens":999}},'
            b'"message":{"usage' + giant + b'":{"output_tokens":888},'
            b'"usage":{"input_tokens' + giant + b'":777,"input_tokens":19}},'
            b'"discard":"' + giant + b'","unknown_float":' + b"9" * (128 * 1024) + b'e0}'
        )
        self.assertJSONValueEqual(_oracle(raw), self.parseChunks(_chunks(raw, 4093)))

    def test_late_syntax_errors_after_large_unknown_values_are_not_ignored(self):
        giant = b"x" * (128 * 1024)
        for tail in (b'",}', b'","bad":[1,]}', b'"}garbage'):
            raw = b'{"message":{"usage":{"input_tokens":11}},"discard":"' + giant + tail
            with self.subTest(tail=tail):
                with self.assertRaises(ValueError):
                    _oracle(raw)
                with self.assertRaises(BadJSON):
                    self.parseChunks(_chunks(raw, 4093))


class ProjectionRecordEquivalenceTests(ProjectionAssertions):
    def test_duplicate_nan_ids_and_fallback_keys_keep_stdlib_first_wins_identity(self):
        from tokens_cli import readers

        fixtures = {
            "nan_id": (
                b'{"type":"assistant","timestamp":"2026-10-22T00:00:00Z",'
                b'"message":{"model":"synthetic-model","id":NaN,'
                b'"usage":{"input_tokens":1,"output_tokens":2}}}'
            ),
            "nan_fallback_usage": (
                b'{"type":"assistant","timestamp":"2026-10-22T00:00:00Z",'
                b'"message":{"model":"synthetic-model",'
                b'"usage":{"input_tokens":NaN,"output_tokens":2}}}'
            ),
        }
        with mock.patch.object(readers, "_resolve_model", side_effect=lambda model: model):
            with tempfile.TemporaryDirectory(prefix="tokens-nan-dedupe-") as tmp:
                for name, raw in fixtures.items():
                    with self.subTest(key_kind=name):
                        # Two independent loads calls intentionally share the
                        # stdlib NaN constant. NaN value equality alone cannot
                        # prove that the parser preserves this set-key behavior.
                        oracle_keys = set()
                        for _ in range(2):
                            event = json.loads(raw.decode("utf-8", "replace").strip())
                            normalized = readers._claude_event_record(event)
                            self.assertIsNotNone(normalized, "the oracle must produce a real event")
                            oracle_keys.add(normalized[1])
                        self.assertEqual(1, len(oracle_keys))

                        path = Path(tmp) / (name + ".jsonl")
                        path.write_bytes(raw + b"\n" + raw + b"\n")
                        records = readers.claude_parse(os.fspath(path))
                        self.assertEqual(1, len(records), "duplicate NaN-bearing keys must remain first-wins")

    def test_normalized_records_billing_and_complete_saved_keys_match_full_json_events(self):
        # This integration contract is intentionally not skipped on old baselines:
        # the guarded integration runner must supply the current readers module.
        from tokens_cli import readers

        base = {
            "type": "assistant", "timestamp": "2026-10-22T00:00:00Z",
            "sessionId": "session-" + "S" * 512 + "-suffix",
            "cwd": "/synthetic/" + "C" * 512 + "/suffix",
            "message": {
                "model": "synthetic-model", "id": "id-" + "M" * 512 + "-suffix",
                "usage": {
                    "input_tokens": 11, "output_tokens": 7,
                    "cache_read_input_tokens": 13, "cache_creation_input_tokens": 17,
                },
            },
        }
        raws = [_wire(base)]
        for mid in (None, "", False, 0, "id-distinct-suffix", ["unhashable"], {"full": "unhashable"}):
            event = dict(base, message=dict(base["message"], id=mid))
            raws.append(_wire(event))
        for metadata in (None, False, 0, "", [], {}, [1, {"full": [False, None]}], {"full": [1, 2]}):
            raws.append(_wire(dict(base, sessionId=metadata, cwd=metadata)))
        for key in sorted(_FIELDS["usage"]):
            for value in (None, False, True, -1, 0, 1.5, "9", [], {}, {"full": [1]}, float("nan"), float("inf")):
                usage = dict(base["message"]["usage"], **{key: value})
                raws.append(_wire(dict(base, message=dict(base["message"], usage=usage))))
        for usage in (None, False, 0, "", [], {}, [1], {"output_tokens": 0}):
            raws.append(_wire(dict(base, message=dict(base["message"], usage=usage))))
        raws.extend([
            b'{"type":"assistant","timestamp":"2026-10-22T00:00:00Z","message":{"model":"m","id":"old","usage":{"input_tokens":9}},"message":{"model":"m","id":"new","usage":{"output_tokens":2}}}',
            b'{"type":"assistant","timestamp":"2026-10-22T00:00:00Z","message":{"model":"m","usage":{"input_tokens":9},"usage":{"output_tokens":2}}}',
            b'{"type":"assistant","timestamp":"2026-10-22T00:00:00Z","message":{"model":"m","usage":{}}}',
            b'{"type":"user","message":{"model":"m","usage":{"input_tokens":99}}}',
        ])
        local_bad_event = (TypeError, ValueError, RecursionError, OverflowError)

        def outcome(value):
            try:
                return "returned", readers._claude_event_record(value)
            except local_bad_event as error:
                return "raised", type(error).__name__

        # Only the external router/model boundary is mocked. Normalization,
        # billing, date conversion, hashability and saved keys are real helpers.
        with mock.patch.object(readers, "_resolve_model", side_effect=lambda model: model):
            for index, raw in enumerate(raws):
                with self.subTest(case=index):
                    full = json.loads(raw.decode("utf-8", "replace").strip())
                    expected = outcome(full)
                    actual = outcome(self.parseChunks(_chunks(raw, 7)))
                    self.assertEqual(expected[0], actual[0])
                    if expected[0] == "raised":
                        self.assertEqual(expected[1], actual[1])
                    elif expected[1] is None:
                        self.assertIsNone(actual[1])
                    else:
                        expected_record, expected_key, expected_saved = expected[1]
                        record, key, saved = actual[1]
                        self.assertJSONValueEqual(expected_record, record)
                        if isinstance(expected_key, tuple):
                            self.assertIsInstance(key, tuple)
                            self.assertJSONValueEqual(list(expected_key), list(key))
                        else:
                            self.assertJSONValueEqual(expected_key, key)
                        self.assertJSONValueEqual(expected_saved, saved)
            # An explicit nonempty success prevents a vacuous both-ignored pass.
            record, key, saved = readers._claude_event_record(self.parseChunks([raws[0]]))
            self.assertEqual(base["message"]["id"], key)
            self.assertJSONValueEqual(["id", base["message"]["id"]], saved)
            self.assertEqual(base["sessionId"], record["session"])
            self.assertEqual(base["cwd"], record["cwd"])
            self.assertIn("billing", record)


class ProjectionCapacityTests(ProjectionAssertions):
    def assertLimit(self, raw, reason, **limits):
        # Both a single small-buffer feed and a streaming feed enforce the same bound.
        for chunks in ([raw], _chunks(raw, 1)):
            with self.subTest(limits=limits, chunk_count=len(chunks)):
                with self.assertRaises(ProjectionLimit) as caught:
                    self.parseChunks(chunks, **limits)
                self.assertEqual(reason, caught.exception.reason)
                self.assertNotIsInstance(caught.exception, BadJSON)

    def assertExactCapacity(self, raw, argument, exact, reason):
        self.assertJSONValueEqual(_oracle(raw), self.parseChunks([raw], **{argument: exact}))
        self.assertJSONValueEqual(_oracle(raw), self.parseChunks(_chunks(raw, 1), **{argument: exact}))
        self.assertLimit(raw, reason, **{argument: exact - 1})

    def test_depth_exact_and_next_container_apply_to_selected_and_discarded_values(self):
        self.assertExactCapacity(
            b'{"sessionId":[{"full":[]}]}', "max_depth", 4, "json_depth_limit"
        )
        self.assertExactCapacity(
            b'{"discard":[{"ignored":[]}]}', "max_depth", 4, "json_depth_limit"
        )
        self.assertExactCapacity(b'[[[[]]]]', "max_depth", 4, "json_depth_limit")
        self.assertExactCapacity(b'{}', "max_depth", 1, "json_depth_limit")

    def test_token_exact_and_next_include_punctuation_keys_scalars_and_discarded_values(self):
        fixtures = [
            (b'{}', 2),
            (b'{"message":{}}', 6),
            (b'{"discard":["x",1,true,null,NaN,Infinity,-Infinity]}', 19),
            (b'{"a":1,"a":2}', 9),
            (b' [ true , false , null ] ', 7),
        ]
        for raw, tokens in fixtures:
            with self.subTest(raw=raw, tokens=tokens):
                self.assertExactCapacity(raw, "max_tokens", tokens, "json_token_limit")
                parser = ProjectionParser(max_tokens=tokens)
                self.assertIsNone(parser.feed(raw))
                parser.finish_line()
                self.assertEqual(tokens, parser.stats["tokens"])

    def test_projection_byte_exact_and_next_follow_independent_engineering_costs(self):
        # Nodes cost 128; object members cost 64 + decoded key bytes; strings
        # and numeric lexemes add their UTF-8-surrogatepass / ASCII byte size.
        fixtures = [
            (b'{}', 128),
            (b'{"sessionId":"x"}', 330),
            (b'{"sessionId":null}', 329),
            (b'{"sessionId":false}', 329),
            (b'{"sessionId":1}', 330),
            (b'{"sessionId":-0.0}', 333),
            (br'{"sessionId":"\ud800"}', 332),
            ('{"sessionId":"𝄞"}'.encode("utf-8"), 333),
            (br'{"sessionId":"x"}', 330),
            (b'{"sessionId":{"x":[]}}', 522),
            (b'{"sessionId":[null,0,"x"]}', 715),
            (b'{"message":{"usage":{"input_tokens":1}}}', 729),
        ]
        for raw, cost in fixtures:
            with self.subTest(raw=raw, cost=cost):
                self.assertExactCapacity(raw, "max_projection_bytes", cost, "json_projection_limit")
                parser = ProjectionParser(max_projection_bytes=cost)
                self.assertIsNone(parser.feed(raw))
                self.assertJSONValueEqual(_oracle(raw), parser.finish_line())
                self.assertEqual(cost, parser.stats["projection_bytes"])
                self.assertEqual(cost, parser.stats["peak_projection_bytes"])

    def test_projection_node_exact_and_next_count_full_selected_leaves_not_unknown_subtrees(self):
        fixtures = [
            (b'{}', 1),
            (b'{"sessionId":"x"}', 2),
            (b'{"sessionId":[null,0,"x"]}', 5),
            (b'{"message":{"usage":{"input_tokens":1}}}', 4),
            (b'{"discard":[{},[1,2,3]],"message":{}}', 2),
        ]
        for raw, nodes in fixtures:
            with self.subTest(raw=raw, nodes=nodes):
                self.assertExactCapacity(raw, "max_projection_nodes", nodes, "json_projection_limit")
                parser = ProjectionParser(max_projection_nodes=nodes)
                self.assertIsNone(parser.feed(raw))
                parser.finish_line()
                self.assertEqual(nodes, parser.stats["projection_nodes"])
                self.assertEqual(nodes, parser.stats["peak_projection_nodes"])

    def test_selected_number_lexeme_exact_and_next_are_measured_before_conversion(self):
        for number in (b'12345', b'-12.5', b'1e+02', b'-0.0', b'NaN', b'Infinity', b'-Infinity'):
            raw = b'{"message":{"usage":{"input_tokens":' + number + b'}}}'
            with self.subTest(number=number):
                self.assertExactCapacity(raw, "max_number_bytes", len(number), "json_number_limit")
        self.assertExactCapacity(
            b'{"sessionId":[{"nested":12345}]}', "max_number_bytes", 5, "json_number_limit"
        )

    def test_fixed_slot_duplicate_replacement_releases_old_bytes_and_nodes_before_new_value(self):
        repeated = b'{"sessionId":"' + b'x' * 64 + b'"' + (b',"sessionId":"' + b'y' * 64 + b'"') * 100 + b'}'
        self.assertExactCapacity(repeated, "max_projection_bytes", 393, "json_projection_limit")
        self.assertExactCapacity(repeated, "max_projection_nodes", 2, "json_projection_limit")
        raw = (
            b'{"message":{"id":"old","usage":{"input_tokens":1}},'
            b'"message":{"id":"new","usage":{"output_tokens":2}},'
            b'"message":{"model":"last"}}'
        )
        # This budget admits each replacement independently, not their aggregate.
        self.assertJSONValueEqual(_oracle(raw), self.parseChunks(_chunks(raw, 1), max_projection_bytes=1200, max_projection_nodes=5))
        repeated_usage = (
            b'{"message":{"usage":{"input_tokens":1}'
            + b',"usage":{"output_tokens":2}' * 100 + b'}}'
        )
        self.assertJSONValueEqual(_oracle(repeated_usage), self.parseChunks(_chunks(repeated_usage, 1), max_projection_bytes=1000, max_projection_nodes=4))

    def test_duplicate_full_leaf_members_account_for_only_the_live_temporary_decoded_key(self):
        raw = b'{"sessionId":{"x":"a","x":"b","x":"c"}}'
        # Final = 523. While identifying a duplicate FULL member's key, its
        # temporary member/key costs 65 in addition to the existing live tree.
        self.assertExactCapacity(raw, "max_projection_bytes", 588, "json_projection_limit")
        parser = ProjectionParser(max_projection_bytes=588)
        self.assertIsNone(parser.feed(raw))
        self.assertJSONValueEqual(_oracle(raw), parser.finish_line())
        self.assertEqual(523, parser.stats["projection_bytes"])
        self.assertEqual(588, parser.stats["peak_projection_bytes"])
        self.assertEqual(3, parser.stats["projection_nodes"])
        self.assertEqual(3, parser.stats["peak_projection_nodes"])

    def test_unknown_key_string_and_number_lengths_do_not_consume_selected_value_limits(self):
        giant = b'x' * (128 * 1024)
        raw = (
            b'{"message' + giant + b'":"' + giant + b'",'
            b'"unknown_float":' + b'9' * (128 * 1024) + b'e0,"discard":123456789}'
        )
        parser = ProjectionParser(max_projection_bytes=128, max_projection_nodes=1, max_number_bytes=1)
        for chunk in _chunks(raw, 4093):
            self.assertIsNone(parser.feed(chunk))
        self.assertJSONValueEqual({}, parser.finish_line())
        self.assertEqual(128, parser.stats["peak_projection_bytes"])
        self.assertEqual(1, parser.stats["peak_projection_nodes"])

    def test_resource_failure_is_not_reported_as_bad_json_or_an_empty_success(self):
        raw = b'{"message":{"usage":{"input_tokens":1}}}'
        self.assertLimit(raw, "json_depth_limit", max_depth=1)
        self.assertLimit(raw, "json_token_limit", max_tokens=1)
        self.assertLimit(raw, "json_projection_limit", max_projection_bytes=128)
        self.assertLimit(raw, "json_projection_limit", max_projection_nodes=1)
        self.assertLimit(b'{"sessionId":12}', "json_number_limit", max_number_bytes=1)

    def test_unfinished_selected_strings_and_numbers_are_limited_during_feed(self):
        # No closing quote, number delimiter, container terminator, or finish call
        # is supplied: a parser that materializes then charges would miss this.
        fixtures = [
            (b'{"sessionId":"xx', {"max_projection_bytes": 330}, "json_projection_limit"),
            (b'{"sessionId":12', {"max_number_bytes": 1}, "json_number_limit"),
            (b'{"sessionId":{"xx', {"max_projection_bytes": 394}, "json_projection_limit"),
        ]
        for prefix, limits, reason in fixtures:
            with self.subTest(prefix=prefix, limits=limits):
                parser = ProjectionParser(**limits)
                with self.assertRaises(ProjectionLimit) as caught:
                    for byte in prefix:
                        self.assertIsNone(parser.feed(bytes([byte])))
                self.assertEqual(reason, caught.exception.reason)

    def test_unknown_float_can_cross_int_digit_ceiling_before_eventual_exponent(self):
        getter = getattr(sys, "get_int_max_str_digits", None)
        limit = getter() if getter is not None else 4300
        if limit == 0:
            limit = 4300
        if limit > 10000:
            self.skipTest("custom integer ceiling is too large for this bounded unit fixture")
        raw = b'{"discard":' + b'9' * (limit + 1) + b'e0}'
        parser = ProjectionParser(max_number_bytes=1, max_projection_bytes=128)
        # The exponent arrives only after a would-be oversize integer prefix.
        for byte in raw:
            self.assertIsNone(parser.feed(bytes([byte])))
        self.assertJSONValueEqual(_oracle(raw), parser.finish_line())

    def test_statistics_bound_every_feed_and_report_peak_stack_and_live_projection(self):
        raw = b'{"sessionId":[{"all":[1,"two",true]}],"discard":[[[0]]]}'
        limits = {
            "max_depth": 5, "max_tokens": 100,
            "max_projection_bytes": 2048, "max_projection_nodes": 10,
            "max_number_bytes": 8,
        }
        parser = ProjectionParser(**limits)
        peaks = {name: 0 for name in ("peak_depth", "peak_projection_bytes", "peak_projection_nodes")}
        for chunk in _chunks(raw, 1):
            self.assertIsNone(parser.feed(chunk))
            stats = parser.stats
            for current, peak, maximum in (
                ("depth", "peak_depth", "max_depth"),
                ("projection_bytes", "peak_projection_bytes", "max_projection_bytes"),
                ("projection_nodes", "peak_projection_nodes", "max_projection_nodes"),
            ):
                self.assertLessEqual(0, stats[current])
                self.assertLessEqual(stats[current], stats[peak])
                self.assertLessEqual(peaks[peak], stats[peak])
                self.assertLessEqual(stats[peak], limits[maximum])
                peaks[peak] = stats[peak]
            self.assertLessEqual(stats["tokens"], limits["max_tokens"])
        self.assertJSONValueEqual(_oracle(raw), parser.finish_line())
        self.assertEqual(0, parser.stats["depth"])
        self.assertEqual(4, parser.stats["peak_depth"])


if __name__ == "__main__":
    unittest.main()
