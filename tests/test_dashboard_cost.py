"""Independent Playwright suite for the 费用账本 (Cost Ledger) dashboard module.

Synthetic only: every page is built from mock records via build_payload, with a
hand-written ``cost`` block injected afterwards (the backend contract is fixed;
the backend aggregation itself is out of scope here). No private logs, no
network, no screenshots. Browser selection via TOKENS_DASHBOARD_BROWSER
(webkit supported). Run this file alone; it is not part of the full regression.
"""

import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

import sys
sys.path.insert(0, str(SRC))

from tokens_cli import dashboard_wire, report_dashboard

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

COST_PARTS = ["input", "output", "cache_read", "cache_write", "thoughts"]


def price_key(model, source="claude"):
    """Canonical price key: must match JS JSON.stringify([source, model])."""
    return json.dumps([source, model], separators=(",", ":"))


def record(date, model, total, session):
    return {
        "source": "claude",
        "ts": date + "T09:00:00+08:00",
        "date": date,
        "model": model,
        "input": total // 2,
        "output": total // 4,
        "cache_read": total // 4,
        "cache_write": 0,
        "total": total,
        "session": session,
        "cwd": "/synthetic/cost-fixture",
    }


def cost_block(models, rows, total_incomplete=None):
    """models: [(model, identity, hidden)] -> fixed contract shape."""
    block = {
        "schema": 1,
        "components": list(COST_PARTS),
        "models": [
            {"source": "claude", "model": model, "identity": identity, "hidden": hidden}
            for model, identity, hidden in models
        ],
        "rows": rows,
    }
    if total_incomplete is not None:
        block["total_incomplete"] = total_incomplete
    return block


@unittest.skipIf(sync_playwright is None, "Playwright is not installed")
class DashboardCostTests(unittest.TestCase):
    BROWSER = os.environ.get("TOKENS_DASHBOARD_BROWSER", "chromium")

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        out = Path(cls._tmp.name)

        def build(records, since, until, generated_at, cost=None):
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
                payload = report_dashboard.build_payload(
                    records,
                    since=since,
                    until=until,
                    sources=["claude"],
                    generated_at=generated_at,
                )
            if cost is not None:
                payload["cost"] = cost
            else:
                # Newer backends auto-attach a cost block; simulate a legacy
                # snapshot by stripping it so the regenerate notice is tested.
                payload.pop("cost", None)
            return report_dashboard.render_dashboard(
                dashboard_wire.encode_payload(payload)
            )

        # Two models across two ISO weeks (07-01/02 in week one, 07-20 in week four).
        cls._identities = ["model-a", "model-b"]
        base_records = [
            record("2026-07-01", "model-a", 1000, "synthetic-cost-a1"),
            record("2026-07-01", "model-b", 1200, "synthetic-cost-b1"),
            record("2026-07-02", "model-a", 900, "synthetic-cost-a2"),
            record("2026-07-20", "model-a", 600, "synthetic-cost-a3"),
        ]
        cls._cost = cost_block(
            [("model-a", "model-a", False), ("model-b", "model-b", False)],
            [
                ["2026-07-01", 0, [1_000_000, 0, 0, 0, 0], 1_000_000, 10, False],
                ["2026-07-01", 1, [2_000_000, 500_000, 0, 0, 0], 2_500_000, 4, False],
                ["2026-07-02", 0, [0, 0, 3_000_000, 0, 0], 3_000_000, 6, False],
                ["2026-07-20", 0, [500_000, 0, 0, 0, 0], 500_000, 2, False],
            ],
        )
        cls._path = out / "cost-dashboard.html"
        cls._path.write_text(
            build(base_records, "2026-07-01", "2026-07-31",
                  datetime(2026, 8, 10, 12, 0), cls._cost),
            encoding="utf-8",
        )

        # Legacy payload without a cost block.
        cls._legacy_path = out / "cost-dashboard-legacy.html"
        cls._legacy_path.write_text(
            build(base_records, "2026-07-01", "2026-07-31",
                  datetime(2026, 8, 10, 12, 0), None),
            encoding="utf-8",
        )

        # Catalog of 14 entries for pagination checks (7 identities from payload).
        catalog = [(f"model-{i:02d}", cls._identities[i % 2], False) for i in range(14)]
        cls._catalog_path = out / "cost-dashboard-catalog.html"
        cls._catalog_path.write_text(
            build(base_records, "2026-07-01", "2026-07-31",
                  datetime(2026, 8, 10, 12, 0),
                  cost_block(
                        catalog,
                        [
                            ["2026-07-01", i, [100 * (i + 1), 0, 0, 0, 0],
                             100 * (i + 1), 1, False]
                            for i in range(14)
                        ],
                  )),
            encoding="utf-8",
        )

        # Same-bucket split into multiple rows whose grand sum exceeds 2**53-1,
        # plus one row with an individually unsafe (non-safe-int) part value.
        cls._split_path = out / "cost-dashboard-split.html"
        cls._split_path.write_text(
            build(base_records, "2026-07-01", "2026-07-31",
                  datetime(2026, 8, 10, 12, 0),
                  cost_block(
                        [("model-a", "model-a", False), ("model-b", "model-b", False)],
                        [
                            ["2026-07-01", 0, [4_600_000_000_000_000, 0, 0, 0, 0],
                             4_600_000_000_000_000, 1, False],
                            ["2026-07-02", 0, [4_600_000_000_000_000, 0, 0, 0, 0],
                             4_600_000_000_000_000, 3, False],
                            ["2026-07-02", 1, [10_000_000_000_000_000, 0, 0, 0, 0],
                             10_000_000_000_000_000, 1, False],
                        ],
                  )),
            encoding="utf-8",
        )

        # Uncertain + invalid rows both land in unknown coverage, never billed.
        cls._unknown_path = out / "cost-dashboard-unknown.html"
        cls._unknown_path.write_text(
            build(base_records, "2026-07-01", "2026-07-31",
                  datetime(2026, 8, 10, 12, 0),
                  cost_block(
                        [("model-a", "model-a", False), ("model-b", "model-b", False)],
                        [
                            ["2026-07-01", 0, [1_000, 0, 0, 0, 0], 1_000, 1, False],
                            ["2026-07-01", 1, [100, 0, 0, 0, 0], 100, 2, True],
                            ["2026/07/01", 0, [50, 0, 0, 0, 0], 50, 5, False],
                        ],
                        total_incomplete=True,
                  )),
            encoding="utf-8",
        )

        # Hidden (anonymized) catalog model.
        cls._hidden_path = out / "cost-dashboard-hidden.html"
        cls._hidden_path.write_text(
            build(base_records, "2026-07-01", "2026-07-31",
                  datetime(2026, 8, 10, 12, 0),
                  cost_block(
                        [("model-a", "model-a", False), ("model-b", "model-b", True)],
                        [
                            ["2026-07-01", 0, [1_000_000, 0, 0, 0, 0], 1_000_000, 3, False],
                            ["2026-07-01", 1, [2_000_000, 0, 0, 0, 0], 2_000_000, 2, False],
                        ],
                  )),
            encoding="utf-8",
        )

        # Partial token coverage: 999 covered of 1,000 total -> 99.9%.
        cls._partial_path = out / "cost-dashboard-partial.html"
        cls._partial_path.write_text(
            build(base_records, "2026-07-01", "2026-07-31",
                  datetime(2026, 8, 10, 12, 0),
                  cost_block(
                        [("model-a", "model-a", False)],
                        [
                            ["2026-07-01", 0, [999, 0, 0, 0, 0], 999, 1, False],
                            ["2026-07-02", 0, [1, 0, 0, 0, 0], 1, 1, True],
                        ],
                  )),
            encoding="utf-8",
        )

        # Row pointing at a malformed catalog entry: counted into coverage as
        # unknown (never billed), so call coverage can never exceed 100%.
        cls._badmodel_path = out / "cost-dashboard-badmodel.html"
        cls._badmodel_path.write_text(
            build(base_records, "2026-07-01", "2026-07-31",
                  datetime(2026, 8, 10, 12, 0),
                  cost_block(
                        [("model-a", "model-a", False), (None, None, False)],
                        [
                            ["2026-07-01", 1, [500, 0, 0, 0, 0], 500, 3, False],
                        ],
                  )),
            encoding="utf-8",
        )

        cls._playwright = sync_playwright().start()
        try:
            cls._browser = getattr(cls._playwright, cls.BROWSER).launch(headless=True)
        except Exception as exc:
            cls._playwright.stop()
            cls._tmp.cleanup()
            raise unittest.SkipTest(f"{cls.BROWSER} is unavailable: {exc}")

    @classmethod
    def tearDownClass(cls):
        cls._browser.close()
        cls._playwright.stop()
        cls._tmp.cleanup()

    # -- harness ---------------------------------------------------------

    def new_page(self, *, path=None, viewport=None, init_scripts=()):
        context = self._browser.new_context(
            viewport=viewport or {"width": 1280, "height": 820},
            color_scheme="light",
            reduced_motion="no-preference",
        )
        page = context.new_page()
        for script in init_scripts:
            page.add_init_script(script)
        page_errors, console_errors = [], []
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        page.on(
            "console",
            lambda message: console_errors.append(message.text)
            if message.type == "error"
            else None,
        )
        target = path or self._path
        page.goto(target.as_uri(), wait_until="load")
        return context, page, page_errors, console_errors

    def open_ledger(self, page, path=None):
        """Scroll the cost card into view and wait until it renders."""
        page.locator("#section-cost").scroll_into_view_if_needed()
        page.wait_for_function(
            "() => document.querySelectorAll('#cost-body .cost-bar-row, "
            "#cost-body .cost-empty, #cost-body .cost-empty-inline').length > 0"
        )

    def seed_prices(self, page, prices, currency="CNY"):
        page.evaluate(
            """value => {
                 localStorage.setItem('tk-cost-v1', JSON.stringify(value));
                 costPrices = costLoadConfig();
                 costPriceRevision += 1;
                 invalidateDerived();
                 renderLazy('cost', true);
               }""",
            prices,
        )

    def full_config(self):
        return {
            "v": 1,
            "currency": "CNY",
            "prices": {
                price_key("model-a"): {
                    "rates": ["1", "0", "0.5", "0", "0"], "note": ""},
                price_key("model-b"): {
                    "rates": ["0.5", "0.25", "", "", ""], "note": ""},
            },
        }

    def assertNoErrors(self, page_errors, console_errors):
        self.assertEqual(page_errors, [])
        self.assertEqual(console_errors, [])

    # -- tests -----------------------------------------------------------

    def test_legacy_payload_shows_regenerate_notice_and_disables_pricing(self):
        context, page, page_errors, console_errors = self.new_page(path=self._legacy_path)
        self.open_ledger(page)
        body = page.locator("#cost-body").inner_text()
        self.assertIn("旧版快照没有计价数据", body)
        self.assertIn("重新生成", body)
        self.assertTrue(page.locator("#cost-price-btn").is_disabled())
        self.assertFalse(page.locator("#cost-details").is_visible())
        self.assertNoErrors(page_errors, console_errors)
        context.close()

    def test_no_prices_dash_then_editor_pricing_flow(self):
        context, page, page_errors, console_errors = self.new_page()
        self.open_ledger(page)
        self.assertEqual(page.locator(".cost-value").inner_text(), "—")
        self.assertIn("待定价", page.locator(".cost-hero-label").inner_text())
        self.assertGreater(page.locator(".cost-bar-row.is-pending").count(), 0)
        # Price model-a through the editor, save, subtotal (model-b still pending).
        page.click("#cost-price-btn")
        page.wait_for_selector("#cost-modal.open")
        inputs = page.locator(
            '#cost-editor-list input[data-cost-key=\'["claude","model-a"]\'][data-cost-part]'
        )
        for part, value in enumerate(["1", "0", "0.5", "0", "0"]):
            inputs.nth(part).fill(value)
        page.click("#cost-save")
        page.wait_for_function(
            "() => !document.getElementById('cost-modal').classList.contains('open')"
        )
        page.wait_for_function(
            "() => document.querySelector('.cost-value') && "
            "document.querySelector('.cost-value').textContent !== '—'"
        )
        self.assertEqual(page.locator(".cost-value").inner_text(), "$3.00")
        self.assertIn("已定价小计", page.locator(".cost-hero-label").inner_text())
        # Price model-b as well -> full estimate with half-up rounding.
        page.click("#cost-price-btn")
        inputs_b = page.locator(
            '#cost-editor-list input[data-cost-key=\'["claude","model-b"]\'][data-cost-part]'
        )
        inputs_b.nth(0).fill("0.5")
        inputs_b.nth(1).fill("0.25")
        page.click("#cost-save")
        page.wait_for_function(
            "() => document.querySelector('.cost-hero-label').textContent.includes('估算总费用')"
        )
        self.assertEqual(page.locator(".cost-value").inner_text(), "$4.13")
        stored = page.evaluate("() => localStorage.getItem('tk-cost-v1')")
        self.assertEqual(json.loads(stored)["currency"], "USD")
        self.assertIn(price_key("model-b"), json.loads(stored)["prices"])
        self.assertNoErrors(page_errors, console_errors)
        context.close()

    def test_full_pricing_precise_detail_amounts(self):
        context, page, page_errors, console_errors = self.new_page()
        self.seed_prices(page, self.full_config())
        self.open_ledger(page)
        self.assertEqual(page.locator(".cost-value").inner_text(), "¥4.13")
        page.evaluate("() => { document.getElementById('cost-details').open = true; }")
        rows = page.locator("#cost-table-body tr")
        self.assertEqual(rows.count(), 2)
        texts = [rows.nth(i).inner_text() for i in range(rows.count())]
        self.assertTrue(any("¥3.0000" in t for t in texts), texts)
        self.assertTrue(any("¥1.1250" in t for t in texts), texts)
        self.assertTrue(any("已定价" in t for t in texts), texts)
        self.assertNoErrors(page_errors, console_errors)
        context.close()

    def test_zero_free_price_and_small_amount_flooring(self):
        context, page, page_errors, console_errors = self.new_page()
        self.seed_prices(page, {
            "v": 1, "currency": "CNY", "prices": {
                price_key("model-a"):
                    {"rates": ["0.000001", "0", "0.000001", "", ""], "note": ""},
                price_key("model-b"):
                    {"rates": ["0", "0", "", "", ""], "note": ""},
            },
        })
        self.open_ledger(page)
        # model-a: 1.5M tokens * 1e-6 -> 0.0015 -> '<0.01'; model-b free -> ¥0.00.
        row_texts = page.locator(".cost-bar-row").all_inner_texts()
        self.assertTrue(any("¥0.00" in t for t in row_texts), row_texts)
        self.assertEqual(page.locator(".cost-value").inner_text(), "¥<0.01")
        page.evaluate("() => { document.getElementById('cost-details').open = true; }")
        detail = page.locator("#cost-table-body").inner_text()
        self.assertIn("<0.0001", detail)
        # Zero price is legal (free), so the hero is still a full estimate.
        self.assertIn("估算总费用", page.locator(".cost-hero-label").inner_text())
        self.assertNoErrors(page_errors, console_errors)
        context.close()

    def test_illegal_rates_block_save_and_focus_first_invalid(self):
        context, page, page_errors, console_errors = self.new_page()
        self.open_ledger(page)
        page.click("#cost-price-btn")
        bad_values = ["-1", "1.1234567", "1000000001", "1,5", "abc"]
        inputs = page.locator(
            '#cost-editor-list input[data-cost-key=\'["claude","model-a"]\'][data-cost-part]'
        )
        for part, value in enumerate(bad_values):
            inputs.nth(part).fill(value)
        invalid = page.locator("#cost-editor-list input.cost-rate.invalid")
        self.assertEqual(invalid.count(), 5)
        self.assertEqual(
            invalid.first.get_attribute("aria-invalid"), "true")
        page.click("#cost-save")
        # Modal stays open, status explains the rule, nothing persisted.
        self.assertTrue(page.locator("#cost-modal").evaluate("el => el.classList.contains('open')"))
        self.assertIn("非法价格", page.locator("#cost-editor-status").inner_text())
        self.assertIsNone(page.evaluate("() => localStorage.getItem('tk-cost-v1')"))
        self.assertEqual(page.evaluate("() => document.activeElement.className"), "cost-rate invalid")
        # Legal values clear the invalid state and save succeeds.
        for part, value in enumerate(["0", "1.5", "1000", "", ""]):
            inputs.nth(part).fill(value)
        page.click("#cost-save")
        page.wait_for_function(
            "() => !document.getElementById('cost-modal').classList.contains('open')"
        )
        self.assertIsNotNone(page.evaluate("() => localStorage.getItem('tk-cost-v1')"))
        self.assertNoErrors(page_errors, console_errors)
        context.close()

    def test_split_rows_sum_exactly_with_bigint_and_unsafe_row_is_unknown(self):
        context, page, page_errors, console_errors = self.new_page(
            path=self._split_path,
        )
        self.seed_prices(page, {
            "v": 1, "currency": "CNY", "prices": {
                price_key("model-a"):
                    {"rates": ["0.001", "", "", "", ""], "note": ""},
            },
        })
        self.open_ledger(page)
        # Two split rows of 4.6e15 input tokens sum to 9.2e15 (past 2**53-1):
        # BigInt keeps the sum exact and priced: 9.2e15 / 1e6 * 0.001 = ¥9,200,000.00.
        self.assertEqual(page.locator(".cost-value").inner_text(), "¥9,200,000.00")
        # The third row's 1e16 part is not a JS safe integer: invalid row ->
        # unknown coverage, so the hero is a subtotal, never a full total.
        self.assertIn("已定价小计", page.locator(".cost-hero-label").inner_text())
        chips = page.locator(".cost-chip").all_inner_texts()
        self.assertTrue(any("非法数据行" in c for c in chips), chips)
        self.assertTrue(any("口径未确认" in c and "1 次" in c for c in chips), chips)
        self.assertTrue(any("调用覆盖 4/5" in c for c in chips), chips)
        page.evaluate("() => { document.getElementById('cost-details').open = true; }")
        self.assertIn("¥9,200,000.0000", page.locator("#cost-table-body").inner_text())
        self.assertIn("9,200,000,000,000,000", page.locator("#cost-table-body").inner_text())
        self.assertNoErrors(page_errors, console_errors)
        context.close()

    def test_uncertain_and_invalid_rows_counted_as_unknown_coverage(self):
        context, page, page_errors, console_errors = self.new_page(
            path=self._unknown_path,
        )
        self.seed_prices(page, {
            "v": 1, "currency": "CNY", "prices": {
                price_key("model-a"):
                    {"rates": ["1000", "0", "0", "0", "0"], "note": ""},
            },
        })
        self.open_ledger(page)
        # Only model-a's verified row is billed; uncertain+invalid join unknown.
        self.assertEqual(page.locator(".cost-value").inner_text(), "¥1.00")
        label = page.locator(".cost-hero-label").inner_text()
        self.assertIn("已定价小计", label)
        chips = page.locator(".cost-chip").all_inner_texts()
        self.assertTrue(any("口径未确认" in c and "7 次" in c for c in chips), chips)
        self.assertTrue(any("非法数据行" in c for c in chips), chips)
        self.assertEqual(page.locator(".cost-bar-row").count(), 1)
        # Optional total_incomplete=true: calls coverage chip stays with the
        # exact call ratio, full token totals are replaced by an explicit
        # notice, and no token coverage chip / percentage may render.
        self.assertTrue(any("调用覆盖" in c and "1/8" in c for c in chips), chips)
        self.assertFalse(any("Token 覆盖" in c for c in chips), chips)
        self.assertFalse(any("%" in c for c in chips), chips)
        notices = page.locator(".cost-notice").all_inner_texts()
        self.assertTrue(any("total_incomplete" in t and "Token 总量不可用" in t for t in notices), notices)
        self.assertNoErrors(page_errors, console_errors)
        context.close()

    def test_token_coverage_percent_partial(self):
        context, page, page_errors, console_errors = self.new_page(
            path=self._partial_path,
        )
        self.open_ledger(page)
        # 999 of 1,000 covered tokens must render 99.9% (tenths, half-up),
        # not a 10x-smaller value like 9.9%.
        chips = page.locator(".cost-chip").all_inner_texts()
        self.assertTrue(
            any("Token 覆盖 999/1,000 · 99.9%" in c for c in chips), chips
        )

    def test_bad_catalog_entry_row_keeps_coverage_within_bounds(self):
        context, page, page_errors, console_errors = self.new_page(
            path=self._badmodel_path,
        )
        self.open_ledger(page)
        # A row whose models[idx] is malformed joins totals as unknown: the
        # call/token denominators include it, so coverage never exceeds 100%.
        chips = page.locator(".cost-chip").all_inner_texts()
        self.assertTrue(any("调用覆盖 0/3" in c for c in chips), chips)
        self.assertTrue(
            any("Token 覆盖 0/500 · 0.0%" in c for c in chips), chips
        )
        self.assertTrue(any("非法数据行" in c for c in chips), chips)
        self.assertNoErrors(page_errors, console_errors)
        context.close()

    def test_tooltip_omits_zero_usage_parts(self):
        context, page, page_errors, console_errors = self.new_page()
        self.open_ledger(page)
        # model-a has input + cache_read usage only; the bar tooltip must not
        # list zero-usage parts (BigInt 0n check, not Number 0).
        title = page.locator(".cost-bar-row").first.get_attribute("title")
        self.assertIn("输入", title)
        self.assertIn("缓存读", title)
        self.assertNotIn("输出", title)
        self.assertNotIn("缓存写", title)
        self.assertNotIn("思考", title)
        self.assertNoErrors(page_errors, console_errors)
        context.close()

    def test_editor_focus_trap_cycles_and_escape_closes(self):
        context, page, page_errors, console_errors = self.new_page()
        self.open_ledger(page)
        page.click("#cost-price-btn")
        page.wait_for_selector("#cost-modal.open")
        ends = page.evaluate(
            """() => {
                 const modal = document.getElementById('cost-modal');
                 const items = [...modal.querySelectorAll(
                   'button,input,select,textarea,a[href],[tabindex]:not([tabindex="-1"])'
                 )].filter(x => !x.disabled && x.getClientRects().length);
                 return {firstId: items[0] ? items[0].id : null,
                         lastId: items[items.length - 1]
                           ? items[items.length - 1].id : null};
               }"""
        )
        self.assertIsNotNone(ends["firstId"])
        self.assertIsNotNone(ends["lastId"])
        # Shift+Tab on the first focusable wraps to the last one.
        page.evaluate(
            """() => {
                 const m = document.getElementById('cost-modal');
                 const f = [...m.querySelectorAll(
                   'button,input,select,textarea,a[href],[tabindex]:not([tabindex="-1"])'
                 )].filter(x => !x.disabled && x.getClientRects().length);
                 if (f.length) f[0].focus();
               }"""
        )
        page.keyboard.press("Shift+Tab")
        focused_shift = page.evaluate(
            """() => {
                 const m = document.getElementById('cost-modal');
                 const f = [...m.querySelectorAll(
                   'button,input,select,textarea,a[href],[tabindex]:not([tabindex="-1"])'
                 )].filter(x => !x.disabled && x.getClientRects().length);
                 return document.activeElement === f[f.length - 1];
               }"""
        )
        self.assertTrue(focused_shift)
        # Tab on the last focusable wraps back to the first.
        page.evaluate(
            """() => {
                 const m = document.getElementById('cost-modal');
                 const f = [...m.querySelectorAll(
                   'button,input,select,textarea,a[href],[tabindex]:not([tabindex="-1"])'
                 )].filter(x => !x.disabled && x.getClientRects().length);
                 if (f.length) f[f.length - 1].focus();
               }"""
        )
        page.keyboard.press("Tab")
        focused_tab = page.evaluate(
            """() => {
                 const m = document.getElementById('cost-modal');
                 const f = [...m.querySelectorAll(
                   'button,input,select,textarea,a[href],[tabindex]:not([tabindex="-1"])'
                 )].filter(x => !x.disabled && x.getClientRects().length);
                 return document.activeElement === f[0];
               }"""
        )
        self.assertTrue(focused_tab)
        # Escape closes the modal without saving.
        page.keyboard.press("Escape")
        page.wait_for_function(
            "() => !document.getElementById('cost-modal').classList.contains('open')"
        )
        self.assertNoErrors(page_errors, console_errors)
        context.close()

    def test_hidden_model_is_pending_and_disabled_in_editor(self):
        context, page, page_errors, console_errors = self.new_page(
            path=self._hidden_path,
        )
        self.open_ledger(page)
        rows = page.locator(".cost-bar-row").all_inner_texts()
        self.assertTrue(any("隐藏 · 待定价" in t for t in rows), rows)
        self.assertEqual(page.locator(".cost-value").inner_text(), "—")
        page.click("#cost-price-btn")
        hidden_inputs = page.locator(
            '#cost-editor-list input[data-cost-key=\'["claude","model-b"]\'][data-cost-part]'
        )
        for i in range(hidden_inputs.count()):
            self.assertTrue(hidden_inputs.nth(i).is_disabled())
        hint = page.locator(".cost-ed-hint").all_inner_texts()
        self.assertTrue(any("匿名快照" in t for t in hint), hint)
        page.click("#cost-cancel")
        self.assertNoErrors(page_errors, console_errors)
        context.close()

    def test_scope_respects_model_filter_granularity_and_focus(self):
        context, page, page_errors, console_errors = self.new_page()
        self.seed_prices(page, self.full_config())
        self.open_ledger(page)
        # Model filter: drop model-b entirely.
        removed = page.evaluate(
            """() => {
                 state.models.delete('model-b');
                 invalidateDerived();
                 return costView().entries.map(e => e.model.model);
               }"""
        )
        self.assertEqual(removed, ["model-a"])
        page.evaluate("() => { state.models = new Set(DATA.models); invalidateDerived(); }")
        # Week granularity with focus on the first week drops the 07-20 row.
        scoped = page.evaluate(
            """() => {
                 state.gran = 'week';
                 state.focusPeriod = DATA.week[0].period;
                 invalidateDerived();
                 const view = costView();
                 return {calls: view.totalCalls.toString(), full: view.fullEstimate};
               }"""
        )
        self.assertEqual(scoped["calls"], "20")
        self.assertTrue(scoped["full"])
        # Day granularity focused on 07-20 keeps only that single day.
        day = page.evaluate(
            """() => {
                 state.gran = 'day';
                 state.focusPeriod = '2026-07-20';
                 invalidateDerived();
                 const view = costView();
                 return view.entries.map(e => [e.model.model, e.calls]);
               }"""
        )
        self.assertEqual(day, [["model-a", 2]])
        self.assertNoErrors(page_errors, console_errors)
        context.close()

    def test_currency_switch_confirm_clears_and_cancel_restores(self):
        context, page, page_errors, console_errors = self.new_page()
        self.seed_prices(page, self.full_config())
        self.open_ledger(page)
        page.click("#cost-price-btn")
        inputs_a = page.locator(
            '#cost-editor-list input[data-cost-key=\'["claude","model-a"]\'][data-cost-part]'
        )
        # Cancel: nothing changes.
        page.select_option("#cost-currency", "USD")
        self.assertFalse(page.locator("#cost-currency-confirm").is_hidden())
        page.click("#cost-cur-cancel")
        self.assertTrue(page.locator("#cost-currency-confirm").is_hidden())
        self.assertEqual(page.eval_on_selector("#cost-currency", "el => el.value"), "CNY")
        self.assertEqual(inputs_a.nth(0).input_value(), "1")
        # Confirm: currency switches, draft rates cleared, notes kept.
        page.evaluate(
            """() => {
                 Object.values(costDraft.prices).forEach(e => { e.note = 'keep'; });
               }"""
        )
        page.select_option("#cost-currency", "USD")
        page.click("#cost-cur-ok")
        self.assertEqual(page.eval_on_selector("#cost-currency", "el => el.value"), "USD")
        self.assertEqual(inputs_a.nth(0).input_value(), "")
        note = page.locator(
            '#cost-editor-list input[data-cost-key=\'["claude","model-a"]\'][data-cost-note]'
        )
        self.assertEqual(note.input_value(), "keep")
        # Escape closes the modal without saving.
        page.keyboard.press("Escape")
        page.wait_for_function(
            "() => !document.getElementById('cost-modal').classList.contains('open')"
        )
        self.assertEqual(
            json.loads(page.evaluate("() => localStorage.getItem('tk-cost-v1')"))["currency"],
            "CNY",
        )
        self.assertNoErrors(page_errors, console_errors)
        context.close()

    def test_editor_lists_all_catalog_models_across_pages_despite_filter(self):
        context, page, page_errors, console_errors = self.new_page(
            path=self._catalog_path,
        )
        self.open_ledger(page)
        # Filter down to one identity: the editor must still show all 14 entries.
        page.evaluate("() => { state.models = new Set(['model-a']); invalidateDerived(); }")
        page.click("#cost-price-btn")
        self.assertEqual(page.locator(".cost-ed-row").count(), 8)
        self.assertEqual(page.locator("#cost-editor-pager .pager-info").inner_text(), "1 / 2")
        page.click("#cost-editor-pager button[data-step='1']")
        page.wait_for_function(
            "() => document.querySelectorAll('#cost-editor-list .cost-ed-row').length === 6"
        )
        names = page.evaluate(
            """() => [...document.querySelectorAll('#cost-editor-list .cost-ed-model')]
                 .map(el => el.textContent)"""
        )
        self.assertEqual(len(names), 6)
        self.assertIn("model-13", names)
        page.click("#cost-cancel")
        # Reset the identity filter set above before ledger pager checks.
        page.evaluate(
            "() => { state.models = new Set(DATA.models); invalidateDerived(); }"
        )
        # Ledger pager: 14 entries -> 12 per page, keyboard operable.
        self.seed_prices(page, {
            "v": 1, "currency": "CNY", "prices": {
                price_key("model-13"): {"rates": ["1", "", "", "", ""], "note": ""},
            },
        })
        self.assertEqual(page.locator(".cost-bar-row").count(), 12)
        self.assertEqual(page.locator("#cost-pager .pager-info").inner_text(), "1 / 2")
        page.focus("#cost-pager button[data-step='1']")
        page.keyboard.press("Enter")
        page.wait_for_function(
            "() => document.querySelectorAll('#cost-body .cost-bar-row').length === 2"
        )
        self.assertEqual(page.locator("#cost-pager .pager-info").inner_text(), "2 / 2")
        # Out-of-range page state clamps safely.
        page.evaluate("() => { costState.page = 99; renderCostLedger(); }")
        self.assertEqual(page.locator("#cost-pager .pager-info").inner_text(), "2 / 2")
        self.assertNoErrors(page_errors, console_errors)
        context.close()

    def test_live_reconcile_preserves_local_prices(self):
        context, page, page_errors, console_errors = self.new_page()
        self.seed_prices(page, self.full_config())
        self.open_ledger(page)
        self.assertEqual(page.locator(".cost-value").inner_text(), "¥4.13")
        page.evaluate(
            """() => { reconcileLiveData(JSON.parse(JSON.stringify(DATA))); }"""
        )
        page.wait_for_function(
            "() => document.querySelector('.cost-value') && "
            "document.querySelector('.cost-value').textContent === '¥4.13'"
        )
        self.assertEqual(
            json.loads(page.evaluate("() => localStorage.getItem('tk-cost-v1')"))["v"], 1
        )
        self.assertNoErrors(page_errors, console_errors)
        context.close()

    def test_corrupt_storage_notice_and_no_overwrite(self):
        context, page, page_errors, console_errors = self.new_page()
        page.evaluate(
            "() => localStorage.setItem('tk-cost-v1', 'not-json{')"
        )
        page.reload(wait_until="load")
        self.open_ledger(page)
        self.assertIn("损坏", page.locator(".cost-notice").inner_text())
        # The corrupt stored value is not touched until an explicit save.
        self.assertEqual(
            page.evaluate("() => localStorage.getItem('tk-cost-v1')"), "not-json{"
        )
        self.assertNoErrors(page_errors, console_errors)
        context.close()

    def test_quota_failure_degrades_to_memory_only(self):
        context, page, page_errors, console_errors = self.new_page(
            init_scripts=["""
                const original = Storage.prototype.setItem;
                Storage.prototype.setItem = function(key, value) {
                  if (key === 'tk-cost-v1') {
                    throw new DOMException('full', 'QuotaExceededError');
                  }
                  return original.call(this, key, value);
                };
            """],
        )
        self.open_ledger(page)
        # Quota failures only surface on write, so no notice yet at load time.
        self.assertEqual(page.locator(".cost-notice").count(), 0)
        page.click("#cost-price-btn")
        inputs = page.locator(
            '#cost-editor-list input[data-cost-key=\'["claude","model-a"]\'][data-cost-part]'
        )
        inputs.nth(0).fill("1")
        inputs.nth(2).fill("1")
        page.click("#cost-save")
        page.wait_for_function(
            "() => !document.getElementById('cost-modal').classList.contains('open')"
        )
        # Save failed to persist but the in-memory config still prices the ledger.
        notice = page.locator(".cost-notice").inner_text()
        self.assertIn("不可用", notice)
        self.assertIn("仅本次内存有效", notice)
        page.wait_for_function(
            "() => document.querySelector('.cost-value') && "
            "document.querySelector('.cost-value').textContent === '$4.50'"
        )
        self.assertIsNone(page.evaluate("() => localStorage.getItem('tk-cost-v1')"))
        self.assertNoErrors(page_errors, console_errors)
        context.close()

    def test_language_switch_rerenders_ledger_and_editor(self):
        context, page, page_errors, console_errors = self.new_page()
        self.seed_prices(page, self.full_config())
        self.open_ledger(page)
        self.assertIn("估算总费用", page.locator(".cost-hero-label").inner_text())
        page.click("#lang-btn")
        page.wait_for_function(
            "() => document.querySelector('.cost-hero-label').textContent.includes('Estimated total cost')"
        )
        self.assertIn("CNY", page.locator(".cost-cur").inner_text())
        page.click("#lang-btn")
        page.wait_for_function(
            "() => document.querySelector('.cost-hero-label').textContent.includes('估算总费用')"
        )
        self.assertNoErrors(page_errors, console_errors)
        context.close()

    def test_module_toggle_hides_and_restores_cost_section(self):
        context, page, page_errors, console_errors = self.new_page()
        self.open_ledger(page)
        page.click("#mods-btn")
        page.locator("#mods-pop label").filter(
            has=page.locator("input[data-mod='cost']")
        ).click()
        self.assertEqual(
            page.eval_on_selector("#section-cost", "el => getComputedStyle(el).display"),
            "none",
        )
        page.locator("#mods-pop label").filter(
            has=page.locator("input[data-mod='cost']")
        ).click()
        self.assertNotEqual(
            page.eval_on_selector("#section-cost", "el => getComputedStyle(el).display"),
            "none",
        )
        self.assertNoErrors(page_errors, console_errors)
        context.close()

    def test_theme_switch_keeps_ledger_rendered(self):
        context, page, page_errors, console_errors = self.new_page()
        self.seed_prices(page, self.full_config())
        self.open_ledger(page)
        before = page.locator(".cost-bar-row").count()
        page.click("#theme-btn")
        page.wait_for_timeout(120)
        page.click("#theme-btn")
        page.wait_for_timeout(120)
        self.assertEqual(page.locator(".cost-bar-row").count(), before)
        self.assertEqual(page.locator(".cost-value").inner_text(), "¥4.13")
        self.assertNoErrors(page_errors, console_errors)
        context.close()

    def test_mobile_viewport_no_horizontal_overflow(self):
        context, page, page_errors, console_errors = self.new_page(
            viewport={"width": 390, "height": 780},
        )
        self.seed_prices(page, self.full_config())
        self.open_ledger(page)
        page.evaluate("() => { document.getElementById('cost-details').open = true; }")
        overflow = page.evaluate(
            "() => document.documentElement.scrollWidth - window.innerWidth"
        )
        self.assertLessEqual(overflow, 1)
        self.assertNoErrors(page_errors, console_errors)
        context.close()


# ---- 官方参考价（USD reference prices）回归测试 --------------------------------
#
# Contract under test (tk-cost-v1 reference layer):
#   * 内置 10 模型精确参考价（USD/1M tokens，''=官网未公布不得填 0）。
#   * 默认配置 v1/USD/reference=true/prices={}，且不自动写 tk-cost-v1。
#   * 旧有效配置无 reference 字段按 false；CNY 永不套用 USD 参考价。
#   * 用户 [source, model] 条目整体优先（含显式 0 与全空覆盖）；hidden、
#     带前缀/大小写不同的未知模型名不做猜测（整串精确匹配）。
#   * reference 字段必须为 boolean，非法值按损坏处理且不覆盖原存储。
#   * 编辑器 #cost-reference 开关；参考值只读展示 .cost-ed-reference；
#     手填未改的空输入不创建条目；用户主动编辑后清空则保留全空条目防回填。
#   * 保存持久化 reference；取消不修改配置。CNY 下启用参考需复用
#     #cost-currency-confirm（#cost-cur-ok/#cost-cur-cancel）确认换 USD；
#     待换币未确认时保存不能生效；切 CNY 禁用参考。
#   * 账本标注官方参考估算（非渠道扣费）与命中数；cache_write 未公布但
#     有用量时为待定价而非免费；页面不主动请求供应商网络。

REFERENCE_EXPECTED_RATES = {
    "gpt-6.1-sol": ["2", "10", "0.10", "2.50", ""],
    "gpt-6-sol": ["2", "10", "0.20", "2.50", ""],
    "gpt-5.6-sol": ["4", "20", "0.40", "5", ""],
    "gpt-5.6-luna": ["0.20", "1.20", "0.02", "0.25", ""],
    "gpt-5.6-terra": ["2", "12", "0.20", "2.50", ""],
    "deepseek-flash": ["0.30", "1.20", "0.006", "", ""],
    "deepseek-v4-flash": ["0.30", "1.20", "0.006", "", ""],
    "deepseek-v4-pro": ["1.32", "3.96", "0.044", "", ""],
    "glm-5.2": ["1.40", "4.40", "0.26", "", ""],
    "glm-5.3": ["1.40", "4.40", "0.26", "", ""],
}


def build_reference_page(records, cost):
    """Build a dashboard page with an injected cost block (same mocks as above)."""
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
        payload = report_dashboard.build_payload(
            records,
            since="2026-07-01",
            until="2026-07-31",
            sources=["claude"],
            generated_at=datetime(2026, 8, 10, 12, 0),
        )
    payload["cost"] = cost
    return report_dashboard.render_dashboard(
        dashboard_wire.encode_payload(payload)
    )


@unittest.skipIf(sync_playwright is None, "Playwright is not installed")
class DashboardCostReferenceTests(unittest.TestCase):
    """官方参考价层：默认开启、覆盖优先级、编辑器与换币确认、损坏防护。"""

    BROWSER = os.environ.get("TOKENS_DASHBOARD_BROWSER", "chromium")

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        out = Path(cls._tmp.name)
        # Two identities from real records; catalog rows reuse them.
        records = [
            record("2026-07-01", "model-a", 1000, "synthetic-ref-a1"),
            record("2026-07-01", "model-b", 1200, "synthetic-ref-b1"),
        ]
        # Three whitelisted models plus one non-whitelisted control model.
        # gpt-6.1-sol:  1M in * 2 + 0.5M out * 10            -> $7.00
        # ds-v4-flash:  2M * 0.30 + 1M * 1.20 + 1M * 0.006   -> $1.806
        # glm-5.2:      cache_write 用量、参考价未公布        -> pending, never free
        cls._ref_path = out / "cost-reference.html"
        cls._ref_path.write_text(
            build_reference_page(
                records,
                cost_block(
                    [
                        ("gpt-6.1-sol", "model-a", False),
                        ("deepseek-v4-flash", "model-a", False),
                        ("glm-5.2", "model-b", False),
                        ("model-a", "model-a", False),
                    ],
                    [
                        ["2026-07-01", 0, [1_000_000, 500_000, 0, 0, 0],
                         1_500_000, 1, False],
                        ["2026-07-01", 1, [2_000_000, 1_000_000, 1_000_000, 0, 0],
                         4_000_000, 2, False],
                        ["2026-07-01", 2, [0, 0, 0, 500_000, 0], 500_000, 1, False],
                        ["2026-07-01", 3, [1_000_000, 0, 0, 0, 0],
                         1_000_000, 1, False],
                    ],
                ),
            ),
            encoding="utf-8",
        )
        # Near-miss names must never be guessed: suffix, prefix, different case.
        cls._prefix_path = out / "cost-reference-prefix.html"
        cls._prefix_path.write_text(
            build_reference_page(
                records,
                cost_block(
                    [
                        ("gpt-6.1-sol-2026", "model-a", False),
                        ("azure/gpt-6.1-sol", "model-b", False),
                        ("GPT-6.1-SOL", "model-a", False),
                    ],
                    [
                        ["2026-07-01", i, [1_000_000, 0, 0, 0, 0],
                         1_000_000, 1, False]
                        for i in range(3)
                    ],
                ),
            ),
            encoding="utf-8",
        )
        # Hidden (anonymized) whitelisted model: reference must not apply.
        cls._hidden_ref_path = out / "cost-reference-hidden.html"
        cls._hidden_ref_path.write_text(
            build_reference_page(
                records,
                cost_block(
                    [("gpt-6.1-sol", "model-a", True)],
                    [
                        ["2026-07-01", 0, [1_000_000, 0, 0, 0, 0],
                         1_000_000, 1, False],
                    ],
                ),
            ),
            encoding="utf-8",
        )

        cls._playwright = sync_playwright().start()
        try:
            cls._browser = getattr(cls._playwright, cls.BROWSER).launch(headless=True)
        except Exception as exc:
            cls._playwright.stop()
            cls._tmp.cleanup()
            raise unittest.SkipTest(f"{cls.BROWSER} is unavailable: {exc}")

    @classmethod
    def tearDownClass(cls):
        cls._browser.close()
        cls._playwright.stop()
        cls._tmp.cleanup()

    # -- harness (mirrors DashboardCostTests) ----------------------------

    def new_page(self, *, path=None, viewport=None):
        context = self._browser.new_context(
            viewport=viewport or {"width": 1280, "height": 820},
            color_scheme="light",
            reduced_motion="no-preference",
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
        page.goto((path or self._ref_path).as_uri(), wait_until="load")
        return context, page, page_errors, console_errors

    def open_ledger(self, page, path=None):
        page.locator("#section-cost").scroll_into_view_if_needed()
        page.wait_for_function(
            "() => document.querySelectorAll('#cost-body .cost-bar-row, "
            "#cost-body .cost-empty, #cost-body .cost-empty-inline').length > 0"
        )

    def seed_config(self, page, config):
        page.evaluate(
            """value => {
                 localStorage.setItem('tk-cost-v1', JSON.stringify(value));
                 costPrices = costLoadConfig();
                 costPriceRevision += 1;
                 invalidateDerived();
                 renderLazy('cost', true);
               }""",
            config,
        )

    def stored(self, page):
        raw = page.evaluate("() => localStorage.getItem('tk-cost-v1')")
        return (json.loads(raw) if raw is not None else None), raw

    def open_editor(self, page):
        page.click("#cost-price-btn")
        page.wait_for_selector("#cost-modal.open")
        return page.locator("#cost-reference")

    def close_editor_and_wait(self, page):
        page.wait_for_function(
            "() => !document.getElementById('cost-modal').classList.contains('open')"
        )

    def editor_row(self, page, model):
        return page.locator("#cost-editor-list .cost-ed-row").filter(
            has_text=model
        )

    def assertNoErrors(self, page_errors, console_errors):
        self.assertEqual(page_errors, [])
        self.assertEqual(console_errors, [])

    # -- tests -----------------------------------------------------------

    def test_reference_table_pins_exact_usd_rates_for_all_ten_models(self):
        context, page, page_errors, console_errors = self.new_page()
        self.open_ledger(page)
        table = page.evaluate("() => COST_REFERENCE")
        self.assertEqual(table["currency"], "USD")
        self.assertEqual(set(table["prices"]), set(REFERENCE_EXPECTED_RATES))
        for model, rates in REFERENCE_EXPECTED_RATES.items():
            entry = table["prices"][model]
            self.assertEqual(entry["rates"], rates, model)
            vendor = table["vendors"][entry["vendor"]]
            self.assertTrue(str(vendor["url"]).startswith("https://"), model)
            # Every published rate must parse as a legal price; '' stays ''.
            parse_ok = page.evaluate(
                "rates => rates.every(r => r === '' || costParseRate(r).ok)",
                rates,
            )
            self.assertTrue(parse_ok, model)
        self.assertNoErrors(page_errors, console_errors)
        context.close()

    def test_fresh_storage_defaults_to_usd_reference_on_without_autowrite(self):
        context, page, page_errors, console_errors = self.new_page()
        self.open_ledger(page)
        config = page.evaluate(
            "() => ({v: costPrices.v, currency: costPrices.currency, "
                    "reference: costPrices.reference, "
                    "priceKeys: Object.keys(costPrices.prices).length})"
        )
        self.assertEqual(config["v"], 1)
        self.assertEqual(config["currency"], "USD")
        self.assertTrue(config["reference"])
        self.assertEqual(config["priceKeys"], 0)
        # Loading and rendering never auto-persist a config.
        self.assertIsNone(page.evaluate("() => localStorage.getItem('tk-cost-v1')"))
        self.assertNoErrors(page_errors, console_errors)
        context.close()

    def test_legacy_config_without_reference_field_is_false_and_not_migrated(self):
        context, page, page_errors, console_errors = self.new_page()
        seed = {"v": 1, "currency": "USD", "prices": {}}
        self.seed_config(page, seed)
        self.open_ledger(page)
        config = page.evaluate(
            "() => ({currency: costPrices.currency, "
                    "reference: costPrices.reference})"
        )
        self.assertEqual(config["currency"], "USD")
        self.assertIs(config["reference"], False)
        # Whitelisted model stays pending; nothing rewrites the stored value.
        rows = page.locator(".cost-bar-row").all_inner_texts()
        self.assertTrue(any("gpt-6.1-sol" in t and "待定价" in t for t in rows), rows)
        _, raw = self.stored(page)
        self.assertEqual(json.loads(raw), seed)
        self.assertNotIn("reference", json.loads(raw))
        self.assertNoErrors(page_errors, console_errors)
        context.close()

    def test_cny_config_never_applies_usd_reference(self):
        context, page, page_errors, console_errors = self.new_page()
        self.seed_config(page, {"v": 1, "currency": "CNY", "reference": True,
                                "prices": {}})
        self.open_ledger(page)
        config = page.evaluate(
            "() => ({currency: costPrices.currency, "
                    "reference: costPrices.reference})"
        )
        self.assertEqual(config["currency"], "CNY")
        self.assertTrue(config["reference"])  # stored as-is, but inert in CNY
        body = page.locator("#cost-body").inner_text()
        self.assertNotIn("$", body)
        rows = page.locator(".cost-bar-row").all_inner_texts()
        self.assertTrue(any("gpt-6.1-sol" in t and "待定价" in t for t in rows), rows)
        self.assertEqual(page.locator(".cost-value").inner_text(), "—")
        self.assertNoErrors(page_errors, console_errors)
        context.close()

    def test_reference_prices_rows_subtotal_official_note_and_hit_count(self):
        context, page, page_errors, console_errors = self.new_page()
        self.open_ledger(page)
        rows = page.locator(".cost-bar-row").all_inner_texts()
        self.assertTrue(
            any("gpt-6.1-sol" in t and "$7.00" in t for t in rows), rows)
        self.assertTrue(
            any("deepseek-v4-flash" in t and "$1.81" in t for t in rows), rows)
        self.assertTrue(any("glm-5.2" in t and "待定价" in t for t in rows), rows)
        self.assertTrue(any("model-a" in t and "待定价" in t for t in rows), rows)
        # Subtotal (glm + model-a pending), never presented as a full total.
        self.assertEqual(page.locator(".cost-value").inner_text(), "$8.81")
        self.assertIn("已定价小计", page.locator(".cost-hero-label").inner_text())
        chips = page.locator(".cost-chip").all_inner_texts()
        self.assertTrue(
            any("官方参考命中" in c and "3" in c for c in chips), chips)
        # The ledger labels the estimate as official reference, not charges.
        self.assertIn("官方参考", page.locator(".cost-notes").inner_text())
        # Precise per-model amounts in the details table.
        page.evaluate("() => { document.getElementById('cost-details').open = true; }")
        detail = page.locator("#cost-table-body").inner_text()
        self.assertIn("$7.0000", detail)
        self.assertIn("$1.8060", detail)
        self.assertNoErrors(page_errors, console_errors)
        context.close()

    def test_reference_cache_write_unknown_with_usage_is_pending_not_free(self):
        context, page, page_errors, console_errors = self.new_page()
        self.open_ledger(page)
        glm = page.locator(".cost-bar-row").filter(has_text="glm-5.2")
        self.assertIn("待定价", glm.inner_text())
        self.assertNotIn("$0.00", glm.inner_text())
        # A pending cache_write keeps the hero a subtotal, never a full total,
        # and never collapses to free.
        self.assertNotEqual(page.locator(".cost-value").inner_text(), "$0.00")
        self.assertIn("已定价小计", page.locator(".cost-hero-label").inner_text())
        page.evaluate("() => { document.getElementById('cost-details').open = true; }")
        glm_detail = page.locator("#cost-table-body tr").filter(has_text="glm-5.2")
        self.assertIn("待定价", glm_detail.inner_text())
        self.assertNotIn("$0.0000", glm_detail.inner_text())
        self.assertNoErrors(page_errors, console_errors)
        context.close()

    def test_reference_matching_is_exact_only_no_prefix_case_or_hidden(self):
        # Suffixed / prefixed / different-case names: all pending, no hits.
        context, page, page_errors, console_errors = self.new_page(
            path=self._prefix_path,
        )
        self.open_ledger(page)
        rows = page.locator(".cost-bar-row").all_inner_texts()
        self.assertEqual(len(rows), 3)
        self.assertTrue(all("待定价" in t for t in rows), rows)
        self.assertEqual(page.locator(".cost-value").inner_text(), "—")
        # Enabled reference with zero exact hits still surfaces a 0-hit chip
        # (explicitly enabled but nothing matched), never silence.
        chips = page.locator(".cost-chip").all_inner_texts()
        self.assertTrue(
            any("官方参考命中" in c and "0" in c for c in chips), chips)
        self.assertNoErrors(page_errors, console_errors)
        context.close()
        # Hidden (anonymized) whitelisted name: never guessed either.
        context, page, page_errors, console_errors = self.new_page(
            path=self._hidden_ref_path,
        )
        self.open_ledger(page)
        rows = page.locator(".cost-bar-row").all_inner_texts()
        self.assertTrue(any("隐藏" in t and "待定价" in t for t in rows), rows)
        self.assertEqual(page.locator(".cost-value").inner_text(), "—")
        self.assertNoErrors(page_errors, console_errors)
        context.close()

    def test_user_entries_override_reference_zero_and_all_empty(self):
        context, page, page_errors, console_errors = self.new_page()
        self.seed_config(page, {
            "v": 1, "currency": "USD", "reference": True,
            "prices": {
                # Explicit zeros: free, reference fully ignored.
                price_key("gpt-6.1-sol"):
                    {"rates": ["0", "0", "0", "0", "0"], "note": ""},
                # All-empty entry: a full override that blocks backfill.
                price_key("deepseek-v4-flash"):
                    {"rates": ["", "", "", "", ""], "note": ""},
            },
        })
        self.open_ledger(page)
        rows = page.locator(".cost-bar-row").all_inner_texts()
        self.assertTrue(
            any("gpt-6.1-sol" in t and "$0.00" in t for t in rows), rows)
        self.assertTrue(
            any("deepseek-v4-flash" in t and "待定价" in t for t in rows), rows)
        self.assertNoErrors(page_errors, console_errors)
        context.close()

    def test_editor_readonly_reference_display_and_untouched_save_creates_no_entries(self):
        context, page, page_errors, console_errors = self.new_page()
        self.open_ledger(page)
        checkbox = self.open_editor(page)
        self.assertTrue(checkbox.is_checked())
        # Read-only reference display next to the manual inputs.
        gpt_ref = self.editor_row(page, "gpt-6.1-sol").locator(".cost-ed-reference")
        self.assertEqual(gpt_ref.count(), 1)
        for value in ("2", "10", "0.10", "2.50"):
            self.assertIn(value, gpt_ref.inner_text())
        self.assertEqual(gpt_ref.locator("input").count(), 0)
        ds_ref = self.editor_row(page, "deepseek-v4-flash").locator(
            ".cost-ed-reference")
        self.assertEqual(ds_ref.count(), 1)
        self.assertIn("0.006", ds_ref.inner_text())
        glm_ref = self.editor_row(page, "glm-5.2").locator(".cost-ed-reference")
        self.assertEqual(glm_ref.count(), 1)
        self.assertIn("0.26", glm_ref.inner_text())
        # Non-whitelisted model has no reference display.
        self.assertEqual(
            self.editor_row(page, "model-a").locator(".cost-ed-reference").count(), 0)
        # Manual input stays hand-filled and enabled.
        gpt_input = page.locator(
            '#cost-editor-list input[data-cost-key=\'["claude","gpt-6.1-sol"]\']'
            '[data-cost-part="0"]'
        )
        self.assertTrue(gpt_input.is_enabled())
        self.assertEqual(gpt_input.input_value(), "")
        # Save without touching inputs: no per-model entries are created.
        page.click("#cost-save")
        self.close_editor_and_wait(page)
        parsed, _ = self.stored(page)
        self.assertEqual(parsed["v"], 1)
        self.assertEqual(parsed["currency"], "USD")
        self.assertIs(parsed["reference"], True)
        self.assertEqual(parsed["prices"], {})
        self.assertNoErrors(page_errors, console_errors)
        context.close()

    def test_editor_clear_after_edit_persists_all_empty_entry_no_backfill(self):
        context, page, page_errors, console_errors = self.new_page()
        self.open_ledger(page)
        self.open_editor(page)
        inputs = page.locator(
            '#cost-editor-list input[data-cost-key=\'["claude","gpt-6.1-sol"]\']'
            '[data-cost-part]'
        )
        inputs.nth(0).fill("3")
        inputs.nth(0).fill("")
        page.click("#cost-save")
        self.close_editor_and_wait(page)
        parsed, _ = self.stored(page)
        self.assertIn(price_key("gpt-6.1-sol"), parsed["prices"])
        self.assertEqual(
            parsed["prices"][price_key("gpt-6.1-sol")]["rates"],
            ["", "", "", "", ""],
        )
        self.assertIs(parsed["reference"], True)
        # The kept all-empty entry blocks reference backfill in the ledger.
        rows = page.locator(".cost-bar-row").all_inner_texts()
        self.assertTrue(
            any("gpt-6.1-sol" in t and "待定价" in t for t in rows), rows)
        self.assertNoErrors(page_errors, console_errors)
        context.close()

    def test_editor_reference_toggle_save_and_cancel_semantics(self):
        context, page, page_errors, console_errors = self.new_page()
        self.open_ledger(page)
        checkbox = self.open_editor(page)
        checkbox.uncheck()
        page.click("#cost-save")
        self.close_editor_and_wait(page)
        parsed, _ = self.stored(page)
        self.assertIs(parsed["reference"], False)
        self.assertEqual(parsed["currency"], "USD")
        # With reference off nothing is priced.
        self.assertEqual(page.locator(".cost-value").inner_text(), "—")
        self.assertIn("待定价", page.locator(".cost-hero-label").inner_text())
        # Cancel must not modify the stored config.
        before, _ = self.stored(page)
        checkbox = self.open_editor(page)
        self.assertFalse(checkbox.is_checked())
        checkbox.check()
        page.click("#cost-cancel")
        self.close_editor_and_wait(page)
        after, _ = self.stored(page)
        self.assertEqual(after, before)
        self.assertNoErrors(page_errors, console_errors)
        context.close()

    def test_enabling_reference_in_cny_needs_confirm_cancel_and_pending_save_inert(self):
        context, page, page_errors, console_errors = self.new_page()
        seed = {
            "v": 1, "currency": "CNY", "prices": {
                price_key("gpt-6.1-sol"):
                    {"rates": ["1", "0", "0", "0", "0"], "note": ""},
            },
        }
        self.seed_config(page, seed)
        self.open_ledger(page)
        checkbox = self.open_editor(page)
        self.assertFalse(checkbox.is_checked())
        # Enabling reference under CNY with manual prices reuses the
        # currency confirm; cancelling keeps reference off and CNY.
        checkbox.check()
        self.assertFalse(page.locator("#cost-currency-confirm").is_hidden())
        page.click("#cost-cur-cancel")
        self.assertTrue(page.locator("#cost-currency-confirm").is_hidden())
        self.assertFalse(checkbox.is_checked())
        self.assertEqual(
            page.eval_on_selector("#cost-currency", "el => el.value"), "CNY")
        page.click("#cost-cancel")
        self.close_editor_and_wait(page)
        parsed, _ = self.stored(page)
        self.assertEqual(parsed, seed)
        # Saving while the currency switch is still unconfirmed must not
        # apply it: no USD, no enabled reference in storage.
        checkbox = self.open_editor(page)
        checkbox.check()
        self.assertFalse(page.locator("#cost-currency-confirm").is_hidden())
        page.click("#cost-save")
        page.wait_for_timeout(400)
        parsed, _ = self.stored(page)
        self.assertEqual(parsed.get("currency"), "CNY")
        self.assertNotEqual(parsed.get("reference"), True)
        self.assertNoErrors(page_errors, console_errors)
        context.close()

    def test_reference_enable_with_all_empty_or_note_only_entries_needs_confirm_and_clears(self):
        """全空/仅 note 条目也是覆盖：勾选参考仍需确认；取消原样保留；
        确认后连空覆盖与 note 一起移除并切换 USD，参考回退生效。"""
        context, page, page_errors, console_errors = self.new_page()
        empty_key = price_key("gpt-6.1-sol")
        empty2_key = price_key("deepseek-v4-flash")
        note_key = price_key("model-a")
        seed = {
            "v": 1, "currency": "CNY", "prices": {
                # 白名单模型的全空覆盖（rates 全空，阻止参考回填）。
                empty_key: {"rates": ["", "", "", "", ""], "note": ""},
                # 另一条全空覆盖。
                empty2_key: {"rates": ["", "", "", "", ""], "note": ""},
                # 仅 note 的条目（rates 全空 + note）。
                note_key: {"rates": ["", "", "", "", ""], "note": "keep"},
            },
        }
        self.seed_config(page, seed)
        self.open_ledger(page)
        checkbox = self.open_editor(page)
        self.assertFalse(checkbox.is_checked())
        # 前置：seed 三条目 rates 必须全空——任何条目存在即需确认，
        # 与是否有手填 rates 无关（旧实现仅看 rates 会对全空静默生效）。
        for key in (empty_key, empty2_key, note_key):
            inputs = page.locator(
                '#cost-editor-list input[data-cost-key=\'%s\']'
                '[data-cost-part]' % key
            )
            self.assertEqual(inputs.count(), 5, key)
            for part in range(5):
                self.assertEqual(
                    inputs.nth(part).input_value(), "", "%s part %d" % (key, part))
        checkbox.check()
        self.assertFalse(page.locator("#cost-currency-confirm").is_hidden())
        # 取消：所有条目（含全空覆盖与 note）原样保留。
        page.click("#cost-cur-cancel")
        self.assertTrue(page.locator("#cost-currency-confirm").is_hidden())
        self.assertFalse(checkbox.is_checked())
        page.click("#cost-cancel")
        self.close_editor_and_wait(page)
        parsed, _ = self.stored(page)
        self.assertEqual(parsed, seed)
        # 重新勾选并确认：空覆盖与 note 一并被移除而非保留，
        # 切换 USD 后保存生效。
        checkbox = self.open_editor(page)
        checkbox.check()
        page.click("#cost-cur-ok")
        self.assertEqual(
            page.eval_on_selector("#cost-currency", "el => el.value"), "USD")
        for key in (empty_key, empty2_key, note_key):
            inputs = page.locator(
                '#cost-editor-list input[data-cost-key=\'%s\']'
                '[data-cost-part]' % key
            )
            self.assertEqual(inputs.nth(0).input_value(), "", key)
        note = page.locator(
            '#cost-editor-list input[data-cost-key=\'%s\']'
            '[data-cost-note]' % note_key
        )
        self.assertEqual(note.input_value(), "")
        page.click("#cost-save")
        self.close_editor_and_wait(page)
        parsed, _ = self.stored(page)
        self.assertEqual(parsed["currency"], "USD")
        self.assertIs(parsed["reference"], True)
        for key in (empty_key, empty2_key, note_key):
            self.assertNotIn(key, parsed["prices"], key)
        # 空覆盖移除后参考回退生效：白名单模型由参考计价。
        page.wait_for_function(
            "() => document.querySelector('.cost-value') && "
            "document.querySelector('.cost-value').textContent === '$8.81'"
        )
        rows = page.locator(".cost-bar-row").all_inner_texts()
        self.assertTrue(
            any("deepseek-v4-flash" in t and "$1.81" in t for t in rows), rows)
        self.assertNoErrors(page_errors, console_errors)
        context.close()

    def test_currency_confirm_ok_switches_to_usd_and_reference_prices_apply(self):
        context, page, page_errors, console_errors = self.new_page()
        self.seed_config(page, {
            "v": 1, "currency": "CNY", "prices": {
                price_key("gpt-6.1-sol"):
                    {"rates": ["1", "0", "0", "0", "0"], "note": ""},
            },
        })
        self.open_ledger(page)
        checkbox = self.open_editor(page)
        checkbox.check()
        self.assertFalse(page.locator("#cost-currency-confirm").is_hidden())
        page.click("#cost-cur-ok")
        self.assertEqual(
            page.eval_on_selector("#cost-currency", "el => el.value"), "USD")
        self.assertTrue(checkbox.is_checked())
        # The confirmed switch clears the old manual price so reference can
        # take over again (no leftover override entry is persisted).
        inputs = page.locator(
            '#cost-editor-list input[data-cost-key=\'["claude","gpt-6.1-sol"]\']'
            '[data-cost-part="0"]'
        )
        self.assertEqual(inputs.input_value(), "")
        page.click("#cost-save")
        self.close_editor_and_wait(page)
        parsed, _ = self.stored(page)
        self.assertEqual(parsed["currency"], "USD")
        self.assertIs(parsed["reference"], True)
        self.assertNotIn(price_key("gpt-6.1-sol"), parsed["prices"])
        # Reference now prices the previously manually-priced model.
        page.wait_for_function(
            "() => document.querySelector('.cost-value') && "
            "document.querySelector('.cost-value').textContent === '$8.81'"
        )
        rows = page.locator(".cost-bar-row").all_inner_texts()
        self.assertTrue(
            any("gpt-6.1-sol" in t and "$7.00" in t for t in rows), rows)
        self.assertNoErrors(page_errors, console_errors)
        context.close()

    def test_selecting_cny_disables_reference(self):
        context, page, page_errors, console_errors = self.new_page()
        self.open_ledger(page)
        checkbox = self.open_editor(page)
        self.assertTrue(checkbox.is_checked())
        page.select_option("#cost-currency", "CNY")
        self.assertFalse(checkbox.is_checked())
        page.click("#cost-save")
        self.close_editor_and_wait(page)
        parsed, _ = self.stored(page)
        self.assertEqual(parsed["currency"], "CNY")
        self.assertIs(parsed["reference"], False)
        self.assertEqual(page.locator(".cost-value").inner_text(), "—")
        self.assertNoErrors(page_errors, console_errors)
        context.close()

    def test_non_boolean_reference_field_is_corrupt_and_not_overwritten(self):
        for bad in ("yes", 1):
            context, page, page_errors, console_errors = self.new_page()
            raw = json.dumps({"v": 1, "currency": "USD", "prices": {},
                              "reference": bad})
            page.evaluate(
                "value => localStorage.setItem('tk-cost-v1', value)", raw
            )
            page.reload(wait_until="load")
            self.open_ledger(page)
            self.assertIn("损坏", page.locator(".cost-notice").inner_text())
            # The corrupt stored value is never rewritten.
            self.assertEqual(
                page.evaluate("() => localStorage.getItem('tk-cost-v1')"), raw)
            # In-memory config falls back to the USD reference default.
            config = page.evaluate(
                "() => ({currency: costPrices.currency, "
                        "reference: costPrices.reference, "
                        "keys: Object.keys(costPrices.prices).length})"
            )
            self.assertEqual(config["currency"], "USD")
            self.assertTrue(config["reference"])
            self.assertEqual(config["keys"], 0)
            self.assertNoErrors(page_errors, console_errors)
            context.close()

    def test_no_vendor_network_requests_while_reference_source_links_render(self):
        context = self._browser.new_context(
            viewport={"width": 1280, "height": 820},
            color_scheme="light",
            reduced_motion="no-preference",
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
        requested = []
        page.on("request", lambda request: requested.append(request.url))
        page.goto(self._ref_path.as_uri(), wait_until="load")
        self.open_ledger(page)
        # Source links to the vendor pricing pages live in the ledger
        # (attribution belongs to the ledger, not necessarily the editor).
        hrefs = page.evaluate(
            "() => [...document.querySelectorAll('#cost-body a[href]')]"
            ".map(a => a.getAttribute('href'))"
        )
        self.assertTrue(
            any("developers.openai.com" in href for href in hrefs), hrefs)
        self.assertTrue(
            any("api-docs.deepseek.com" in href for href in hrefs), hrefs)
        # Opening the editor renders the reference layer without fetching.
        self.open_editor(page)
        page.click("#cost-cancel")
        # ...but the page never issues a vendor request by itself.
        remote = [url for url in requested if url.startswith("http")]
        self.assertEqual(remote, [])
        self.assertNoErrors(page_errors, console_errors)
        context.close()

    def test_live_reconcile_prices_new_whitelisted_model_under_reference(self):
        context, page, page_errors, console_errors = self.new_page()
        self.open_ledger(page)
        page.evaluate(
            """() => {
                 const next = JSON.parse(JSON.stringify(DATA));
                 next.cost.models.push(
                   {source: 'claude', model: 'glm-5.3', identity: 'model-b'});
                 const idx = next.cost.models.length - 1;
                 next.cost.rows.push(
                   ['2026-07-01', idx, [1000000, 500000, 0, 0, 0],
                    1500000, 1, false]);
                 reconcileLiveData(next);
                 return true;
               }"""
        )
        # glm-5.3: 1M in * 1.40 + 0.5M out * 4.40 = $3.60 via reference.
        page.wait_for_function(
            "() => [...document.querySelectorAll('.cost-bar-row')]"
            ".some(r => r.textContent.includes('glm-5.3') && "
            "r.textContent.includes('$3.60'))"
        )
        # Live reconcile must not auto-persist a config either.
        self.assertIsNone(page.evaluate("() => localStorage.getItem('tk-cost-v1')"))
        self.assertNoErrors(page_errors, console_errors)
        context.close()


if __name__ == "__main__":
    unittest.main()
