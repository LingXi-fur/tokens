"""费用账本端到端测试：合成三源日志 → 真实 reader → build_payload（真实
cost 块，不手工注入/覆盖）→ 真实 dashboard HTML → Playwright 验证分量计价
与 unknown。

- 全部日志为合成 fixture，不读私人数据；不发外部 API / 供应商请求；不访问
  本地 8765 服务。
- PipelineTests 不依赖 UI：锁定 reader→payload 三源计费口径。
- CostEndToEndUiTests 默认使用 repo 自带 dashboard_assets 直接可运行；
  TOKENS_COST_E2E_ASSETS 仅作可选 override（指向另一份资产目录）。
  浏览器引擎沿用项目惯例 TOKENS_DASHBOARD_BROWSER（chromium/webkit）。
- 价格全部通过真实编辑器 UI 填写并保存（fill + #cost-save），不直接写
  localStorage；unknown（tool>0）记录不可计价。
"""

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from tokens_cli import dashboard_payload, dashboard_wire, readers, report_dashboard  # noqa: E402

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

ASSETS_OVERRIDE = os.environ.get("TOKENS_COST_E2E_ASSETS", "")
GENERATED = datetime(2026, 7, 5, 12, 0)

# ---- 合成 fixture：三源各一条可信 + 一条 Gemini tool>0 unknown ----------
CLAUDE_USAGE = {
    "input_tokens": 100,
    "output_tokens": 40,
    "cache_read_input_tokens": 1000,
    "cache_creation_input_tokens": 200,
}
# billing parts = [input, output, cache_read, cache_write, thoughts]
CLAUDE_PARTS = [100, 40, 1000, 200, 0]
CLAUDE_TOTAL = 1340

CODEX_USAGE = {
    "input_tokens": 1000,
    "output_tokens": 200,
    "cached_input_tokens": 300,
    "reasoning_output_tokens": 100,
    "total_tokens": 1200,
}
# cached ⊆ input 扣除、输出取原始 outp（reasoning 不重复计）：
# [1000-300, 200, 300, 0, 0]，sum=1200 与 total 守恒。
CODEX_PARTS = [700, 200, 300, 0, 0]
CODEX_TOTAL = 1200

GEMINI_TOKENS = {
    "input": 50, "output": 30, "cached": 20, "thoughts": 10,
    "tool": 0, "total": 110,
}
GEMINI_PARTS = [50, 30, 20, 0, 10]
GEMINI_TOTAL = 110

GEMINI_TOOL_TOKENS = {
    "input": 50, "output": 30, "cached": 0, "thoughts": 0,
    "tool": 5, "total": 115,
}
# tool 无法归属可定价分量 → 整条 unknown（parts 全 0，total/calls 保留）。

# 每百万 token 单价（字符串进编辑器）：金额 = Σ(part/1e6 × rate)。
RATES = {
    "claude": ["1000", "2000", "500", "800", "0"],   # $0.84
    "codex": ["3000", "2500", "1000", "0", "0"],     # $2.90
    "gemini": ["4000", "6000", "2000", "0", "12000"],  # $0.54
}
# claude: (100·1000 + 40·2000 + 1000·500 + 200·800)/1e6 = 0.84
# codex:  (700·3000 + 200·2500 + 300·1000)/1e6      = 2.90
# gemini: (50·4000 + 30·6000 + 20·2000 + 10·12000)/1e6 = 0.54
EXPECTED_SUBTOTAL = "$4.28"  # 0.84 + 2.90 + 0.54；tool unknown 行不计价。默认币种 USD。


def _write_claude_log(tmp, usage, model="claude-e2e-model", ts="2026-07-01T01:00:00Z"):
    path = Path(tmp) / "session-e2e-claude.jsonl"
    path.write_text(json.dumps({
        "type": "assistant",
        "timestamp": ts,
        "sessionId": "e2e-claude",
        "message": {"id": "m1", "model": model, "usage": usage},
    }) + "\n", encoding="utf-8")
    return path


def _write_gemini_log(tmp, tokens, model="gemini-e2e-model",
                      ts="2026-07-02T01:00:00Z", name="session-e2e-gem.json"):
    path = Path(tmp) / name
    path.write_text(json.dumps({
        "sessionId": "e2e-gem",
        "messages": [{
            "type": "gemini",
            "model": model,
            "timestamp": ts,
            "tokens": tokens,
        }],
    }), encoding="utf-8")
    return path


def _write_codex_log(tmp, usage, model="codex-e2e-model", ts="2026-07-03T01:00:00Z"):
    path = Path(tmp) / "rollout-e2e.jsonl"
    path.write_text("\n".join([
        json.dumps({"type": "event_msg",
                    "payload": {"type": "turn_context", "model": model}}),
        json.dumps({"type": "event_msg", "timestamp": ts,
                    "payload": {"type": "token_count",
                                "info": {"last_token_usage": usage}}}),
    ]) + "\n", encoding="utf-8")
    return path


def _e2e_records(tmp):
    """合成三源日志经真实 SOURCES 注册表（真实 parse 函数）读出 records。"""
    paths = {
        "claude": _write_claude_log(tmp, CLAUDE_USAGE),
        "codex": _write_codex_log(tmp, CODEX_USAGE),
    }
    ok_log = _write_gemini_log(tmp, GEMINI_TOKENS)
    tool_log = _write_gemini_log(
        tmp, GEMINI_TOOL_TOKENS, model="gemini-e2e-tool-model",
        ts="2026-07-02T02:00:00Z", name="session-e2e-gem-tool.json")
    fake_sources = {
        "claude": (lambda: [str(paths["claude"])], readers.claude_parse),
        "gemini": (lambda: [str(ok_log), str(tool_log)], readers.gemini_parse),
        "codex": (lambda: [str(paths["codex"])], readers.codex_parse),
    }
    with mock.patch.dict(readers.SOURCES, fake_sources), \
            mock.patch.object(
                readers.config, "CCR_ROUTER_FILE",
                os.path.join(tmp, "nonexistent-router.json")):
        records = readers.read_all(
            sources=["claude", "gemini", "codex"], use_cache=False)
    return records


def _build_e2e_payload(records):
    """真实 build_payload：cost 块由后端聚合产出，不手工覆盖。"""
    with mock.patch(
        "tokens_cli.dashboard_payload.readers.build_session_index",
        return_value={},
    ), mock.patch(
        "tokens_cli.dashboard_payload.readers.session_title",
        return_value="",
    ), mock.patch(
        "tokens_cli.dashboard_payload.readers.load_session_summaries",
        return_value={},
    ):
        return dashboard_payload.build_payload(
            records,
            since="2026-07-01",
            until="2026-07-03",
            sources=["claude", "gemini", "codex"],
            generated_at=GENERATED,
            session_titles={},
        )


def _cost_rows_by_model(cost):
    out = {}
    for day, model_index, parts, reported_total, calls, uncertain in cost["rows"]:
        entry = cost["models"][model_index]
        key = (entry["source"], entry["model"])
        row = out.setdefault(key, [[0] * 5, 0, 0, False])
        for i, value in enumerate(parts):
            row[0][i] += value
        row[1] += reported_total
        row[2] += calls
        row[3] = row[3] or uncertain
    return out


class PipelineTests(unittest.TestCase):
    """不依赖 UI 的端到端口径锁定：真实 reader → build_payload。"""

    def test_three_source_billing_parts_exact(self):
        with tempfile.TemporaryDirectory() as tmp:
            records = _e2e_records(tmp)
        self.assertEqual(4, len(records))
        payload = _build_e2e_payload(records)
        cost = payload["cost"]
        self.assertFalse(cost["total_incomplete"])
        rows = _cost_rows_by_model(cost)
        # Claude：cache_read/cache_write 均为可计价分量，total=1340 精确。
        claude = rows[("claude", "claude-e2e-model")]
        self.assertEqual(CLAUDE_PARTS, claude[0])
        self.assertEqual(CLAUDE_TOTAL, claude[1])
        self.assertEqual(1, claude[2])
        self.assertFalse(claude[3])
        # Codex：reasoning 不重复计（output 分量=原始 200，非 300），
        # cached 扣除后 input=700 且 cache_read=300，sum 守恒 1200。
        codex = rows[("codex", "codex-e2e-model")]
        self.assertEqual(CODEX_PARTS, codex[0])
        self.assertEqual(CODEX_TOTAL, codex[1])
        self.assertEqual(1, codex[2])
        self.assertFalse(codex[3])
        # Gemini 可信条目：thoughts 独立分量。
        gemini = rows[("gemini", "gemini-e2e-model")]
        self.assertEqual(GEMINI_PARTS, gemini[0])
        self.assertEqual(GEMINI_TOTAL, gemini[1])
        self.assertEqual(1, gemini[2])
        self.assertFalse(gemini[3])
        # Gemini tool>0：整条 unknown，parts 全 0、total/calls 保留。
        tool = rows[("gemini", "gemini-e2e-tool-model")]
        self.assertEqual([0, 0, 0, 0, 0], tool[0])
        self.assertEqual(115, tool[1])
        self.assertEqual(1, tool[2])
        self.assertTrue(tool[3])


@unittest.skipIf(sync_playwright is None, "Playwright is not installed")
class CostEndToEndUiTests(unittest.TestCase):
    """真实 dashboard HTML + Playwright：三源分量计价、默认空价、unknown。

    默认用 repo 自带 dashboard_assets；TOKENS_COST_E2E_ASSETS 指向另一份
    资产目录时优先使用该目录（可选 override，非运行必要条件）。
    """

    BROWSER = os.environ.get("TOKENS_DASHBOARD_BROWSER", "chromium")

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        records = _e2e_records(cls._tmp.name)
        payload = _build_e2e_payload(records)
        render = None
        if ASSETS_OVERRIDE:
            asset_dir = Path(ASSETS_OVERRIDE)
            for name in ("cost_core.js", "dashboard.js", "dashboard.css", "template.html"):
                if not (asset_dir / name).is_file():
                    raise unittest.SkipTest(
                        "TOKENS_COST_E2E_ASSETS 缺少 %s：%s" % (name, asset_dir))

            def _read_from_dir(name):
                return (asset_dir / name).read_text(encoding="utf-8")

            with mock.patch.object(report_dashboard, "_read_asset", _read_from_dir):
                template = report_dashboard._dashboard_template()
            render = mock.patch.object(
                report_dashboard, "_TEMPLATE", template, create=True)
            render.start()
        html = report_dashboard.render_dashboard(
            dashboard_wire.encode_payload(payload))
        if render is not None:
            render.stop()
        cls._html_path = Path(cls._tmp.name) / "cost-e2e.html"
        cls._html_path.write_text(html, encoding="utf-8")
        cls._playwright = sync_playwright().start()
        try:
            cls._browser = getattr(cls._playwright, cls.BROWSER).launch(
                headless=True)
        except Exception as exc:
            cls._playwright.stop()
            cls._tmp.cleanup()
            raise unittest.SkipTest("%s is unavailable: %s" % (cls.BROWSER, exc))

    @classmethod
    def tearDownClass(cls):
        cls._browser.close()
        cls._playwright.stop()
        cls._tmp.cleanup()

    # -- harness ---------------------------------------------------------

    def new_page(self):
        context = self._browser.new_context(
            viewport={"width": 1280, "height": 820},
            color_scheme="light",
        )
        page = context.new_page()
        page_errors, console_errors = [], []
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        page.on(
            "console",
            lambda message: console_errors.append(message.text)
            if message.type == "error"
            else None,
        )
        page.goto(self._html_path.as_uri(), wait_until="load")
        return context, page, page_errors, console_errors

    def open_ledger(self, page):
        page.locator("#section-cost").scroll_into_view_if_needed()
        page.wait_for_function(
            "() => document.querySelectorAll('#cost-body .cost-bar-row, "
            "#cost-body .cost-empty, #cost-body .cost-empty-inline').length > 0"
        )

    def price_via_editor(self, page, source, model, rates):
        """真实编辑器流程：打开 → 逐分量 fill → 保存 → 等待关闭与生效。"""
        page.click("#cost-price-btn")
        page.wait_for_selector("#cost-modal.open")
        # 价格键 = JSON.stringify([source, model])，紧凑无空格。
        key = json.dumps([source, model], separators=(",", ":"))
        inputs = page.locator(
            "#cost-editor-list input[data-cost-key='%s'][data-cost-part]" % key)
        assert inputs.count() == 5, "应有 5 个分量输入：%s" % key
        for part, value in enumerate(rates):
            inputs.nth(part).fill(value)
        page.click("#cost-save")
        page.wait_for_function(
            "() => !document.getElementById('cost-modal')"
            ".classList.contains('open')"
        )

    def assert_no_errors(self, page_errors, console_errors):
        self.assertEqual(page_errors, [])
        self.assertEqual(console_errors, [])

    def chips(self, page):
        return page.locator(".cost-chip").all_inner_texts()

    # -- tests -----------------------------------------------------------

    def test_default_empty_price_is_not_priced(self):
        """默认空价：显示待定价而非 0/全额，unknown tool 行单独标注。"""
        context, page, page_errors, console_errors = self.new_page()
        self.open_ledger(page)
        self.assertEqual(page.locator(".cost-value").inner_text(), "—")
        self.assertIn("待定价", page.locator(".cost-hero-label").inner_text())
        bar_rows = page.locator(".cost-bar-row")
        self.assertEqual(3, bar_rows.count())  # tool unknown 行不进 bar
        for i in range(bar_rows.count()):
            self.assertIn(
                "is-pending",
                bar_rows.nth(i).get_attribute("class"),
                "空价时所有已知行均为待定价",
            )
        chips = self.chips(page)
        self.assertTrue(
            any("口径未确认" in c and "1 次" in c for c in chips), chips)
        self.assert_no_errors(page_errors, console_errors)
        context.close()

    def test_known_prices_exact_amount_via_real_editor(self):
        """真实编辑器 fill+save 定价三源：exact 金额验证分量口径。"""
        context, page, page_errors, console_errors = self.new_page()
        self.open_ledger(page)
        self.price_via_editor(
            page, "claude", "claude-e2e-model", RATES["claude"])
        self.price_via_editor(
            page, "codex", "codex-e2e-model", RATES["codex"])
        self.price_via_editor(
            page, "gemini", "gemini-e2e-model", RATES["gemini"])
        page.wait_for_function(
            "() => document.querySelector('.cost-value') && "
            "document.querySelector('.cost-value').textContent !== '—'"
        )
        # $0.84 + $2.90 + $0.54 = $4.28；Codex 若重复计 reasoning 或
        # 不扣 cached，Claude 若漏 cache 计价，此精确值都会变。
        self.assertEqual(EXPECTED_SUBTOTAL, page.locator(".cost-value").inner_text())
        # tool unknown 行存在 → 永远只是已定价小计，不是全额估算。
        self.assertIn(
            "已定价小计", page.locator(".cost-hero-label").inner_text())
        page.evaluate(
            "() => { document.getElementById('cost-details').open = true; }")
        detail = page.locator("#cost-table-body").inner_text()
        for expected in ("$0.8400", "$2.9000", "$0.5400"):
            self.assertIn(expected, detail)
        self.assertTrue(
            any("调用覆盖" in c and "3/4" in c for c in self.chips(page)),
            self.chips(page))
        self.assert_no_errors(page_errors, console_errors)
        context.close()

    def test_unknown_tool_record_never_priced(self):
        """tool>0 的 unknown 记录：即使对其定价也不产生任何金额。"""
        context, page, page_errors, console_errors = self.new_page()
        self.open_ledger(page)
        self.price_via_editor(
            page, "claude", "claude-e2e-model", RATES["claude"])
        self.price_via_editor(
            page, "codex", "codex-e2e-model", RATES["codex"])
        self.price_via_editor(
            page, "gemini", "gemini-e2e-model", RATES["gemini"])
        # 对 unknown tool 模型也定价（编辑器不禁止，但计价层必须排除）。
        self.price_via_editor(
            page, "gemini", "gemini-e2e-tool-model",
            ["1000", "1000", "1000", "1000", "1000"])
        self.assertEqual(EXPECTED_SUBTOTAL,
                         page.locator(".cost-value").inner_text())
        self.assertIn(
            "已定价小计", page.locator(".cost-hero-label").inner_text())
        # unknown bar 行不存在，chip 按口径未确认计 1 次。
        self.assertEqual(3, page.locator(".cost-bar-row").count())
        chips = self.chips(page)
        self.assertTrue(
            any("口径未确认" in c and "1 次" in c for c in chips), chips)
        page.evaluate(
            "() => { document.getElementById('cost-details').open = true; }")
        detail = page.locator("#cost-table-body").inner_text()
        self.assertNotIn("$0.0000", detail)  # 不得出现免费冒充已计价
        self.assert_no_errors(page_errors, console_errors)
        context.close()


if __name__ == "__main__":
    unittest.main()
