"""Browser runtime checks for the overview insights.

Covers the today-vs-yesterday pace race, the model share stream and the
activity calendar on a deterministic synthetic demo payload: numbers agree with
the embedded payload, interactions drive the shared date range, both languages
render without leftovers, motion is gated, and narrow viewports neither overflow
nor shrink touch targets.
"""

import re
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from tokens_cli import demo, report_dashboard  # noqa: E402

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover - depends on optional browser tooling
    sync_playwright = None

CJK = re.compile(r"[㐀-鿿]")
TODAY = date(2026, 9, 24)


@unittest.skipIf(sync_playwright is None, "Playwright is not installed")
class DashboardInsightsRuntimeTests(unittest.TestCase):
    BROWSER = "chromium"

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        bundle = demo.build_demo(today=TODAY)
        common = dict(sources=bundle["sources"], session_titles=bundle["session_titles"], demo=True)
        cls._path = Path(cls._tmp.name) / "insights-demo.html"
        cls._path.write_text(report_dashboard.build_dashboard_html(
            bundle["records"], since=bundle["since"], until=bundle["until"],
            generated_at=bundle["generated_at"], **common), encoding="utf-8")
        # A historical report generated well after its range: "today" is not in it.
        cls._stale_path = Path(cls._tmp.name) / "insights-stale.html"
        cls._stale_path.write_text(report_dashboard.build_dashboard_html(
            bundle["records"], since=bundle["since"], until=bundle["until"],
            generated_at=datetime.combine(TODAY + timedelta(days=5), datetime.min.time().replace(hour=9)),
            **common), encoding="utf-8")
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

    def open(self, *, path=None, viewport=None, color_scheme="light", reduced_motion="no-preference",
             has_touch=False, language=None):
        context = self._browser.new_context(
            viewport=viewport or {"width": 1280, "height": 900},
            color_scheme=color_scheme, reduced_motion=reduced_motion, has_touch=has_touch,
        )
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
        page.goto((path or self._path).as_uri())
        page.wait_for_function("() => document.getElementById('share-stream') && !document.getElementById('share-stream').hidden")
        if language:
            page.evaluate("lang => applyLanguage(lang)", language)
        self.addCleanup(context.close)
        return page, errors

    # ---- pace race -------------------------------------------------------

    def test_pace_race_matches_payload_and_follows_model_filter(self):
        page, errors = self.open()
        info = page.evaluate("""() => {
          const day=generatedDay(),d=DATA.day.find(r=>r.period===day),y=DATA.day.find(r=>r.period===addISODays(day,-1));
          return {visible:!document.getElementById('pace-race').hidden,day,todayTotal:d.total,yesterdayTotal:y.total,
                  race:{today:insightState.race.today.total,yesterday:insightState.race.yesterday.total,hour:insightState.race.hour},
                  delta:document.getElementById('pace-delta').textContent,lead:document.getElementById('pace-delta').dataset.lead,
                  stats:document.querySelectorAll('#pace-stats dt').length,paths:document.querySelectorAll('#pace-chart .pace-today,#pace-chart .pace-yesterday').length,
                  legend:document.getElementById('pace-legend').textContent};
        }""")
        self.assertTrue(info["visible"])
        self.assertEqual(TODAY.isoformat(), info["day"])
        self.assertEqual(info["todayTotal"], info["race"]["today"])
        self.assertEqual(info["yesterdayTotal"], info["race"]["yesterday"])
        self.assertEqual(12, info["race"]["hour"])
        self.assertIn(info["lead"], {"ahead", "behind", "even", "new", "idle"})
        self.assertRegex(info["delta"], r"[+−]\d+\.\d%")
        self.assertGreaterEqual(info["stats"], 4)
        self.assertEqual(2, info["paths"])
        self.assertIn("今日", info["legend"])

        # Isolate one model through the real filter chips: the race narrows to that model only.
        model = page.evaluate("() => Object.keys(DATA.day.find(r=>r.period===generatedDay()).models)[0]")
        for other in page.evaluate("m => DATA.models.filter(x=>x!==m)", model):
            page.locator("#filters label.chip", has=page.locator(f'input[value="{other}"]')).click()
        narrowed = page.evaluate("""m => ({race:insightState.race&&insightState.race.today.total,
            expected:DATA.day.find(r=>r.period===generatedDay()).models[m]||0})""", model)
        self.assertEqual(narrowed["expected"], narrowed["race"])

        # Hovering the chart shows an hourly tooltip.
        page.locator("#pace-chart").scroll_into_view_if_needed()
        box = page.locator("#pace-chart").bounding_box()
        page.mouse.move(box["x"] + box["width"] * 0.2, box["y"] + box["height"] / 2)
        tip = page.locator("#pace-tip")
        self.assertTrue(tip.is_visible())
        self.assertRegex(tip.inner_text(), r"\d{2}:00")
        self.assertEqual([], errors)

    def test_pace_race_hidden_when_generation_day_is_outside_report(self):
        page, errors = self.open(path=self._stale_path)
        state = page.evaluate("""() => ({pace:document.getElementById('pace-race').hidden,
            stream:document.getElementById('share-stream').hidden,cal:document.getElementById('activity-cal').hidden})""")
        self.assertEqual({"pace": True, "stream": False, "cal": False}, state)
        self.assertEqual([], errors)

    # ---- share stream ----------------------------------------------------

    def test_share_stream_layers_hover_and_click_sets_range(self):
        page, errors = self.open()
        info = page.evaluate("""() => {
          const layers=[...document.querySelectorAll('#share-stream-svg .ss-layer')];
          const present=DATA.models.filter(m=>DATA.day.some(r=>(r.models[m]||0)>0));
          return {models:layers.map(l=>l.dataset.model),present,
                  colorsOk:layers.every(l=>l.style.fill&&getComputedStyle(l).fill!=='none'),
                  days:insightState.stream.days.length,span:InsightCore.continuousDays(DATA.range.since,DATA.range.until).length,
                  seg:document.querySelectorAll('#share-stream .seg,#activity-cal .seg,#pace-race .seg').length};
        }""")
        self.assertEqual(info["present"], info["models"])
        self.assertTrue(info["colorsOk"])
        self.assertEqual(info["span"], info["days"])
        self.assertEqual(0, info["seg"], "new charts must not reuse the .seg class")

        svg = page.locator("#share-stream-svg")
        svg.scroll_into_view_if_needed()
        box = svg.bounding_box()
        page.mouse.move(box["x"] + box["width"] - 3, box["y"] + box["height"] / 2)
        tip = page.locator("#share-stream-tip")
        self.assertTrue(tip.is_visible())
        self.assertIn(TODAY.isoformat(), tip.inner_text())
        tip_box, plot_box = tip.bounding_box(), page.locator("#share-stream-plot").bounding_box()
        self.assertGreaterEqual(tip_box["x"], plot_box["x"] - 1)
        self.assertLessEqual(tip_box["x"] + tip_box["width"], plot_box["x"] + plot_box["width"] + 1)

        page.mouse.click(box["x"] + box["width"] - 3, box["y"] + box["height"] / 2)
        rng = page.evaluate("() => ({range:state.range,date:state.rangeDate})")
        self.assertEqual({"range": "custom", "date": TODAY.isoformat()}, rng)
        dims = page.locator("#share-stream-svg .ss-dim").count()
        self.assertGreaterEqual(dims, 1, "days outside the selected range are dimmed")
        self.assertEqual(1, page.locator("#share-stream-svg .ss-range").count())
        self.assertEqual([], errors)

    def test_share_stream_keyboard_and_mode_toggle(self):
        page, errors = self.open()
        svg = page.locator("#share-stream-svg")
        svg.focus()
        self.assertTrue(page.locator("#share-stream-tip").is_visible())
        page.keyboard.press("ArrowLeft")
        page.keyboard.press("ArrowLeft")
        expected = (TODAY - timedelta(days=2)).isoformat()
        self.assertIn(expected, page.locator("#share-stream-readout").inner_text())
        page.keyboard.press("Home")
        first = page.evaluate("() => insightState.stream.days[0]")
        self.assertIn(first, page.locator("#share-stream-readout").inner_text())
        page.keyboard.press("End")
        page.keyboard.press("ArrowLeft")
        page.keyboard.press("Enter")
        self.assertEqual((TODAY - timedelta(days=1)).isoformat(), page.evaluate("() => state.rangeDate"))

        share = page.locator('#share-stream-modes [data-stream-mode="share"]')
        volume = page.locator('#share-stream-modes [data-stream-mode="volume"]')
        self.assertEqual("true", share.get_attribute("aria-pressed"))
        volume.click()
        self.assertEqual("true", volume.get_attribute("aria-pressed"))
        self.assertEqual("false", share.get_attribute("aria-pressed"))
        mode = page.evaluate("""() => {
          const s=insightState.stream,i=Math.floor(s.days.length/2),sum=s.layers.reduce((a,l)=>a+(l.y1[i]-l.y0[i]),0);
          return {mode:s.mode,centre:s.layers[0].y0[i]+s.layers[s.layers.length-1].y1[i],sum,ticks:document.querySelectorAll('#share-stream-svg .ss-grid').length};
        }""")
        self.assertEqual("volume", mode["mode"])
        self.assertAlmostEqual(0, mode["centre"], places=6)
        self.assertGreater(mode["sum"], 1)
        self.assertEqual(0, mode["ticks"], "percentage gridlines only belong to share mode")
        self.assertEqual([], errors)

    def test_share_stream_touch_first_tap_previews_second_tap_commits(self):
        page, errors = self.open(viewport={"width": 390, "height": 844}, has_touch=True)
        svg = page.locator("#share-stream-svg")
        svg.scroll_into_view_if_needed()
        box = svg.bounding_box()
        point = {"x": box["x"] + box["width"] - 2, "y": box["y"] + box["height"] / 2}
        page.touchscreen.tap(point["x"], point["y"])
        self.assertEqual("all", page.evaluate("() => state.range"), "first tap only previews")
        self.assertTrue(page.locator("#share-stream-tip").is_visible())
        page.touchscreen.tap(point["x"], point["y"])
        self.assertEqual({"range": "custom", "date": TODAY.isoformat()},
                         page.evaluate("() => ({range:state.range,date:state.rangeDate})"))
        self.assertEqual([], errors)

    PALETTE_MISMATCH = """() => [...document.querySelectorAll('#share-stream-svg .ss-layer')].filter(layer => {
      const probe=document.createElement('i');probe.style.color=modelColor(layer.dataset.model);document.body.appendChild(probe);
      const want=getComputedStyle(probe).color;probe.remove();return getComputedStyle(layer).fill!==want;
    }).map(layer=>layer.dataset.model)"""

    def test_share_stream_follows_theme_palette(self):
        for scheme in ("light", "dark"):
            with self.subTest(scheme=scheme):
                page, errors = self.open(color_scheme=scheme)
                self.assertEqual(scheme, page.evaluate("() => effectiveTheme()"))
                self.assertEqual([], page.evaluate(self.PALETTE_MISMATCH))
                self.assertEqual([], errors)
        page, errors = self.open(color_scheme="light")
        fills = "() => [...document.querySelectorAll('#share-stream-svg .ss-layer')].map(l=>getComputedStyle(l).fill)"
        before = page.evaluate(fills)
        page.evaluate("() => applyTheme('dark')")
        self.assertNotEqual(before, page.evaluate(fills), "theme switch repaints the stream")
        self.assertEqual([], page.evaluate(self.PALETTE_MISMATCH))
        self.assertEqual([], errors)

    # ---- activity calendar -----------------------------------------------

    def test_activity_calendar_streaks_click_and_keyboard(self):
        page, errors = self.open()
        info = page.evaluate("""() => {
          const cells=[...document.querySelectorAll('#activity-svg .ac-cell')];
          const totals=insightDayTotals(),active=Object.keys(totals).filter(d=>totals[d]>0).sort();
          let best=null;active.forEach(d=>{if(!best||totals[d]>totals[best])best=d;});
          return {last:cells.at(-1).dataset.day,count:cells.length,weeks:insightState.cal.weeks,active:active.length,
                  activeTile:document.querySelector('[data-stat=active] b').textContent,best,
                  busiest:document.querySelector('[data-stat=busiest]').dataset.day,
                  levels:[...new Set(cells.map(c=>c.getAttribute('class').match(/\\bl(\\d)\\b/)[1]))].sort()};
        }""")
        self.assertEqual(TODAY.isoformat(), info["last"])
        self.assertGreaterEqual(info["weeks"], 13)
        self.assertTrue(info["activeTile"].startswith(str(info["active"])))
        self.assertEqual(info["best"], info["busiest"])
        self.assertTrue({"1", "2", "3", "4"} <= set(info["levels"]))

        target = (TODAY - timedelta(days=10)).isoformat()
        page.locator(f'#activity-svg rect[data-day="{target}"]').click()
        self.assertEqual({"range": "custom", "date": target},
                         page.evaluate("() => ({range:state.range,date:state.rangeDate})"))
        self.assertIn("is-range", page.locator(f'#activity-svg rect[data-day="{target}"]').get_attribute("class"))
        self.assertIn(target, page.locator("#activity-readout").inner_text())

        page.locator("#activity-svg").focus()
        page.keyboard.press("ArrowRight")  # +7 days
        page.keyboard.press("ArrowUp")     # -1 day
        moved = (TODAY - timedelta(days=4)).isoformat()
        self.assertIn(moved, page.locator("#activity-readout").inner_text())
        self.assertEqual("1", page.evaluate("() => getComputedStyle(document.getElementById('ac-cursor')).opacity"))
        page.keyboard.press("End")
        page.keyboard.press("ArrowRight")  # clamped at the report end
        page.keyboard.press("Enter")
        self.assertEqual(TODAY.isoformat(), page.evaluate("() => state.rangeDate"))

        page.locator('[data-stat=busiest]').click()
        self.assertEqual(info["busiest"], page.evaluate("() => state.rangeDate"))
        self.assertEqual([], errors)

    # ---- cross-cutting ---------------------------------------------------

    def test_insights_localize_to_english_without_cjk(self):
        page, errors = self.open(language="en")
        page.locator("#share-stream-svg").focus()
        page.locator("#activity-svg").focus()
        texts = page.evaluate("""() => ['pace-race','share-stream','activity-cal'].map(id=>{
          const el=document.getElementById(id);
          const attrs=[...el.querySelectorAll('[aria-label]')].map(n=>n.getAttribute('aria-label')).join(' ');
          return id+': '+el.textContent+' '+el.innerText+' '+attrs+' '+el.querySelector('svg').getAttribute('aria-label');
        })""")
        for text in texts:
            with self.subTest(block=text.split(":", 1)[0]):
                self.assertIsNone(CJK.search(text), text)
        self.assertIn("Today vs yesterday", texts[0])
        self.assertIn("Model share stream", texts[1])
        self.assertIn("Activity calendar", texts[2])
        page.evaluate("() => applyLanguage('zh')")
        self.assertIn("模型份额流", page.locator("#share-stream-title").inner_text())
        self.assertIn("活跃日历", page.locator("#activity-title").inner_text())
        self.assertEqual([], errors)

    def test_insight_motion_is_gated(self):
        probe = """() => ({pace:getComputedStyle(document.querySelector('#pace-chart .pace-today')).animationName,
                         stream:getComputedStyle(document.querySelector('#share-stream-svg .ss-layer')).animationName})"""
        page, errors = self.open(reduced_motion="reduce")
        self.assertEqual("off", page.evaluate("() => document.documentElement.dataset.motion"))
        self.assertEqual({"pace": "none", "stream": "none"}, page.evaluate(probe))
        page, errors2 = self.open()
        page.evaluate("() => applyMotion('full')")
        page.evaluate("() => renderInsights()")
        self.assertEqual({"pace": "paceDraw", "stream": "streamGrow"}, page.evaluate(probe))
        for level in ("low", "off"):
            page.evaluate("level => applyMotion(level)", level)
            page.evaluate("() => renderInsights()")
            self.assertEqual({"pace": "none", "stream": "none"}, page.evaluate(probe), level)
        self.assertEqual([], errors + errors2)

    def test_insights_mobile_no_overflow_and_touch_targets(self):
        for width in (320, 390):
            for scheme, language in (("light", "zh"), ("dark", "en")):
                with self.subTest(width=width, scheme=scheme, language=language):
                    page, errors = self.open(viewport={"width": width, "height": 844}, color_scheme=scheme,
                                             language=language)
                    metrics = page.evaluate("""() => {
                      const box=id=>document.getElementById(id).getBoundingClientRect();
                      const blocks=['pace-race','share-stream','activity-cal'].map(id=>({id,right:box(id).right,left:box(id).left}));
                      const svgs=['pace-chart','share-stream-svg'].map(id=>({id,right:box(id).right}));
                      const targets=[...document.querySelectorAll('#share-stream-modes button,#activity-stats button')]
                        .map(el=>{const r=el.getBoundingClientRect();return {h:r.height,w:r.width};});
                      const scroll=document.getElementById('activity-scroll');
                      return {scroll:document.documentElement.scrollWidth,client:document.documentElement.clientWidth,blocks,svgs,targets,
                              calScrolledToEnd:scroll.scrollWidth<=scroll.clientWidth||scroll.scrollLeft+scroll.clientWidth>=scroll.scrollWidth-2};
                    }""")
                    self.assertLessEqual(metrics["scroll"], metrics["client"])
                    for block in metrics["blocks"] + metrics["svgs"]:
                        self.assertLessEqual(block["right"], metrics["client"] + 0.5, block)
                    self.assertTrue(metrics["targets"])
                    for target in metrics["targets"]:
                        self.assertGreaterEqual(target["h"], 44, target)
                        self.assertGreaterEqual(target["w"], 44, target)
                    self.assertTrue(metrics["calScrolledToEnd"], "latest weeks are visible first")
                    self.assertEqual([], errors)

    def test_section_order_is_unchanged(self):
        page, errors = self.open()
        first = page.evaluate("() => document.querySelector('main section.card, section.card').id")
        self.assertEqual("section-scope", first)
        parents = page.evaluate("""() => ({pace:document.getElementById('pace-race').closest('section').id,
            stream:document.getElementById('share-stream').closest('section').id,
            cal:document.getElementById('activity-cal').closest('section').id})""")
        self.assertEqual({"pace": "section-overview", "stream": "section-daily-models", "cal": "section-rhythm"}, parents)
        self.assertEqual([], errors)


if __name__ == "__main__":
    unittest.main()
