import tempfile
import unittest
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


@unittest.skipIf(sync_playwright is None, "Playwright is not installed")
class DashboardRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        records = [
            {
                "source": "claude",
                "ts": "2026-07-01T01:00:00+08:00",
                "date": "2026-07-01",
                "model": "model-a",
                "input": 70,
                "output": 20,
                "cache_read": 10,
                "cache_write": 0,
                "total": 100,
                "session": "synthetic-session-a",
                "cwd": "/synthetic/long-running-project-alpha",
            },
            {
                "source": "claude",
                "ts": "2026-07-01T02:00:00+08:00",
                "date": "2026-07-01",
                "model": "model-b",
                "input": 90,
                "output": 30,
                "cache_read": 30,
                "cache_write": 0,
                "total": 150,
                "session": "synthetic-session-b",
                "cwd": "/synthetic/long-running-project-alpha",
            },
            {
                "source": "claude",
                "ts": "2026-07-02T13:00:00+08:00",
                "date": "2026-07-02",
                "model": "model-a",
                "input": 120,
                "output": 50,
                "cache_read": 30,
                "cache_write": 0,
                "total": 200,
                "session": "synthetic-session-c",
                "cwd": "/synthetic/project-b",
            },
        ]
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
                until="2026-07-02",
                sources=["claude"],
            )
        html = report_dashboard.render_dashboard(
            dashboard_wire.encode_payload(payload)
        )
        cls._path = Path(cls._tmp.name) / "synthetic-dashboard.html"
        cls._path.write_text(html, encoding="utf-8")
        cls._malicious_path = Path(cls._tmp.name) / "synthetic-dashboard-malicious-model.html"
        malicious_records = records + [{
            "source": "claude",
            "ts": "2026-07-02T14:00:00+08:00",
            "date": "2026-07-02",
            "model": "<img src=x onerror=window.__paletteXss=1>",
            "input": 30,
            "output": 10,
            "cache_read": 10,
            "cache_write": 0,
            "total": 50,
            "session": "synthetic-session-malicious-model",
            "cwd": "/synthetic/security-fixture",
        }]
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
            malicious_payload = report_dashboard.build_payload(
                malicious_records,
                since="2026-07-01",
                until="2026-07-02",
                sources=["claude"],
            )
        cls._malicious_path.write_text(
            report_dashboard.render_dashboard(
                dashboard_wire.encode_payload(malicious_payload)
            ),
            encoding="utf-8",
        )
        cls._playwright = sync_playwright().start()
        try:
            cls._browser = cls._playwright.chromium.launch(headless=True)
        except Exception as exc:
            cls._playwright.stop()
            cls._tmp.cleanup()
            raise unittest.SkipTest(f"Chromium is unavailable: {exc}")

    @classmethod
    def tearDownClass(cls):
        cls._browser.close()
        cls._playwright.stop()
        cls._tmp.cleanup()

    def new_page(
        self,
        *,
        viewport=None,
        color_scheme="light",
        reduced_motion="no-preference",
        freeze_lazy=False,
        path=None,
    ):
        context = self._browser.new_context(
            viewport=viewport or {"width": 1280, "height": 820},
            color_scheme=color_scheme,
            reduced_motion=reduced_motion,
        )
        page = context.new_page()
        if freeze_lazy:
            page.add_init_script("""
                class FrozenIntersectionObserver {
                  observe() {}
                  unobserve() {}
                  disconnect() {}
                  takeRecords() { return []; }
                }
                window.IntersectionObserver=FrozenIntersectionObserver;
            """)
        page_errors = []
        console_errors = []
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        page.on(
            "console",
            lambda message: console_errors.append(message.text)
            if message.type == "error"
            else None,
        )
        page.goto((path or self._path).as_uri(), wait_until="load")
        return context, page, page_errors, console_errors

    def wait_for_flow(self, page):
        page.locator("#section-flow").scroll_into_view_if_needed()
        page.wait_for_function(
            "document.querySelectorAll('#flow-map .flow-node').length > 0 && "
            "document.querySelectorAll('#flow-map .flow-link').length > 0"
        )

    def force_flow_error(self, page):
        return page.evaluate("""
            () => {
              const svg=document.getElementById('flow-map');
              window.__detachedFlowMap=svg;
              svg.remove();
              return renderLazy('flow',true);
            }
        """)

    def restore_flow_map(self, page):
        page.evaluate("""
            () => {
              const shell=document.querySelector('#section-flow .flow-shell');
              shell.insertBefore(
                window.__detachedFlowMap,
                document.getElementById('flow-panel')
              );
            }
        """)

    def test_command_palette_treats_model_names_as_text(self):
        context, page, page_errors, console_errors = self.new_page(
            path=self._malicious_path
        )
        try:
            page.evaluate("openPalette()")
            model_name = "<img src=x onerror=window.__paletteXss=1>"
            palette = page.locator("#palette-list")
            self.assertIn(model_name, palette.inner_text())
            self.assertEqual(0, palette.locator("img").count())
            self.assertIsNone(page.evaluate("window.__paletteXss"))
            self.assertEqual([], page_errors)
            self.assertEqual([], console_errors)
        finally:
            context.close()

    def test_flow_is_visible_and_preserves_full_titles(self):
        context, page, page_errors, console_errors = self.new_page()
        try:
            self.wait_for_flow(page)
            page.evaluate("applyLanguage('en',false)")
            visible = page.evaluate("""
                () => {
                  const section=document.getElementById('section-flow');
                  const svg=document.getElementById('flow-map');
                  const node=svg.querySelector('.flow-node');
                  const path=svg.querySelector('.flow-link');
                  const sectionStyle=getComputedStyle(section);
                  const svgStyle=getComputedStyle(svg);
                  const pathStyle=getComputedStyle(path);
                  const rect=svg.getBoundingClientRect();
                  const box=node.getBBox();
                  return {
                    sectionDisplay:sectionStyle.display,
                    pending:section.classList.contains('lazy-pending'),
                    error:!!section.querySelector('.lazy-error-state'),
                    ariaBusy:section.getAttribute('aria-busy'),
                    nodes:svg.querySelectorAll('.flow-node').length,
                    links:svg.querySelectorAll('.flow-link').length,
                    svgDisplay:svgStyle.display,
                    svgVisibility:svgStyle.visibility,
                    width:rect.width,
                    height:rect.height,
                    nodeWidth:box.width,
                    nodeHeight:box.height,
                    pathLength:path.getTotalLength(),
                    pathOpacity:Number(pathStyle.opacity),
                    stats:document.getElementById('flow-stats').textContent,
                  };
                }
            """)
            self.assertNotEqual("none", visible["sectionDisplay"])
            self.assertFalse(visible["pending"])
            self.assertFalse(visible["error"])
            self.assertEqual("false", visible["ariaBusy"])
            self.assertGreater(visible["nodes"], 0)
            self.assertGreater(visible["links"], 0)
            self.assertEqual("block", visible["svgDisplay"])
            self.assertNotEqual("hidden", visible["svgVisibility"])
            self.assertGreater(visible["width"], 0)
            self.assertGreater(visible["height"], 0)
            self.assertGreater(visible["nodeWidth"], 0)
            self.assertGreater(visible["nodeHeight"], 0)
            self.assertGreater(visible["pathLength"], 0)
            self.assertGreaterEqual(visible["pathOpacity"], 0.45)
            self.assertIn("actual flows", visible["stats"])
            page.evaluate("applyLanguage('zh',false)")

            page.wait_for_function("""
                [...document.querySelectorAll('#flow-map .flow-node.project')]
                  .some(item=>item.querySelector('title').textContent.includes('悬停 Peek'))
            """)
            title = page.evaluate("""
                () => {
                  const node=[...document.querySelectorAll('#flow-map .flow-node.project')]
                    .find(item=>item.dataset.flowName.includes('long-running-project-alpha'));
                  return {
                    full:node.dataset.flowName,
                    visible:node.querySelector('text').textContent,
                    title:node.querySelector('title').textContent,
                  };
                }
            """)
            self.assertGreater(len(title["full"]), 20)
            self.assertNotEqual(title["full"], title["visible"])
            self.assertTrue(title["visible"].endswith("…"))
            self.assertEqual(
                title["full"] + " · 悬停 Peek · 点击 Pin 信号",
                title["title"],
            )

            page.evaluate("applyLanguage('en',false)")
            page.wait_for_function("""
                [...document.querySelectorAll('#flow-map .flow-node.project')]
                  .some(item=>item.querySelector('title').textContent.includes('Hover to Peek'))
            """)
            translated = page.evaluate("""
                () => {
                  const node=[...document.querySelectorAll('#flow-map .flow-node.project')]
                    .find(item=>item.dataset.flowName.includes('long-running-project-alpha'));
                  return node.querySelector('title').textContent;
                }
            """)
            self.assertEqual(
                title["full"] + " · Hover to Peek · Click to Pin",
                translated,
            )

            page.evaluate("state.models.clear();renderLazy('flow',true)")
            page.wait_for_function(
                "document.getElementById('flow-stats').textContent === '0 flow links'"
            )
            self.assertEqual("0 flow links", page.locator("#flow-stats").inner_text())
            self.assertEqual([], page_errors)
            self.assertEqual([], console_errors)
        finally:
            context.close()

    def test_lazy_placeholder_is_bilingual_and_hides_after_render(self):
        context, page, page_errors, console_errors = self.new_page(freeze_lazy=True)
        try:
            page.evaluate("applyLanguage('zh',false)")
            state = page.evaluate("""
                () => {
                  const card=document.getElementById('section-flow');
                  const placeholder=card.querySelector(':scope > .lazy-placeholder');
                  return {
                    pending:card.classList.contains('lazy-pending'),
                    text:placeholder.textContent,
                    display:getComputedStyle(placeholder).display,
                  };
                }
            """)
            self.assertTrue(state["pending"])
            self.assertEqual("进入视野后加载", state["text"])
            self.assertEqual("grid", state["display"])

            page.evaluate("applyLanguage('en',false)")
            self.assertEqual(
                "Loads when scrolled into view",
                page.locator("#section-flow > .lazy-placeholder").inner_text(),
            )
            self.assertTrue(page.evaluate("renderLazy('flow',true)"))
            ready = page.evaluate("""
                () => {
                  const card=document.getElementById('section-flow');
                  const placeholder=card.querySelector(':scope > .lazy-placeholder');
                  return {
                    pending:card.classList.contains('lazy-pending'),
                    display:getComputedStyle(placeholder).display,
                    status:lazyState.flow.status,
                  };
                }
            """)
            self.assertFalse(ready["pending"])
            self.assertEqual("none", ready["display"])
            self.assertEqual("ready", ready["status"])
            self.assertEqual([], page_errors)
            self.assertEqual([], console_errors)
        finally:
            context.close()

    def test_flow_survives_theme_and_reduced_motion_changes(self):
        context, page, page_errors, console_errors = self.new_page()
        try:
            self.wait_for_flow(page)
            for theme in ("light", "dark", "auto"):
                with self.subTest(theme=theme):
                    page.evaluate(
                        "theme => { applyTheme(theme); renderLazy('flow',true); }",
                        theme,
                    )
                    geometry = page.evaluate("""
                        () => {
                          const svg=document.getElementById('flow-map');
                          return {
                            nodes:svg.querySelectorAll('.flow-node').length,
                            length:svg.querySelector('.flow-link').getTotalLength(),
                            visibility:getComputedStyle(svg).visibility,
                          };
                        }
                    """)
                    self.assertGreater(geometry["nodes"], 0)
                    self.assertGreater(geometry["length"], 0)
                    self.assertNotEqual("hidden", geometry["visibility"])

            page.emulate_media(reduced_motion="reduce", color_scheme="dark")
            page.evaluate("applyTheme('auto'); renderLazy('flow',true)")
            self.assertGreater(page.locator("#flow-map .flow-link").count(), 0)
            self.assertEqual(
                "none",
                page.locator("#flow-map .flow-link").first.evaluate(
                    "element => getComputedStyle(element).animationName"
                ),
            )
            self.assertEqual([], page_errors)
            self.assertEqual([], console_errors)
        finally:
            context.close()

    def test_flow_module_and_retry_restore_keyboard_focus(self):
        context, page, page_errors, console_errors = self.new_page()
        try:
            self.wait_for_flow(page)
            flow = page.locator("#section-flow")
            page.evaluate("""
                () => {
                  const input=document.querySelector('input[data-mod="flow"]');
                  input.checked=false;
                  input.dispatchEvent(new Event('change',{bubbles:true}));
                }
            """)
            self.assertEqual("none", flow.evaluate("element => element.style.display"))
            page.evaluate("""
                () => {
                  const input=document.querySelector('input[data-mod="flow"]');
                  input.checked=true;
                  input.dispatchEvent(new Event('change',{bubbles:true}));
                }
            """)
            page.wait_for_function(
                "document.getElementById('section-flow').style.display !== 'none' && "
                "document.querySelectorAll('#flow-map .flow-node').length > 0"
            )

            self.assertFalse(self.force_flow_error(page))
            self.assertTrue(flow.locator(".lazy-error-state").is_visible())
            self.assertTrue(flow.locator("[data-lazy-retry]").is_visible())
            failed_state = page.evaluate("lazyState.flow")
            self.assertTrue(failed_state["dirty"])
            self.assertFalse(failed_state["rendered"])
            self.assertTrue(failed_state["error"])
            self.assertEqual("error", failed_state["status"])

            page.locator("[data-lazy-retry]").focus()
            page.evaluate("document.querySelector('[data-lazy-retry]').click()")
            page.wait_for_function("""
                document.activeElement.matches(
                  '#section-flow .lazy-error-state [data-lazy-retry]'
                ) && lazyState.flow.status === 'error'
            """)
            self.assertEqual("error", page.evaluate("lazyState.flow.status"))

            self.restore_flow_map(page)
            page.evaluate("document.querySelector('[data-lazy-retry]').click()")
            page.wait_for_function(
                "!document.querySelector('#section-flow .lazy-error-state') && "
                "document.querySelectorAll('#flow-map .flow-node').length > 0 && "
                "lazyState.flow.status === 'ready' && "
                "document.activeElement.matches('#section-flow h2, #section-flow h3')"
            )
            focus = page.evaluate("""
                () => ({
                  tag:document.activeElement.tagName,
                  inside:document.activeElement.closest('#section-flow') !== null,
                  text:document.activeElement.textContent,
                  tabindex:document.activeElement.getAttribute('tabindex'),
                })
            """)
            self.assertEqual("H2", focus["tag"])
            self.assertTrue(focus["inside"])
            self.assertIn("Token", focus["text"])
            self.assertEqual("-1", focus["tabindex"])
            self.assertFalse(
                flow.evaluate("element => element.classList.contains('lazy-error')")
            )
            self.assertEqual([], page_errors)
            self.assertGreaterEqual(len(console_errors), 2)
            self.assertTrue(all(
                message == "[tokens] lazy renderer failed: flow"
                for message in console_errors
            ))
        finally:
            context.close()

    def test_mobile_flow_region_scrolls_from_keyboard_without_page_overflow(self):
        context, page, page_errors, console_errors = self.new_page(
            viewport={"width": 390, "height": 760}
        )
        try:
            self.wait_for_flow(page)
            page.evaluate("applyLanguage('en',false)")
            shell = page.locator("#section-flow .flow-shell")
            page.locator("#flow-save").focus()
            page.keyboard.press("Tab")
            self.assertTrue(shell.evaluate("element => document.activeElement === element"))
            self.assertEqual("region", shell.get_attribute("role"))
            self.assertEqual(
                "Token Flow; horizontally scrollable",
                shell.get_attribute("aria-label"),
            )
            before = shell.evaluate("element => element.scrollLeft")
            for _ in range(8):
                page.keyboard.press("ArrowRight")
            page.wait_for_timeout(250)
            mobile = page.evaluate("""
                () => {
                  const shell=document.querySelector('#section-flow .flow-shell');
                  const svg=document.getElementById('flow-map');
                  return {
                    pageWidth:document.documentElement.scrollWidth,
                    viewportWidth:document.documentElement.clientWidth,
                    shellClient:shell.clientWidth,
                    shellScroll:shell.scrollWidth,
                    shellLeft:shell.scrollLeft,
                    svgWidth:svg.getBoundingClientRect().width,
                    nodes:svg.querySelectorAll('.flow-node').length,
                    outline:getComputedStyle(shell).outlineStyle,
                  };
                }
            """)
            self.assertLessEqual(mobile["pageWidth"], mobile["viewportWidth"] + 1)
            self.assertGreater(mobile["shellScroll"], mobile["shellClient"])
            self.assertGreater(mobile["svgWidth"], mobile["shellClient"])
            self.assertGreater(mobile["nodes"], 0)
            self.assertGreater(mobile["shellLeft"], before)
            self.assertNotEqual("none", mobile["outline"])
            self.assertEqual([], page_errors)
            self.assertEqual([], console_errors)
        finally:
            context.close()

    def test_lazy_error_contrast_in_light_and_dark_themes(self):
        context, page, page_errors, console_errors = self.new_page()
        try:
            self.wait_for_flow(page)
            ratios = {}
            for theme in ("light", "dark"):
                page.evaluate("theme => applyTheme(theme)", theme)
                self.assertFalse(self.force_flow_error(page))
                ratios[theme] = page.evaluate("""
                    () => {
                      const state=document.querySelector('#section-flow .lazy-error-state');
                      const parse=color=>{
                        const value=color.trim();
                        let match=value.match(/^rgba?\\((.+)\\)$/i);
                        if(match){
                          const parts=match[1].replace(/,/g,' ').split(/[\\s/]+/)
                            .filter(Boolean).slice(0,3);
                          return parts.map(part=>part.endsWith('%')
                            ?parseFloat(part)/100:parseFloat(part)/255);
                        }
                        match=value.match(/^color\\(srgb\\s+(.+)\\)$/i);
                        if(match){
                          return match[1].split(/[\\s/]+/).filter(Boolean)
                            .slice(0,3).map(Number);
                        }
                        throw new Error('Unsupported color: '+value);
                      };
                      const luminance=color=>parse(color).reduce((sum,channel,index)=>{
                        const linear=channel<=.04045
                          ?channel/12.92:Math.pow((channel+.055)/1.055,2.4);
                        return sum+linear*[.2126,.7152,.0722][index];
                      },0);
                      const contrast=(a,b)=>{
                        const first=luminance(a),second=luminance(b);
                        return (Math.max(first,second)+.05)/(Math.min(first,second)+.05);
                      };
                      const background=getComputedStyle(state).backgroundColor;
                      const body=getComputedStyle(state.querySelector('span')).color;
                      const heading=getComputedStyle(state.querySelector('b')).color;
                      const glyph=getComputedStyle(state,'::before').color;
                      return {
                        body:contrast(background,body),
                        heading:contrast(background,heading),
                        glyph:contrast(background,glyph),
                        colors:{background,body,heading,glyph},
                      };
                    }
                """)
                self.restore_flow_map(page)
                self.assertTrue(page.evaluate("renderLazy('flow',true)"))

            for theme, measured in ratios.items():
                with self.subTest(theme=theme, colors=measured["colors"]):
                    self.assertGreaterEqual(measured["body"], 4.5)
                    self.assertGreaterEqual(measured["heading"], 4.5)
                    self.assertGreaterEqual(measured["glyph"], 3.0)
            self.assertEqual([], page_errors)
            self.assertGreaterEqual(len(console_errors), 2)
            self.assertTrue(all(
                message == "[tokens] lazy renderer failed: flow"
                for message in console_errors
            ))
        finally:
            context.close()

    def test_trend_legend_isolates_models_and_recovers_from_empty(self):
        context, page, page_errors, console_errors = self.new_page()
        try:
            buttons = page.locator("#trend-legend [data-model-toggle]")
            self.assertGreaterEqual(buttons.count(), 2)
            pressed = [buttons.nth(i).get_attribute("aria-pressed") for i in range(buttons.count())]
            self.assertTrue(all(value == "true" for value in pressed))
            buttons.nth(1).click()
            self.assertEqual(
                "false", buttons.nth(1).get_attribute("aria-pressed"), "legend click must toggle only its own model"
            )
            self.assertEqual("true", buttons.nth(0).get_attribute("aria-pressed"))
            for i in range(buttons.count()):
                if buttons.nth(i).get_attribute("aria-pressed") == "true":
                    buttons.nth(i).click()
            self.assertEqual(
                0,
                page.locator("#trend-legend [data-model-toggle][aria-pressed=true]").count(),
            )
            self.assertIn(
                "0/2 个模型", page.locator("#filter-summary").inner_text().split(" · ")[0]
            )
            buttons.first.click()
            self.assertEqual("true", buttons.first.get_attribute("aria-pressed"))
            self.assertGreater(
                page.locator("#tbody tr[data-period]").count(), 0, "empty legend selection must stay recoverable"
            )
            self.assertEqual([], page_errors)
            self.assertEqual([], console_errors)
        finally:
            context.close()

    def test_scrub_links_exactly_one_table_row_and_drops_false_aria_current(self):
        context, page, page_errors, console_errors = self.new_page()
        try:
            period = page.evaluate("selectedRows(true)[0].period")
            page.evaluate("setScrubPreview(0,'test',false,false)")
            linked = page.locator("#tbody tr.row-linked")
            self.assertEqual(1, linked.count())
            self.assertEqual(period, linked.first.get_attribute("data-period"))
            self.assertEqual(
                1,
                page.evaluate(
                    "[...document.querySelectorAll('#bar .barstack')]"
                    ".filter(el=>el.getAttribute('aria-current')==='true').length"
                ),
            )
            self.assertEqual(
                0,
                page.evaluate(
                    "[...document.querySelectorAll('#bar .barstack')]"
                    ".filter(el=>el.getAttribute('aria-current')==='false').length"
                ),
            )
            page.evaluate("clearScrub()")
            self.assertEqual(0, page.locator("#tbody tr.row-linked").count())
            self.assertTrue(
                page.evaluate(
                    "[...document.querySelectorAll('#bar .barstack')]"
                    ".every(el=>el.getAttribute('aria-current')===null)"
                )
            )
            self.assertEqual([], page_errors)
            self.assertEqual([], console_errors)
        finally:
            context.close()

    def test_table_hover_previews_trend_without_commit(self):
        context, page, page_errors, console_errors = self.new_page()
        try:
            row = page.locator("#tbody tr[data-period]").first
            row.dispatch_event("pointerenter")
            self.assertEqual(1, page.locator("#bar .barstack.scrub-preview").count())
            self.assertEqual(1, page.locator("#tbody tr.row-linked").count())
            self.assertEqual(0, page.locator("#tbody tr.row-focused").count())
            self.assertNotEqual("", page.locator("#trend-readout").inner_text())
            row.dispatch_event("pointerleave")
            self.assertEqual(0, page.locator("#bar .barstack.scrub-preview").count())
            self.assertEqual(0, page.locator("#tbody tr.row-linked").count())
            self.assertEqual([], page_errors)
            self.assertEqual([], console_errors)
        finally:
            context.close()

    def test_mobile_trend_touch_targets_readout_and_no_overflow(self):
        context, page, page_errors, console_errors = self.new_page(
            viewport={"width": 390, "height": 760}
        )
        try:
            metrics = page.evaluate(
                """
                () => {
                  const targets=[...document.querySelectorAll('.tl-item,.chip,#tabs button')]
                    .filter(el=>getComputedStyle(el).display!=='none')
                    .map(el=>el.getBoundingClientRect().height);
                  const legend=getComputedStyle(document.getElementById('trend-legend'));
                  return {
                    minHeight:Math.min(...targets),
                    pageWidth:document.documentElement.scrollWidth,
                    viewportWidth:document.documentElement.clientWidth,
                    legendOverflowX:legend.overflowX,
                    readoutDisplay:getComputedStyle(document.getElementById('trend-readout')).display,
                  };
                }
                """
            )
            self.assertGreaterEqual(metrics["minHeight"], 44)
            self.assertLessEqual(metrics["pageWidth"], metrics["viewportWidth"] + 1)
            self.assertEqual("auto", metrics["legendOverflowX"])
            self.assertNotEqual("none", metrics["readoutDisplay"])
            desktop, desktop_page, _, _ = self.new_page()
            try:
                self.assertEqual(
                    "none",
                    desktop_page.evaluate(
                        "getComputedStyle(document.getElementById('trend-readout')).display"
                    ),
                )
            finally:
                desktop.close()
            self.assertEqual([], page_errors)
            self.assertEqual([], console_errors)
        finally:
            context.close()

    def test_faint_color_contrast_meets_aa_in_both_themes(self):
        context, page, page_errors, console_errors = self.new_page()
        try:
            for theme in ("light", "dark"):
                page.evaluate("theme => applyTheme(theme)", theme)
                ratio = page.evaluate(
                    """
                    () => {
                      const parse=color=>{
                        const value=color.trim();
                        let match=value.match(/^#([0-9a-f]{6})$/i);
                        if(match){
                          return [0,2,4].map(index=>parseInt(match[1].slice(index,index+2),16)/255);
                        }
                        match=value.match(/^#([0-9a-f]{3})$/i);
                        if(match){
                          return [...match[1]].map(part=>parseInt(part+part,16)/255);
                        }
                        match=value.match(/^rgba?\\((.+)\\)$/i);
                        if(match){
                          const parts=match[1].replace(/,/g,' ').split(/[\\s/]+/)
                            .filter(Boolean).slice(0,3);
                          return parts.map(part=>part.endsWith('%')
                            ?parseFloat(part)/100:parseFloat(part)/255);
                        }
                        match=value.match(/^color\\(srgb\\s+(.+)\\)$/i);
                        if(match){
                          return match[1].split(/[\\s/]+/).filter(Boolean)
                            .slice(0,3).map(Number);
                        }
                        throw new Error('Unsupported color: '+value);
                      };
                      const luminance=color=>parse(color).reduce((sum,channel,index)=>{
                        const linear=channel<=.04045
                          ?channel/12.92:Math.pow((channel+.055)/1.055,2.4);
                        return sum+linear*[.2126,.7152,.0722][index];
                      },0);
                      const contrast=(a,b)=>{
                        const first=luminance(a),second=luminance(b);
                        return (Math.max(first,second)+.05)/(Math.min(first,second)+.05);
                      };
                      const styles=getComputedStyle(document.documentElement);
                      return contrast(
                        styles.getPropertyValue('--surface').trim(),
                        styles.getPropertyValue('--faint').trim()
                      );
                    }
                    """
                )
                self.assertGreaterEqual(ratio, 4.5, f"--faint contrast in {theme} theme")
            self.assertEqual([], page_errors)
            self.assertEqual([], console_errors)
        finally:
            context.close()


if __name__ == "__main__":
    unittest.main()
