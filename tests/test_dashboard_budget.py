"""Monthly budget integration; synthetic HTML and isolated browser only."""
import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from tokens_cli import dashboard_wire, report_dashboard
from tests import test_dashboard_cost as base

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None


class BudgetIntegrationContracts(unittest.TestCase):
    def test_budget_core_is_embedded_once_before_dashboard(self):
        template = report_dashboard._dashboard_template()
        self.assertEqual(1, template.count('global.BudgetCore='))
        self.assertLess(template.index('global.BudgetCore='), template.index('BudgetCore.create('))
        self.assertIn('id=budget-body', template)
        self.assertIn('id=budget-modal', template)


@unittest.skipUnless(sync_playwright, 'Playwright is required')
class DashboardBudgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        with mock.patch('tokens_cli.dashboard_payload.readers.build_session_index', return_value={}), \
             mock.patch('tokens_cli.dashboard_payload.readers.session_title', return_value=''), \
             mock.patch('tokens_cli.dashboard_payload.readers.load_session_summaries', return_value={}):
            cls.payload = report_dashboard.build_payload([
                base.record('2026-10-01', 'model-a', 1000000, 'synthetic-budget-one'),
                base.record('2026-10-09', 'model-a', 1000000, 'synthetic-budget-two'),
                base.record('2026-10-10', 'model-a', 2000000, 'synthetic-budget-three'),
            ], since=None, until=None, sources=['claude'], generated_at=datetime(2026, 10, 10, 12, 0))
        cls.payload['cost'] = base.cost_block([('model-a', 'model-a', False)], [
            ['2026-10-01', 0, [1000000, 0, 0, 0, 0], 1000000, 1, False],
            ['2026-10-09', 0, [1000000, 0, 0, 0, 0], 1000000, 1, False],
            ['2026-10-10', 0, [2000000, 0, 0, 0, 0], 2000000, 1, False],
        ])
        cls.payload['snapshot']['timezone'] = 'UTC'
        cls.path = Path(cls._tmp.name) / 'synthetic-budget.html'
        cls.path.write_text(report_dashboard.render_dashboard(dashboard_wire.encode_payload(cls.payload)), encoding='utf-8')
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        cls._tmp.cleanup()

    def page(self, stored=None, *, unavailable=False, viewport=1280):
        context = self.browser.new_context(viewport={'width': viewport, 'height': 820}, reduced_motion='reduce')
        page = context.new_page()
        page.add_init_script("""
          const originalSet=Storage.prototype.setItem;
          window.budgetWrites=[];
          Storage.prototype.setItem=function(key,value){
            if(key==='tk-budget-v1')window.budgetWrites.push(value);
            return originalSet.call(this,key,value);
          };
        """)
        prices = {'v': 1, 'currency': 'USD', 'reference': False, 'prices': {
            base.price_key('model-a'): {'rates': ['1', '1', '1', '1', '1'], 'note': ''}}}
        page.add_init_script('localStorage.setItem("tk-cost-v1",'+json.dumps(json.dumps(prices))+');')
        if stored is not None:
            page.add_init_script('localStorage.setItem("tk-budget-v1",'+json.dumps(stored)+');window.budgetWrites=[];')
        if unavailable:
            page.add_init_script("""
              const read=Storage.prototype.getItem;
              Storage.prototype.getItem=function(key){if(key==='tk-budget-v1')throw new Error('synthetic blocked');return read.call(this,key);};
              const write=Storage.prototype.setItem;
              Storage.prototype.setItem=function(key,value){if(key==='tk-budget-v1')throw new Error('synthetic blocked');return write.call(this,key,value);};
            """)
        errors=[]
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('console', lambda message: errors.append(message.text) if message.type=='error' else None)
        page.route('http://**/*', lambda route: route.abort())
        page.route('https://**/*', lambda route: route.abort())
        page.goto(self.path.as_uri(), wait_until='load')
        page.locator('#section-cost').scroll_into_view_if_needed()
        page.wait_for_function("document.querySelector('#budget-body')?.textContent.length>0")
        self.addCleanup(context.close)
        self.addCleanup(lambda: self.assertEqual([], errors))
        return page

    def save(self, page, value='100'):
        page.locator('#budget-edit').click()
        page.locator('#budget-amount').fill(value)
        page.locator('#budget-save').click()

    def test_load_cancel_save_clear_and_reload_do_not_autowrite(self):
        page=self.page()
        self.assertEqual([], page.evaluate('budgetWrites'))
        self.assertEqual(0, page.locator('[data-budget-comparison]').count())
        page.locator('#budget-edit').click()
        page.locator('#budget-amount').fill('123.45')
        page.keyboard.press('Escape')
        self.assertEqual([], page.evaluate('budgetWrites'))
        self.assertEqual('budget-edit', page.evaluate('document.activeElement.id'))
        self.save(page)
        self.assertEqual('100.00', page.evaluate("JSON.parse(localStorage.getItem('tk-budget-v1')).budgets['2026-10'].USD"))
        self.assertGreater(page.locator('[data-budget-comparison]').count(), 0)
        page.reload();page.locator('#section-cost').scroll_into_view_if_needed()
        page.wait_for_selector('[data-budget-comparison]')
        self.assertEqual([], page.evaluate('budgetWrites'))
        page.locator('#budget-clear').click()
        self.assertEqual({}, page.evaluate("JSON.parse(localStorage.getItem('tk-budget-v1')).budgets"))
        self.assertEqual(0, page.locator('[data-budget-comparison]').count())

    def test_bad_input_corrupt_storage_and_memory_only(self):
        page=self.page('{broken')
        self.assertEqual('{broken',page.evaluate("localStorage.getItem('tk-budget-v1')"))
        self.assertEqual([],page.evaluate('budgetWrites'))
        self.assertIn('损坏',page.locator('#budget-storage').inner_text())
        page.locator('#budget-edit').click()
        for value in ['0','-1','+1','1e3','1.001','1000000.01']:
            page.locator('#budget-amount').fill(value);page.locator('#budget-save').click()
            self.assertEqual([],page.evaluate('budgetWrites'))
            self.assertTrue(page.locator('#budget-modal').evaluate("el=>el.classList.contains('open')"))
        page.locator('#budget-amount').fill('100');page.locator('#budget-save').click()
        self.assertEqual(1,len(page.evaluate('budgetWrites')))
        memory=self.page(unavailable=True)
        self.save(memory)
        self.assertGreater(memory.locator('[data-budget-comparison]').count(),0)
        self.assertIn('本次',memory.locator('#budget-storage').inner_text())

    def test_corrupt_configuration_shapes_are_preserved_without_writes(self):
        oversized=' ' * 32769
        invalid=[
            '', oversized, 'null', '[]',
            json.dumps({'v':2,'budgets':{}}),
            json.dumps({'v':1,'budgets':{'2026-13':{'USD':'100'}}}),
            json.dumps({'v':1,'budgets':{'2026-10':{'EUR':'100'}}}),
            json.dumps({'v':1,'budgets':{'2026-10':{'USD':'1000000.01'}}}),
        ]
        for stored in invalid:
            with self.subTest(size=len(stored),prefix=stored[:60]):
                page=self.page(stored)
                self.assertEqual(stored,page.evaluate("localStorage.getItem('tk-budget-v1')"))
                self.assertEqual([],page.evaluate('budgetWrites'))
                self.assertIn('损坏',page.locator('#budget-storage').inner_text())
                self.assertEqual(0,page.locator('[data-budget-comparison]').count())
                page.locator('#budget-edit').click()
                page.locator('#budget-amount').fill('123')
                page.keyboard.press('Escape')
                self.assertEqual(stored,page.evaluate("localStorage.getItem('tk-budget-v1')"))
                self.assertEqual([],page.evaluate('budgetWrites'))
                page.context.close()

    def test_capacity_rejects_new_month_without_deleting_or_blocking_existing(self):
        budgets={f'{2000+n//12:04d}-{n%12+1:02d}':{'USD':'1.00'} for n in range(120)}
        raw=json.dumps({'v':1,'budgets':budgets})
        page=self.page(raw)
        self.save(page,'100')
        self.assertIn('容量',page.locator('#budget-editor-status').inner_text())
        self.assertTrue(page.locator('#budget-modal').evaluate("el=>el.classList.contains('open')"))
        self.assertEqual(raw,page.evaluate("localStorage.getItem('tk-budget-v1')"))
        self.assertEqual([],page.evaluate('budgetWrites'))
        page.keyboard.press('Escape')
        page.evaluate("DATA.calendar_day='2000-01-10';renderCostLedger()")
        self.save(page,'2')
        saved=page.evaluate("JSON.parse(localStorage.getItem('tk-budget-v1')).budgets")
        self.assertEqual(120,len(saved))
        self.assertEqual('2.00',saved['2000-01']['USD'])
        self.assertEqual('1.00',saved['2000-02']['USD'])
        self.assertEqual(1,len(page.evaluate('budgetWrites')))

    def test_same_month_refresh_preserves_draft_and_currency_change_rejects_save(self):
        page=self.page();self.save(page,'100')
        before=page.evaluate("localStorage.getItem('tk-budget-v1')")
        page.locator('#budget-edit').click()
        page.locator('#budget-amount').fill('123.45')
        page.evaluate("""() => {
          const next=structuredClone(DATA);
          next.generated='2026-10-10 13:00';
          next.snapshot.id='synthetic-budget-same-month';
          reconcileLiveData(next);
        }""")
        self.assertEqual('123.45',page.locator('#budget-amount').input_value())
        self.assertEqual('budget-amount',page.evaluate('document.activeElement.id'))
        self.assertEqual(before,page.evaluate("localStorage.getItem('tk-budget-v1')"))
        page.evaluate("costPrices={...costPrices,currency:'CNY'};renderCostLedger()")
        page.locator('#budget-save').click()
        self.assertIn('变化',page.locator('#budget-editor-status').inner_text())
        self.assertEqual(before,page.evaluate("localStorage.getItem('tk-budget-v1')"))
        self.assertEqual(1,len(page.evaluate('budgetWrites')))
        page.keyboard.press('Escape')
        self.save(page,'200')
        self.assertEqual({'USD':'100.00','CNY':'200.00'},page.evaluate("JSON.parse(localStorage.getItem('tk-budget-v1')).budgets['2026-10']"))

    def test_write_failure_keeps_saved_value_and_only_changes_page_memory(self):
        raw=json.dumps({'v':1,'budgets':{'2026-10':{'USD':'100.00'}}})
        page=self.page(raw)
        page.evaluate("""() => {
          const write=Storage.prototype.setItem;
          Storage.prototype.setItem=function(key,value){
            if(key==='tk-budget-v1')throw new Error('synthetic quota exceeded');
            return write.call(this,key,value);
          };
        }""")
        self.save(page,'200')
        self.assertIn('$200.00',page.locator('#budget-values').inner_text())
        self.assertIn('本次',page.locator('#budget-storage').inner_text())
        self.assertEqual(raw,page.evaluate("localStorage.getItem('tk-budget-v1')"))
        page.locator('#budget-clear').click()
        self.assertEqual(0,page.locator('[data-budget-comparison]').count())
        self.assertEqual(raw,page.evaluate("localStorage.getItem('tk-budget-v1')"))
        page.reload()
        page.locator('#section-cost').scroll_into_view_if_needed()
        page.wait_for_function("document.querySelectorAll('[data-budget-comparison]').length===4")
        self.assertIn('$100.00',page.locator('#budget-values').inner_text())
        self.assertEqual([],page.evaluate('budgetWrites'))
        self.assertEqual('',page.locator('#budget-storage').inner_text())

    def test_enter_saves_valid_amount_but_not_invalid_or_composing_input(self):
        page=self.page()
        page.locator('#budget-edit').click()
        page.locator('#budget-amount').fill('12.34')
        for composition in ({'isComposing':True},{'keyCode':229}):
            page.locator('#budget-amount').dispatch_event('keydown',{'key':'Enter','code':'Enter',**composition})
            self.assertEqual([],page.evaluate('budgetWrites'))
            self.assertTrue(page.locator('#budget-modal').evaluate("el=>el.classList.contains('open')"))
        page.locator('#budget-amount').fill('0')
        page.keyboard.press('Enter')
        self.assertEqual('true',page.locator('#budget-amount').get_attribute('aria-invalid'))
        self.assertEqual([],page.evaluate('budgetWrites'))
        self.assertEqual('budget-amount',page.evaluate('document.activeElement.id'))
        page.locator('#budget-amount').fill('12.34')
        page.keyboard.press('Enter')
        page.wait_for_function("!document.getElementById('budget-modal').classList.contains('open')")
        self.assertEqual('12.34',page.evaluate("JSON.parse(localStorage.getItem('tk-budget-v1')).budgets['2026-10'].USD"))
        self.assertEqual(1,len(page.evaluate('budgetWrites')))
        self.assertEqual('budget-edit',page.evaluate('document.activeElement.id'))

    def test_keyboard_clear_returns_focus_to_budget_editor(self):
        page=self.page();self.save(page,'100')
        page.locator('#budget-clear').focus()
        page.keyboard.press('Enter')
        self.assertEqual(0,page.locator('[data-budget-comparison]').count())
        self.assertTrue(page.locator('#budget-clear').is_disabled())
        self.assertEqual('budget-edit',page.evaluate('document.activeElement.id'))
        page.keyboard.press('Enter')
        page.wait_for_function("document.activeElement.id==='budget-amount'")
        self.assertEqual('',page.locator('#budget-amount').input_value())
        page.locator('#budget-amount').fill('100')
        page.keyboard.press('Enter')
        page.locator('#cost-price-btn').focus()
        page.evaluate('clearBudget()')
        self.assertEqual('cost-price-btn',page.evaluate('document.activeElement.id'))

    def test_manager_lists_confirmed_deletion_without_automatic_writes(self):
        raw=json.dumps({'v':1,'budgets':{'2026-09':{'CNY':'200.00'},'2026-10':{'CNY':'300.00','USD':'100.00'}}})
        page=self.page(raw)
        self.assertEqual(1,page.locator('#budget-manage').count())
        page.locator('#budget-manage').click()
        rows=page.locator('#budget-manager-list [data-budget-entry]')
        self.assertEqual(3,rows.count())
        self.assertIn('2026-10',rows.nth(0).inner_text())
        self.assertIn('USD',rows.nth(0).inner_text())
        self.assertIn('CNY',rows.nth(1).inner_text())
        self.assertEqual([],page.evaluate('budgetWrites'))
        rows.nth(0).locator('button').click()
        self.assertIn('100.00',page.locator('#budget-manager-confirm-text').inner_text())
        page.locator('#budget-manager-cancel-delete').click()
        self.assertEqual(raw,page.evaluate("localStorage.getItem('tk-budget-v1')"))
        rows.nth(0).locator('button').click()
        page.locator('#budget-manager-confirm-delete').click()
        saved=page.evaluate("JSON.parse(localStorage.getItem('tk-budget-v1')).budgets")
        self.assertEqual({'CNY':'300.00'},saved['2026-10'])
        self.assertEqual({'CNY':'200.00'},saved['2026-09'])
        self.assertEqual(1,len(page.evaluate('budgetWrites')))
        page.keyboard.press('Escape')
        self.assertEqual('budget-manage',page.evaluate('document.activeElement.id'))

    def test_manager_pagination_and_last_page_deletion_preserve_focus(self):
        budgets={f'2025-{month:02d}':{'USD':'1.00'} for month in range(1,13)}
        budgets['2026-01']={'USD':'2.00'}
        page=self.page(json.dumps({'v':1,'budgets':budgets}))
        page.locator('#budget-manage').click()
        self.assertEqual(12,page.locator('[data-budget-entry]').count())
        page.locator('#budget-manager-next').click()
        self.assertEqual(1,page.locator('[data-budget-entry]').count())
        self.assertIn('2025-01',page.locator('[data-budget-entry]').inner_text())
        self.assertEqual([],page.evaluate('budgetWrites'))
        page.locator('[data-budget-delete]').click()
        page.locator('#budget-manager-confirm-delete').click()
        self.assertEqual(12,page.locator('[data-budget-entry]').count())
        self.assertTrue(page.locator('#budget-manager-next').is_disabled())
        self.assertTrue(page.locator('#budget-manager-prev').is_disabled())
        self.assertTrue(page.evaluate("document.activeElement.matches('[data-budget-delete]')"))
        self.assertNotIn('2025-01',page.evaluate("JSON.parse(localStorage.getItem('tk-budget-v1')).budgets"))
        self.assertEqual(1,len(page.evaluate('budgetWrites')))

    def test_manager_confirmation_survives_language_and_live_month_changes(self):
        raw=json.dumps({'v':1,'budgets':{'2026-10':{'USD':'100.00','CNY':'200.00'}}})
        page=self.page(raw)
        page.locator('#budget-manage').click()
        page.locator('[data-budget-delete]').first.click()
        page.locator('#budget-manager-confirm-delete').focus()
        page.evaluate("""() => {
          applyLanguage('en',false);
          const next=structuredClone(DATA);next.calendar_day='2026-11-10';
          next.snapshot.id='synthetic-manager-month-change';reconcileLiveData(next);
          costPrices={...costPrices,currency:'CNY'};renderCostLedger();
        }""")
        self.assertEqual('budget-manager-confirm-delete',page.evaluate('document.activeElement.id'))
        self.assertIn('2026-10 · USD · 100.00',page.locator('#budget-manager-confirm-text').inner_text())
        self.assertEqual([],page.evaluate('budgetWrites'))
        page.keyboard.press('Enter')
        page.evaluate('confirmBudgetDeletion();confirmBudgetDeletion()')
        self.assertEqual({'CNY':'200.00'},page.evaluate("JSON.parse(localStorage.getItem('tk-budget-v1')).budgets['2026-10']"))
        self.assertEqual(1,len(page.evaluate('budgetWrites')))

    def test_manager_rejects_stale_confirmation_and_escape_never_writes(self):
        raw=json.dumps({'v':1,'budgets':{'2026-10':{'USD':'100.00'}}})
        page=self.page(raw)
        page.locator('#budget-manage').click();page.locator('[data-budget-delete]').click()
        page.evaluate("budgetConfig.budgets['2026-10'].USD='101.00';renderBudget()")
        page.locator('#budget-manager-confirm-delete').click()
        self.assertIn('变化',page.locator('#budget-manager-status').inner_text())
        self.assertIn('100.00',page.locator('#budget-manager-confirm-text').inner_text())
        self.assertEqual(raw,page.evaluate("localStorage.getItem('tk-budget-v1')"))
        page.keyboard.press('Escape')
        self.assertTrue(page.locator('#budget-manager-confirm').is_hidden())
        self.assertTrue(page.locator('#budget-manager-modal').evaluate("el=>el.classList.contains('open')"))
        page.keyboard.press('Escape')
        self.assertEqual('budget-manage',page.evaluate('document.activeElement.id'))
        self.assertEqual([],page.evaluate('budgetWrites'))

    def test_manager_unknown_date_empty_corrupt_and_failed_delete_storage(self):
        for stored in (None,'{broken'):
            page=self.page(stored)
            page.evaluate('delete DATA.calendar_day;renderBudget()')
            self.assertTrue(page.locator('#budget-edit').is_disabled())
            page.locator('#budget-manage').click()
            self.assertEqual(0,page.locator('[data-budget-entry]').count())
            self.assertTrue(page.locator('#budget-manager-empty').is_visible())
            if stored:self.assertIn('损坏',page.locator('#budget-manager-storage').inner_text())
            self.assertEqual([],page.evaluate('budgetWrites'))
            page.keyboard.press('Escape');page.context.close()
        raw=json.dumps({'v':1,'budgets':{'2026-10':{'USD':'100.00'}}})
        page=self.page(raw)
        page.evaluate("""() => {const write=Storage.prototype.setItem;
          Storage.prototype.setItem=function(key,value){if(key==='tk-budget-v1')throw new Error('synthetic quota exceeded');return write.call(this,key,value)};
          delete DATA.calendar_day;renderBudget();
        }""")
        page.locator('#budget-manage').click();page.locator('[data-budget-delete]').click()
        page.locator('#budget-manager-confirm-delete').click()
        self.assertTrue(page.locator('#budget-manager-empty').is_visible())
        self.assertIn('刷新',page.locator('#budget-manager-storage').inner_text())
        self.assertEqual('budget-manager-close',page.evaluate('document.activeElement.id'))
        self.assertEqual(raw,page.evaluate("localStorage.getItem('tk-budget-v1')"))

    def test_manager_releases_month_capacity_only_after_last_currency_removed(self):
        budgets={f'{2000+n//12:04d}-{n%12+1:02d}':{'USD':'1.00','CNY':'2.00'} for n in range(120)}
        page=self.page(json.dumps({'v':1,'budgets':budgets}))
        page.locator('#budget-manage').click()
        for remaining in (120,119):
            page.locator('[data-budget-delete]').first.click()
            page.locator('#budget-manager-confirm-delete').click()
            self.assertEqual(remaining,len(page.evaluate("JSON.parse(localStorage.getItem('tk-budget-v1')).budgets")))
        page.keyboard.press('Escape');self.save(page,'100')
        saved=page.evaluate("JSON.parse(localStorage.getItem('tk-budget-v1')).budgets")
        self.assertEqual(120,len(saved));self.assertEqual({'USD':'100.00'},saved['2026-10'])
        self.assertNotIn('2009-12',saved)

    def test_filters_do_not_change_budget_and_limits_hide_comparisons(self):
        page=self.page();self.save(page)
        value=page.locator('#budget-values').inner_text()
        page.evaluate("state.models=new Set();state.range='custom';state.rangeDate='2026-10-09';state.gran='day';state.focusPeriod=null;invalidateDerived();renderCostLedger()")
        self.assertEqual(value,page.locator('#budget-values').inner_text())
        page.evaluate("DATA.cost.total_incomplete=true;invalidateDerived();renderCostLedger()")
        self.assertEqual(0,page.locator('[data-budget-comparison]').count())
        self.assertIn('不完整',page.locator('#budget-status').inner_text())

    def test_currency_month_isolation_and_stale_draft(self):
        page=self.page();self.save(page)
        page.evaluate("costPrices={...costPrices,currency:'CNY'};renderCostLedger()")
        self.assertEqual(0,page.locator('[data-budget-comparison]').count())
        self.save(page,'200')
        saved=page.evaluate("JSON.parse(localStorage.getItem('tk-budget-v1')).budgets")
        self.assertEqual({'USD':'100.00','CNY':'200.00'},saved['2026-10'])
        page.locator('#budget-edit').click();page.locator('#budget-amount').fill('300')
        page.evaluate("DATA.calendar_day='2026-11-10';renderCostLedger()")
        page.locator('#budget-save').click()
        self.assertIn('变化',page.locator('#budget-editor-status').inner_text())
        self.assertEqual(saved,page.evaluate("JSON.parse(localStorage.getItem('tk-budget-v1')).budgets"))

    def test_clear_preserves_other_buckets_and_load_never_rewrites_storage(self):
        raw=json.dumps({'v':1,'budgets':{'2026-10':{'USD':'100.00','CNY':'200.00'},'2026-09':{'USD':'300.00'}}},indent=2)
        page=self.page(raw)
        self.assertEqual(raw,page.evaluate("localStorage.getItem('tk-budget-v1')"))
        self.assertEqual([],page.evaluate('budgetWrites'))
        page.locator('#budget-clear').click()
        self.assertEqual({'2026-10':{'CNY':'200.00'},'2026-09':{'USD':'300.00'}},page.evaluate("JSON.parse(localStorage.getItem('tk-budget-v1')).budgets"))

    def test_zero_counters_uncertain_and_unknown_snapshot_dates_hide_comparisons(self):
        page=self.page();self.save(page)
        page.evaluate("DATA.cost.rows.push(['2026-10-09',0,[0,0,0,0,0],0,0,true]);renderCostLedger()")
        self.assertEqual(0,page.locator('[data-budget-comparison]').count())
        self.assertIn('未确认',page.locator('#budget-status').inner_text())
        page.evaluate("DATA.cost.rows.pop();delete DATA.calendar_day;renderCostLedger()")
        self.assertEqual(0,page.locator('[data-budget-comparison]').count())
        self.assertTrue(page.locator('#budget-edit').is_disabled())
        page.evaluate("DATA.calendar_day='2026-10-10';DATA.snapshot.timezone='unknown-zone';renderCostLedger()")
        self.assertIn('时区',page.locator('#budget-status').inner_text())
        self.assertEqual(0,page.locator('[data-budget-comparison]').count())

    def test_keyboard_editor_draft_survives_language_and_price_save_recomputes(self):
        page=self.page();self.save(page,'100')
        self.assertIn('$4.00',page.locator('#budget-values').inner_text())
        page.locator('#budget-edit').focus();page.keyboard.press('Enter')
        page.wait_for_function("document.activeElement.id==='budget-amount'")
        page.locator('#budget-amount').fill('112.35')
        before=page.evaluate("localStorage.getItem('tk-budget-v1')")
        page.evaluate("applyLanguage('en',false)")
        self.assertEqual('112.35',page.locator('#budget-amount').input_value())
        self.assertEqual('budget-amount',page.evaluate('document.activeElement.id'))
        page.keyboard.press('Shift+Tab')
        self.assertTrue(page.locator('#budget-modal').evaluate("el=>el.contains(document.activeElement)"))
        page.keyboard.press('Escape')
        self.assertEqual(before,page.evaluate("localStorage.getItem('tk-budget-v1')"))
        page.locator('#cost-price-btn').click()
        rate=page.locator('#cost-editor-list input[data-cost-part="0"]').first
        rate.fill('2')
        page.locator('#cost-save').click()
        self.assertIn('$8.00',page.locator('#budget-values').inner_text())
        self.assertEqual(before,page.evaluate("localStorage.getItem('tk-budget-v1')"))

    def test_successful_snapshot_reconciles_month_without_saving_drafts(self):
        page=self.page();self.save(page,'100')
        snapshot=json.loads(json.dumps(self.payload));snapshot['calendar_day']='2026-11-10';snapshot['generated']='2026-11-10 12:00'
        snapshot['snapshot']['id']='synthetic-budget-november'
        snapshot['cost']['rows']=[['2026-11-09',0,[1000000,0,0,0,0],1000000,1,False]]
        page.locator('#budget-edit').click();page.locator('#budget-amount').fill('777')
        before=page.evaluate("localStorage.getItem('tk-budget-v1')")
        page.evaluate('next=>reconcileLiveData(next)',snapshot)
        page.locator('#budget-save').click()
        self.assertIn('变化',page.locator('#budget-editor-status').inner_text())
        self.assertEqual(before,page.evaluate("localStorage.getItem('tk-budget-v1')"))
        page.keyboard.press('Escape')
        self.assertIn('2026-11',page.locator('#budget-body').inner_text())
        self.assertEqual(0,page.locator('[data-budget-comparison]').count())
        self.save(page,'200')
        saved=page.evaluate("JSON.parse(localStorage.getItem('tk-budget-v1')).budgets")
        self.assertEqual('100.00',saved['2026-10']['USD']);self.assertEqual('200.00',saved['2026-11']['USD'])

    def test_live_polling_keeps_last_budget_on_bad_wire_then_accepts_new_month(self):
        context=self.browser.new_context(reduced_motion='reduce')
        self.addCleanup(context.close)
        page=context.new_page();errors=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.on('console',lambda message:errors.append(message.text) if message.type=='error' else None)
        self.addCleanup(lambda:self.assertEqual([],errors))
        wire=dashboard_wire.encode_payload(self.payload)
        html=report_dashboard.render_dashboard(wire,live={'enabled':True,'interval':300,'has_snapshot':True,'snapshot':self.payload['snapshot']['id']})
        response={'has_snapshot':True,'refreshing':False,'error':None,'snapshot':self.payload['snapshot']['id'],'wire':None}
        page.route('**/*',lambda route:route.abort())
        page.route('http://127.0.0.1:9876/dashboard',lambda route:route.fulfill(content_type='text/html',body=html))
        page.route('http://127.0.0.1:9876/api/status',lambda route:route.fulfill(content_type='application/json',body=json.dumps({key:value for key,value in response.items() if key!='wire'})))
        page.route('http://127.0.0.1:9876/api/snapshot',lambda route:route.fulfill(content_type='application/json',body=json.dumps(response)))
        prices={'v':1,'currency':'USD','reference':False,'prices':{base.price_key('model-a'):{'rates':['1','1','1','1','1'],'note':''}}}
        page.add_init_script('localStorage.setItem("tk-cost-v1",'+json.dumps(json.dumps(prices))+');')
        page.goto('http://127.0.0.1:9876/dashboard');page.locator('#section-cost').scroll_into_view_if_needed()
        page.wait_for_function("document.querySelector('#budget-body')?.textContent.includes('2026-10')")
        self.save(page)
        before=page.locator('#budget-values').inner_text()
        response.update(snapshot='synthetic-budget-bad',wire={'v':999})
        page.select_option('#live-refresh','300')
        page.wait_for_function("liveUi.kind==='error'")
        self.assertEqual(before,page.locator('#budget-values').inner_text())
        self.assertIn('2026-10',page.locator('#budget-body').inner_text())
        snapshot=json.loads(json.dumps(self.payload));snapshot['calendar_day']='2026-11-10';snapshot['generated']='2026-11-10 12:00'
        snapshot['snapshot']['id']='synthetic-budget-live-november'
        snapshot['cost']['rows']=[['2026-11-09',0,[1000000,0,0,0,0],1000000,1,False]]
        response.update(snapshot=snapshot['snapshot']['id'],wire=dashboard_wire.encode_payload(snapshot))
        page.select_option('#live-refresh','900')
        page.wait_for_function("DATA.calendar_day==='2026-11-10'")
        self.assertIn('2026-11',page.locator('#budget-body').inner_text())
        self.assertEqual(0,page.locator('[data-budget-comparison]').count())
        self.assertEqual('100.00',page.evaluate("JSON.parse(localStorage.getItem('tk-budget-v1')).budgets['2026-10'].USD"))

    def test_language_layout_and_export_privacy(self):
        page=self.page();self.save(page,'9876.54')
        page.locator('#budget-manage').click()
        page.locator('[data-budget-delete]').click()
        page.locator('#budget-manager-confirm-delete').focus()
        for width in (320,390,1280):
            page.set_viewport_size({'width':width,'height':820})
            for language in ('en','zh'):
                for theme in ('dark','light'):
                    page.evaluate("([language,theme])=>{applyLanguage(language,false);applyTheme(theme);renderCostLedger()}",[language,theme])
                    self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),width+1)
                    self.assertLessEqual(page.locator('.budget-manager-sheet').evaluate('el=>el.scrollWidth'),page.locator('.budget-manager-sheet').evaluate('el=>el.clientWidth')+1)
                    self.assertEqual('budget-manager-confirm-delete',page.evaluate('document.activeElement.id'))
                    self.assertNotIn('9876.54',page.evaluate('JSON.stringify(DATA)'))
        page.evaluate("() => {window.__budgetBlobs=[];const original=URL.createObjectURL.bind(URL);URL.createObjectURL=blob=>{window.__budgetBlobs.push(blob);return original(blob)};}")
        page.evaluate('exportCostCSV();exportCSV();exportDailyCSV();exportMarkdown();saveFlowSVG()')
        page.keyboard.press('Escape')
        self.assertEqual(1,len(page.evaluate('budgetWrites')))
        page.keyboard.press('Escape')
        self.assertEqual('budget-manage',page.evaluate('document.activeElement.id'))
        for kind in ('passport', 'receipt'):
            page.evaluate('(kind)=>openShare(kind)', kind)
            page.locator('#share-save').click()
            page.evaluate('closeShare()')
        contents=page.evaluate('Promise.all(window.__budgetBlobs.map(blob=>blob.text()))')
        self.assertGreaterEqual(len(contents),7)
        self.assertEqual(2,page.evaluate("window.__budgetBlobs.filter(blob=>blob.type.startsWith('text/html')).length"))
        self.assertFalse(any('9876.54' in text for text in contents))
        self.assertNotIn('9876.54',self.path.read_text(encoding='utf-8'))
        self.assertEqual('9876.54',page.evaluate("JSON.parse(localStorage.getItem('tk-budget-v1')).budgets['2026-10'].USD"))


if __name__ == '__main__':
    unittest.main()
