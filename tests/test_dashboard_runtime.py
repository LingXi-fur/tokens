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


@unittest.skipIf(sync_playwright is None, "Playwright is not installed")
class DashboardRuntimeTests(unittest.TestCase):
    BROWSER = "chromium"

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

        # Synthetic multi-month fixture for the interval lens / peak profile.
        # All periods are complete relative to the fixed generated_at, the peak
        # day (2026-02-04) has a consecutive complete previous day, and the peak
        # month (2026-02, first complete month) has no comparable prior period.
        def interval_record(date, model, total, session):
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
                "cwd": "/synthetic/interval-fixture",
            }

        interval_records = [
            interval_record("2026-02-03", "model-a", 300, "synthetic-session-i1"),
            interval_record("2026-02-04", "model-b", 900, "synthetic-session-i1"),
            interval_record("2026-03-05", "model-a", 600, "synthetic-session-i2"),
            interval_record("2026-04-07", "model-a", 350, "synthetic-session-i3"),
            interval_record("2026-05-09", "model-b", 200, "synthetic-session-i4"),
            interval_record("2026-06-01", "model-a", 100, "synthetic-session-i5"),
            interval_record("2026-06-02", "model-b", 120, "synthetic-session-i5"),
            interval_record("2026-06-03", "model-a", 80, "synthetic-session-i5"),
            interval_record("2026-06-04", "model-b", 90, "synthetic-session-i5"),
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
            interval_payload = report_dashboard.build_payload(
                interval_records,
                since="2026-02-01",
                until="2026-06-30",
                sources=["claude"],
                generated_at=datetime(2026, 7, 15, 12, 0),
            )
        cls._interval_path = Path(cls._tmp.name) / "synthetic-dashboard-interval.html"
        cls._interval_path.write_text(
            report_dashboard.render_dashboard(
                dashboard_wire.encode_payload(interval_payload)
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
        target = path or self._path
        page.goto(
            target if isinstance(target, str) and "://" in target else target.as_uri(),
            wait_until="load",
        )
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

    def test_new_attribution_and_archive_labels_localize_to_english(self):
        context, page, page_errors, console_errors = self.new_page()
        try:
            page.evaluate("applyLanguage('en',false)")
            page.locator("#ach-open").scroll_into_view_if_needed()
            page.locator("#ach-open").click()
            labels = page.evaluate(
                """
                () => ({
                  dock:[...document.querySelectorAll('.section-links button')]
                    .find(item=>item.dataset.target==='section-delta').textContent.trim(),
                  title:document.querySelector('#section-delta h2').textContent.trim(),
                  window:document.getElementById('delta-window').textContent.trim(),
                  archive:document.querySelector('.ach-archive-k').textContent.trim(),
                  copy:document.getElementById('ach-copy').textContent.trim(),
                  search:document.getElementById('ach-search').placeholder,
                  opener:document.getElementById('ach-open').textContent.trim(),
                })
                """
            )
            self.assertEqual("Attribution", labels["dock"])
            self.assertEqual("What drove this period’s change", labels["title"])
            self.assertEqual(
                "Requires two consecutive periods and a previous total above 0",
                labels["window"],
            )
            self.assertEqual("LOCAL ACHIEVEMENT ARCHIVE", labels["archive"])
            self.assertEqual("⧉ Copy link", labels["copy"])
            self.assertEqual(
                "Search achievements (name/story/condition/category)…",
                labels["search"],
            )
            self.assertEqual("📜 Open full achievement archive →", labels["opener"])
            self.assertEqual([], page_errors)
            self.assertEqual([], console_errors)
        finally:
            context.close()

    def test_dynamic_attribution_sort_and_achievement_details_localize_to_english(self):
        context, page, page_errors, console_errors = self.new_page()
        try:
            page.evaluate("applyLanguage('en',false)")
            page.locator('#tabs [data-gran="day"]').click()
            model_button = page.locator('#thead [data-sort-key="m"]').first
            model_button.click()
            page.wait_for_function(
                "document.getElementById('toast').textContent.includes('Sorted by')"
            )
            toast = page.locator("#toast").inner_text()

            page.locator("#ach-open").scroll_into_view_if_needed()
            page.locator("#ach-open").click()
            page.locator("#ach-filter").select_option("on")
            page.locator("#ach-body .badge.on").first.click()
            texts = page.evaluate(
                """
                () => ({
                  window:document.getElementById('delta-window').textContent.trim(),
                  story:document.getElementById('delta-story').textContent.trim(),
                  names:[...document.querySelectorAll('#delta-list .delta-name')]
                    .map(item=>item.textContent.trim()),
                  achievementStory:document.querySelector('#ach-detail .ach-story').textContent.trim(),
                  condition:document.querySelector('#ach-detail .ach-condition').textContent.trim(),
                  detail:document.getElementById('ach-detail').textContent.trim(),
                  fallbackName:achievementNameText({n:'初窥门径 · 01',category:'累计 token'}),
                })
                """
            )
            self.assertIn("current 200 vs previous 250", texts["window"])
            self.assertIn("drove the largest change", texts["story"])
            self.assertEqual("Sorted by model-a descending", toast)
            self.assertTrue(texts["condition"].startswith("Unlock condition: "))
            self.assertNotEqual("", texts["achievementStory"])
            for value in [toast, *texts.values()]:
                if isinstance(value, list):
                    value = " ".join(value)
                self.assertIsNone(
                    __import__("re").search(r"[㐀-鿿]", value),
                    value,
                )
            self.assertEqual([], page_errors)
            self.assertEqual([], console_errors)
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

    def test_table_sort_cycles_three_states_and_returns_to_time_order(self):
        context, page, page_errors, console_errors = self.new_page()
        try:
            page.locator('#tabs [data-gran="day"]').click()
            chronological = page.locator("#tbody tr[data-period]").evaluate_all(
                "els => els.map(el => el.dataset.period)"
            )
            totals = page.evaluate("() => selectedRows(true).map(r => [r.period, r.total])")
            self.assertGreaterEqual(len(chronological), 2)
            button = page.locator('#thead [data-sort-key="total"]')
            header = page.locator("#thead th").nth(1)
            self.assertEqual("none", header.get_attribute("aria-sort"))
            displayed = lambda: page.locator("#tbody tr[data-period]").evaluate_all(
                "els => els.map(el => el.dataset.period)"
            )
            button.click()
            self.assertEqual("descending", header.get_attribute("aria-sort"))
            self.assertTrue(button.evaluate("el => document.activeElement === el"))
            self.assertEqual(
                [period for period, _ in sorted(totals, key=lambda item: -item[1])],
                displayed(),
            )
            button.click()
            self.assertEqual("ascending", header.get_attribute("aria-sort"))
            self.assertEqual(
                [period for period, _ in sorted(totals, key=lambda item: item[1])],
                displayed(),
            )
            button.click()
            self.assertEqual("none", header.get_attribute("aria-sort"))
            self.assertEqual(chronological, displayed())
            page.locator('#thead [data-sort-key="cache"]').click()
            self.assertEqual(
                1,
                page.locator('#thead th[aria-sort="descending"], #thead th[aria-sort="ascending"]').count(),
                "exactly one header may carry a non-none aria-sort",
            )
            self.assertEqual([], page_errors)
            self.assertEqual([], console_errors)
        finally:
            context.close()


    def test_model_column_sort_cycles_safely_and_resets_when_filtered(self):
        context, page, page_errors, console_errors = self.new_page()
        try:
            page.locator('#tabs [data-gran="day"]').click()
            button = page.locator('#thead [data-sort-key="m"][data-sort-model="model-a"]')
            header = button.locator("xpath=..")
            model_values = page.evaluate(
                "() => selectedRows(true).map(r => [r.period, r.models['model-a'] || 0])"
            )
            displayed = lambda: page.locator("#tbody tr[data-period]").evaluate_all(
                "els => els.map(el => el.dataset.period)"
            )
            chronological = displayed()
            button.click()
            self.assertEqual("descending", header.get_attribute("aria-sort"))
            self.assertEqual(
                [period for period, _ in sorted(model_values, key=lambda item: -item[1])],
                displayed(),
            )
            button.click()
            self.assertEqual("ascending", header.get_attribute("aria-sort"))
            button.click()
            self.assertEqual(chronological, displayed())
            button = page.locator('#thead [data-sort-key="m"][data-sort-model="model-a"]')
            button.click()
            page.evaluate("setModels(['model-b'],'test filter')")
            self.assertEqual(
                {"key": None, "dir": None, "model": None},
                page.evaluate("tableSort"),
            )
            self.assertEqual(0, page.locator('#thead [aria-sort="descending"], #thead [aria-sort="ascending"]').count())
            self.assertEqual([], page_errors)
            self.assertEqual([], console_errors)
        finally:
            context.close()

    def test_malicious_model_name_is_safe_in_model_sort_attributes(self):
        context, page, page_errors, console_errors = self.new_page(path=self._malicious_path)
        try:
            model_name = "<img src=x onerror=window.__paletteXss=1>"
            button = page.locator('#thead [data-sort-key="m"]').filter(has_text=model_name)
            self.assertEqual(1, button.count())
            button.click()
            self.assertEqual("descending", button.locator("xpath=..").get_attribute("aria-sort"))
            self.assertEqual(0, page.locator("#thead img, #tbody img").count())
            self.assertIsNone(page.evaluate("window.__paletteXss"))
            self.assertEqual([], page_errors)
            self.assertEqual([], console_errors)
        finally:
            context.close()

    def test_attribution_reconciles_and_tracks_model_filter(self):
        context, page, page_errors, console_errors = self.new_page()
        try:
            page.locator('#tabs [data-gran="day"]').click()
            result = page.evaluate("attributionFor(selectedRows())")
            self.assertIsNotNone(result)
            self.assertEqual(
                result["currTotal"] - result["prevTotal"],
                sum(part["delta"] for part in result["parts"]),
            )
            page.evaluate("setModels(['model-a'],'test attribution filter')")
            filtered = page.evaluate("attributionFor(selectedRows())")
            self.assertEqual(["model-a"], [part["model"] for part in filtered["parts"]])
            self.assertIn("model-a", page.locator("#delta-list").inner_text())
            self.assertNotIn("model-b", page.locator("#delta-list").inner_text())
            self.assertEqual([], page_errors)
            self.assertEqual([], console_errors)
        finally:
            context.close()

    def test_achievement_archive_direct_url_history_and_details(self):
        direct = self._path.as_uri() + "?view=achievements"
        context, page, page_errors, console_errors = self.new_page(path=direct)
        try:
            modal = page.locator("#ach-modal")
            self.assertTrue(modal.evaluate("el => el.classList.contains('open')"))
            self.assertTrue(page.locator("#ach-search").evaluate("el => document.activeElement === el"))
            self.assertIn("view=achievements", page.url)
            page.locator("#ach-x").click()
            self.assertFalse(modal.evaluate("el => el.classList.contains('open')"))
            self.assertNotIn("view=achievements", page.url)

            opener = page.locator("#ach-open")
            opener.scroll_into_view_if_needed()
            opener.click()
            self.assertIn("view=achievements", page.url)
            self.assertTrue(modal.evaluate("el => el.classList.contains('open')"))
            page.go_back(wait_until="load")
            self.assertFalse(modal.evaluate("el => el.classList.contains('open')"))
            page.go_forward(wait_until="load")
            self.assertTrue(modal.evaluate("el => el.classList.contains('open')"))

            page.locator("#ach-filter").select_option("on")
            unfiltered_count = page.locator("#ach-body .badge").count()
            badge = page.locator("#ach-body .badge.on").first
            badge.click()
            self.assertNotEqual("", page.locator("#ach-detail .ach-story").inner_text())
            self.assertTrue(page.locator("#ach-detail .ach-condition").inner_text().startswith("达成条件："))
            story_text = page.locator("#ach-detail .ach-story").inner_text()
            page.locator("#ach-search").fill(story_text)
            filtered_count = page.locator("#ach-body .badge").count()
            self.assertGreater(filtered_count, 0)
            self.assertLess(filtered_count, unfiltered_count)
            page.locator("#ach-search").fill("")
            page.keyboard.press("Escape")
            page.wait_for_function("!document.getElementById('ach-modal').classList.contains('open')")
            self.assertTrue(opener.evaluate("el => document.activeElement === el"))
            self.assertEqual([], page_errors)
            self.assertEqual([], console_errors)
        finally:
            context.close()

    def test_achievement_archive_copy_and_mobile_geometry(self):
        for width in (390, 320):
            context, page, page_errors, console_errors = self.new_page(
                viewport={"width": width, "height": 760}
            )
            try:
                page.evaluate("window.__copied=null;copyText=text=>{window.__copied=text;return Promise.resolve(true)}")
                page.locator("#ach-open").scroll_into_view_if_needed()
                page.locator("#ach-open").click()
                page.locator("#ach-copy").click()
                page.wait_for_function("window.__copied !== null")
                self.assertIn("view=achievements", page.evaluate("window.__copied"))
                metrics = page.evaluate(
                    """
                    () => {
                      const controls=[...document.querySelectorAll('#ach-modal .ach-bar input, #ach-modal .ach-bar select, #ach-modal .ach-bar button')]
                        .filter(el=>getComputedStyle(el).display!=='none');
                      const delta=document.getElementById('section-delta').getBoundingClientRect();
                      const project=document.getElementById('section-project');
                      const projectChildren=[...project.querySelectorAll('*')].map(el=>{
                        const rect=el.getBoundingClientRect();
                        return {element:el.tagName.toLowerCase()+(el.id?'#'+el.id:'.'+String(el.className).trim().split(/\s+/)[0]),
                          right:Math.round(rect.right),width:Math.round(rect.width),
                          scrollWidth:el.scrollWidth,clientWidth:el.clientWidth,
                          overflow:getComputedStyle(el).overflowX};
                      }).filter(item=>item.right>project.getBoundingClientRect().right+1||item.scrollWidth>item.clientWidth+1).slice(0,20);
                      return {
                        pageWidth:document.documentElement.scrollWidth,
                        viewportWidth:document.documentElement.clientWidth,
                        projectWidth:project.scrollWidth,
                        projectClientWidth:project.clientWidth,
                        projectChildren,
                        minControlHeight:Math.min(...controls.map(el=>el.getBoundingClientRect().height)),
                        sheetWidth:document.querySelector('#ach-modal .ach-sheet').getBoundingClientRect().width,
                        deltaRight:delta.right,
                      };
                    }
                    """
                )
                self.assertGreaterEqual(metrics["minControlHeight"], 43.9)
                self.assertLessEqual(metrics["projectWidth"], metrics["projectClientWidth"] + 1, metrics)
                self.assertLessEqual(metrics["pageWidth"], metrics["viewportWidth"] + 1, metrics)
                self.assertLessEqual(metrics["sheetWidth"], metrics["viewportWidth"])
                self.assertLessEqual(metrics["deltaRight"], metrics["viewportWidth"] + 1)
                self.assertEqual([], page_errors)
                self.assertEqual([], console_errors)
            finally:
                context.close()

    def test_table_row_keyboard_previews_clears_and_commits(self):
        context, page, page_errors, console_errors = self.new_page()
        try:
            page.locator('#tabs [data-gran="day"]').click()
            row = page.locator("#tbody tr[data-period]").first
            row.focus()
            self.assertEqual(1, page.locator("#tbody tr.row-linked").count())
            self.assertEqual(1, page.locator("#bar .barstack.scrub-preview").count())
            page.keyboard.press("Escape")
            self.assertEqual(0, page.locator("#tbody tr.row-linked").count())
            self.assertEqual(0, page.locator("#bar .barstack.scrub-preview").count())
            page.keyboard.press("ArrowDown")
            self.assertEqual(1, page.locator("#tbody tr.row-linked").count())
            period = page.locator("#tbody tr.row-linked").get_attribute("data-period")
            page.keyboard.press("Enter")
            focused = page.locator("#tbody tr.row-focused")
            self.assertEqual(1, focused.count())
            self.assertEqual(period, focused.get_attribute("data-period"))
            self.assertEqual(1, page.locator("#tbody tr.row-linked").count())
            self.assertEqual(1, page.locator("#bar .barstack.scrub-preview").count())
            page.keyboard.press("Escape")
            self.assertEqual(0, page.locator("#tbody tr.row-linked").count())
            self.assertEqual(0, page.locator("#bar .barstack.scrub-preview").count())
            self.assertEqual([], page_errors)
            self.assertEqual([], console_errors)
        finally:
            context.close()

    def test_donut_legend_syncs_surfaces_and_recovers_from_all_off(self):
        context, page, page_errors, console_errors = self.new_page()
        try:
            donut = page.locator("#donut-legend [data-model-toggle]")
            trend = page.locator("#trend-legend [data-model-toggle]")
            slices = page.locator("#donut .slice[data-model]")
            count = donut.count()
            self.assertGreaterEqual(count, 2)
            self.assertEqual(count, trend.count())
            self.assertEqual(count, slices.count())
            donut.nth(1).click()
            self.assertEqual("false", donut.nth(1).get_attribute("aria-pressed"))
            self.assertEqual("false", trend.nth(1).get_attribute("aria-pressed"))
            self.assertEqual(count - 1, slices.count())
            for index in range(count):
                if donut.nth(index).get_attribute("aria-pressed") == "true":
                    donut.nth(index).click()
            self.assertEqual(
                0, page.locator("#donut-legend [data-model-toggle][aria-pressed=true]").count()
            )
            self.assertEqual(0, slices.count(), "all-off must empty the donut but keep its legend")
            donut.first.click()
            self.assertEqual("true", donut.first.get_attribute("aria-pressed"))
            self.assertGreaterEqual(slices.count(), 1)
            self.assertGreater(page.locator("#tbody tr[data-period]").count(), 0)
            self.assertEqual([], page_errors)
            self.assertEqual([], console_errors)
        finally:
            context.close()

    def test_footer_and_share_cards_link_to_project_without_tracking(self):
        project_url = "https://github.com/LingXi-fur/tokens"
        for width in (1280, 390, 320):
            context, page, page_errors, console_errors = self.new_page(
                viewport={"width": width, "height": 820}
            )
            try:
                footer_link = page.locator("#dynamic-footer a.project-link")
                self.assertEqual(project_url, footer_link.get_attribute("href"))
                self.assertEqual("_blank", footer_link.get_attribute("target"))
                self.assertEqual(
                    "noopener noreferrer",
                    footer_link.get_attribute("rel"),
                )
                for card_type in ("passport", "receipt"):
                    page.evaluate("kind => openShare(kind)", card_type)
                    card = page.locator("#share-card")
                    link = card.locator("a.share-project-link")
                    self.assertEqual(project_url, link.get_attribute("href"))
                    self.assertEqual("_blank", link.get_attribute("target"))
                    self.assertEqual("noopener noreferrer", link.get_attribute("rel"))
                    self.assertIn(project_url, card.evaluate("el => el.outerHTML"))
                    box = card.bounding_box()
                    self.assertLessEqual(box["width"], width + 1)
                    page.evaluate("closeShare()")
                metrics = page.evaluate(
                    "() => ({scroll:document.documentElement.scrollWidth,"
                    "client:document.documentElement.clientWidth})"
                )
                self.assertLessEqual(metrics["scroll"], metrics["client"] + 1)
                self.assertEqual([], page_errors)
                self.assertEqual([], console_errors)
            finally:
                context.close()

    def test_mobile_table_detail_expands_without_horizontal_overflow(self):
        for width in (390, 320):
            context, page, page_errors, console_errors = self.new_page(
                viewport={"width": width, "height": 760}
            )
            try:
                toggle = page.locator("#tbody tr[data-period] .row-toggle").first
                self.assertTrue(toggle.is_visible(), f"row toggle must be visible at {width}px")
                self.assertGreaterEqual(toggle.bounding_box()["height"], 44)
                self.assertEqual(0, page.locator("#tbody .col-model:visible").count())
                header_cells = page.locator("#thead th").count()
                row_cells = page.locator("#tbody tr[data-period]").first.locator("td").count()
                self.assertEqual(header_cells, row_cells)
                detail = page.locator("#tbody tr.row-detail").first
                self.assertTrue(detail.is_hidden())
                toggle.scroll_into_view_if_needed()
                toggle.hover()
                page.wait_for_timeout(150)
                toggle.click()
                self.assertEqual("true", toggle.get_attribute("aria-expanded"))
                self.assertFalse(detail.is_hidden())
                self.assertTrue(detail.locator(".dl-grid").is_visible())
                metrics = page.evaluate(
                    "() => ({ scroll: document.documentElement.scrollWidth,"
                    " client: document.documentElement.clientWidth })"
                )
                self.assertLessEqual(metrics["scroll"], metrics["client"] + 1)
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


    # --- interval lens / peak profile ---------------------------------

    def interval_url(self, query=""):
        return self._interval_path.as_uri() + query

    def click_bar(self, page, period):
        page.locator(f".bar-hit[data-period='{period}']").click()

    def press_bar(self, page, period, key):
        # Keyboard activation parked on a bar. Scrub is cleared first so the
        # keydown handler resolves the period from the focused bar itself.
        # The pointer is also parked off-chart: scrolling a bar into view can
        # fire a pointer-driven setScrubPreview for whatever sits under the
        # stale cursor, and onkeydown prefers scrubState.period over the
        # focused bar, which would silently retarget the lens.
        page.mouse.move(2, 2)
        page.evaluate("clearScrub()")
        page.focus(f".barstack[data-period='{period}']")
        page.locator(f".barstack[data-period='{period}']").dispatch_event(
            "keydown", {"key": key}
        )

    def interval_snapshot(self, page):
        return page.evaluate(
            """
            () => {
              const result = intervalResult();
              return {
                active: intervalState.active,
                start: intervalState.start,
                end: intervalState.end,
                bStart: intervalState.bStart,
                a: result ? result.a.map(row => row.period) : null,
                b: result ? result.b.map(row => row.period) : null,
              };
            }
            """
        )

    def test_interval_month_granularity_builds_equal_length_cross_month_span(self):
        context, page, page_errors, console_errors = self.new_page(
            path=self.interval_url()
        )
        try:
            self.assertEqual("month", page.evaluate("state.gran"))
            self.assertEqual(
                [
                    "2026-02-01",
                    "2026-03-01",
                    "2026-04-01",
                    "2026-05-01",
                    "2026-06-01",
                ],
                page.evaluate("completeIntervalRows().map(row => row.period)"),
            )
            month_tab = page.locator('#tabs [data-gran="month"]')
            self.assertIn("on", month_tab.get_attribute("class"))
            self.assertEqual("true", month_tab.get_attribute("aria-pressed"))
            page.locator("#interval-btn").click()
            self.assertEqual(
                "true", page.locator("#interval-btn").get_attribute("aria-pressed")
            )
            for period in ("2026-02-01", "2026-03-01", "2026-04-01"):
                self.click_bar(page, period)
            snapshot = self.interval_snapshot(page)
            self.assertEqual("2026-02-01", snapshot["start"])
            self.assertEqual("2026-03-01", snapshot["end"])
            self.assertEqual("2026-04-01", snapshot["bStart"])
            self.assertEqual(["2026-02-01", "2026-03-01"], snapshot["a"])
            self.assertEqual(["2026-04-01", "2026-05-01"], snapshot["b"])
            self.assertEqual(
                "A 2026-02 → 2026-03 · B 2026-04 → 2026-05",
                page.inner_text("#interval-prompt"),
            )
            self.assertIn(
                "interval=1&a=2026-02-01&aEnd=2026-03-01&b=2026-04-01",
                page.evaluate("viewParams().toString()"),
            )
            self.assertEqual([], page_errors)
            self.assertEqual([], console_errors)
        finally:
            context.close()

    def test_interval_day_granularity_keyboard_and_click_select_same_span(self):
        context, page, page_errors, console_errors = self.new_page(
            path=self.interval_url("?gran=day")
        )
        try:
            page.locator('#tabs [data-gran="day"]').click()
            self.assertEqual(
                [
                    "2026-02-03",
                    "2026-02-04",
                    "2026-03-05",
                    "2026-04-07",
                    "2026-05-09",
                    "2026-06-01",
                    "2026-06-02",
                    "2026-06-03",
                    "2026-06-04",
                ],
                page.evaluate("completeIntervalRows().map(row => row.period)"),
            )
            page.locator("#interval-btn").click()
            for period in ("2026-06-01", "2026-06-02", "2026-06-03"):
                self.click_bar(page, period)
            clicked = self.interval_snapshot(page)
            self.assertEqual(["2026-06-01", "2026-06-02"], clicked["a"])
            self.assertEqual(["2026-06-03", "2026-06-04"], clicked["b"])
            self.assertEqual(
                "A 06-01 → 06-02 · B 06-03 → 06-04",
                page.inner_text("#interval-prompt"),
            )
            self.assertEqual(
                "gran=day&interval=1&a=2026-06-01&aEnd=2026-06-02&b=2026-06-03",
                page.evaluate("viewParams().toString()"),
            )
            self.assertIn(
                "interval-a",
                page.locator(".barstack[data-period='2026-06-01']").get_attribute("class"),
            )
            self.assertIn(
                "interval-b",
                page.locator(".barstack[data-period='2026-06-03']").get_attribute("class"),
            )
            self.assertIn(
                "已选 A 时段",
                page.locator(".barstack[data-period='2026-06-01']").get_attribute("aria-label"),
            )
            self.assertIn(
                "已选 B 时段",
                page.locator(".barstack[data-period='2026-06-03']").get_attribute("aria-label"),
            )
            self.assertEqual(
                1,
                page.evaluate(
                    """document.querySelectorAll('#bar .barstack[tabindex="0"]').length"""
                ),
            )
            self.assertEqual(9, page.locator("#bar .barstack[role=button]").count())
            self.assertEqual([], page_errors)
            self.assertEqual([], console_errors)
        finally:
            context.close()

        # The keyboard path over the same bars must produce the same span.
        context, page, page_errors, console_errors = self.new_page(
            path=self.interval_url("?gran=day")
        )
        try:
            page.locator("#interval-btn").click()
            for period in ("2026-06-01", "2026-06-02", "2026-06-03"):
                self.press_bar(page, period, "Enter")
            self.assertEqual(clicked, self.interval_snapshot(page))
            page.keyboard.press("Escape")
            self.assertFalse(page.evaluate("intervalState.active"))
            self.assertIsNone(page.evaluate("intervalState.start"))
            self.assertEqual(
                "false", page.locator("#interval-btn").get_attribute("aria-pressed")
            )
            self.assertEqual([], page_errors)
            self.assertEqual([], console_errors)
        finally:
            context.close()

    def test_mouse_drag_selects_a_then_click_selects_b(self):
        context, page, page_errors, console_errors = self.new_page(
            path=self.interval_url("?gran=day")
        )
        try:
            page.locator("#interval-btn").click()
            page.locator(".bar-hit[data-period='2026-06-01']").scroll_into_view_if_needed()
            start = page.locator(".bar-hit[data-period='2026-06-01']").bounding_box()
            end = page.locator(".bar-hit[data-period='2026-06-02']").bounding_box()
            page.mouse.move(start["x"] + start["width"] / 2, start["y"] + 30)
            page.mouse.down()
            page.mouse.move(end["x"] + end["width"] / 2, end["y"] + 30, steps=5)
            page.mouse.up()
            self.assertEqual("2026-06-01", page.evaluate("intervalState.start"))
            self.assertEqual("2026-06-02", page.evaluate("intervalState.end"))
            self.click_bar(page, "2026-06-03")
            self.assertEqual(
                ["2026-06-03", "2026-06-04"], self.interval_snapshot(page)["b"]
            )
            self.assertEqual([], page_errors)
            self.assertEqual([], console_errors)
        finally:
            context.close()

    def test_interval_and_peak_copy_is_english_in_browser(self):
        context, page, page_errors, console_errors = self.new_page(
            path=self.interval_url("?gran=day")
        )
        try:
            page.evaluate("applyLanguage('en',false)")
            page.locator("#interval-btn").click()
            for period in ("2026-06-01", "2026-06-02", "2026-06-03"):
                self.click_bar(page, period)
            self.assertEqual(
                "A 06-01 → 06-02 · B 06-03 → 06-04",
                page.inner_text("#interval-prompt"),
            )
            page.locator("#peak-btn").click()
            self.assertIn(
                "Previous period 300", page.inner_text("#peak-content .peak-lead")
            )
            untranslated = page.evaluate(
                """() => {
                  const visible = element => element.getClientRects().length &&
                    !element.closest('script,style,[hidden]') &&
                    getComputedStyle(element).display !== 'none';
                  const leftovers = [];
                  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
                  while (walker.nextNode()) {
                    const node = walker.currentNode;
                    if (node.parentElement && visible(node.parentElement) &&
                        /[㐀-鿿]/.test(node.nodeValue) &&
                        node.parentElement.id !== 'lang-btn')
                      leftovers.push(node.nodeValue.trim());
                  }
                  for (const element of document.querySelectorAll('[aria-label],[title],[placeholder]')) {
                    if (!visible(element)) continue;
                    for (const name of ['aria-label','title','placeholder']) {
                      const value = element.getAttribute(name);
                      if (value && /[㐀-鿿]/.test(value)) leftovers.push(name + ': ' + value);
                    }
                  }
                  return leftovers;
                }"""
            )
            self.assertEqual([], untranslated)
            self.assertEqual([], page_errors)
            self.assertEqual([], console_errors)
        finally:
            context.close()

    def test_peak_profile_previous_period_and_empty_state(self):
        context, page, page_errors, console_errors = self.new_page(
            path=self.interval_url("?gran=day")
        )
        try:
            self.assertEqual("2026-02-04", page.evaluate("peakPeriod()"))
            self.assertEqual("false", page.locator("#peak-btn").get_attribute("aria-expanded"))
            self.press_bar(page, "2026-02-04", "p")
            self.assertEqual("2026-02-04", page.evaluate("peakState.period"))
            self.assertEqual("峰值剖面 · 02-04", page.inner_text("#peak-heading"))
            self.assertEqual("true", page.locator("#peak-btn").get_attribute("aria-expanded"))
            self.assertFalse(page.locator("#peak-profile").is_hidden())
            lead = page.inner_text("#peak-content .peak-lead")
            self.assertIn("900 Token", lead)
            self.assertIn("前一期 300", lead)
            self.assertIn("+600", lead)
            page.keyboard.press("Escape")
            self.assertIsNone(page.evaluate("peakState.period"))
            self.assertTrue(page.locator("#peak-profile").is_hidden())
            self.assertEqual("false", page.locator("#peak-btn").get_attribute("aria-expanded"))
            self.assertEqual([], page_errors)
            self.assertEqual([], console_errors)
        finally:
            context.close()

        context, page, page_errors, console_errors = self.new_page(
            path=self.interval_url()
        )
        try:
            # Default month view: the peak is the first complete month, so there
            # is no complete consecutive prior period and the empty state shows.
            self.assertEqual("2026-02-01", page.evaluate("peakPeriod()"))
            self.assertEqual(
                "2026-02-01",
                page.evaluate("completeIntervalRows().map(row => row.period)[0]"),
            )
            page.locator("#peak-btn").click()
            self.assertEqual("true", page.locator("#peak-btn").get_attribute("aria-expanded"))
            self.assertEqual("峰值剖面 · 2026-02", page.inner_text("#peak-heading"))
            self.assertIn("无完整相邻前期可比", page.inner_text("#peak-content .peak-lead"))
            self.assertEqual([], page_errors)
            self.assertEqual([], console_errors)
        finally:
            context.close()

    def test_interval_and_peak_restore_from_url(self):
        context, page, page_errors, console_errors = self.new_page(
            path=self.interval_url(
                "?gran=day&interval=1&a=2026-06-01&aEnd=2026-06-02&b=2026-06-03"
            )
        )
        try:
            snapshot = self.interval_snapshot(page)
            self.assertTrue(snapshot["active"])
            self.assertEqual("2026-06-01", snapshot["start"])
            self.assertEqual("2026-06-02", snapshot["end"])
            self.assertEqual("2026-06-03", snapshot["bStart"])
            self.assertEqual(["2026-06-01", "2026-06-02"], snapshot["a"])
            self.assertEqual(["2026-06-03", "2026-06-04"], snapshot["b"])
            self.assertEqual(
                "true", page.locator("#interval-btn").get_attribute("aria-pressed")
            )
            self.assertEqual([], page_errors)
            self.assertEqual([], console_errors)
        finally:
            context.close()

        context, page, page_errors, console_errors = self.new_page(
            path=self.interval_url("?peak=2026-02-01")
        )
        try:
            self.assertEqual("2026-02-01", page.evaluate("peakState.period"))
            self.assertFalse(page.locator("#peak-profile").is_hidden())
            self.assertEqual("峰值剖面 · 2026-02", page.inner_text("#peak-heading"))
            self.assertIn("无完整相邻前期可比", page.inner_text("#peak-content .peak-lead"))
            self.assertEqual([], page_errors)
            self.assertEqual([], console_errors)
        finally:
            context.close()

    def test_interval_lens_leaves_normal_scrub_untouched(self):
        context, page, page_errors, console_errors = self.new_page(
            path=self.interval_url("?gran=day")
        )
        try:
            # Lens closed: a bar click still commits the time probe.
            self.click_bar(page, "2026-06-02")
            self.assertEqual("2026-06-02", page.evaluate("state.focusPeriod"))
            page.evaluate("clearFocus()")
            self.assertIsNone(page.evaluate("state.focusPeriod"))

            # Preview plumbing still works while the lens is closed.
            page.evaluate("setScrubPreview(5,'test',false,false)")
            self.assertEqual(1, page.locator("#bar .barstack.scrub-preview").count())
            self.assertEqual(1, page.locator("#tbody tr.row-linked").count())
            page.evaluate("clearScrub()")
            self.assertEqual(0, page.locator("#bar .barstack.scrub-preview").count())
            self.assertEqual(0, page.locator("#tbody tr.row-linked").count())

            # Lens open: a bar click feeds the lens instead of the probe.
            page.locator("#interval-btn").click()
            self.click_bar(page, "2026-06-03")
            self.assertIsNone(page.evaluate("state.focusPeriod"))
            self.assertEqual("2026-06-03", page.evaluate("intervalState.start"))
            self.assertFalse(
                page.evaluate("!!document.querySelector('#tbody tr.row-focused')")
            )

            page.keyboard.press("Escape")
            self.assertFalse(page.evaluate("intervalState.active"))
            self.assertIsNone(page.evaluate("state.focusPeriod"))
            self.assertEqual([], page_errors)
            self.assertEqual([], console_errors)
        finally:
            context.close()


if __name__ == "__main__":
    unittest.main()
