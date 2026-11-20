"""Every source must reject non-finite/invalid token components consistently."""
from tests import _hermetic  # noqa: F401
import json
import math
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tokens_cli import antigravity_usage, config, readers
from tests.test_antigravity_usage import (
    _create_db,
    _make_gen_data,
    _make_step_metadata,
)
from tests.test_codex_usage import USAGE, header, legacy
from tests.test_opencode_reader import assistant, build_db

INVALID = (float("nan"), float("inf"), -1, 1.5, True)


def _finite(record):
    return (math.isfinite(record["total"]) and record["total"] >= 0
            and record["billing"]["uncertain"] is True
            and all(record[name] == 0 for name in
                    ("input", "output", "cache_read", "cache_write", "total")))


class FiniteTokenTests(unittest.TestCase):
    def test_claude_invalid_components_are_zeroed_and_uncertain(self):
        for value in INVALID:
            with self.subTest(value=value), tempfile.TemporaryDirectory() as tmp:
                event = {
                    "type": "assistant", "timestamp": "2026-11-10T10:00:00Z",
                    "sessionId": "synthetic", "cwd": "/synthetic",
                    "message": {"id": "msg-1", "model": "claude-opus-5.5",
                                "usage": {"input_tokens": value,
                                          "output_tokens": 2,
                                          "cache_read_input_tokens": 3,
                                          "cache_creation_input_tokens": 1}},
                }
                path = Path(tmp) / "event.jsonl"
                path.write_text(json.dumps(event, allow_nan=True) + "\n",
                                encoding="utf-8")
                (record,) = readers.claude_parse(str(path))
                self.assertTrue(_finite(record))

    def test_gemini_invalid_components_are_zeroed_and_uncertain(self):
        for value in INVALID:
            with self.subTest(value=value), tempfile.TemporaryDirectory() as tmp:
                payload = {"sessionId": "synthetic", "messages": [{
                    "type": "gemini", "timestamp": "2026-11-10T10:00:00Z",
                    "model": "gemini-synthetic",
                    "tokens": {"input": value, "output": 2, "cached": 3,
                               "thoughts": 1, "tool": 0, "total": 100},
                }]}
                path = Path(tmp) / "session.json"
                path.write_text(json.dumps(payload, allow_nan=True), encoding="utf-8")
                (record,) = readers.gemini_parse(str(path))
                self.assertTrue(_finite(record))

    def test_codex_invalid_legacy_components_are_zeroed_and_uncertain(self):
        for value in INVALID:
            with self.subTest(value=value), tempfile.TemporaryDirectory() as tmp:
                usage = dict(USAGE, input_tokens=value)
                path = Path(tmp) / "rollout.jsonl"
                path.write_text("\n".join(json.dumps(event, allow_nan=True)
                                          for event in header() + [legacy(usage=usage)])
                                + "\n", encoding="utf-8")
                (record,) = readers.codex_parse(str(path))
                self.assertTrue(_finite(record))

    def test_opencode_invalid_components_are_zeroed_and_uncertain(self):
        for value in INVALID:
            with self.subTest(value=value), tempfile.TemporaryDirectory() as tmp:
                path = os.path.join(tmp, "opencode.db")
                stored = 1 if isinstance(value, float) and not math.isfinite(value) else value
                build_db(path, [("assistant", assistant({
                    "input": stored, "output": 2, "reasoning": 0,
                }))]).close()
                if isinstance(value, float) and not math.isfinite(value):
                    # SQLite JSON1 rejects NaN/Infinity as invalid JSON, so
                    # exercise the Python projection seam directly.
                    with mock.patch.object(
                            readers, "_opencode_tokens",
                            return_value={"input": value, "output": 2,
                                          "reasoning": 0}):
                        (record,) = readers.opencode_parse(path)
                else:
                    (record,) = readers.opencode_parse(path)
                self.assertTrue(_finite(record))

    def test_antigravity_invalid_record_is_zeroed_and_uncertain(self):
        raw = {
            "source": "antigravity", "ts": "2026-11-10T10:00:00Z",
            "date": "2026-11-10", "model": "antigravity-synthetic",
            "input": 0, "output": 0, "cache_read": 0, "cache_write": 0,
            "total": 0, "session": "synthetic",
            "billing": {"v": 1, "present": {}, "raw": {}, "parts": [0, 0, 0, 0, 0],
                        "uncertain": True, "reasons": ["invalid_input"]},
        }
        for value in INVALID:
            with self.subTest(value=value):
                record = dict(raw, input=value, total=value)
                with mock.patch("tokens_cli.antigravity_usage.parse_state",
                                return_value=([record], 0)):
                    (parsed,) = readers.antigravity_parse("synthetic.db")
                self.assertTrue(_finite(parsed))

    def test_invalid_values_never_reach_cache_json_or_warm_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            projects = root / "projects"
            cache_dir = root / "cache"
            projects.mkdir()
            cache_dir.mkdir()
            path = projects / "session.jsonl"
            event = {
                "type": "assistant", "timestamp": "2026-11-10T10:00:00Z",
                "sessionId": "synthetic", "cwd": "/synthetic",
                "message": {"id": "msg-1", "model": "claude-opus-5.5",
                            "usage": {"input_tokens": float("nan"),
                                      "output_tokens": float("inf"),
                                      "cache_read_input_tokens": -1,
                                      "cache_creation_input_tokens": True}},
            }
            path.write_text(json.dumps(event, allow_nan=True) + "\n",
                            encoding="utf-8")
            cache_file = cache_dir / "records-v8.json"
            with mock.patch.object(config, "CLAUDE_PROJECTS", str(projects)), \
                    mock.patch.object(config, "CACHE_DIR", str(cache_dir)), \
                    mock.patch.object(config, "CACHE_FILE", str(cache_file)), \
                    mock.patch.object(config, "CCR_ROUTER_FILE",
                                      str(root / "missing-router.js")):
                cold = readers.read_all(sources=["claude"], use_cache=True)
                raw = cache_file.read_bytes()
                warm = readers.read_all(sources=["claude"], use_cache=True)
        self.assertEqual(1, len(cold))
        self.assertEqual(cold, warm)
        self.assertEqual(0, cold[0]["total"])
        self.assertNotIn(b"NaN", raw)
        self.assertNotIn(b"Infinity", raw)

    def test_antigravity_real_oversized_varint_is_zeroed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "conv.db")
            con = _create_db(
                path,
                steps=[(0, _make_step_metadata(1794600000))],
                gens=[(0, _make_gen_data(inp=2**53 + 1, outp=1, cache_read=1))],
            )
            con.close()
            (record,) = readers.antigravity_parse(path)
        self.assertTrue(_finite(record))


if __name__ == "__main__":
    unittest.main()
