"""Playwright suite for the 费用账单 restore-official-reference action and the
safe cost CSV export (approved plan 2026-10-13).

Synthetic only: every page is built from mock records via the shared helpers
in ``test_dashboard_cost`` (``record`` / ``cost_block``), with a hand-written
``cost`` block injected afterwards. No private logs, no network egress, no
screenshots. Browser selection via TOKENS_DASHBOARD_BROWSER (webkit
supported). Run this file alone; it is not part of the full regression.

Aligned to the shipped implementation (agent ad754fd96388025b3,
/tmp/tokens-030-assets-a754fd/):
  * restore: ``button[data-cost-restore]`` per editor row, ``hidden`` attr
    when unavailable; inline confirm ``.cost-ed-restore-confirm`` with
    ``[data-cost-restore-ok]`` / ``[data-cost-restore-cancel]``; draft-only
    semantics (``delete costDraft.prices[key]`` on confirm).
  * cost CSV: ``#cost-csv-btn`` -> ``tokens-cost-<gran>.csv``, UTF-8 with
    BOM, LF rows, 25 fixed columns, one entry row per model (scope
    aggregated, unpaginated) + exactly one trailing summary row.
  * csvCell formula guard: ``'`` prefix when the cell starts (after leading
    whitespace / control chars) with ``= + - @``; RFC4180 quoting otherwise.
"""

import csv
import io
import json
import os
import re
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

try:
    from tests import test_dashboard_cost as base
except ImportError:
    import test_dashboard_cost as base

record = base.record
cost_block = base.cost_block
price_key = base.price_key

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

# --- fixed contract constants (product agent ad754fd96388025b3) -------------
RESTORE_BTN = "#cost-editor-list .cost-ed-row button[data-cost-restore]"
RESTORE_CONFIRM = ".cost-ed-restore-confirm"
RESTORE_OK = "[data-cost-restore-ok]"
RESTORE_CANCEL = "[data-cost-restore-cancel]"
CSV_BTN = "#cost-csv-btn"
SAVE_BLOCKED_MSG = "请先确认或取消恢复官方参考，再保存。"
CURRENCY_BLOCKED_MSG = "请先确认或取消币种切换，再保存。"

CSV_COLUMNS = [
    "row_type", "granularity", "period", "source", "model", "currency",
    "status",
    "input_tokens", "output_tokens", "cache_read_tokens",
    "cache_write_tokens", "thoughts_tokens",
    "input_rate", "output_rate", "cache_read_rate", "cache_write_rate",
    "thoughts_rate",
    "estimated_cost",
    "total_calls", "unknown_calls", "unknown_tokens", "invalid_rows",
    "total_incomplete", "full_estimate", "priced_subtotal",
]
COL = {name: i for i, name in enumerate(CSV_COLUMNS)}

HOSTILE_NAMES = [
    "plain-model",
    "comma,model",
    'quote"model',
    "line\r\nbreak",
    "=SUM(A1:A9)",
    "+1024",
    "-42",
    "@cmd",
    " \tleading-ws",
    " =leadws-trigger",
    "\x01ctrl-char",
    # Unicode-leading cases (coordinator widening 2026-10-13): JS \s plus
    # BOM/zero-width chars must also trigger the formula guard.
    " =nbsp-eq",
    "﻿=bom-eq",
    "​=zwsp-eq",
    "　 wide-eq",
]
assert len(HOSTILE_NAMES) == 15
# What csvCell + csv.reader round-trip each hostile name to.
HOSTILE_EXPECTED = {
    "=SUM(A1:A9)": "'=SUM(A1:A9)",
    "+1024": "'+1024",
    "-42": "'-42",
    "@cmd": "'@cmd",
    " =leadws-trigger": "' =leadws-trigger",
    " =nbsp-eq": "' =nbsp-eq",
    "﻿=bom-eq": "'﻿=bom-eq",
    "​=zwsp-eq": "'​=zwsp-eq",
}
# Mirror of the shipped csvCell guard class: ASCII ws/controls + Unicode
# whitespace (NBSP, U+1680, U+2000-U+200A, LS/PS, NNBSP, MMSP, ideographic)
# + BOM + zero-width/directional (U+200B-U+200F, U+2060).
FORMULA_LEAD = re.compile(
    r"^[ \t\r\n\x00-\x1f\x7f"
    r"\xa0  -‏    ⁠　﻿]*"
)


def build_page(records, cost):
    """Dashboard HTML with an injected cost block (same mocks as base suite)."""
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
        payload = base.report_dashboard.build_payload(
            records,
            since="2026-07-01",
            until="2026-07-31",
            sources=["claude"],
            generated_at=datetime(2026, 8, 10, 12, 0),
        )
    if cost is None:
        payload.pop("cost", None)  # legacy snapshot simulation
    else:
        payload["cost"] = cost
    return base.report_dashboard.render_dashboard(
        base.dashboard_wire.encode_payload(payload)
    )


class ActionsPageMixin:
    """Shared setUpClass/tearDownClass + harness, mirroring the base suite."""

    BROWSER = os.environ.get("TOKENS_DASHBOARD_BROWSER", "chromium")

    @classmethod
    def start_browser(cls):
        cls._playwright = sync_playwright().start()
        try:
            cls._browser = getattr(cls._playwright, cls.BROWSER).launch(headless=True)
        except Exception as exc:
            cls._playwright.stop()
            cls._tmp.cleanup()
            raise unittest.SkipTest(f"{cls.BROWSER} is unavailable: {exc}")

    @classmethod
    def stop_browser(cls):
        cls._browser.close()
        cls._playwright.stop()
        cls._tmp.cleanup()

    def new_page(self, *, path=None, viewport=None):
        context = self._browser.new_context(
            viewport=viewport or {"width": 1280, "height": 820},
            color_scheme="light",
            reduced_motion="no-preference",
            accept_downloads=True,
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
        page.goto((path or self._page).as_uri(), wait_until="load")
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
        return page.locator("#cost-editor-list .cost-ed-row").filter(has_text=model)

    def restore_btn(self, page, model):
        return self.editor_row(page, model).locator("button[data-cost-restore]")

    def rate_inputs(self, page, model):
        return page.locator(
            '#cost-editor-list input.cost-rate[data-cost-key=\'%s\'][data-cost-part]'
            % price_key(model)
        )

    def set_gran(self, page, gran="day"):
        page.evaluate(
            "g => { state.gran = g; invalidateDerived(); }", gran
        )

    def open_cost_details(self, page):
        page.evaluate("() => { document.getElementById('cost-details').open = true; }")

    def detail_rows(self, page):
        self.open_cost_details(page)
        return page.locator("#cost-table-body tr").all_inner_texts()

    def assertNoErrors(self, page_errors, console_errors):
        self.assertEqual(page_errors, [])
        self.assertEqual(console_errors, [])

    # -- CSV helpers ------------------------------------------------------

    def download_csv(self, page, target=CSV_BTN):
        with page.expect_download() as download_info:
            page.click(target)
        download = download_info.value
        return download.suggested_filename, Path(download.path()).read_bytes()

    def decode_csv(self, data):
        # UTF-8 with BOM per contract; strip it before csv parsing.
        text = data.decode("utf-8-sig")
        return text, list(csv.reader(io.StringIO(text, newline="")))

    def fetch_cost_csv(self, page):
        filename, data = self.download_csv(page)
        text, rows = self.decode_csv(data)
        return filename, text, rows

    def entry_rows(self, rows):
        return [r for r in rows if r and r[COL["row_type"]] == "entry"]

    def summary_row(self, rows):
        found = [r for r in rows if r and r[COL["row_type"]] == "summary"]
        self.assertEqual(len(found), 1, "exactly one summary row expected")
        return found[0]

    def row_by_model(self, rows, model):
        for row in self.entry_rows(rows):
            if row[COL["model"]] == model:
                return row
        self.fail("no entry row for model %r" % model)

    def assertFormulaSafe(self, cell):
        stripped = FORMULA_LEAD.sub("", cell)
        self.assertFalse(
            stripped.startswith(("=", "+", "-", "@")),
            "formula-unsafe cell %r" % cell,
        )


# =====================================================================
# Restore-official-reference action
# =====================================================================

@unittest.skipIf(sync_playwright is None, "Playwright is not installed")
class DashboardCostRestoreTests(ActionsPageMixin, unittest.TestCase):
    """恢复官方参考：可见性矩阵、确认/取消、保存、互斥与焦点。"""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        out = Path(cls._tmp.name)
        records = [
            record("2026-07-01", "model-a", 1000, "synthetic-restore-a1"),
            record("2026-07-01", "model-b", 1200, "synthetic-restore-b2"),
        ]
        # Whitelisted non-hidden models, one unknown control, one
        # whitelisted-but-hidden model (reference must never apply to it).
        cls._page = out / "cost-restore.html"
        cls._page.write_text(
            build_page(
                records,
                cost_block(
                    [
                        ("gpt-6.1-sol", "model-a", False),
                        ("deepseek-v4-flash", "model-a", False),
                        ("glm-5.3", "model-b", False),
                        ("model-a", "model-b", False),
                        ("glm-5.2", "model-b", True),
                    ],
                    [
                        ["2026-07-01", 0, [1_000_000, 0, 0, 0, 0], 1_000_000, 1, False],
                        ["2026-07-01", 1, [1_000_000, 0, 0, 0, 0], 1_000_000, 1, False],
                        ["2026-07-01", 2, [1_000_000, 0, 0, 0, 0], 1_000_000, 1, False],
                        ["2026-07-01", 3, [1_000_000, 0, 0, 0, 0], 1_000_000, 1, False],
                        ["2026-07-01", 4, [1_000_000, 0, 0, 0, 0], 1_000_000, 1, False],
                    ],
                ),
            ),
            encoding="utf-8",
        )
        cls.start_browser()

    @classmethod
    def tearDownClass(cls):
        cls.stop_browser()

    def usd_seed(self):
        """USD + reference on; entries cover 0-rates / all-empty / note-only."""
        return {
            "v": 1, "currency": "USD", "reference": True,
            "prices": {
                price_key("gpt-6.1-sol"):
                    {"rates": ["0", "0", "0", "0", "0"], "note": ""},
                price_key("deepseek-v4-flash"):
                    {"rates": ["", "", "", "", ""], "note": ""},
                price_key("glm-5.3"):
                    {"rates": ["", "", "", "", ""], "note": "only note"},
                price_key("model-a"):
                    {"rates": ["", "", "", "", ""], "note": "keep me"},
            },
        }

    # -- visibility matrix ------------------------------------------------

    def test_restore_visible_for_zero_all_empty_and_note_only_entries(self):
        """0 价、全空、仅 note 条目都算“有条目”：非 hidden 白名单行可见。"""
        context, page, page_errors, console_errors = self.new_page()
        self.seed_config(page, self.usd_seed())
        self.open_ledger(page)
        self.open_editor(page)
        for model in ("gpt-6.1-sol", "deepseek-v4-flash", "glm-5.3"):
            button = self.restore_btn(page, model)
            self.assertEqual(button.count(), 1, model)
            self.assertIsNone(button.first.get_attribute("hidden"), model)
            self.assertTrue(button.first.is_visible(), model)
            self.assertIn("恢复官方参考", button.first.inner_text())
        self.assertNoErrors(page_errors, console_errors)
        context.close()

    def test_restore_button_hidden_without_entry_unknown_or_hidden_model(self):
        """无条目/未知模型/隐藏模型：按钮留在 DOM 但带 hidden 属性。"""
        context, page, page_errors, console_errors = self.new_page()
        self.seed_config(page, self.usd_seed())
        self.open_ledger(page)
        self.open_editor(page)
        # Unknown model: note-only entry exists but no reference to restore.
        unknown = self.restore_btn(page, "model-a")
        self.assertEqual(unknown.count(), 1)
        self.assertIsNotNone(unknown.first.get_attribute("hidden"))
        # Hidden whitelisted model: reference never applies to it.
        hidden = self.restore_btn(page, "glm-5.2")
        self.assertEqual(hidden.count(), 1)
        self.assertIsNotNone(hidden.first.get_attribute("hidden"))
        page.click("#cost-cancel")
        self.close_editor_and_wait(page)
        # No entries at all: every button hidden.
        self.seed_config(page, {"v": 1, "currency": "USD", "reference": True,
                                "prices": {}})
        self.open_editor(page)
        buttons = page.locator(RESTORE_BTN)
        self.assertGreater(buttons.count(), 0)
        for i in range(buttons.count()):
            self.assertIsNotNone(buttons.nth(i).get_attribute("hidden"))
        self.assertNoErrors(page_errors, console_errors)
        context.close()

    def test_restore_hidden_when_reference_off_or_cny(self):
        context, page, page_errors, console_errors = self.new_page()
        self.open_ledger(page)
        # Reference off: restore meaningless even with entries.
        self.seed_config(page, {"v": 1, "currency": "USD", "reference": False,
                                "prices": self.usd_seed()["prices"]})
        self.open_editor(page)
        button = self.restore_btn(page, "gpt-6.1-sol")
        self.assertIsNotNone(button.first.get_attribute("hidden"))
        page.click("#cost-cancel")
        self.close_editor_and_wait(page)
        # CNY: official reference is USD-only.
        self.seed_config(page, {"v": 1, "currency": "CNY", "reference": True,
                                "prices": self.usd_seed()["prices"]})
        self.open_editor(page)
        self.assertIsNotNone(
            self.restore_btn(page, "gpt-6.1-sol").first.get_attribute("hidden")
        )
        self.assertNoErrors(page_errors, console_errors)
        context.close()

    def test_typing_in_row_creates_entry_and_unhides_restore_without_blur(self):
        """在该行任一 input 输入即时创建条目并去掉 hidden（不整表重渲染）。"""
        context, page, page_errors, console_errors = self.new_page()
        self.seed_config(page, {"v": 1, "currency": "USD", "reference": True,
                                "prices": {}})
        self.open_ledger(page)
        self.open_editor(page)
        button = self.restore_btn(page, "gpt-6.1-sol")
        self.assertIsNotNone(button.first.get_attribute("hidden"))
        inputs = self.rate_inputs(page, "gpt-6.1-sol")
        inputs.nth(0).click()
        page.keyboard.type("2")
        # No full re-render: the same input node keeps focus.
        self.assertTrue(
            inputs.nth(0).evaluate("el => el === document.activeElement")
        )
        self.assertIsNone(self.restore_btn(page, "gpt-6.1-sol")
                          .first.get_attribute("hidden"))
        # Cancel: the draft entry created by typing never reaches storage
        # (the seeded config stays byte-for-byte).
        page.click("#cost-cancel")
        self.close_editor_and_wait(page)
        parsed, _ = self.stored(page)
        self.assertEqual(
            parsed, {"v": 1, "currency": "USD", "reference": True,
                     "prices": {}}
        )
        self.assertNoErrors(page_errors, console_errors)
        context.close()

    # -- confirm / cancel semantics ----------------------------------------

    def test_restore_cancel_keeps_draft_and_storage_and_refocuses_button(self):
        context, page, page_errors, console_errors = self.new_page()
        seed = self.usd_seed()
        self.seed_config(page, seed)
        self.open_ledger(page)
        self.open_editor(page)
        inputs = self.rate_inputs(page, "gpt-6.1-sol")
        before = [inputs.nth(i).input_value() for i in range(inputs.count())]
        row = self.editor_row(page, "gpt-6.1-sol")
        row.locator("button[data-cost-restore]").click()
        confirm = row.locator(RESTORE_CONFIRM)
        self.assertTrue(confirm.is_visible())
        # Focus moves to the ok button when the confirm appears.
        self.assertTrue(
            row.locator(RESTORE_OK).evaluate("el => el === document.activeElement")
        )
        # The confirm buttons carry the model key as their value.
        self.assertEqual(
            row.locator(RESTORE_OK).get_attribute("data-cost-restore-ok"),
            price_key("gpt-6.1-sol"),
        )
        row.locator(RESTORE_CANCEL).click()
        self.assertEqual(
            row.locator(RESTORE_CONFIRM).count(),
            0,
            "cancel must re-render the confirm row away",
        )
        # Draft and storage unchanged.
        after = [inputs.nth(i).input_value() for i in range(inputs.count())]
        self.assertEqual(after, before)
        parsed, _ = self.stored(page)
        self.assertEqual(parsed, seed)
        # Focus returns to the row's restore button (re-rendered node).
        focused_key = page.evaluate(
            "() => document.activeElement "
            "? document.activeElement.getAttribute('data-cost-restore') : null"
        )
        self.assertEqual(focused_key, price_key("gpt-6.1-sol"))
        self.assertNoErrors(page_errors, console_errors)
        context.close()

    def test_editor_cancel_after_restore_confirm_keeps_storage_byte_identical(self):
        context, page, page_errors, console_errors = self.new_page()
        seed = self.usd_seed()
        self.seed_config(page, seed)
        _, raw_before = self.stored(page)
        self.open_ledger(page)
        self.open_editor(page)
        row = self.editor_row(page, "deepseek-v4-flash")
        row.locator("button[data-cost-restore]").click()
        row.locator(RESTORE_OK).click()
        # Confirmed restore only mutates the draft; editor cancel discards it.
        page.click("#cost-cancel")
        self.close_editor_and_wait(page)
        self.assertEqual(
            page.evaluate("() => localStorage.getItem('tk-cost-v1')"), raw_before
        )
        self.assertNoErrors(page_errors, console_errors)
        context.close()

    def test_currency_select_resets_pending_restore(self):
        context, page, page_errors, console_errors = self.new_page()
        self.seed_config(page, self.usd_seed())
        self.open_ledger(page)
        self.open_editor(page)
        row = self.editor_row(page, "gpt-6.1-sol")
        row.locator("button[data-cost-restore]").click()
        self.assertTrue(row.locator(RESTORE_CONFIRM).is_visible())
        page.select_option("#cost-currency", "CNY")
        self.assertEqual(
            page.locator("#cost-editor-list " + RESTORE_CONFIRM).count(), 0,
            "currency change must reset the pending restore",
        )
        page.click("#cost-cancel")
        self.close_editor_and_wait(page)
        self.assertNoErrors(page_errors, console_errors)
        context.close()

    # -- save semantics ------------------------------------------------------

    def test_restore_confirm_deletes_entry_focuses_rate_and_shows_status(self):
        context, page, page_errors, console_errors = self.new_page()
        self.seed_config(page, self.usd_seed())
        self.open_ledger(page)
        self.open_editor(page)
        row = self.editor_row(page, "gpt-6.1-sol")
        row.locator("button[data-cost-restore]").click()
        row.locator(RESTORE_OK).click()
        # Draft entry gone immediately (row inputs empty again).
        inputs = self.rate_inputs(page, "gpt-6.1-sol")
        for i in range(inputs.count()):
            self.assertEqual(inputs.nth(i).input_value(), "")
        # Focus lands on the row's first rate input.
        self.assertTrue(
            inputs.nth(0).evaluate("el => el === document.activeElement")
        )
        # Status line reports the restore.
        self.assertIn(
            "已恢复官方参考",
            page.locator("#cost-editor-status").inner_text(),
        )
        # Restore is draft-only: no storage write before save.
        parsed, _ = self.stored(page)
        self.assertIn(price_key("gpt-6.1-sol"), parsed["prices"])
        self.assertNoErrors(page_errors, console_errors)
        context.close()

    def test_restore_save_restores_reference_and_leaves_other_entries(self):
        context, page, page_errors, console_errors = self.new_page()
        self.seed_config(page, self.usd_seed())
        self.open_ledger(page)
        self.open_editor(page)
        row = self.editor_row(page, "gpt-6.1-sol")
        row.locator("button[data-cost-restore]").click()
        row.locator(RESTORE_OK).click()
        page.click("#cost-save")
        self.close_editor_and_wait(page)
        parsed, _ = self.stored(page)
        self.assertEqual(parsed["currency"], "USD")
        self.assertIs(parsed["reference"], True)
        # Restored key: the whole entry (rates + note) is deleted so the
        # reference applies again -- not a copy of the reference rates.
        self.assertNotIn(price_key("gpt-6.1-sol"), parsed["prices"])
        # Other entries untouched (all-empty + note-only overrides).
        self.assertEqual(
            parsed["prices"][price_key("deepseek-v4-flash")],
            {"rates": ["", "", "", "", ""], "note": ""},
        )
        self.assertEqual(
            parsed["prices"][price_key("glm-5.3")],
            {"rates": ["", "", "", "", ""], "note": "only note"},
        )
        self.assertEqual(
            parsed["prices"][price_key("model-a")],
            {"rates": ["", "", "", "", ""], "note": "keep me"},
        )
        # Ledger: gpt-6.1-sol back on reference 1M in * $2/M = $2.00;
        # deepseek's all-empty override still blocks its backfill.
        self.assertEqual(page.locator(".cost-value").inner_text(), "$2.00")
        rows = self.detail_rows(page)
        self.assertTrue(
            any("gpt-6.1-sol" in t and "$2.0000" in t for t in rows), rows
        )
        self.assertTrue(
            any("deepseek-v4-flash" in t and "待定价" in t for t in rows), rows
        )
        self.assertNoErrors(page_errors, console_errors)
        context.close()

    def test_reenter_after_restore_overrides_reference_again(self):
        context, page, page_errors, console_errors = self.new_page()
        self.seed_config(page, self.usd_seed())
        self.open_ledger(page)
        self.open_editor(page)
        row = self.editor_row(page, "gpt-6.1-sol")
        row.locator("button[data-cost-restore]").click()
        row.locator(RESTORE_OK).click()
        # Focus already sits on the first rate input; typing re-creates the
        # override entry (and the restore button shows up again).
        page.keyboard.type("1.5")
        self.assertIsNone(
            self.restore_btn(page, "gpt-6.1-sol").first.get_attribute("hidden")
        )
        page.click("#cost-save")
        self.close_editor_and_wait(page)
        parsed, _ = self.stored(page)
        self.assertEqual(
            parsed["prices"][price_key("gpt-6.1-sol")]["rates"][0], "1.5"
        )
        self.assertEqual(page.locator(".cost-value").inner_text(), "$1.50")
        self.assertNoErrors(page_errors, console_errors)
        context.close()

    def test_restore_save_updates_revision_and_derived_cache(self):
        """保存后 revision 递增且派生缓存重算（以渲染结果断言，不测实现）。"""
        context, page, page_errors, console_errors = self.new_page()
        self.seed_config(page, self.usd_seed())
        self.open_ledger(page)
        revision_before = page.evaluate("() => costPriceRevision")
        self.open_editor(page)
        row = self.editor_row(page, "gpt-6.1-sol")
        row.locator("button[data-cost-restore]").click()
        row.locator(RESTORE_OK).click()
        page.click("#cost-save")
        self.close_editor_and_wait(page)
        self.assertGreater(
            page.evaluate("() => costPriceRevision"), revision_before
        )
        # Stale-cache guard: the ledger reflects the reference price without
        # a reload (gpt-6.1-sol reference $2.00).
        self.assertEqual(page.locator(".cost-value").inner_text(), "$2.00")
        self.assertNoErrors(page_errors, console_errors)
        context.close()

    # -- save mutex ------------------------------------------------------------

    def test_save_blocked_while_restore_confirm_pending(self):
        """pending restore 未确认时保存被阻断：提示、modal 不关、存储不变。"""
        context, page, page_errors, console_errors = self.new_page()
        seed = self.usd_seed()
        self.seed_config(page, seed)
        self.open_ledger(page)
        self.open_editor(page)
        row = self.editor_row(page, "gpt-6.1-sol")
        row.locator("button[data-cost-restore]").click()
        page.click("#cost-save")
        # Modal stays open with the explicit guidance message.
        self.assertTrue(
            page.locator("#cost-modal").evaluate(
                "el => el.classList.contains('open')"
            )
        )
        self.assertEqual(
            page.locator("#cost-editor-status").inner_text(), SAVE_BLOCKED_MSG
        )
        parsed, _ = self.stored(page)
        self.assertEqual(parsed, seed)
        # Resolving the pending restore unblocks the save.
        row.locator(RESTORE_OK).click()
        page.click("#cost-save")
        self.close_editor_and_wait(page)
        parsed, _ = self.stored(page)
        self.assertNotIn(price_key("gpt-6.1-sol"), parsed["prices"])
        self.assertNoErrors(page_errors, console_errors)
        context.close()

    def test_save_blocked_while_currency_confirm_pending(self):
        """换币确认未决时（互斥），保存不能生效、存储不变。"""
        context, page, page_errors, console_errors = self.new_page()
        seed = self.usd_seed()
        self.seed_config(page, seed)
        self.open_ledger(page)
        self.open_editor(page)
        page.select_option("#cost-currency", "CNY")
        self.assertFalse(page.locator("#cost-currency-confirm").is_hidden())
        page.click("#cost-save")
        self.assertEqual(
            page.locator("#cost-editor-status").inner_text(),
            CURRENCY_BLOCKED_MSG,
        )
        self.assertTrue(
            page.locator("#cost-modal").evaluate(
                "el => el.classList.contains('open')"
            )
        )
        parsed, _ = self.stored(page)
        self.assertEqual(parsed, seed)
        self.assertNoErrors(page_errors, console_errors)
        context.close()

    # -- currency x restore interaction matrix (product agent directed) -------

    def test_both_pending_currency_and_restore_block_save_in_order(self):
        """币种与 restore 同时 pending：先报币种；逐个解除后才能保存。"""
        context, page, page_errors, console_errors = self.new_page()
        seed = self.usd_seed()
        self.seed_config(page, seed)
        self.open_ledger(page)
        self.open_editor(page)
        page.select_option("#cost-currency", "CNY")
        self.editor_row(page, "gpt-6.1-sol") \
            .locator("button[data-cost-restore]").click()
        # Both pending: currency message wins (checked first).
        page.click("#cost-save")
        self.assertEqual(
            page.locator("#cost-editor-status").inner_text(),
            CURRENCY_BLOCKED_MSG,
        )
        self.assertTrue(
            page.locator("#cost-modal").evaluate(
                "el => el.classList.contains('open')"
            )
        )
        # Cancel currency only: restore still blocks with its own message.
        page.click("#cost-cur-cancel")
        page.click("#cost-save")
        self.assertEqual(
            page.locator("#cost-editor-status").inner_text(), SAVE_BLOCKED_MSG
        )
        parsed, _ = self.stored(page)
        self.assertEqual(parsed, seed)
        # Cancel the pending restore: save now succeeds, config intact.
        self.editor_row(page, "gpt-6.1-sol") \
            .locator(RESTORE_CANCEL).click()
        page.click("#cost-save")
        self.close_editor_and_wait(page)
        parsed, _ = self.stored(page)
        self.assertEqual(parsed, seed)
        self.assertNoErrors(page_errors, console_errors)
        context.close()

    def test_confirming_currency_clears_pending_restore_and_rates(self):
        """确认换币：取消 restore pending、清空全部手填价，但不删条目/备注。"""
        context, page, page_errors, console_errors = self.new_page()
        self.seed_config(page, self.usd_seed())
        self.open_ledger(page)
        self.open_editor(page)
        page.select_option("#cost-currency", "CNY")
        self.editor_row(page, "gpt-6.1-sol") \
            .locator("button[data-cost-restore]").click()
        page.click("#cost-cur-ok")
        self.assertTrue(page.locator("#cost-currency-confirm").is_hidden())
        self.assertEqual(
            page.locator("#cost-editor-list " + RESTORE_CONFIRM).count(), 0
        )
        # Draft rates cleared in the form (no auto conversion) ...
        inputs = self.rate_inputs(page, "gpt-6.1-sol")
        for i in range(inputs.count()):
            self.assertEqual(inputs.nth(i).input_value(), "")
        page.click("#cost-save")
        self.close_editor_and_wait(page)
        # ... but entries and notes survive (no key deletion beyond restores).
        parsed, _ = self.stored(page)
        self.assertEqual(parsed["currency"], "CNY")
        self.assertIs(parsed["reference"], False)
        self.assertEqual(
            parsed["prices"][price_key("gpt-6.1-sol")],
            {"rates": ["", "", "", "", ""], "note": ""},
        )
        self.assertEqual(
            parsed["prices"][price_key("model-a")],
            {"rates": ["", "", "", "", ""], "note": "keep me"},
        )
        self.assertNoErrors(page_errors, console_errors)
        context.close()

    def test_canceling_currency_keeps_pending_restore(self):
        context, page, page_errors, console_errors = self.new_page()
        seed = self.usd_seed()
        self.seed_config(page, seed)
        self.open_ledger(page)
        self.open_editor(page)
        page.select_option("#cost-currency", "CNY")
        # Open a fresh restore confirm while the currency confirm is pending.
        row = self.editor_row(page, "deepseek-v4-flash")
        row.locator("button[data-cost-restore]").click()
        self.assertTrue(row.locator(RESTORE_CONFIRM).is_visible())
        page.click("#cost-cur-cancel")
        self.assertTrue(page.locator("#cost-currency-confirm").is_hidden())
        self.assertEqual(page.evaluate("() => document.getElementById('cost-currency').value"), "USD")
        confirm_left = page.locator("#cost-editor-list " + RESTORE_CONFIRM)
        self.assertEqual(confirm_left.count(), 1)
        self.assertTrue(confirm_left.first.is_visible())
        # Resolving it the normal way stays lossless.
        confirm_left.first.locator(RESTORE_CANCEL).click()
        parsed, _ = self.stored(page)
        self.assertEqual(parsed, seed)
        self.assertNoErrors(page_errors, console_errors)
        context.close()

    def test_disabling_reference_cancels_pending_restore_losslessly(self):
        context, page, page_errors, console_errors = self.new_page()
        seed = self.usd_seed()
        self.seed_config(page, seed)
        self.open_ledger(page)
        self.open_editor(page)
        row = self.editor_row(page, "gpt-6.1-sol")
        row.locator("button[data-cost-restore]").click()
        self.assertTrue(row.locator(RESTORE_CONFIRM).is_visible())
        page.uncheck("#cost-reference")
        self.assertEqual(
            page.locator("#cost-editor-list " + RESTORE_CONFIRM).count(), 0,
            "reference off must cancel the pending restore",
        )
        # Lossless: draft entries untouched, storage untouched.
        inputs = self.rate_inputs(page, "gpt-6.1-sol")
        self.assertEqual(inputs.nth(0).input_value(), "0")
        parsed, _ = self.stored(page)
        self.assertEqual(parsed, seed)
        # Re-enabling while still on USD restores the flag directly (the
        # clear-with-confirm path only triggers on an actual currency jump).
        page.check("#cost-reference")
        self.assertTrue(page.locator("#cost-currency-confirm").is_hidden())
        self.assertIs(
            page.evaluate("() => document.getElementById('cost-reference').checked"),
            True,
        )
        self.assertNoErrors(page_errors, console_errors)
        context.close()


# =====================================================================
# Safe cost CSV export
# =====================================================================

@unittest.skipIf(sync_playwright is None, "Playwright is not installed")
class DashboardCostCsvTests(ActionsPageMixin, unittest.TestCase):
    """费用 CSV：真实下载内容断言（csv.reader）、范围、精度与注入安全。"""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        out = Path(cls._tmp.name)
        records = [
            record("2026-07-01", "model-a", 1000, "synthetic-csv-a1"),
            record("2026-07-01", "model-b", 1200, "synthetic-csv-b1"),
            # 07-02 must exist in DATA.day so a focus-period export can
            # scope to it (cost rows alone are not enough).
            record("2026-07-02", "model-a", 800, "synthetic-csv-a2"),
        ]

        # Base: whitelisted models (reference + custom states) + unknown,
        # with a second day so focus scoping is observable.
        cls._page = out / "cost-csv-base.html"
        cls._page.write_text(
            build_page(
                records,
                cost_block(
                    [
                        ("gpt-6.1-sol", "model-a", False),
                        ("deepseek-v4-flash", "model-a", False),
                        ("model-a", "model-b", False),
                    ],
                    [
                        ["2026-07-01", 0, [1_000_000, 500_000, 0, 0, 0],
                         1_500_000, 1, False],
                        ["2026-07-02", 0, [1_000_000, 0, 0, 0, 0],
                         1_000_000, 1, False],
                        ["2026-07-01", 1, [2_000_000, 1_000_000, 1_000_000, 0, 0],
                         4_000_000, 2, False],
                        ["2026-07-01", 2, [0, 0, 0, 500_000, 0], 500_000, 1, False],
                    ],
                ),
            ),
            encoding="utf-8",
        )

        # Hostile catalog: exactly 15 models (> 12-per-page ledger limit).
        catalog = [(name, "model-a" if i % 2 == 0 else "model-b", False)
                   for i, name in enumerate(HOSTILE_NAMES)]
        cls._hostile_path = out / "cost-csv-hostile.html"
        cls._hostile_path.write_text(
            build_page(
                records,
                cost_block(
                    catalog,
                    [["2026-07-01", i, [100 * (i + 1), 0, 0, 0, 0],
                      100 * (i + 1), 1, False]
                     for i in range(len(catalog))],
                ),
            ),
            encoding="utf-8",
        )

        # BigInt: two split rows summing past 2**53-1.
        cls._bigint_path = out / "cost-csv-bigint.html"
        cls._bigint_path.write_text(
            build_page(
                records,
                cost_block(
                    [("gpt-6.1-sol", "model-a", False)],
                    [
                        ["2026-07-01", 0, [4_600_000_000_000_000, 0, 0, 0, 0],
                         4_600_000_000_000_000, 1, False],
                        ["2026-07-02", 0, [4_600_000_000_000_000, 0, 0, 0, 0],
                         4_600_000_000_000_000, 3, False],
                    ],
                ),
            ),
            encoding="utf-8",
        )

        # Uncertain + invalid date + hidden model + total_incomplete.
        cls._summary_path = out / "cost-csv-summary.html"
        cls._summary_path.write_text(
            build_page(
                records,
                cost_block(
                    [
                        ("gpt-6.1-sol", "model-a", False),
                        ("deepseek-v4-flash", "model-a", False),
                        ("glm-5.2", "model-b", True),
                    ],
                    [
                        ["2026-07-01", 0, [1_000, 0, 0, 0, 0], 1_000, 1, False],
                        ["2026-07-01", 1, [100, 0, 0, 0, 0], 100, 2, True],
                        ["2026/07/01", 0, [50, 0, 0, 0, 0], 50, 5, False],
                        ["2026-07-01", 2, [2_000, 0, 0, 0, 0], 2_000, 1, False],
                    ],
                    total_incomplete=True,
                ),
            ),
            encoding="utf-8",
        )

        # Empty cost block (no models, no rows).
        cls._empty_path = out / "cost-csv-empty.html"
        cls._empty_path.write_text(
            build_page(records, cost_block([], [])),
            encoding="utf-8",
        )

        # Legacy snapshot without a cost block.
        cls._legacy_path = out / "cost-csv-legacy.html"
        cls._legacy_path.write_text(
            build_page(records, None),
            encoding="utf-8",
        )

        # Hostile-named records for the trend CSV (#csv-btn) injection test.
        # Keep to 7 models: the trend table caps model columns (7 + "Other").
        trend_names = ["comma,model", 'quote"model', "line\r\nbreak",
                       "=SUM(A1:A9)", "+1024", "-42", "@cmd"]
        hostile_records = [
            record("2026-07-01", name, 1000, "synthetic-trend-%d" % i)
            for i, name in enumerate(trend_names)
        ]
        cls._trend_path = out / "cost-csv-trend.html"
        cls._trend_path.write_text(
            build_page(hostile_records,
                       cost_block([], [])),
            encoding="utf-8",
        )

        cls.start_browser()

    @classmethod
    def tearDownClass(cls):
        cls.stop_browser()

    def usd_reference_config(self, prices=None):
        return {"v": 1, "currency": "USD", "reference": True,
                "prices": prices or {}}

    # -- download mechanics -------------------------------------------------

    def test_csv_click_downloads_real_content_with_fixed_header(self):
        context, page, page_errors, console_errors = self.new_page()
        self.seed_config(page, self.usd_reference_config())
        self.open_ledger(page)
        self.set_gran(page)  # default view is month; pin day everywhere
        filename, data = self.download_csv(page)
        self.assertEqual(filename, "tokens-cost-day.csv")
        self.assertTrue(data.startswith(b"\xef\xbb\xbf"))  # UTF-8 BOM
        self.assertNotIn(b"\r", data)  # LF row endings
        _, rows = self.decode_csv(data)
        self.assertEqual(rows[0], CSV_COLUMNS)
        self.assertEqual(len(rows[0]), 25)
        self.assertEqual(len(self.entry_rows(rows)), 3)
        self.summary_row(rows)  # exactly one, and it parses
        self.assertNoErrors(page_errors, console_errors)
        context.close()

    def test_csv_filename_follows_granularity(self):
        context, page, page_errors, console_errors = self.new_page()
        self.seed_config(page, self.usd_reference_config())
        self.open_ledger(page)
        self.set_gran(page, "week")
        filename, _, _ = self.fetch_cost_csv(page)
        self.assertEqual(filename, "tokens-cost-week.csv")
        self.assertNoErrors(page_errors, console_errors)
        context.close()

    def test_legacy_snapshot_disables_cost_csv_button(self):
        context, page, page_errors, console_errors = self.new_page(
            path=self._legacy_path
        )
        self.open_ledger(page)
        self.assertTrue(page.locator(CSV_BTN).is_disabled())
        self.assertTrue(page.locator("#cost-price-btn").is_disabled())
        self.assertNoErrors(page_errors, console_errors)
        context.close()

    def test_no_autodownload_and_no_external_requests(self):
        context = self._browser.new_context(
            viewport={"width": 1280, "height": 820},
            color_scheme="light",
            reduced_motion="no-preference",
            accept_downloads=True,
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
        auto = []
        page.on(
            "download", lambda download: auto.append(download.suggested_filename)
        )
        page.goto(self._page.as_uri(), wait_until="load")
        self.open_ledger(page)
        page.wait_for_timeout(600)
        self.assertEqual(auto, [])  # never downloads without a click
        remote = [url for url in requested if url.startswith("http")]
        self.assertEqual(remote, [])
        # The export itself stays local too.
        self.download_csv(page)
        remote = [url for url in requested if url.startswith("http")]
        self.assertEqual(remote, [])
        self.assertNoErrors(page_errors, console_errors)
        context.close()

    # -- scope ----------------------------------------------------------------

    def test_csv_entries_not_limited_by_pagination(self):
        context, page, page_errors, console_errors = self.new_page(
            path=self._hostile_path
        )
        self.open_ledger(page)
        # Ledger page 1 shows at most 12 of the 15 hostile catalog models.
        self.assertLessEqual(page.locator(".cost-bar-row").count(), 12)
        _, _, rows = self.fetch_cost_csv(page)
        self.assertEqual(len(self.entry_rows(rows)), 15)
        for name in HOSTILE_NAMES:
            self.row_by_model(rows, HOSTILE_EXPECTED.get(name, name))
        self.assertNoErrors(page_errors, console_errors)
        context.close()

    def test_csv_respects_model_filter_and_focus_period(self):
        context, page, page_errors, console_errors = self.new_page()
        self.seed_config(page, self.usd_reference_config())
        self.open_ledger(page)
        self.set_gran(page)
        # Unfiltered: 3 entries, ALL period.
        _, _, full = self.fetch_cost_csv(page)
        self.assertEqual(len(self.entry_rows(full)), 3)
        for row in self.entry_rows(full):
            self.assertEqual(row[COL["period"]], "ALL")
            self.assertEqual(row[COL["granularity"]], "day")
        # Identity filter: drop model-b -> the unknown "model-a" row goes.
        page.evaluate(
            "() => { state.models = new Set(['model-a']); invalidateDerived(); }"
        )
        _, _, filtered = self.fetch_cost_csv(page)
        models = [r[COL["model"]] for r in self.entry_rows(filtered)]
        self.assertEqual(
            sorted(models), ["deepseek-v4-flash", "gpt-6.1-sol"]
        )
        # Focus: day granularity on 07-02 keeps only gpt-6.1-sol, scoped
        # to that single day's usage (1M input, not 2M).
        page.evaluate(
            """() => {
                 state.models = new Set(DATA.models);
                 state.gran = 'day';
                 state.focusPeriod = '2026-07-02';
                 invalidateDerived();
               }"""
        )
        _, _, focused = self.fetch_cost_csv(page)
        entries = self.entry_rows(focused)
        self.assertEqual(len(entries), 1)
        row = entries[0]
        self.assertEqual(row[COL["model"]], "gpt-6.1-sol")
        self.assertEqual(row[COL["period"]], "2026-07-02")
        self.assertEqual(row[COL["input_tokens"]], "1000000")
        self.assertNoErrors(page_errors, console_errors)
        context.close()

    def test_csv_status_currency_rates_and_amounts_per_pricing_source(self):
        context, page, page_errors, console_errors = self.new_page()
        self.seed_config(page, self.usd_reference_config({
            price_key("gpt-6.1-sol"): {"rates": ["2", "10", "0.10", "2.50", ""],
                                       "note": ""},
        }))
        self.open_ledger(page)
        _, _, rows = self.fetch_cost_csv(page)
        # Custom-priced entry: status, raw rate strings, exact amount.
        custom = self.row_by_model(rows, "gpt-6.1-sol")
        self.assertEqual(custom[COL["status"]], "priced_custom")
        self.assertEqual(custom[COL["currency"]], "USD")
        self.assertEqual(
            [custom[COL[c]] for c in
             ("input_rate", "output_rate", "cache_read_rate",
              "cache_write_rate", "thoughts_rate")],
            ["2", "10", "0.10", "2.50", ""],
        )
        # 2M in * 2 + 0.5M out * 10 = 9 -> '9' (integer, no decimal point).
        self.assertEqual(custom[COL["estimated_cost"]], "9")
        self.assertEqual(custom[COL["input_tokens"]], "2000000")
        self.assertEqual(custom[COL["output_tokens"]], "500000")
        # Reference-priced entry: 0.6 + 1.2 + 0.006 -> '1.806' exact.
        reference = self.row_by_model(rows, "deepseek-v4-flash")
        self.assertEqual(reference[COL["status"]], "priced_reference")
        self.assertEqual(reference[COL["estimated_cost"]], "1.806")
        self.assertEqual(reference[COL["cache_read_rate"]], "0.006")
        # Unknown model: pending, rates and amount empty -- never '0'.
        pending = self.row_by_model(rows, "model-a")
        self.assertEqual(pending[COL["status"]], "pending")
        self.assertEqual(pending[COL["estimated_cost"]], "")
        self.assertEqual(
            [pending[COL[c]] for c in
             ("input_rate", "output_rate", "cache_read_rate",
              "cache_write_rate", "thoughts_rate")],
            ["", "", "", "", ""],
        )
        # Entry rows leave the summary-only columns empty.
        for row in self.entry_rows(rows):
            self.assertEqual(len(row), 25)
            for col in ("total_calls", "unknown_calls", "unknown_tokens",
                        "invalid_rows", "total_incomplete", "full_estimate",
                        "priced_subtotal"):
                self.assertEqual(row[COL[col]], "", (col, row[COL["model"]]))
        # Summary: subtotal covers the two priced entries, not a full total.
        summary = self.summary_row(rows)
        self.assertEqual(summary[COL["total_calls"]], "5")
        self.assertEqual(summary[COL["priced_subtotal"]], "10.806")
        self.assertEqual(summary[COL["full_estimate"]], "false")
        self.assertNoErrors(page_errors, console_errors)
        context.close()

    def test_csv_free_zero_differs_from_unknown_pending(self):
        context, page, page_errors, console_errors = self.new_page()
        self.seed_config(page, self.usd_reference_config({
            price_key("gpt-6.1-sol"):
                {"rates": ["0", "0", "0", "0", "0"], "note": ""},
        }))
        self.open_ledger(page)
        _, _, rows = self.fetch_cost_csv(page)
        free = self.row_by_model(rows, "gpt-6.1-sol")
        self.assertEqual(free[COL["status"]], "priced_custom")
        self.assertEqual(free[COL["estimated_cost"]], "0")
        self.assertEqual(free[COL["input_rate"]], "0")  # explicit free
        pending = self.row_by_model(rows, "model-a")
        self.assertEqual(pending[COL["status"]], "pending")
        self.assertEqual(pending[COL["estimated_cost"]], "")  # unknown != 0
        self.assertEqual(pending[COL["input_rate"]], "")
        # Zero-priced custom rows still count as priced: subtotal covers the
        # free row (0) plus the reference-priced deepseek entry (1.806).
        self.assertEqual(self.summary_row(rows)[COL["priced_subtotal"]], "1.806")
        self.assertNoErrors(page_errors, console_errors)
        context.close()

    def test_csv_hidden_model_flagged_and_never_priced(self):
        context, page, page_errors, console_errors = self.new_page(
            path=self._summary_path
        )
        self.open_ledger(page)
        _, _, rows = self.fetch_cost_csv(page)
        hidden = self.row_by_model(rows, "glm-5.2")
        self.assertEqual(hidden[COL["status"]], "hidden")
        self.assertEqual(hidden[COL["estimated_cost"]], "")
        for col in ("input_rate", "output_rate"):
            self.assertEqual(hidden[COL[col]], "")
        self.assertNoErrors(page_errors, console_errors)
        context.close()

    # -- summary integrity ------------------------------------------------------

    def test_csv_keeps_uncertain_invalid_and_total_incomplete_summary(self):
        """uncertain/invalid/totalIncomplete 汇总不可丢、不可被数据行覆盖。"""
        context, page, page_errors, console_errors = self.new_page(
            path=self._summary_path
        )
        self.open_ledger(page)
        _, _, rows = self.fetch_cost_csv(page)
        # The summary row is last and unique; data rows never fill its cols.
        self.assertEqual(rows[-1][COL["row_type"]], "summary")
        summary = self.summary_row(rows)
        # 1 verified + 2 uncertain + 5 invalid-date + 1 hidden = 9 calls.
        self.assertEqual(summary[COL["total_calls"]], "9")
        # Uncertain (2) + invalid date (5) join unknown: exactly 7.
        self.assertEqual(summary[COL["unknown_calls"]], "7")
        # Unknown tokens: 100 (uncertain) + 50 (invalid date) = 150.
        self.assertEqual(summary[COL["unknown_tokens"]], "150")
        self.assertEqual(summary[COL["invalid_rows"]], "1")
        self.assertEqual(summary[COL["total_incomplete"]], "true")
        self.assertEqual(summary[COL["full_estimate"]], "false")
        # gpt-6.1-sol's verified 1,000 tokens at $2/M -> exact '0.002'.
        verified = self.row_by_model(rows, "gpt-6.1-sol")
        self.assertEqual(verified[COL["estimated_cost"]], "0.002")
        self.assertEqual(summary[COL["priced_subtotal"]], "0.002")
        # Summary row carries no per-model token/rate/cost values.
        for col in CSV_COLUMNS[7:18]:
            self.assertEqual(summary[COL[col]], "", col)
        self.assertNoErrors(page_errors, console_errors)
        context.close()

    def test_csv_unsupported_view_outputs_summary_row_without_throwing(self):
        """view 不支持（无有效 cost 块）时导出只出 unsupported 汇总行，不抛错。"""
        context, page, page_errors, console_errors = self.new_page(
            path=self._legacy_path
        )
        self.open_ledger(page)
        # The button is disabled for legacy snapshots; call the exporter
        # directly so the unsupported path itself is exercised.
        with page.expect_download() as download_info:
            page.evaluate("() => exportCostCSV()")
        download = download_info.value
        _, rows = self.decode_csv(Path(download.path()).read_bytes())
        self.assertEqual(rows[0], CSV_COLUMNS)
        self.assertEqual(len(rows), 2)
        summary = rows[1]
        self.assertEqual(summary[COL["row_type"]], "summary")
        self.assertEqual(summary[COL["status"]], "unsupported")
        self.assertEqual(len(summary), 25)
        # No entry columns leak into the unsupported row.
        for col in CSV_COLUMNS[7:]:
            self.assertEqual(summary[COL[col]], "", col)
        self.assertNoErrors(page_errors, console_errors)
        context.close()

    def test_csv_with_no_records_renders_no_entries_summary(self):
        context, page, page_errors, console_errors = self.new_page(
            path=self._empty_path
        )
        self.open_ledger(page)
        self.set_gran(page)
        filename, _, rows = self.fetch_cost_csv(page)
        self.assertEqual(filename, "tokens-cost-day.csv")
        self.assertEqual(rows[0], CSV_COLUMNS)
        self.assertEqual(self.entry_rows(rows), [])
        summary = self.summary_row(rows)
        self.assertEqual(summary[COL["status"]], "no_entries")
        self.assertEqual(summary[COL["total_calls"]], "0")
        self.assertEqual(summary[COL["priced_subtotal"]], "")
        self.assertNoErrors(page_errors, console_errors)
        context.close()

    def test_csv_bigint_tokens_and_amounts_exact(self):
        """BigInt 超 safe integer：token 与金额精确（12 位小数内无漂移）。"""
        context, page, page_errors, console_errors = self.new_page(
            path=self._bigint_path
        )
        self.seed_config(page, self.usd_reference_config())
        self.open_ledger(page)
        _, _, rows = self.fetch_cost_csv(page)
        row = self.row_by_model(rows, "gpt-6.1-sol")
        # 9.2e15 > 2**53-1: raw decimal digits, no separators, no sci-notation.
        self.assertEqual(row[COL["input_tokens"]], "9200000000000000")
        # 9.2e15 / 1e6 * $2/M = $18,400,000,000 exactly.
        self.assertEqual(row[COL["estimated_cost"]], "18400000000")
        summary = self.summary_row(rows)
        self.assertEqual(summary[COL["priced_subtotal"]], "18400000000")
        flat = ",".join(",".join(r) for r in rows)
        self.assertNotIn("9.2e", flat.lower())
        self.assertNotIn("9200000000000001", flat)
        self.assertNoErrors(page_errors, console_errors)
        context.close()

    # -- injection safety ---------------------------------------------------

    def test_csv_escapes_quotes_commas_crlf_and_formula_prefixes(self):
        context, page, page_errors, console_errors = self.new_page(
            path=self._hostile_path
        )
        self.open_ledger(page)
        _, text, rows = self.fetch_cost_csv(page)
        # Every decoded cell is formula-safe after the csvCell guard.
        for row in rows:
            for cell in row:
                self.assertFormulaSafe(cell)
        # Round-trip: names survive csv.reader intact.
        for name, expected in HOSTILE_EXPECTED.items():
            row = self.row_by_model(rows, expected)
            self.assertIn(name, row[COL["model"]])
        for name in ("plain-model", "comma,model", 'quote"model',
                     " \tleading-ws", "\x01ctrl-char"):
            self.row_by_model(rows, name)
        # Raw text: RFC4180 quoting for comma/quote/CRLF cells.
        self.assertIn('"comma,model"', text)
        self.assertIn('"quote""model"', text)
        self.assertIn('"line\r\nbreak"', text)
        # Row terminators are LF; the only CRLF lives inside the quoted cell.
        self.assertEqual(text.count("\r\n"), 1)
        # Unicode-leading formula cells carry the guard prefix verbatim.
        self.assertIn("' =nbsp-eq", text)
        self.assertIn("'﻿=bom-eq", text)
        self.assertIn("'​=zwsp-eq", text)
        self.assertNoErrors(page_errors, console_errors)
        context.close()

    def test_trend_csv_also_neutralizes_formula_prefixes(self):
        """趋势 CSV（既有 #csv-btn）同样走 csvCell：公式防护 + quoting。"""
        context, page, page_errors, console_errors = self.new_page(
            path=self._trend_path
        )
        self.open_ledger(page)
        self.set_gran(page)
        filename, raw = self.download_csv(page, "#csv-btn")
        self.assertEqual(filename, "tokens-day.csv")
        text, rows = self.decode_csv(raw)
        for row in rows:
            for cell in row:
                self.assertFormulaSafe(cell)
        # Raw text carries the apostrophe guard for hostile header names.
        self.assertIn("'=SUM(A1:A9)", text)
        self.assertIn("'@cmd", text)
        self.assertIn("'+1024", text)
        self.assertIn("'-42", text)
        # Comma / quote names stay RFC4180-quoted.
        self.assertIn('"comma,model"', text)
        self.assertIn('"quote""model"', text)
        self.assertIn('"line\r\nbreak"', text)
        self.assertNoErrors(page_errors, console_errors)
        context.close()

    # -- privacy ---------------------------------------------------------------

    def test_csv_leaks_no_notes_sessions_or_paths(self):
        context, page, page_errors, console_errors = self.new_page()
        self.seed_config(page, self.usd_reference_config({
            price_key("model-a"):
                {"rates": ["1", "", "", "", ""],
                 "note": "SECRET-CHANNEL-NOTE"},
        }))
        self.open_ledger(page)
        _, text, rows = self.fetch_cost_csv(page)
        self.assertNotIn("SECRET-CHANNEL-NOTE", text)
        self.assertNotIn("synthetic-csv-a1", text)          # session ids
        self.assertNotIn("/synthetic/cost-fixture", text)   # cwd paths
        header = ",".join(rows[0]).lower()
        for banned in ("note", "session", "title", "path"):
            self.assertNotIn(banned, header)
        self.assertNoErrors(page_errors, console_errors)
        context.close()


if __name__ == "__main__":
    unittest.main()
