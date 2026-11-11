"""Standalone synthetic prototype browser checks. Never load private profiles."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from urllib.parse import urlsplit

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "ui" / "world"


@unittest.skipIf(sync_playwright is None or not (WORLD / "generated/world.bundle.js").exists(), "Playwright and prototype build required")
class TestWorldRuntime(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("world_builder_runtime", ROOT / "scripts/build_world_prototype.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls.temp = tempfile.TemporaryDirectory(prefix="tokens-world-test-")
        cls.root = Path(cls.temp.name)
        cls.html = cls.root / "index.html"
        cls.html.write_text(module.build_html(), encoding="utf-8")
        cls.runner = sync_playwright().start()
        engine = os.environ.get("TOKENS_WORLD_BROWSER", "chromium")
        cls.engine = engine
        arguments = ['--password-store=basic', '--use-mock-keychain', '--disable-sync',
                     '--disable-extensions', '--disable-background-networking',
                     '--disable-component-update', '--no-first-run', '--no-default-browser-check'] if engine == "chromium" else []
        cls.browser = getattr(cls.runner, engine).launch_persistent_context(
            str(cls.root / "fresh-profile"), headless=True, args=arguments,
            viewport={"width": 1360, "height": 900}, accept_downloads=False, has_touch=True,
        )

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.runner.stop()
        cls.temp.cleanup()

    def setUp(self):
        self.page = self.browser.new_page()
        self.errors, self.external = [], []
        self.page.on("pageerror", lambda error: self.errors.append(str(error)[:200]))

        def guard(route):
            if urlsplit(route.request.url).scheme in ("http", "https"):
                self.external.append(True)
                route.abort()
            else:
                route.continue_()
        self.page.route("**/*", guard)

    def tearDown(self):
        self.page.close()
        self.assertEqual(self.errors, [])
        self.assertEqual(self.external, [])

    def load(self, *, no_webgl=False, reduced=False):
        if no_webgl:
            self.page.add_init_script("const get=HTMLCanvasElement.prototype.getContext;HTMLCanvasElement.prototype.getContext=function(type,...args){return type==='webgl2'?null:get.call(this,type,...args)}")
        if reduced:
            self.page.emulate_media(reduced_motion="reduce")
        self.page.goto(self.html.as_uri(), wait_until="load")
        self.page.wait_for_function("window.TokensWorld?.ready")

    def require_webgl(self):
        self.assertTrue(self.page.evaluate("!!TokensWorld.metrics()"), "3D did not initialize: don't silently count fallback as WebGL acceptance")

    def test_scene_scroll_hover_click_and_idle(self):
        self.load()
        self.require_webgl()
        self.assertEqual(self.page.locator("canvas").count(), 1)
        self.page.wait_for_function("!TokensWorld.metrics().pending")
        first = self.page.evaluate("TokensWorld.metrics().camera")
        self.page.locator('a[href="#village"][data-chapter]').click()
        self.page.wait_for_function("TokensWorld.metrics().progress > .99 && !TokensWorld.metrics().pending")
        self.assertNotEqual(first, self.page.evaluate("TokensWorld.metrics().camera"))
        label = self.page.locator('#labels button:visible').first
        self.assertGreater(self.page.locator('#labels button:visible').count(), 0)
        label.hover()
        self.assertTrue(self.page.locator('#tooltip').is_visible())
        rect = label.bounding_box()
        self.page.mouse.move(rect['x'] + rect['width'] * .6, rect['y'] + rect['height'] * .5)
        self.assertTrue(self.page.locator('#tooltip').is_visible())
        label.click()
        self.assertTrue(self.page.locator('#detail').evaluate('(node)=>node.open'))
        self.assertEqual(self.page.locator('#detail').get_attribute('aria-labelledby'), 'detail-title')
        self.page.keyboard.press('Escape')
        self.assertFalse(self.page.locator('#detail').evaluate('(node)=>node.open'))
        self.assertEqual(self.page.evaluate('document.activeElement.dataset.object'), label.get_attribute('data-object'))
        self.page.mouse.move(0, 0)
        self.page.wait_for_function('!TokensWorld.metrics().pending')
        self.assertLess(self.page.evaluate('TokensWorld.metrics().calls'), 150)
        self.assertLess(self.page.evaluate('TokensWorld.metrics().triangles'), 120000)
        self.assertEqual(self.page.evaluate('localStorage.length'), 0)

    def test_fallback_is_complete_and_safe(self):
        self.load(no_webgl=True)
        self.assertTrue(self.page.locator('body').evaluate("node=>node.classList.contains('fallback')"))
        self.assertEqual(self.page.locator('#labels button:visible').count(), 0)
        self.assertGreater(self.page.locator('#project-list button').count(), 0)
        self.page.locator('#project-list button').first.click()
        self.assertTrue(self.page.locator('#detail').evaluate('(node)=>node.open'))
        self.page.keyboard.press('Escape')
        self.page.locator('#model-filters button').first.click()
        self.assertEqual(self.page.locator('#model-filters button').first.get_attribute('aria-pressed'), 'false')

    def test_keyboard_filters_theme_language_and_project_scope(self):
        self.load()
        before = self.page.evaluate('TokensWorld.model().total')
        self.page.locator('#projects-open').click()
        button = self.page.locator('#project-list button').first
        button.focus()
        self.page.keyboard.press('Enter')
        self.assertTrue(self.page.locator('#detail').evaluate('(node)=>node.open'))
        self.assertEqual(before, self.page.evaluate('TokensWorld.model().total'))
        self.page.keyboard.press('Escape')
        self.page.locator('#theme').click()
        self.page.locator('#language').click()
        self.assertEqual(self.page.locator('html').get_attribute('lang'), 'en')
        self.page.locator('#model-filters button').first.click()
        self.assertLess(self.page.evaluate('TokensWorld.model().total'), before)
        self.page.locator('#project-search').fill('not-a-real-project')
        self.assertEqual(self.page.locator('#project-list button').count(), 0)

    def test_reduced_motion_and_context_loss(self):
        self.load(reduced=True)
        self.require_webgl()
        self.assertEqual(self.page.locator('#motion').get_attribute('aria-pressed'), 'true')
        self.page.locator('a[href="#meadow"][data-chapter]').click()
        self.page.wait_for_function('TokensWorld.metrics().progress === .5')
        self.page.evaluate("document.querySelector('canvas').dispatchEvent(new Event('webglcontextlost',{cancelable:true}))")
        self.assertTrue(self.page.locator('body').evaluate("node=>node.classList.contains('fallback')"))
        self.assertEqual(self.page.locator('canvas').count(), 0)
        self.page.locator('#projects-open').click()
        self.page.locator('#project-list button').first.click()
        self.assertTrue(self.page.locator('#detail').evaluate('(node)=>node.open'))

    def test_mobile_layout_data_and_pointer(self):
        for width in (360, 390, 768, 1360):
            with self.subTest(width=width):
                self.page.set_viewport_size({"width": width, "height": 820})
                self.load()
                self.assertFalse(self.page.evaluate('document.documentElement.scrollWidth > innerWidth + 1'))
                self.page.locator('#projects-open').click()
                self.assertGreater(self.page.locator('#project-list button').count(), 0)
                self.page.locator('#project-list button').first.click()
                self.assertTrue(self.page.locator('#detail').evaluate('(node)=>node.open'))
                self.page.keyboard.press('Escape')
                self.page.locator('#view-toggle').click()
                self.assertTrue(self.page.locator('#data-view').is_visible())

    def test_motion_toggle_stops_existing_parallax(self):
        self.load()
        self.require_webgl()
        self.page.mouse.move(1300, 750)
        self.page.wait_for_function('!TokensWorld.metrics().pending')
        self.page.locator('#motion').click()
        self.page.wait_for_function('!TokensWorld.metrics().pending')
        camera = self.page.evaluate('TokensWorld.metrics().camera')
        draws = self.page.evaluate('TokensWorld.metrics().draws')
        self.page.mouse.move(1150, 680)
        self.page.wait_for_function('!TokensWorld.metrics().pending')
        self.assertEqual(camera, self.page.evaluate('TokensWorld.metrics().camera'))
        self.assertLessEqual(self.page.evaluate('TokensWorld.metrics().draws') - draws, 1)

    def test_mesh_picking_occlusion_and_touch(self):
        self.load()
        self.require_webgl()
        self.page.locator('a[href="#village"][data-chapter]').click()
        self.page.wait_for_function('TokensWorld.metrics().progress > .99 && !TokensWorld.metrics().pending')
        # Remove the HTML hit layer only for this real-geometry picking test.
        self.page.locator('#labels').evaluate("node=>node.style.pointerEvents='none'")
        self.page.add_style_tag(content='#labels button{pointer-events:none!important}')
        result = self.page.evaluate('''() => {
          const probes=TokensWorld.probes().filter(p=>p.id.startsWith('project:'));
          const visible=probes.find(p=>p.visible && p.x>0 && p.x<innerWidth && p.y>135 && p.y<innerHeight
            && !document.elementFromPoint(p.x,p.y)?.closest('button,a,input,dialog,.chapter-copy,.data-view,.bar,.core-stats')
            && TokensWorld.pick(p.x,p.y)===p.id);
          const hidden=probes.filter(p=>!p.visible && p.x>0 && p.x<innerWidth && p.y>0 && p.y<innerHeight);
          return {visible,hidden: hidden.map(p=>({id:p.id,picked:TokensWorld.pick(p.x,p.y)}))};
        }''')
        self.assertIsNotNone(result.get('visible'), 'No exposed house for actual mesh raycast/touch')
        for hidden in result['hidden']:
            self.assertNotEqual(hidden['picked'], hidden['id'])
        point = result['visible']
        self.page.touchscreen.tap(point['x'], point['y'])
        self.assertTrue(self.page.locator('#tooltip').is_visible())
        self.assertFalse(self.page.locator('#detail').evaluate('(node)=>node.open'))
        self.page.touchscreen.tap(point['x'], point['y'])
        self.assertTrue(self.page.locator('#detail').evaluate('(node)=>node.open'))
        self.page.keyboard.press('Escape')
        self.assertGreater(self.page.locator('#project-list button').count(), 0)

    def test_rebuild_resources_and_render_budget(self):
        self.load()
        self.require_webgl()
        self.page.wait_for_function('!TokensWorld.metrics().pending')
        # Warm every chapter: GPU geometries are uploaded lazily when visible.
        for chapter in ('meadow', 'village', 'summit'):
            self.page.locator(f'a[href="#{chapter}"][data-chapter]').click()
            self.page.wait_for_function('!TokensWorld.metrics().pending')
        first = self.page.evaluate('TokensWorld.metrics()')
        self.assertEqual(first['ownedTextures'], 10)
        self.assertTrue(first['upgraded'])
        self.assertTrue(first['shadow'])
        for _ in range(4):
            self.page.locator('#model-filters button').first.click()
            self.page.wait_for_function('!TokensWorld.metrics().pending')
            self.page.locator('#model-filters button').first.click()
            self.page.wait_for_function('!TokensWorld.metrics().pending')
        for chapter in ('meadow', 'village', 'summit'):
            self.page.locator(f'a[href="#{chapter}"][data-chapter]').click()
            self.page.wait_for_function('!TokensWorld.metrics().pending')
        final = self.page.evaluate('TokensWorld.metrics()')
        self.assertEqual(final['textures'], first['textures'])
        self.assertEqual(final['geometries'], first['geometries'])
        self.assertLess(final['calls'], 150)
        self.assertLess(final['triangles'], 120000)
        self.page.set_viewport_size({'width': 390, 'height': 820})
        self.page.wait_for_function('TokensWorld.metrics().shadow === false && !TokensWorld.metrics().pending')
        self.assertFalse(self.page.evaluate('TokensWorld.metrics().shadow'))
        self.page.evaluate('TokensWorld.dispose()')
        self.assertEqual(self.page.locator('canvas').count(), 0)
        self.assertIsNone(self.page.evaluate('TokensWorld.metrics()'))

    def test_full_village_budget_and_hidden_house_pick(self):
        spec = importlib.util.spec_from_file_location('world_builder_capacity', ROOT / 'scripts/build_world_prototype.py')
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        payload = builder.synthetic_payload()
        model = payload['models'][0]
        day = payload['day'][0]['period']
        payload['day_details'] = {day: {'cwds': [[f'Project {i}', 100, f'/synthetic/capacity-{i}', {model: 100}] for i in range(100)]}}
        html = self.root / 'capacity.html'
        html.write_text(builder.build_html(payload), encoding='utf-8')
        self.page.goto(html.as_uri(), wait_until='load')
        self.page.wait_for_function('window.TokensWorld?.ready')
        self.require_webgl()
        self.assertEqual(self.page.evaluate('TokensWorld.model().houses.length'), 24)
        self.assertEqual(self.page.locator('#project-list button').count(), 100)
        for chapter in ('summit', 'meadow', 'village'):
            self.page.locator(f'a[href="#{chapter}"][data-chapter]').click()
            self.page.wait_for_function('!TokensWorld.metrics().pending')
            self.assertLess(self.page.evaluate('TokensWorld.metrics().calls'), 150)
            self.assertLess(self.page.evaluate('TokensWorld.metrics().triangles'), 120000)
        hidden = self.page.evaluate('''()=>TokensWorld.probes().filter(p=>p.id.startsWith('project:')&&!p.visible
          &&p.x>0&&p.x<innerWidth&&p.y>0&&p.y<innerHeight).map(p=>({id:p.id,picked:TokensWorld.pick(p.x,p.y)}))''')
        self.assertGreater(len(hidden), 0, 'Capacity fixture must exercise actual house occlusion')
        for point in hidden:
            self.assertNotEqual(point['id'], point['picked'])

    def test_forced_colors_retains_data(self):
        self.page.emulate_media(forced_colors='active')
        self.load()
        self.assertTrue(self.page.locator('body').evaluate("node=>node.classList.contains('fallback')"))
        self.assertGreater(self.page.locator('#day-table tbody tr').count(), 0)
        self.assertEqual(self.page.locator('#labels button:visible').count(), 0)


if __name__ == '__main__':
    unittest.main()
