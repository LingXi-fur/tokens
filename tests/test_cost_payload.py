"""费用账本（cost ledger）后端合成用例：reader 计费证据、payload cost 块、
缓存 v4→v5 与 wire 往返。不依赖浏览器；不读取真实日志。"""
import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

import sys as _sys
if str(SRC) not in _sys.path:
    _sys.path.insert(0, str(SRC))

from tokens_cli import config, dashboard_payload, dashboard_wire, readers


def _write_claude_log(tmp, usage, model="claude-backend-x", ts="2026-07-01T01:00:00Z"):
    path = Path(tmp) / "session-cost.jsonl"
    path.write_text(json.dumps({
        "type": "assistant",
        "timestamp": ts,
        "sessionId": "cost-session",
        "message": {"id": "m1", "model": model, "usage": usage},
    }) + "\n", encoding="utf-8")
    return path


def _write_gemini_log(tmp, tokens, model="gemini-pro-x", ts="2026-07-02T01:00:00Z"):
    path = Path(tmp) / "session-cost-gem.json"
    path.write_text(json.dumps({
        "sessionId": "gem-cost",
        "messages": [{
            "type": "gemini",
            "model": model,
            "timestamp": ts,
            "tokens": tokens,
        }],
    }), encoding="utf-8")
    return path


def _write_codex_log(tmp, usage, model="codex-model-x", ts="2026-07-03T01:00:00Z"):
    path = Path(tmp) / "rollout-cost.jsonl"
    path.write_text("\n".join([
        json.dumps({"type": "event_msg",
                    "payload": {"type": "turn_context", "model": model}}),
        json.dumps({"type": "event_msg", "timestamp": ts,
                    "payload": {"type": "token_count",
                                "info": {"last_token_usage": usage}}}),
    ]) + "\n", encoding="utf-8")
    return path


def _no_router(tmp):
    return mock.patch.object(readers.config, "CCR_ROUTER_FILE",
                             str(Path(tmp) / "missing-router.js"))


class ClaudeBillingTests(unittest.TestCase):
    def test_full_usage_billing_parts_and_legacy_stats_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp, _no_router(tmp):
            path = _write_claude_log(tmp, {
                "input_tokens": 70, "output_tokens": 20,
                "cache_read_input_tokens": 10, "cache_creation_input_tokens": 5,
            })
            record = readers.claude_parse(path)[0]
        # 既有统计口径完全不变。
        self.assertEqual(70, record["input"])
        self.assertEqual(20, record["output"])
        self.assertEqual(10, record["cache_read"])
        self.assertEqual(5, record["cache_write"])
        self.assertEqual(105, record["total"])
        billing = record["billing"]
        self.assertEqual(readers.BILLING_SCHEMA, billing["v"])
        self.assertFalse(billing["uncertain"])
        self.assertEqual([70, 20, 10, 5, 0], billing["parts"])
        self.assertEqual(
            {"input": True, "output": True, "cache_read": True, "cache_write": True},
            billing["present"])
        self.assertEqual([], billing["reasons"])

    def test_missing_cache_fields_default_zero_with_presence(self):
        with tempfile.TemporaryDirectory() as tmp, _no_router(tmp):
            path = _write_claude_log(tmp, {"input_tokens": 7, "output_tokens": 3})
            record = readers.claude_parse(path)[0]
        billing = record["billing"]
        self.assertFalse(billing["uncertain"])
        self.assertEqual([7, 3, 0, 0, 0], billing["parts"])
        self.assertFalse(billing["present"]["cache_read"])
        self.assertFalse(billing["present"]["cache_write"])
        # 既有统计缺省 0 不变。
        self.assertEqual(0, record["cache_read"])
        self.assertEqual(10, record["total"])

    def test_missing_required_input_is_uncertain_not_free(self):
        with tempfile.TemporaryDirectory() as tmp, _no_router(tmp):
            path = _write_claude_log(tmp, {"output_tokens": 3})
            record = readers.claude_parse(path)[0]
        billing = record["billing"]
        self.assertTrue(billing["uncertain"])
        self.assertEqual([0, 0, 0, 0, 0], billing["parts"])
        self.assertIn("missing_input", billing["reasons"])
        self.assertFalse(billing["present"]["input"])

    def test_invalid_cache_value_degrades_without_crash(self):
        with tempfile.TemporaryDirectory() as tmp, _no_router(tmp):
            path = _write_claude_log(tmp, {
                "input_tokens": 7, "output_tokens": 3,
                "cache_read_input_tokens": 2 ** 53,  # 超 JS 安全整数
            })
            record = readers.claude_parse(path)[0]
        billing = record["billing"]
        self.assertTrue(billing["uncertain"])
        self.assertEqual([0, 0, 0, 0, 0], billing["parts"])
        self.assertIn("invalid_cache_read", billing["reasons"])


class CodexBillingTests(unittest.TestCase):
    USAGE = {
        "input_tokens": 100, "cached_input_tokens": 30,
        "output_tokens": 50, "reasoning_output_tokens": 20,
        "total_tokens": 150,
    }

    def _parse(self, usage):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_codex_log(tmp, usage)
            return readers.codex_parse(path)[0]

    def test_input_excludes_cache_output_raw_and_stats_unchanged(self):
        record = self._parse(dict(self.USAGE))
        # 既有统计：input 含 cached、output 加 reason、total 用 total_tokens。
        self.assertEqual(100, record["input"])
        self.assertEqual(70, record["output"])
        self.assertEqual(30, record["cache_read"])
        self.assertEqual(150, record["total"])
        billing = record["billing"]
        self.assertFalse(billing["uncertain"])
        # 计费输入扣 cached；计费输出仅原始 output，不加 reason。
        self.assertEqual([70, 50, 30, 0, 0], billing["parts"])
        self.assertEqual([], billing["reasons"])

    def test_cache_exceeds_input_is_uncertain(self):
        usage = dict(self.USAGE, cached_input_tokens=120, total_tokens=150)
        billing = self._parse(usage)["billing"]
        self.assertTrue(billing["uncertain"])
        self.assertEqual([0, 0, 0, 0, 0], billing["parts"])
        self.assertIn("cache_exceeds_input", billing["reasons"])

    def test_reasoning_exceeds_output_is_uncertain(self):
        usage = dict(self.USAGE, reasoning_output_tokens=60)
        billing = self._parse(usage)["billing"]
        self.assertTrue(billing["uncertain"])
        self.assertIn("reasoning_exceeds_output", billing["reasons"])

    def test_missing_total_is_uncertain(self):
        usage = {k: v for k, v in self.USAGE.items() if k != "total_tokens"}
        record = self._parse(usage)
        billing = record["billing"]
        self.assertTrue(billing["uncertain"])
        self.assertIn("missing_total", billing["reasons"])
        self.assertEqual([0, 0, 0, 0, 0], billing["parts"])

    def test_missing_raw_output_is_uncertain(self):
        usage = {k: v for k, v in self.USAGE.items() if k != "output_tokens"}
        billing = self._parse(usage)["billing"]
        self.assertTrue(billing["uncertain"])
        self.assertIn("missing_output", billing["reasons"])

    def test_total_mismatch_is_uncertain(self):
        usage = dict(self.USAGE, total_tokens=999)
        billing = self._parse(usage)["billing"]
        self.assertTrue(billing["uncertain"])
        self.assertIn("total_mismatch", billing["reasons"])


class GeminiBillingTests(unittest.TestCase):
    TOKENS = {"input": 10, "output": 20, "cached": 5, "thoughts": 8,
              "tool": 0, "total": 43}

    def _parse(self, tokens):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_gemini_log(tmp, tokens)
            return readers.gemini_parse(path)[0]

    def test_thoughts_separate_and_stats_unchanged(self):
        record = self._parse(dict(self.TOKENS))
        # 既有统计：output 含 thoughts、total 用源值。
        self.assertEqual(10, record["input"])
        self.assertEqual(28, record["output"])
        self.assertEqual(5, record["cache_read"])
        self.assertEqual(43, record["total"])
        billing = record["billing"]
        self.assertFalse(billing["uncertain"])
        # thoughts 单列分量；无 cache write 概念（schema 级 0）。
        self.assertEqual([10, 20, 5, 0, 8], billing["parts"])
        self.assertEqual([], billing["reasons"])

    def test_tool_tokens_make_whole_record_uncertain(self):
        record = self._parse({"input": 10, "output": 20, "cached": 5,
                              "thoughts": 8, "tool": 3, "total": 46})
        billing = record["billing"]
        self.assertTrue(billing["uncertain"])
        self.assertEqual([0, 0, 0, 0, 0], billing["parts"])
        self.assertIn("unattributed_tool", billing["reasons"])

    def test_total_mismatch_is_uncertain(self):
        record = self._parse(dict(self.TOKENS, total=40))
        billing = record["billing"]
        self.assertTrue(billing["uncertain"])
        self.assertIn("total_mismatch", billing["reasons"])

    def test_missing_thoughts_is_uncertain_not_free(self):
        tokens = {k: v for k, v in self.TOKENS.items() if k != "thoughts"}
        tokens["total"] = 35
        billing = self._parse(tokens)["billing"]
        self.assertTrue(billing["uncertain"])
        self.assertIn("missing_thoughts", billing["reasons"])
        self.assertFalse(billing["present"]["thoughts"])


class BillingViewTests(unittest.TestCase):
    def test_legacy_record_without_billing_is_uncertain(self):
        parts, uncertain = readers.billing_view({"model": "m"})
        self.assertEqual([0, 0, 0, 0, 0], parts)
        self.assertTrue(uncertain)

    def test_malformed_evidence_degrades_to_uncertain(self):
        for billing in (
            {"v": 0, "parts": [1, 1, 1, 1, 1], "uncertain": False},
            {"v": 1, "parts": [1, 2], "uncertain": False},
            {"v": 1, "parts": [1, -2, 0, 0, 0], "uncertain": False},
            {"v": 1, "parts": [1, True, 0, 0, 0], "uncertain": False},
            {"v": 1, "parts": [1, 2, 3, 4, 5], "uncertain": True},
            "not-a-dict",
        ):
            with self.subTest(billing=billing):
                parts, uncertain = readers.billing_view({"billing": billing})
                self.assertEqual([0, 0, 0, 0, 0], parts)
                self.assertTrue(uncertain)

    def test_trusted_parts_pass_through(self):
        parts, uncertain = readers.billing_view({
            "total": 35,
            "billing": {"v": 1, "parts": [9, 8, 7, 6, 5], "uncertain": False},
        })
        self.assertEqual([9, 8, 7, 6, 5], parts)
        self.assertFalse(uncertain)

    def test_schema_bool_and_non_bool_uncertain_rejected(self):
        for billing in (
            {"v": True, "parts": [1, 0, 0, 0, 0], "uncertain": False},
            {"v": 1, "parts": [1, 0, 0, 0, 0], "uncertain": "no"},
            {"v": 1, "parts": [1, 0, 0, 0, 0], "uncertain": 0},
            {"v": 1, "parts": [1, 0, 0, 0, 0], "uncertain": None},
        ):
            with self.subTest(billing=billing):
                parts, uncertain = readers.billing_view(
                    {"total": 1, "billing": billing})
                self.assertEqual([0, 0, 0, 0, 0], parts)
                self.assertTrue(uncertain)

    def test_trusted_parts_must_conserve_to_record_total(self):
        # 伪可信 billing：parts 全 0 但 record.total=10 → 不得当免费全价。
        parts, uncertain = readers.billing_view(
            {"total": 10, "billing": _trusted([0, 0, 0, 0, 0])})
        self.assertEqual([0, 0, 0, 0, 0], parts)
        self.assertTrue(uncertain)
        # 缺 total 键无法守恒 → unknown。
        parts, uncertain = readers.billing_view(
            {"billing": _trusted([1, 0, 0, 0, 0])})
        self.assertEqual([0, 0, 0, 0, 0], parts)
        self.assertTrue(uncertain)
        # 守恒成立才放行。
        parts, uncertain = readers.billing_view(
            {"total": 3, "billing": _trusted([1, 2, 0, 0, 0])})
        self.assertEqual([1, 2, 0, 0, 0], parts)
        self.assertFalse(uncertain)


def _record(day, model, total, billing=None, source="claude", ts=None):
    return {
        "source": source,
        "ts": ts or (day + "T10:00:00Z"),
        "date": day,
        "model": model,
        "input": total,
        "output": 0,
        "cache_read": 0,
        "cache_write": 0,
        "total": total,
        "session": "s-" + model,
        "cwd": "/synthetic/" + model,
        "billing": billing,
    }


def _trusted(parts):
    return {"v": 1, "parts": list(parts), "uncertain": False,
            "reasons": [], "present": {}}


GENERATED = datetime(2026, 7, 5, 12, 0)


class CostPayloadTests(unittest.TestCase):
    def build(self, records, **kwargs):
        kwargs.setdefault("session_titles", {})
        kwargs.setdefault("generated_at", GENERATED)
        return dashboard_payload.build_payload(records, **kwargs)

    def test_cost_contract_shape_and_safe_parts(self):
        records = [
            _record("2026-07-01", "model-a", 100, _trusted([70, 20, 10, 0, 0])),
            _record("2026-07-01", "model-b", 50, _trusted([30, 20, 0, 0, 0]),
                    source="codex"),
            _record("2026-07-01", "model-c", 30, None, source="gemini"),
        ]
        payload = self.build(records)
        cost = payload["cost"]
        self.assertEqual(1, cost["schema"])
        # 可选 total_incomplete：正常数据 false 且必为 bool。
        self.assertFalse(cost["total_incomplete"])
        self.assertIsInstance(cost["total_incomplete"], bool)
        self.assertEqual(
            ["input", "output", "cache_read", "cache_write", "thoughts"],
            cost["components"])
        for entry in cost["models"]:
            self.assertEqual(
                {"source", "model", "identity", "hidden"}, set(entry))
            self.assertIsInstance(entry["hidden"], bool)
        for row in cost["rows"]:
            day, model_index, parts, reported_total, calls, uncertain = row
            self.assertIsInstance(day, str)
            self.assertIsInstance(model_index, int)
            self.assertIsInstance(reported_total, int)
            self.assertIsInstance(calls, int)
            self.assertIsInstance(uncertain, bool)
            self.assertEqual(5, len(parts))
            for value in parts:
                self.assertIsInstance(value, int)
                self.assertGreaterEqual(value, 0)
        # 无 billing 的旧记录 → uncertain 行保留原 total/calls。
        uncertain_rows = [row for row in cost["rows"] if row[5]]
        self.assertEqual(1, len(uncertain_rows))
        self.assertEqual([0, 0, 0, 0, 0], uncertain_rows[0][2])
        self.assertEqual(30, uncertain_rows[0][3])
        self.assertEqual(1, uncertain_rows[0][4])

    def test_legacy_payload_fields_unchanged_by_billing(self):
        records = [
            _record("2026-07-01", "model-a", 100, _trusted([70, 20, 10, 0, 0])),
            _record("2026-07-02", "model-b", 50, None, source="gemini"),
        ]
        stripped = [
            {k: v for k, v in record.items() if k != "billing"}
            for record in records
        ]
        with_billing = self.build(records)
        without_billing = self.build(stripped)
        for key in with_billing:
            if key in ("cost", "snapshot"):
                continue
            self.assertEqual(without_billing[key], with_billing[key], key)
        # 无计费证据时全部行为 uncertain。
        self.assertTrue(all(row[5] for row in without_billing["cost"]["rows"]))

    def test_mask_grouping_and_aggregation(self):
        records = [
            _record("2026-07-01", "model-a", 10, _trusted([10, 0, 0, 0, 0])),
            _record("2026-07-01", "model-a", 5, _trusted([0, 5, 0, 0, 0])),
            _record("2026-07-01", "model-a", 7, _trusted([7, 0, 0, 0, 0])),  # 同 mask 合并
            _record("2026-07-02", "model-a", 3, _trusted([1, 2, 0, 0, 0])),
        ]
        cost = self.build(records)["cost"]
        index = {
            (entry["source"], entry["model"]): i
            for i, entry in enumerate(cost["models"])
        }
        idx = index[("claude", "model-a")]
        rows = [row for row in cost["rows"] if row[1] == idx]
        self.assertEqual(3, len(rows))
        by_day = {}
        for row in rows:
            by_day.setdefault(row[0], []).append(row)
        mask_input = by_day["2026-07-01"][0]
        mask_output = by_day["2026-07-01"][1]
        self.assertEqual([17, 0, 0, 0, 0], mask_input[2])
        self.assertEqual(17, mask_input[3])
        self.assertEqual(2, mask_input[4])
        self.assertFalse(mask_input[5])
        self.assertEqual([0, 5, 0, 0, 0], mask_output[2])
        self.assertEqual(1, mask_output[4])
        self.assertEqual([1, 2, 0, 0, 0], by_day["2026-07-02"][0][2])

    def test_safe_int_row_split_on_aggregation(self):
        max_safe = 2 ** 53 - 1
        near = max_safe - 10
        records = [
            _record("2026-07-01", "model-a", near, _trusted([near, 0, 0, 0, 0])),
            _record("2026-07-01", "model-a", 20, _trusted([20, 0, 0, 0, 0])),
            # uncertain 桶（分量全 0）的 reportedTotal 累加同样要拆 row。
            _record("2026-07-01", "model-b", near, None),
            _record("2026-07-01", "model-b", 15, None),
        ]
        cost = self.build(records)["cost"]
        index = {(entry["source"], entry["model"]): i
                 for i, entry in enumerate(cost["models"])}
        rows_a = [row for row in cost["rows"]
                  if row[1] == index[("claude", "model-a")]]
        rows_b = [row for row in cost["rows"]
                  if row[1] == index[("claude", "model-b")]]
        # 累加超 MAX_SAFE → 拆成两个同 key row，各自仍是安全整数。
        self.assertEqual(2, len(rows_a))
        self.assertEqual([near, 0, 0, 0, 0], rows_a[0][2])
        self.assertEqual([20, 0, 0, 0, 0], rows_a[1][2])
        self.assertEqual(near, rows_a[0][3])
        self.assertEqual(20, rows_a[1][3])
        self.assertFalse(rows_a[0][5])
        self.assertFalse(rows_a[1][5])
        # sum 守恒：拆 row 不丢量、不截断。
        self.assertEqual(near + 20, sum(row[3] for row in rows_a))
        self.assertEqual(near + 20, sum(sum(row[2]) for row in rows_a))
        self.assertEqual(2, sum(row[4] for row in rows_a))
        # uncertain 桶同样拆 row 且守恒，total 仍为整数非字符串。
        self.assertEqual(2, len(rows_b))
        for row in rows_b:
            self.assertEqual([0, 0, 0, 0, 0], row[2])
            self.assertTrue(row[5])
            self.assertIsInstance(row[3], int)
            self.assertLessEqual(row[3], max_safe)
        self.assertEqual(near + 15, sum(row[3] for row in rows_b))
        self.assertEqual(2, sum(row[4] for row in rows_b))
        # 边界恰好等于 MAX_SAFE 不拆（仍在安全范围）。
        exact = self.build([
            _record("2026-07-01", "model-c", max_safe,
                    _trusted([max_safe, 0, 0, 0, 0])),
        ])["cost"]
        idx_c = index.get(("claude", "model-c"))
        idx_c = next(i for i, entry in enumerate(exact["models"])
                     if entry["model"] == "model-c")
        rows_c = [row for row in exact["rows"] if row[1] == idx_c]
        self.assertEqual(1, len(rows_c))
        self.assertEqual(max_safe, rows_c[0][2][0])

    def test_oversized_single_total_chunked_into_unknown_rows(self):
        max_safe = 2 ** 53 - 1
        record = _record("2026-07-01", "model-a", max_safe + 1, None)
        cost = self.build([record])["cost"]
        rows = [row for row in cost["rows"]
                if row[0] == "2026-07-01"
                and cost["models"][row[1]]["model"] == "model-a"]
        # 拆成两个 unknown chunk row：parts 0、calls 只计首 row、sum 精确。
        self.assertEqual(2, len(rows))
        self.assertEqual([max_safe, 1], [row[3] for row in rows])
        self.assertEqual([1, 0], [row[4] for row in rows])
        for row in rows:
            self.assertTrue(row[5])
            self.assertEqual([0, 0, 0, 0, 0], row[2])
            self.assertLessEqual(row[3], max_safe)
        # 每个 row 的 reportedTotal 均为安全整数，无超界数字送 JS。

    def test_abnormal_total_zeroed_and_uncertain(self):
        # 注：字符串型 total 会让既有 _model_registry 聚合在 cost 之前抛
        # TypeError（改动前已存在的 legacy 行为，不属于本次范围）。
        for bad in (True, -5, 2.5):
            record = _record("2026-07-01", "model-a", 10, _trusted([10, 0, 0, 0, 0]))
            record["total"] = bad
            cost = self.build([record])["cost"]
            rows = [row for row in cost["rows"]
                    if cost["models"][row[1]]["model"] == "model-a"]
            with self.subTest(bad=bad):
                self.assertEqual(1, len(rows))
                row = rows[0]
                self.assertTrue(row[5])
                self.assertEqual([0, 0, 0, 0, 0], row[2])
                self.assertEqual(0, row[3])
                self.assertEqual(1, row[4])
                self.assertTrue(cost["total_incomplete"])

    def test_missing_none_false_total_incomplete(self):
        # legacy `total = record.get("total", 0) or 0` 会把 缺失/None/False
        # 吞成 0；cost 检测必须读原始 record["total"]，三者均按异常：
        # unknown（parts 0 / reportedTotal 0 / uncertain / calls 照计）并置旗。
        for label, mutate in (
            ("missing", lambda r: r.pop("total")),
            ("none", lambda r: r.__setitem__("total", None)),
            ("false", lambda r: r.__setitem__("total", False)),
        ):
            record = _record("2026-07-01", "model-a", 10)
            mutate(record)
            cost = self.build([record])["cost"]
            rows = [row for row in cost["rows"]
                    if cost["models"][row[1]]["model"] == "model-a"]
            with self.subTest(label=label):
                self.assertEqual(1, len(rows))
                row = rows[0]
                self.assertTrue(row[5])
                self.assertEqual([0, 0, 0, 0, 0], row[2])
                self.assertEqual(0, row[3])
                self.assertEqual(1, row[4])
                self.assertTrue(cost["total_incomplete"])

    def test_chunk_cap_boundary_exact_64_max_and_one_over(self):
        max_safe = 2 ** 53 - 1
        cap_total = 64 * max_safe
        # 恰好 64 个 MAX chunk：精确保留，不置旗。
        cost = self.build([
            _record("2026-07-01", "model-a", cap_total, None)
        ])["cost"]
        rows = [row for row in cost["rows"]
                if cost["models"][row[1]]["model"] == "model-a"]
        self.assertFalse(cost["total_incomplete"])
        self.assertEqual(64, len(rows))
        self.assertEqual(cap_total, sum(row[3] for row in rows))
        self.assertEqual(1, sum(row[4] for row in rows))
        for row in rows:
            self.assertTrue(row[5])
            self.assertEqual([0, 0, 0, 0, 0], row[2])
            self.assertLessEqual(row[3], max_safe)
        # 超过 64 chunk（64*MAX+1）：不截断冒充数值，置旗 + 整条 unknown 计 0。
        cost = self.build([
            _record("2026-07-01", "model-a", cap_total + 1, None)
        ])["cost"]
        rows = [row for row in cost["rows"]
                if cost["models"][row[1]]["model"] == "model-a"]
        self.assertTrue(cost["total_incomplete"])
        self.assertEqual(1, len(rows))
        row = rows[0]
        self.assertTrue(row[5])
        self.assertEqual([0, 0, 0, 0, 0], row[2])
        self.assertEqual(0, row[3])
        self.assertEqual(1, row[4])

    def test_trusted_parts_conserve_to_reported_total(self):
        cost = self.build([
            _record("2026-07-01", "model-a", 105, _trusted([70, 20, 10, 5, 0])),
        ])["cost"]
        row = cost["rows"][0]
        self.assertFalse(row[5])
        self.assertEqual(sum(row[2]), row[3])

    def test_overflow_models_stay_pricable_and_distinct(self):
        # 超过 identity 容量（7）：overflow 保留原始模型名、identity='other'、
        # hidden=False，可独立定价；相近名称不合并。token 总量区分排名。
        records = [
            _record("2026-07-01", "priv-%d" % i, 10 * (i + 1),
                    _trusted([10 * (i + 1), 0, 0, 0, 0]))
            for i in range(9)
        ]
        cost = self.build(records)["cost"]
        catalog = {(entry["source"], entry["model"]): entry
                   for entry in cost["models"]}
        self.assertEqual(9, len(cost["models"]))
        # 用量最低的 priv-0/priv-1 溢出为 identity='other'，但目录项独立。
        overflow = sorted(name for name in catalog
                          if catalog[name]["identity"] == "other")
        self.assertEqual([("claude", "priv-0"), ("claude", "priv-1")], overflow)
        for key in overflow:
            entry = catalog[key]
            self.assertFalse(entry["hidden"])
            self.assertNotEqual("other", entry["model"])
        for i in range(2, 9):
            entry = catalog[("claude", "priv-%d" % i)]
            self.assertFalse(entry["hidden"])
            self.assertEqual("priv-%d" % i, entry["identity"])
        # gpt-6.1-sol 与 gpt-6-sol 必须是两个独立目录项（排序确定性）。
        distinct = self.build([
            _record("2026-07-01", "gpt-6.1-sol", 10, _trusted([10, 0, 0, 0, 0])),
            _record("2026-07-01", "gpt-6-sol", 20, _trusted([20, 0, 0, 0, 0])),
        ])["cost"]["models"]
        self.assertEqual(
            [("claude", "gpt-6-sol"), ("claude", "gpt-6.1-sol")],
            [(entry["source"], entry["model"]) for entry in distinct])

    def test_anonymized_overflow_merged_hidden_and_uncertain(self):
        records = [
            _record("2026-07-01", "priv-%d" % i, 10 * (i + 1),
                    _trusted([10 * (i + 1), 0, 0, 0, 0]))
            for i in range(9)
        ]
        records.append(_record("2026-07-01", "x-model", 4,
                               _trusted([4, 0, 0, 0, 0]), source="codex"))
        cost = self.build(records, anonymize=True)["cost"]
        encoded = json.dumps(cost, ensure_ascii=False)
        # registry 全局容量 7：priv-8..priv-2 按用量入围后，x-model 以最近活跃
        # 提名顶替 priv-2 → 溢出为 priv-0/priv-1/priv-2，被隐藏的原名不得出现。
        for name in ("priv-0", "priv-1", "priv-2"):
            self.assertNotIn(name, encoded)
        hidden = [(entry["source"], entry["model"])
                  for entry in cost["models"] if entry["hidden"]]
        self.assertEqual([("claude", "other")], hidden)
        visible = [entry for entry in cost["models"] if not entry["hidden"]]
        # 匿名下保留原名可见（6 个 claude + codex x-model），隐藏桶合并 3 条记录。
        self.assertEqual(7, len(visible))
        self.assertIn(
            ("codex", "x-model"),
            [(entry["source"], entry["model"]) for entry in visible])
        claude_other = cost["models"][0]
        self.assertEqual("other", claude_other["identity"])
        hidden_rows = [row for row in cost["rows"] if row[1] == 0]
        self.assertEqual(1, len(hidden_rows))
        row = hidden_rows[0]
        # 合并桶不可定价：整条 uncertain、分量全 0，但 total/calls 保留。
        self.assertTrue(row[5])
        self.assertEqual([0, 0, 0, 0, 0], row[2])
        self.assertEqual(60, row[3])
        self.assertEqual(3, row[4])

    def test_range_filtering_applies_to_cost(self):
        records = [
            _record("2026-07-01", "model-a", 10, _trusted([10, 0, 0, 0, 0])),
            _record("2026-07-02", "model-a", 20, _trusted([0, 20, 0, 0, 0])),
            _record("2026-07-03", "model-a", 30, None),
        ]
        cost = self.build(records, since="2026-07-02", until="2026-07-02")["cost"]
        self.assertEqual(["2026-07-02"], sorted({row[0] for row in cost["rows"]}))

    def test_calls_and_totals_match_legacy_stats(self):
        records = [
            _record("2026-07-01", "model-a", 10, _trusted([10, 0, 0, 0, 0])),
            _record("2026-07-01", "model-a", 5, _trusted([5, 0, 0, 0, 0])),
            _record("2026-07-01", "model-a", 3, None),
            _record("2026-07-02", "model-a", 7, _trusted([7, 0, 0, 0, 0])),
        ]
        payload = self.build(records)
        cost = payload["cost"]
        index = {
            (entry["source"], entry["model"]): i
            for i, entry in enumerate(cost["models"])
        }
        idx = index[("claude", "model-a")]
        for day_stats in payload["day"]:
            rows = [row for row in cost["rows"]
                    if row[0] == day_stats["period"] and row[1] == idx]
            self.assertEqual(
                day_stats["model_calls"]["model-a"],
                sum(row[4] for row in rows))
            self.assertEqual(
                day_stats["models"]["model-a"],
                sum(row[3] for row in rows))

    def test_deterministic_order_and_stable_indexes(self):
        records = [
            _record("2026-07-01", "model-b", 10, _trusted([10, 0, 0, 0, 0])),
            _record("2026-07-01", "model-a", 10, _trusted([10, 0, 0, 0, 0])),
        ]
        first = self.build(records)
        second = self.build(list(reversed(records)))
        self.assertEqual(first["cost"], second["cost"])
        models = [(entry["source"], entry["model"]) for entry in first["cost"]["models"]]
        self.assertEqual(sorted(models), models)
        row_keys = [(row[0], row[1], row[5]) for row in first["cost"]["rows"]]
        self.assertEqual(sorted(row_keys), row_keys)

    def test_cost_participates_in_snapshot_identity(self):
        base = [_record("2026-07-01", "model-a", 10, _trusted([10, 0, 0, 0, 0]))]
        other = [_record("2026-07-01", "model-a", 10, _trusted([0, 10, 0, 0, 0]))]
        id_a = self.build(base)["snapshot"]["id"]
        id_b = self.build(list(base))["snapshot"]["id"]
        id_c = self.build(other)["snapshot"]["id"]
        self.assertEqual(id_a, id_b)
        self.assertNotEqual(id_a, id_c)

    def test_wire_roundtrip_preserves_cost(self):
        records = [
            _record("2026-07-01", "model-a", 10, _trusted([10, 0, 0, 0, 0])),
            _record("2026-07-01", "model-b", 4, None, source="gemini"),
        ]
        payload = self.build(records)
        wire = dashboard_wire.encode_payload(payload)
        self.assertEqual(payload, dashboard_wire.decode_payload(wire))

    def test_same_raw_model_per_source_entries(self):
        records = [
            _record("2026-07-01", "shared-model", 10, _trusted([10, 0, 0, 0, 0])),
            _record("2026-07-01", "shared-model", 20, _trusted([20, 0, 0, 0, 0]),
                    source="codex"),
        ]
        models = self.build(records)["cost"]["models"]
        self.assertEqual(
            [("claude", "shared-model"), ("codex", "shared-model")],
            [(entry["source"], entry["model"]) for entry in models])


class CacheVersionTests(unittest.TestCase):
    def test_cache_version_and_filename(self):
        self.assertEqual(7, readers.CACHE_VERSION)
        self.assertTrue(config.CACHE_FILE.endswith("records-v7.json"))

    def test_v5_cache_left_in_place_and_v6_rebuilds(self):
        # Keep the original regression method; its rebuild target is now v7.
        with tempfile.TemporaryDirectory() as tmp:
            log = _write_claude_log(tmp, {"input_tokens": 1, "output_tokens": 2})
            # 旧 v5/v6 缓存自然作废重解析；文件本身不删除。
            old_caches = []
            for version in (5, 6):
                old_cache = Path(tmp) / f"records-v{version}.json"
                old_cache.write_text(json.dumps({
                    "_v": version,
                    "claude::" + str(log): {
                        "key": "stale|stale",
                        "records": [{"source": "claude", "date": "2000-01-01",
                                     "model": "wrong-model", "total": 1}],
                    },
                }), encoding="utf-8")
                old_caches.append((version, old_cache, old_cache.read_bytes()))
            new_cache = Path(tmp) / "records-v7.json"
            with mock.patch.object(readers.config, "CLAUDE_PROJECTS", tmp), \
                    mock.patch.object(readers.config, "CACHE_DIR", tmp), \
                    mock.patch.object(readers.config, "CACHE_FILE", str(new_cache)), \
                    mock.patch.object(readers.config, "CCR_ROUTER_FILE",
                                      str(Path(tmp) / "missing-router.js")):
                records = readers.read_all(sources=["claude"], use_cache=True)
            self.assertEqual(1, len(records))
            self.assertEqual("claude-backend-x", records[0]["model"])
            self.assertEqual(3, records[0]["total"])
            self.assertTrue(new_cache.exists())
            self.assertEqual(7, json.loads(new_cache.read_text(encoding="utf-8"))["_v"])
            for version, old_cache, original in old_caches:
                self.assertEqual(original, old_cache.read_bytes())
                self.assertEqual(version, json.loads(original)["_v"])
            self.assertIn("billing", records[0])


if __name__ == "__main__":
    unittest.main()
