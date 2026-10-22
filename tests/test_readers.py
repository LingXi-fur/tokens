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


class TimezoneCacheTests(unittest.TestCase):
    def test_cache_reparses_for_timezone_and_preserves_hits_within_zone(self):
        from zoneinfo import ZoneInfo

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "synthetic.log"
            path.write_text("synthetic", encoding="utf-8")
            cache_file = Path(tmp) / "records.json"
            parse = mock.Mock(side_effect=lambda _: [{
                "source": "gemini",
                "ts": "2026-10-18T20:00:00Z",
                "date": readers._to_local_date("2026-10-18T20:00:00Z"),
                "model": "glm-5.3-flash",
                "input": 1, "output": 2, "cache_read": 0, "cache_write": 0,
                "total": 3, "session": "synthetic-session",
                "billing": readers._gemini_billing({
                    "input": 1, "output": 2, "cached": 0,
                    "thoughts": 0, "total": 3,
                }),
            }])
            with mock.patch.object(readers.config, "CACHE_DIR", tmp), \
                    mock.patch.object(readers.config, "CACHE_FILE", str(cache_file)), \
                    mock.patch.object(readers, "_ccr_signature", return_value=None), \
                    mock.patch.dict(readers.SOURCES, {"gemini": (lambda: [str(path)], parse)}, clear=True):
                with mock.patch.object(readers.config, "TZ", ZoneInfo("UTC")):
                    self.assertEqual("2026-10-18", readers.read_all()[0]["date"])
                    self.assertEqual("2026-10-18", readers.read_all()[0]["date"])
                    self.assertEqual(1, parse.call_count)
                with mock.patch.object(readers.config, "TZ", ZoneInfo("Asia/Shanghai")):
                    self.assertEqual("2026-10-19", readers.read_all()[0]["date"])
                    self.assertEqual("2026-10-19", readers.read_all()[0]["date"])
                    self.assertEqual(2, parse.call_count)
                    cache = json.loads(cache_file.read_text(encoding="utf-8"))
                    self.assertEqual("Asia/Shanghai", cache["_timezone"])
                    del cache["_timezone"]
                    cache_file.write_text(json.dumps(cache), encoding="utf-8")
                    self.assertEqual("2026-10-19", readers.read_all()[0]["date"])
                    self.assertEqual(3, parse.call_count)

                with mock.patch.object(readers.config, "TZ", readers.config._SYSTEM_LOCAL_TIMEZONE):
                    readers.read_all()
                    readers.read_all()
                    self.assertEqual(5, parse.call_count)

    def test_uncached_read_never_loads_or_writes_cache(self):
        with mock.patch.object(readers, "_load_cache") as load, \
                mock.patch.object(readers, "_save_cache") as save, \
                mock.patch.object(readers, "_ccr_signature", return_value=None), \
                mock.patch.dict(readers.SOURCES, {"synthetic": (lambda: [], mock.Mock())}, clear=True):
            self.assertEqual([], readers.read_all(use_cache=False))
            load.assert_not_called()
            save.assert_not_called()

    def test_timezone_rebuild_does_not_reuse_other_source_dates(self):
        from zoneinfo import ZoneInfo

        with tempfile.TemporaryDirectory() as tmp:
            paths = {source: Path(tmp) / (source + ".log") for source in ("first", "second")}
            for path in paths.values():
                path.write_text("synthetic", encoding="utf-8")
            parses = {
                source: mock.Mock(side_effect=lambda _, model=source: [{
                    "date": readers._to_local_date("2026-10-18T20:00:00Z"), "model": model,
                }]) for source in paths
            }
            sources = {source: (lambda path=path: [str(path)], parses[source])
                       for source, path in paths.items()}
            with mock.patch.object(readers.config, "CACHE_DIR", tmp), \
                    mock.patch.object(readers.config, "CACHE_FILE", str(Path(tmp) / "records.json")), \
                    mock.patch.object(readers, "_ccr_signature", return_value=None), \
                    mock.patch.dict(readers.SOURCES, sources, clear=True):
                with mock.patch.object(readers.config, "TZ", ZoneInfo("UTC")):
                    self.assertEqual(2, len(readers.read_all()))
                with mock.patch.object(readers.config, "TZ", ZoneInfo("Asia/Shanghai")):
                    self.assertEqual("2026-10-19", readers.read_all(sources=["first"])[0]["date"])
                    self.assertEqual("2026-10-19", readers.read_all(sources=["second"])[0]["date"])
                    self.assertEqual([2, 2], [parse.call_count for parse in parses.values()])

    def test_system_local_fallback_never_reuses_unverifiable_dates(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "synthetic.log"
            path.write_text("synthetic", encoding="utf-8")
            parse = mock.Mock(return_value=[{"date": "2026-10-19"}])
            with mock.patch.object(readers.config, "CACHE_DIR", tmp), \
                    mock.patch.object(readers.config, "CACHE_FILE", str(Path(tmp) / "records.json")), \
                    mock.patch.object(readers.config, "TZ", readers.config._SYSTEM_LOCAL_TIMEZONE), \
                    mock.patch.object(readers, "_ccr_signature", return_value=None), \
                    mock.patch.dict(readers.SOURCES, {"synthetic": (lambda: [str(path)], parse)}, clear=True):
                readers.read_all()
                readers.read_all()
                self.assertEqual(2, parse.call_count)


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


class SessionTitleSanitizeTests(unittest.TestCase):
    def test_keeps_normal_chinese_and_english_titles(self):
        cases = (
            "请优化这个性能热点",
            "Fix the flaky login test",
            "重构 dashboard_payload 聚合逻辑",
        )
        for raw in cases:
            with self.subTest(raw=raw):
                self.assertEqual(raw, readers.sanitize_session_title(raw))

    def test_rejects_continuation_summary_and_system_envelopes(self):
        cases = (
            "This session is being continued from a previous conversation that ran out of context.",
            "以下是对话的摘要\n用户想要重构模块",
            "会话摘要如下：…",
            "<system-reminder>ignore</system-reminder>",
            "<task-notification>do something</task-notification>",
            "{{command output}}",
            "Caveat: The messages below were generated by the user",
        )
        for raw in cases:
            with self.subTest(raw=raw):
                self.assertEqual("", readers.sanitize_session_title(raw))

    def test_rejects_pure_path_id_and_code_block(self):
        cases = (
            "/Users/example/synthetic-project/src/parser.py",
            "C:\\Users\\example\\synthetic-project\\main.py",
            "~/code/tokens",
            "550e8400-e29b-41d4-a716-446655440000",
            "deadbeefdeadbeef1",
            "```python\nprint(1)\n```",
            "$ git status",
        )
        for raw in cases:
            with self.subTest(raw=raw):
                self.assertEqual("", readers.sanitize_session_title(raw))

    def test_rejects_short_filler_instructions(self):
        cases = ("继续", "好的", "嗯", "next", "continue", "ok", "thanks")
        for raw in cases:
            with self.subTest(raw=raw):
                self.assertEqual("", readers.sanitize_session_title(raw))

    def test_uses_first_line_only_and_caps_length(self):
        self.assertEqual("优化性能", readers.sanitize_session_title("优化性能\n第二行无关内容"))
        long_title = "重构" + "模" * 200
        self.assertEqual(readers.TITLE_MAX_LEN, len(readers.sanitize_session_title(long_title)))

    def test_empty_and_none_input(self):
        self.assertEqual("", readers.sanitize_session_title(""))
        self.assertEqual("", readers.sanitize_session_title(None))

    def test_non_string_input_is_safe(self):
        for raw in (42, 3.14, True, ["x"], {"a": 1}):
            with self.subTest(raw=raw):
                self.assertEqual("", readers.sanitize_session_title(raw))

    def test_keeps_path_prefixed_task_description(self):
        cases = (
            "/Users/x/proj/app.py 这个函数为什么报错",
            "C:\\proj\\app.py 为什么崩溃",
        )
        for raw in cases:
            with self.subTest(raw=raw):
                self.assertEqual(raw, readers.sanitize_session_title(raw))

    def test_pure_path_without_description_still_rejected(self):
        for raw in ("/Users/x/proj/app.py", "~/code/tokens"):
            with self.subTest(raw=raw):
                self.assertEqual("", readers.sanitize_session_title(raw))

    def test_keeps_short_task_bearing_titles(self):
        cases = ("修复登录", "Fix login", "查崩溃", "登录", "deploy")
        for raw in cases:
            with self.subTest(raw=raw):
                self.assertEqual(raw, readers.sanitize_session_title(raw))

    def test_rejects_system_notification_envelope_and_meta(self):
        cases = (
            "Today's date is 2026-10-09. / Environment: / [SYSTEM NOTIFICATION - NOT USER INPUT] / "
            "'This session is being continued from a previous conversation...'",
            "Today's date is 2026-10-09.",
            "[SYSTEM NOTIFICATION - NOT USER INPUT] do x",
            "Environment: darwin 27.0",
        )
        for raw in cases:
            with self.subTest(raw=raw):
                self.assertEqual("", readers.sanitize_session_title(raw))

    def test_rejects_short_injected_uuid(self):
        cases = ("a3a851048eaed47cb", "deadbeef", "550e8400-e29b-41d4-a716-446655440000")
        for raw in cases:
            with self.subTest(raw=raw):
                self.assertEqual("", readers.sanitize_session_title(raw))


class SessionTitleReadTests(unittest.TestCase):
    def _write(self, tmp, lines):
        path = Path(tmp) / "session-a.jsonl"
        path.write_text("\n".join(json.dumps(o) for o in lines) + "\n", encoding="utf-8")
        return {"session-a": str(path)}

    def test_checks_multiple_text_blocks_not_only_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            index = self._write(tmp, [{
                "type": "user",
                "message": {"content": [
                    {"type": "text", "text": "继续"},
                    {"type": "text", "text": "请修复支付回调超时的 bug"},
                ]},
            }])
            self.assertEqual(
                "请修复支付回调超时的 bug",
                readers.session_title("session-a", session_index=index),
            )

    def test_scans_multiple_messages_and_skips_pollution(self):
        with tempfile.TemporaryDirectory() as tmp:
            index = self._write(tmp, [
                {"type": "user", "message": {"content": "好的"}},
                {"type": "user", "message": {"content": "/Users/x/y"}},
                {"type": "user", "message": {"content": "设计新的导入向导"}},
            ])
            self.assertEqual("设计新的导入向导", readers.session_title("session-a", session_index=index))

    def test_returns_empty_when_no_reliable_title(self):
        with tempfile.TemporaryDirectory() as tmp:
            index = self._write(tmp, [
                {"type": "user", "message": {"content": "<system-reminder>x</system-reminder>"}},
                {"type": "user", "message": {"content": "继续"}},
            ])
            self.assertEqual("", readers.session_title("session-a", session_index=index))

    def test_bounded_scan_stops_on_line_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            filler = {"type": "user", "message": {"content": "继续"}}
            lines = [filler] * (readers.TITLE_SCAN_MAX_LINES + 5)
            lines.append({"type": "user", "message": {"content": "不该被读到的标题"}})
            index = self._write(tmp, lines)
            with mock.patch("tokens_cli.readers.TITLE_SCAN_MAX_LINES", 10):
                self.assertEqual("", readers.session_title("session-a", session_index=index))

    def test_bounded_scan_stops_on_byte_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            big = {"type": "user", "message": {"content": "x" * 500}}
            lines = [big] * 40 + [{"type": "user", "message": {"content": "超出字节上限的标题"}}]
            index = self._write(tmp, lines)
            with mock.patch("tokens_cli.readers.TITLE_SCAN_MAX_BYTES", 100):
                self.assertEqual("", readers.session_title("session-a", session_index=index))

    def test_byte_limit_counts_utf8_bytes_not_characters(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "session-a.jsonl"
            first = json.dumps(
                {"type": "user", "message": {"content": "继续" + "模" * 20}},
                ensure_ascii=False,
            )
            second = json.dumps(
                {"type": "user", "message": {"content": "真实任务标题"}},
                ensure_ascii=False,
            )
            path.write_text(first + "\n" + second + "\n", encoding="utf-8")
            index = {"session-a": str(path)}
            char_len = len(first + "\n")
            byte_len = len((first + "\n").encode("utf-8"))
            limit = char_len + 5  # 介于字符数与 UTF-8 字节数之间
            self.assertLess(limit, byte_len)
            with mock.patch("tokens_cli.readers.TITLE_SCAN_MAX_BYTES", limit):
                self.assertEqual("", readers.session_title("session-a", session_index=index))

    def test_long_line_read_in_bounded_chunks_not_fully(self):
        # 单行上限生效：整行被 readline 上限切块后无法解析成 JSON 记录，
        # 因此得不到标题——证明未把整行一次性读入。
        with tempfile.TemporaryDirectory() as tmp:
            line = json.dumps({"type": "user", "message": {"content": "有界读取测试标题"}})
            index = self._write(tmp, [json.loads(line)])
            self.assertEqual("有界读取测试标题", readers.session_title("session-a", session_index=index))
            with mock.patch("tokens_cli.readers.MAX_LINE_BYTES", len(line) // 2):
                self.assertEqual("", readers.session_title("session-a", session_index=index))

    def test_giant_line_exhausts_budget_returns_unnamed_without_full_read(self):
        # 巨行无换行：首个分块即耗尽总预算，返回「未命名」，不读满整行。
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "session-a.jsonl"
            path.write_text("x" * 50000, encoding="utf-8")  # 无换行巨行
            index = {"session-a": str(path)}
            with mock.patch("tokens_cli.readers.MAX_LINE_BYTES", 128), \
                 mock.patch("tokens_cli.readers.TITLE_SCAN_MAX_BYTES", 64):
                self.assertEqual("", readers.session_title("session-a", session_index=index))

    def test_giant_single_line_under_real_constants_returns_unnamed(self):
        # 真实常量下超 4MB 无换行行：有界读取耗尽预算即停，返回未命名。
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "session-a.jsonl"
            fill = "x" * (readers.TITLE_SCAN_MAX_BYTES + 4096)
            path.write_text(fill, encoding="utf-8")
            index = {"session-a": str(path)}
            self.assertEqual("", readers.session_title("session-a", session_index=index))


if __name__ == "__main__":
    unittest.main()
