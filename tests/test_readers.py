import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]

SRC = ROOT / "src"

import sys
sys.path.insert(0, str(SRC))

import tokens_cli
from tokens_cli import readers


class ReadersTests(unittest.TestCase):
    def test_session_title_uses_supplied_index_without_glob(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "session-a.jsonl"
            path.write_text(
                json.dumps({
                    "type": "user",
                    "message": {"content": "请优化这个性能热点\n第二行"},
                }) + "\n",
                encoding="utf-8",
            )
            with mock.patch("tokens_cli.readers.glob.glob") as glob_fn:
                title = tokens_cli.readers.session_title(
                    "session-a",
                    session_index={"session-a": str(path)},
                )
            glob_fn.assert_not_called()
            self.assertEqual("请优化这个性能热点", title)

    def test_build_session_index_maps_jsonl_stems_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "a" / "session-a.jsonl"
            second = root / "b" / "session-b.jsonl"
            first.parent.mkdir()
            second.parent.mkdir()
            first.write_text("", encoding="utf-8")
            second.write_text("", encoding="utf-8")
            with mock.patch.object(tokens_cli.readers.config, "CLAUDE_PROJECTS", tmp):
                index = tokens_cli.readers.build_session_index()
            self.assertEqual(str(first), index["session-a"])
            self.assertEqual(str(second), index["session-b"])

    def test_safe_to_parse_rejects_symlink_and_oversized_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "target.jsonl"
            target.write_text("{}\n", encoding="utf-8")
            link = root / "link.jsonl"
            link.symlink_to(target)
            self.assertFalse(tokens_cli.readers._safe_to_parse(str(link), os.stat(link)))
            fake = mock.Mock(st_mode=stat.S_IFREG, st_size=tokens_cli.readers.MAX_FILE_BYTES + 1)
            self.assertFalse(tokens_cli.readers._safe_to_parse(str(target), fake))

    def test_cache_writer_uses_private_compact_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache_file = Path(tmp) / "records-v4.json"
            with mock.patch.object(readers.config, "CACHE_DIR", tmp), \
                    mock.patch.object(readers.config, "CACHE_FILE", str(cache_file)):
                readers._save_cache({"claude::x": {"key": "1|2", "records": []}})
            text = cache_file.read_text(encoding="utf-8")
            self.assertNotIn(": ", text)
            self.assertNotIn(", ", text)
            self.assertEqual(readers.CACHE_VERSION, json.loads(text)["_v"])
            if os.name != "nt":
                self.assertEqual(0o600, stat.S_IMODE(cache_file.stat().st_mode))


class CcrModelResolutionTests(unittest.TestCase):
    ROUTER_JS = """module.exports = async function router(req, config) {
  const model = req.body.model || '';
  if (model.includes('direct-x')) {
    return 'provider-a,direct-x';
  }
  if (
    model.includes('request-y') ||
    model.includes('request-y-legacy')
  ) {
    return 'provider-b,backend-y';
  }
  if (model.includes('haiku')) { return 'provider-c,backend-small'; }
  if (model.includes('sonnet')) { return 'provider-a,backend-balanced'; }
  if (model.includes('opus')) {
    return 'provider-a,backend-large';
  }
  return null;
};
"""

    def setUp(self):
        readers._ccr_rules_cache = ("", [])

    def tearDown(self):
        readers._ccr_rules_cache = ("", [])

    def _router_at(self, tmp, text=None):
        path = Path(tmp) / "custom-router.js"
        path.write_text(text if text is not None else self.ROUTER_JS, encoding="utf-8")
        return mock.patch.object(readers.config, "CCR_ROUTER_FILE", str(path))

    def test_parse_ccr_rules_keeps_order_and_merges_multi_needle(self):
        rules = readers._parse_ccr_rules(self.ROUTER_JS)
        self.assertEqual([
            ("direct-x", "direct-x"),
            ("request-y", "backend-y"),
            ("request-y-legacy", "backend-y"),
            ("haiku", "backend-small"),
            ("sonnet", "backend-balanced"),
            ("opus", "backend-large"),
        ], rules)

    def test_parse_ccr_rules_captures_every_alias_on_one_line(self):
        text = """if (model.includes('request-a') || model.includes('request-a-old')) {
  return 'provider-a,backend-a';
}
if (model.includes(\"request-b\") || model.includes('request-b-old')) { return 'provider-b,backend-b'; }
"""
        self.assertEqual([
            ("request-a", "backend-a"),
            ("request-a-old", "backend-a"),
            ("request-b", "backend-b"),
            ("request-b-old", "backend-b"),
        ], readers._parse_ccr_rules(text))

    def test_unsupported_return_clears_pending_needles(self):
        router = """if (model.includes('sonnet')) return 'glm-5.3';
if (model.includes('multi-comma')) return 'provider-a,backend-x,unexpected';
if (model.includes('opus')) return 'provider-a,backend-x';
if (model.includes('haiku')) return null;
if (model.includes('direct-x')) return 'provider-a,direct-x';
"""
        self.assertEqual([
            ("opus", "backend-x"),
            ("direct-x", "direct-x"),
        ], readers._parse_ccr_rules(router))

    def test_resolve_uses_matching_local_router_rule(self):
        with tempfile.TemporaryDirectory() as tmp, self._router_at(tmp):
            self.assertEqual("backend-large", readers._resolve_model("claude-opus-5"))
            self.assertEqual("backend-small", readers._resolve_model("claude-haiku-4-5"))
            self.assertEqual("backend-balanced", readers._resolve_model("sonnet"))

    def test_resolve_preserves_model_when_router_missing_or_unmatched(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = str(Path(tmp) / "missing.js")
            with mock.patch.object(readers.config, "CCR_ROUTER_FILE", missing):
                self.assertEqual("claude-opus-5", readers._resolve_model("claude-opus-5"))
        with tempfile.TemporaryDirectory() as tmp, self._router_at(tmp):
            self.assertEqual("claude-unknown-5", readers._resolve_model("claude-unknown-5"))
            self.assertEqual("backend-unlisted", readers._resolve_model("backend-unlisted"))

    def test_resolve_preserves_router_backend_even_when_name_looks_like_tier(self):
        router = """if (model.includes('opus')) { return 'provider-a,claude-sonnet-backend'; }
if (model.includes('sonnet')) { return 'provider-b,backend-balanced'; }
"""
        with tempfile.TemporaryDirectory() as tmp, self._router_at(tmp, router):
            self.assertEqual("claude-sonnet-backend", readers._resolve_model("claude-sonnet-backend"))
            self.assertEqual("claude-opus-backend", readers._resolve_model("claude-opus-backend"))
            self.assertEqual("claude-sonnet-backend", readers._resolve_model("claude-opus-5"))

    def test_gemini_and_codex_models_are_not_resolved_through_claude_router(self):
        router = """if (model.includes('sonnet')) { return 'provider-a,backend-balanced'; }
if (model.includes('opus')) { return 'provider-b,backend-large'; }
"""
        with tempfile.TemporaryDirectory() as tmp, self._router_at(tmp, router):
            gemini_log = Path(tmp) / "gemini.json"
            gemini_log.write_text(json.dumps({
                "sessionId": "synthetic-gemini",
                "messages": [{
                    "type": "gemini",
                    "model": "gemini-sonnet-research",
                    "timestamp": "2026-07-01T00:00:00Z",
                    "tokens": {"input": 1, "output": 2, "total": 3},
                }],
            }), encoding="utf-8")
            codex_log = Path(tmp) / "codex.jsonl"
            codex_log.write_text("\n".join([
                json.dumps({
                    "type": "event_msg",
                    "payload": {"type": "turn_context", "model": "codex-opus-compatible"},
                }),
                json.dumps({
                    "type": "event_msg",
                    "timestamp": "2026-07-01T00:00:00Z",
                    "payload": {
                        "type": "token_count",
                        "info": {"last_token_usage": {
                            "input_tokens": 1,
                            "output_tokens": 2,
                            "total_tokens": 3,
                        }},
                    },
                }),
            ]) + "\n", encoding="utf-8")

            self.assertEqual("gemini-sonnet-research", readers.gemini_parse(gemini_log)[0]["model"])
            self.assertEqual("codex-opus-compatible", readers.codex_parse(codex_log)[0]["model"])

    def test_pretty_model_preserves_logged_and_router_backend_names(self):
        names = (
            "glm-5.3",
            "gpt-5.6-sol",
            "deepseek-v4-pro",
            "custom-model",
        )
        for name in names:
            with self.subTest(name=name):
                self.assertEqual(name, readers.config.pretty_model(name))
        self.assertEqual("(unknown)", readers.config.pretty_model(None))

    def test_read_all_reparses_when_router_signature_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "session-x.jsonl"
            log.write_text(json.dumps({
                "type": "assistant",
                "timestamp": "2026-07-01T00:00:00Z",
                "sessionId": "x",
                "message": {"id": "m1", "model": "claude-opus-5",
                            "usage": {"input_tokens": 1, "output_tokens": 2}},
            }) + "\n", encoding="utf-8")
            router = Path(tmp) / "custom-router.js"
            router.write_text(
                "if (model.includes('opus')) { return 'provider-a,backend-a'; }\n",
                encoding="utf-8",
            )
            cache_file = Path(tmp) / "records-test.json"
            with mock.patch.object(readers.config, "CLAUDE_PROJECTS", tmp), \
                    mock.patch.object(readers.config, "CACHE_DIR", tmp), \
                    mock.patch.object(readers.config, "CACHE_FILE", str(cache_file)), \
                    mock.patch.object(readers.config, "CCR_ROUTER_FILE", str(router)):
                first = readers.read_all(sources=["claude"], use_cache=True)
                self.assertEqual(1, len(first))
                self.assertEqual("backend-a", first[0]["model"])
                router.write_text(
                    "if (model.includes('opus')) { return 'provider-a,backend-b'; }\n",
                    encoding="utf-8",
                )
                st = router.stat()
                os.utime(router, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))
                second = readers.read_all(sources=["claude"], use_cache=True)
                self.assertEqual(1, len(second))
                self.assertEqual("backend-b", second[0]["model"])
                cache = json.loads(cache_file.read_text(encoding="utf-8"))
                self.assertEqual(readers.CACHE_VERSION, cache["_v"])
                self.assertEqual(readers._ccr_signature(), cache["_router"])


if __name__ == "__main__":
    unittest.main()
