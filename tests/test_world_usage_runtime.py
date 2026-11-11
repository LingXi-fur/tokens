"""Data-first world layer: page-memory rates, explicit scope and safe fallback."""
import unittest

from tests import test_world_runtime as runtime


@unittest.skipIf(runtime.sync_playwright is None or not (runtime.WORLD / "generated/world.bundle.js").exists(), "Playwright and prototype build required")
class TestWorldUsageRuntime(unittest.TestCase):
    setUpClass = classmethod(runtime.TestWorldRuntime.setUpClass.__func__)
    tearDownClass = classmethod(runtime.TestWorldRuntime.tearDownClass.__func__)
    setUp = runtime.TestWorldRuntime.setUp
    tearDown = runtime.TestWorldRuntime.tearDown
    load = runtime.TestWorldRuntime.load
    require_webgl = runtime.TestWorldRuntime.require_webgl

    def test_report_day_costs_and_explicit_filter_scope(self):
        self.load()
        self.require_webgl()
        self.assertIn("2026-10-13", self.page.locator("#report-date").inner_text())
        self.assertIn("USD", self.page.locator("#loaded-cost").inner_text())
        self.assertIn("小计", self.page.locator("#cost-label").inner_text())
        self.assertIn("未知", self.page.locator("#cost-coverage").inner_text())
        headline = self.page.locator("#today-tokens").inner_text()
        amount = self.page.locator("#loaded-cost").inner_text()
        self.page.locator('a[href="#meadow"][data-chapter]').click()
        filters = self.page.locator("#model-filters button")
        for index in range(filters.count()):
            filters.nth(index).click()
        self.assertEqual(self.page.locator("#today-tokens").inner_text(), headline)
        self.assertEqual(self.page.locator("#loaded-cost").inner_text(), amount)
        self.page.locator("#scope-filtered").click()
        self.assertIn("当前筛选无记录", self.page.locator("#today-summary").inner_text())
        self.assertEqual(self.page.locator("#today-models tbody tr").count(), 0)
        self.page.locator("#scope-all").click()
        self.assertGreater(self.page.locator("#today-models tbody tr").count(), 0)
        self.assertGreater(self.page.locator("#cost-models tbody tr").count(), 0)

    def test_rates_cancel_apply_blank_free_restore_and_focus(self):
        self.load(no_webgl=True)
        original = self.page.locator("#loaded-cost").inner_text()
        self.page.locator("#prices-open").click()
        self.assertTrue(self.page.locator("#prices").evaluate("node=>node.open"))
        key = self.page.evaluate("CostCore.modelKey(TokensWorld.usage().all.loaded.cost.entries.find(e=>e.fullPriced&&e.costScaled>0n).model)")
        selector = self.page.evaluate("key=>'#price-fields input[data-price-key=\"'+CSS.escape(key)+'\"]'", key)
        inputs = self.page.locator(selector)
        for index in range(inputs.count()):
            inputs.nth(index).fill("0")
        self.page.locator("#prices-cancel").click()
        self.assertEqual(self.page.locator("#loaded-cost").inner_text(), original)
        self.page.wait_for_function("document.activeElement.id==='prices-open'")
        self.assertEqual(self.page.evaluate("document.activeElement.id"), "prices-open")
        self.page.locator("#prices-open").click()
        for index in range(inputs.count()):
            inputs.nth(index).fill("0")
        self.page.locator('#price-form button[type="submit"]').click()
        self.assertNotEqual(self.page.locator("#loaded-cost").inner_text(), original)
        self.page.locator("#prices-open").click()
        for index in range(inputs.count()):
            inputs.nth(index).fill("")
        self.page.locator('#price-form button[type="submit"]').click()
        self.assertIn("待定价", self.page.locator("#cost-models").inner_text())
        self.page.locator("#prices-open").click()
        inputs.first.fill("-1")
        self.page.locator('#price-form button[type="submit"]').click()
        self.assertTrue(self.page.locator("#prices").evaluate("node=>node.open"))
        self.assertTrue(self.page.locator("#price-error").inner_text())
        self.page.once("dialog", lambda dialog: dialog.accept())
        self.page.locator("#prices-reset").click()
        self.page.locator('#price-form button[type="submit"]').click()
        self.assertEqual(self.page.locator("#loaded-cost").inner_text(), original)
        self.page.reload()
        self.page.wait_for_function("window.TokensWorld?.ready")
        self.assertEqual(self.page.locator("#loaded-cost").inner_text(), original)

    def custom_payload(self, payload, filename):
        import importlib.util
        spec = importlib.util.spec_from_file_location('usage_special_fixture', runtime.ROOT / 'scripts/build_world_prototype.py')
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        destination = self.root / filename
        destination.write_text(builder.build_html(payload), encoding='utf-8')
        self.page.add_init_script("const get=HTMLCanvasElement.prototype.getContext;HTMLCanvasElement.prototype.getContext=function(type,...args){return type==='webgl2'?null:get.call(this,type,...args)}")
        self.page.goto(destination.as_uri(), wait_until='load')
        self.page.wait_for_function('window.TokensWorld?.ready')

    def test_all_unknown_models_no_record_and_free_are_not_confused(self):
        parts = ['input', 'output', 'cache_read', 'cache_write', 'thoughts']
        payload = {'generated': '2026-10-13', 'models': ['a'], 'pretty': {'a': 'Example model'},
                   'day': [{'period': '2026-10-12', 'models': {'a': 50}, 'model_calls': {'a': 1}, 'total': 50, 'calls': 1}],
                   'cost': {'schema': 1, 'components': parts, 'models': [{'identity': 'a', 'model': 'unlisted-model', 'source': 'synthetic', 'hidden': False}],
                            'rows': [['2026-10-12', 0, [0, 0, 0, 0, 0], 50, 1, True]]}}
        self.custom_payload(payload, 'all-unknown.html')
        self.assertEqual(self.page.locator('#today-tokens').inner_text(), '无记录')
        self.assertIn('暂无可计价金额', self.page.locator('#loaded-cost').inner_text())
        self.assertEqual(self.page.locator('#cost-models tbody tr').count(), 1)
        self.assertIn('50', self.page.locator('#cost-models').inner_text())
        self.assertIn('未知', self.page.locator('#cost-models').inner_text())
        self.assertEqual(self.page.locator('#cost-models tbody tr td').nth(2).inner_text(), '—')
        payload['day'][0]['period'] = '2026-10-13'
        payload['cost']['rows'][0] = ['2026-10-13', 0, [50, 0, 0, 0, 0], 50, 1, False]
        self.custom_payload(payload, 'free.html')
        self.page.locator('#prices-open').click()
        inputs = self.page.locator('#price-fields input')
        for index in range(inputs.count()):
            inputs.nth(index).fill('0')
        self.page.locator('#price-form button[type="submit"]').click()
        self.assertEqual(self.page.locator('#loaded-cost').inner_text(), 'USD 0.0000')
        self.assertIn('估算总额', self.page.locator('#cost-label').inner_text())
        self.assertNotIn('暂无', self.page.locator('#loaded-cost').inner_text())

    def test_pending_scroll_keeps_latest_position(self):
        self.page.add_init_script("const timer=window.setTimeout;window.setTimeout=(callback,delay,...args)=>timer(callback,Math.max(delay||0,80),...args)")
        self.page.goto(self.html.as_uri(), wait_until='domcontentloaded')
        self.page.wait_for_function('window.TokensWorld?.metrics() !== null && !!window.TokensWorld')
        self.page.evaluate("""() => {for(const value of [.3,.5,.7]){scrollTo(0,(document.querySelector('#village').offsetTop-96)*value);dispatchEvent(new Event('scroll'));}}""")
        self.page.wait_for_function('window.TokensWorld.ready')
        self.page.wait_for_function('Math.abs(TokensWorld.metrics().progress-.7)<.001 && !TokensWorld.metrics().pending')
        self.assertTrue(self.page.evaluate('TokensWorld.metrics().upgraded'))

    def test_texture_decode_failure_keeps_owned_fallback(self):
        self.page.add_init_script("window.createImageBitmap=()=>Promise.reject(new Error('synthetic decode failure'))")
        self.load()
        self.require_webgl()
        self.assertEqual(self.page.evaluate('TokensWorld.metrics().ownedTextures'), 6)
        self.assertFalse(self.page.evaluate('TokensWorld.metrics().upgraded'))
        self.page.evaluate('TokensWorld.dispose()')
        self.assertEqual(self.page.locator('canvas').count(), 0)

    def test_early_cancel_keeps_data_and_creates_no_canvas(self):
        self.page.add_init_script("const raf=window.requestAnimationFrame;window.requestAnimationFrame=callback=>raf.call(window,time=>{window.TokensWorld?.dispose();callback(time)})")
        self.load()
        self.assertEqual(self.page.locator("canvas").count(), 0)
        self.assertTrue(self.page.locator("#today-tokens").inner_text())
        self.assertIn("USD", self.page.locator("#loaded-cost").inner_text())

    def test_no_storage_access_mobile_language_and_fallback(self):
        self.page.add_init_script("""window.storageCalls=[];for(const method of ['getItem','setItem','removeItem','clear','key']){const old=Storage.prototype[method];Storage.prototype[method]=function(...args){storageCalls.push(method);return old.apply(this,args)}}""")
        self.load(no_webgl=True)
        for width in (360, 390, 768, 1360):
            self.page.set_viewport_size({"width": width, "height": 900})
            self.page.evaluate("scrollTo(0,0)")
            rect = self.page.locator("#core-stats").bounding_box()
            self.assertGreaterEqual(rect["x"], 0)
            self.assertLessEqual(rect["x"] + rect["width"], width + 1)
            self.assertLess(self.page.evaluate("document.documentElement.scrollWidth"), width + 2)
            self.assertTrue(self.page.locator("#today-tokens").is_visible())
            self.assertTrue(self.page.locator("#loaded-cost").is_visible())
            self.assertTrue(self.page.evaluate("document.querySelector('.bar').getBoundingClientRect().bottom<=document.querySelector('#core-stats').getBoundingClientRect().top"))
        self.page.locator("#language").click()
        self.assertIn("Report day", self.page.locator("#report-date").inner_text())
        self.assertIn("Priced subtotal", self.page.locator("#cost-summary").inner_text())
        before = self.page.locator("body").evaluate("node=>node.classList.contains('dark')")
        self.page.locator("#theme").click()
        self.assertNotEqual(self.page.locator("body").evaluate("node=>node.classList.contains('dark')"), before)
        self.assertEqual(self.page.evaluate("storageCalls"), [])


if __name__ == "__main__":
    unittest.main()
