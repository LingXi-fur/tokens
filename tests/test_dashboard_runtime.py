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
        cls._overflow_path = Path(cls._tmp.name) / "synthetic-dashboard-other.html"
        overflow_records = [
            interval_record("2026-01-01", f"model-{index}", 200, f"synthetic-base-{index}")
            for index in range(7)
        ] + [
            interval_record("2026-02-05", "model-6", 1, "synthetic-keep"),
            interval_record("2026-01-06", "other", 5, "synthetic-raw-other"),
            interval_record("2026-01-06", "older-<img src=x onerror=window.__otherXss=1>", 40, "synthetic-overflow-a"),
            interval_record("2026-01-07", "older-<img src=x onerror=window.__otherXss=1>", 20, "synthetic-overflow-b"),
            interval_record("2026-02-04", "older-<img src=x onerror=window.__otherXss=1>", 10, "synthetic-overflow-c"),
            interval_record("2026-02-04", "other", 5, "synthetic-raw-other-b"),
        ]
        with mock.patch("tokens_cli.dashboard_payload.readers.build_session_index", return_value={}), mock.patch(
            "tokens_cli.dashboard_payload.readers.session_title", return_value=""
        ), mock.patch("tokens_cli.dashboard_payload.readers.load_session_summaries", return_value={}):
            overflow_payload = report_dashboard.build_payload(
                overflow_records, since="2026-01-01", until="2026-02-28",
                sources=["claude"], generated_at=datetime(2026, 3, 15, 12, 0),
            )
        cls._overflow_path.write_text(
            report_dashboard.render_dashboard(dashboard_wire.encode_payload(overflow_payload)),
            encoding="utf-8",
        )
        cls._visible_other_path = Path(cls._tmp.name) / "synthetic-visible-other.html"
        with mock.patch("tokens_cli.dashboard_payload.readers.build_session_index", return_value={}), mock.patch(
            "tokens_cli.dashboard_payload.readers.session_title", return_value=""
        ), mock.patch("tokens_cli.dashboard_payload.readers.load_session_summaries", return_value={}):
            visible_payload = report_dashboard.build_payload(
                overflow_records + [
                    interval_record("2026-01-07", "glm-5.3-flash", 13, "synthetic-flash-a"),
                    interval_record("2026-02-04", "glm-5.3-flash", 7, "synthetic-flash-b"),
                ], since="2026-01-01", until="2026-02-28",
                sources=["claude"], generated_at=datetime(2026, 3, 15, 12, 0),
            )
        cls._visible_other_path.write_text(
            report_dashboard.render_dashboard(dashboard_wire.encode_payload(visible_payload)),
            encoding="utf-8",
        )
        untimed_records = overflow_records + [{
            **interval_record("2026-02-04", "older-<img src=x onerror=window.__otherXss=1>",
                              50, "synthetic-untimed"),
            "ts": "invalid-timestamp",
        }]
        with mock.patch("tokens_cli.dashboard_payload.readers.build_session_index", return_value={}), mock.patch(
            "tokens_cli.dashboard_payload.readers.session_title", return_value=""
        ), mock.patch("tokens_cli.dashboard_payload.readers.load_session_summaries", return_value={}):
            untimed_payload = report_dashboard.build_payload(
                untimed_records, since="2026-01-01", until="2026-02-28",
                sources=["claude"], generated_at=datetime(2026, 2, 15, 12, 0),
            )
        cls._untimed_overflow_path = Path(cls._tmp.name) / "synthetic-dashboard-untimed-other.html"
        cls._untimed_overflow_path.write_text(
            report_dashboard.render_dashboard(dashboard_wire.encode_payload(untimed_payload)),
            encoding="utf-8",
        )
        # Synthetic fixture with an historical and a current Sol backend, both
        # heavily used, plus low-usage legacy models that overflow into Other.
        cls._sol_path = Path(cls._tmp.name) / "synthetic-dashboard-sol.html"
        # A single unbreakable backend identity longer than any viewport column:
        # 38 characters with no hyphen break opportunity, so it can only stay put
        # if the legend lets the name span shrink and wrap.
        cls._long_backend_name = "claude_opus_4_6_very_long_backend_name"
        sol_records = [
            interval_record("2026-05-01", "gpt-6-sol", 300, "synthetic-sol-old"),
            # Second-heaviest so it lands in the right-hand legend column, where a
            # spill past the button would push the document wider than 390px.
            interval_record(
                "2026-05-10", cls._long_backend_name, 280, "synthetic-sol-long"
            ),
            interval_record("2026-05-09", "gpt-6.1-sol", 250, "synthetic-sol-new"),
        ] + [
            interval_record(
                f"2026-05-{index + 2:02d}", f"legacy-model-{index}", 20 - index,
                f"synthetic-sol-legacy-{index}",
            )
            for index in range(7)
        ]
        with mock.patch(
            "tokens_cli.dashboard_payload.readers.build_session_index", return_value={}
        ), mock.patch(
            "tokens_cli.dashboard_payload.readers.session_title", return_value=""
        ), mock.patch(
            "tokens_cli.dashboard_payload.readers.load_session_summaries", return_value={}
        ):
            sol_payload = report_dashboard.build_payload(
                sol_records, since="2026-05-01", until="2026-05-31",
                sources=["claude"], generated_at=datetime(2026, 6, 15, 12, 0),
            )
        cls._sol_path.write_text(
            report_dashboard.render_dashboard(dashboard_wire.encode_payload(sol_payload)),
            encoding="utf-8",
        )
        # High-volume fixture: 1000 sessions across two long-named projects and two
        # models. Session labels are blank, so the destinations module exercises its
        # Untitled fallback, pagination remainder and lazy full-set table.
        volume_records = []
        for index in range(1000):
            day = 1 + (index % 28)
            model = "model-a" if index % 3 else "model-b"
            cwd = (
                "/synthetic/volume-long-project-name-alpha"
                if index % 2 == 0
                else "/synthetic/volume-long-project-name-beta"
            )
            volume_records.append({
                "source": "claude",
                "ts": f"2026-08-{day:02d}T09:00:00+08:00",
                "date": f"2026-08-{day:02d}",
                "model": model,
                "input": 10 + (index % 7),
                "output": 5,
                "cache_read": 2,
                "cache_write": 0,
                "total": 20 + (index % 40),
                "session": f"synthetic-volume-{index:04d}",
                "cwd": cwd,
            })
        with mock.patch(
            "tokens_cli.dashboard_payload.readers.build_session_index", return_value={}
        ), mock.patch(
            "tokens_cli.dashboard_payload.readers.session_title", return_value=""
        ), mock.patch(
            "tokens_cli.dashboard_payload.readers.load_session_summaries", return_value={}
        ):
            volume_payload = report_dashboard.build_payload(
                volume_records, since="2026-08-01", until="2026-08-31",
                sources=["claude"], generated_at=datetime(2026, 9, 15, 12, 0),
            )
        cls._volume_path = Path(cls._tmp.name) / "synthetic-dashboard-volume.html"
        cls._volume_path.write_text(
            report_dashboard.render_dashboard(dashboard_wire.encode_payload(volume_payload)),
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
            "document.querySelectorAll('#flow-map .dest-project').length > 0 && "
            "document.querySelectorAll('#flow-map .dest-session').length > 0"
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
              const panel=document.getElementById('flow-panel');
              panel.parentNode.insertBefore(window.__detachedFlowMap, panel);
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
            state = page.evaluate("""
                () => {
                  const section=document.getElementById('section-flow');
                  const grid=document.getElementById('flow-map');
                  const proj=grid.querySelector('.dest-project-name');
                  return {
                    sectionDisplay:getComputedStyle(section).display,
                    pending:section.classList.contains('lazy-pending'),
                    error:!!section.querySelector('.lazy-error-state'),
                    ariaBusy:section.getAttribute('aria-busy'),
                    projects:grid.querySelectorAll('.dest-project').length,
                    sessions:grid.querySelectorAll('.dest-session').length,
                    pager:!!grid.querySelector('.dest-pager'),
                    stats:document.getElementById('flow-stats').textContent,
                    gridWidth:grid.getBoundingClientRect().width,
                    gridVisibility:getComputedStyle(grid).visibility,
                    projectText:proj?proj.textContent:'',
                  };
                }
            """)
            self.assertNotEqual("none", state["sectionDisplay"])
            self.assertFalse(state["pending"])
            self.assertFalse(state["error"])
            self.assertEqual("false", state["ariaBusy"])
            self.assertGreater(state["projects"], 0)
            self.assertGreater(state["sessions"], 0)
            self.assertLessEqual(state["sessions"], 12)
            self.assertTrue(state["pager"])
            self.assertGreater(state["gridWidth"], 0)
            self.assertNotEqual("hidden", state["gridVisibility"])
            self.assertIn("个会话", state["stats"])
            self.assertIn("long-running-project-alpha", state["projectText"])
            self.assertNotIn("…", state["projectText"])

            page.evaluate("applyLanguage('en',false)")
            english = page.evaluate("""
                () => ({
                  stats:document.getElementById('flow-stats').textContent,
                  pager:document.querySelector('#flow-map .dest-pagecount').textContent,
                })
            """)
            self.assertIn("sessions", english["stats"])
            self.assertIn("Page", english["pager"])

            page.evaluate("applyLanguage('zh',false)")
            page.evaluate("state.models.clear();renderLazy('flow',true)")
            page.wait_for_function(
                "document.getElementById('flow-stats').textContent.includes('0 个会话')"
            )
            empty = page.evaluate("""
                () => ({
                  stats:document.getElementById('flow-stats').textContent,
                  empty:!!document.querySelector('#flow-map .dest-empty'),
                  sessions:document.querySelectorAll('#flow-map .dest-session').length,
                })
            """)
            self.assertIn("0 个会话", empty["stats"])
            self.assertTrue(empty["empty"])
            self.assertEqual(0, empty["sessions"])
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
                          const grid=document.getElementById('flow-map');
                          const first=grid.querySelector('.dest-session');
                          return {
                            sessions:grid.querySelectorAll('.dest-session').length,
                            projects:grid.querySelectorAll('.dest-project').length,
                            visibility:getComputedStyle(grid).visibility,
                            anim:first?getComputedStyle(first).animationName:'none',
                          };
                        }
                    """)
                    self.assertGreater(geometry["sessions"], 0)
                    self.assertGreater(geometry["projects"], 0)
                    self.assertNotEqual("hidden", geometry["visibility"])
                    self.assertEqual("none", geometry["anim"])

            page.emulate_media(reduced_motion="reduce", color_scheme="dark")
            page.evaluate("applyTheme('auto'); renderLazy('flow',true)")
            self.assertGreater(page.locator("#flow-map .dest-project").count(), 0)
            self.assertEqual(
                "none",
                page.locator("#flow-map .dest-project").first.evaluate(
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
                "document.querySelectorAll('#flow-map .dest-project').length > 0"
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
                "document.querySelectorAll('#flow-map .dest-project').length > 0 && "
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
            self.assertIn("去向", focus["text"])
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

    def test_destinations_model_filter_and_reset_preserve_global_models(self):
        context, page, page_errors, console_errors = self.new_page()
        try:
            self.wait_for_flow(page)
            baseline = page.evaluate("""
                () => ({
                  sessions:document.querySelectorAll('#flow-map .dest-session').length,
                  models:[...state.models],
                })
            """)
            model = page.evaluate("""
                () => [...document.querySelectorAll('#flow-map .dest-chip')]
                  .map(chip=>chip.dataset.destModel).find(value=>value)
            """)
            self.assertTrue(model)
            page.locator(
                '#flow-map .dest-chip[data-dest-model="' + model + '"]'
            ).click()
            filtered = page.evaluate("""
                () => ({
                  model:destState.model,
                  page:destState.page,
                  note:!!document.querySelector('#flow-map .dest-filter-note'),
                  active:document.querySelectorAll('#flow-map .dest-chip.is-active').length,
                  global:[...state.models],
                })
            """)
            self.assertEqual(model, filtered["model"])
            self.assertEqual(0, filtered["page"])
            self.assertTrue(filtered["note"])
            self.assertEqual(baseline["models"], filtered["global"])

            page.locator("#flow-map .dest-filter-note button").click()
            reset = page.evaluate(
                "() => ({model:destState.model, global:[...state.models]})"
            )
            self.assertIsNone(reset["model"])
            self.assertEqual(baseline["models"], reset["global"])
            self.assertEqual(
                baseline["sessions"], page.locator("#flow-map .dest-session").count()
            )
            self.assertEqual([], page_errors)
            self.assertEqual([], console_errors)
        finally:
            context.close()

    def test_destinations_pagination_builds_only_page_and_full_table(self):
        context, page, page_errors, console_errors = self.new_page(
            path=self._volume_path
        )
        try:
            self.wait_for_flow(page)
            info = page.evaluate("""
                () => {
                  const c=computeDestinations();
                  return {
                    total:c.filtered.length, pageCount:c.pageCount,
                    rendered:document.querySelectorAll('#flow-map .dest-session').length,
                    untitled:document.querySelector('#flow-map .dest-session-title').textContent,
                    sid:document.querySelector('#flow-map .dest-sid').textContent,
                    tableRows:document.querySelectorAll('#flow-map .dest-table tbody tr').length,
                  };
                }
            """)
            self.assertEqual(1000, info["total"])
            self.assertEqual(84, info["pageCount"])
            self.assertEqual(12, info["rendered"])
            self.assertEqual("未命名会话", info["untitled"])
            self.assertTrue(info["sid"].startswith("synthetic-"))
            self.assertTrue(info["sid"].endswith("\u2026"))
            self.assertEqual(0, info["tableRows"])

            page.locator('#flow-map [data-dest-page="next"]').click()
            paged = page.evaluate("""
                () => ({
                  page:destState.page,
                  rendered:document.querySelectorAll('#flow-map .dest-session').length,
                  usage:document.querySelector('#flow-map .dest-usage').textContent,
                })
            """)
            self.assertEqual(1, paged["page"])
            self.assertEqual(12, paged["rendered"])
            self.assertIn("页外", paged["usage"])

            last = page.evaluate("""
                () => {
                  destState.page=computeDestinations().pageCount-1;
                  renderFlow();
                  const c=computeDestinations();
                  return {
                    remainder:c.pageSessions.length,
                    pageTotal:c.pageTotal,
                    outside:c.outsideTotal,
                    filteredTotal:c.filteredTotal,
                  };
                }
            """)
            self.assertEqual(1000 - 83 * 12, last["remainder"])
            self.assertEqual(last["filteredTotal"], last["pageTotal"] + last["outside"])

            page.locator('#flow-map [data-dest-view="table"]').click()
            table = page.evaluate("""
                () => ({
                  pressed:document.querySelector('#flow-map [data-dest-view="table"]').getAttribute('aria-pressed'),
                  rows:document.querySelectorAll('#flow-map .dest-table tbody tr').length,
                  cards:document.querySelectorAll('#flow-map .dest-session').length,
                  sessionsHidden:getComputedStyle(document.querySelector('#flow-map .dest-sessions')).display,
                })
            """)
            self.assertEqual("true", table["pressed"])
            self.assertEqual(1000, table["rows"])
            self.assertEqual("none", table["sessionsHidden"])
            replay = page.locator("#flow-map .dest-table [data-dest-replay]").first
            self.assertEqual(1000, page.locator("#flow-map .dest-table [data-dest-replay]").count())
            replay_id = replay.get_attribute("data-dest-replay")
            self.assertNotIn(replay_id, page.evaluate(
                "computeDestinations().pageSessions.map(session=>session.id)"
            ))
            replay.click()
            self.assertTrue(page.locator("#replay-modal").is_visible())
            self.assertEqual(replay_id, page.evaluate("rp.sid"))
            page.locator("#replay-x").click()
            self.assertFalse(page.locator("#replay-modal").is_visible())

            page.evaluate("destState.page=0;")
            page.locator('#flow-map [data-dest-view="cards"]').click()
            self.assertEqual(
                12, page.locator("#flow-map .dest-session").count()
            )
            self.assertEqual(
                0,
                page.locator("#flow-map .dest-table tbody tr").count(),
            )
            self.assertNotEqual(
                "none",
                page.locator("#flow-map .dest-sessions").evaluate(
                    "element => getComputedStyle(element).display"
                ),
            )
            self.assertEqual([], page_errors)
            self.assertEqual([], console_errors)
        finally:
            context.close()

    def test_destinations_scope_change_resets_pagination_and_filter(self):
        context, page, page_errors, console_errors = self.new_page(
            path=self._volume_path
        )
        try:
            self.wait_for_flow(page)
            before = page.evaluate("""
                () => {
                  destState.page=1;
                  destState.model=computeDestinations().data.models[0];
                  renderFlow();
                  return {page:destState.page, model:destState.model};
                }
            """)
            self.assertEqual(1, before["page"])
            self.assertTrue(before["model"])
            after = page.evaluate("""
                () => {
                  state.gran = state.gran === 'day' ? 'month' : 'day';
                  computeDestinations();
                  renderFlow();
                  return {page:destState.page, model:destState.model};
                }
            """)
            self.assertEqual(0, after["page"])
            self.assertIsNone(after["model"])
            self.assertEqual([], page_errors)
            self.assertEqual([], console_errors)
        finally:
            context.close()

    def test_destinations_model_totals_use_single_projection(self):
        context, page, page_errors, console_errors = self.new_page(
            path=self._volume_path
        )
        try:
            self.wait_for_flow(page)
            measured = page.evaluate("""
                () => {
                  const proj={}, sess={};
                  Object.values(DATA.day_details||{}).forEach(d=>{
                    const f=d.flow||{};
                    (f.project_model||[]).forEach(x=>{
                      if(!state.models.has(x[2]))return;
                      proj[x[2]]=(proj[x[2]]||0)+(x[3]||0);
                    });
                    (f.model_session||[]).forEach(x=>{
                      if(!state.models.has(x[0]))return;
                      sess[x[0]]=(sess[x[0]]||0)+(x[3]||0);
                    });
                  });
                  const chips={};
                  document.querySelectorAll('#flow-map .dest-chip[data-dest-model]')
                    .forEach(c=>{
                      const m=c.getAttribute('data-dest-model');
                      if(m)chips[m]=Number(c.getAttribute('data-signal-value'));
                    });
                  return {proj,sess,chips,totals:destinationData().modelTotals};
                }
            """)
            self.assertTrue(measured["chips"])
            for model, value in measured["chips"].items():
                proj = measured["proj"].get(model, 0)
                sess = measured["sess"].get(model, 0)
                self.assertNotEqual(0, value)
                # chip Signal value equals ONE projection, never the sum (2x)
                self.assertEqual(max(proj, sess), value)
                self.assertEqual(measured["totals"][model], value)
                if proj and sess:
                    self.assertNotEqual(proj + sess, value)
            model, value = next(iter(measured["chips"].items()))
            with page.expect_download() as download_info:
                page.locator("#flow-save").click()
            svg = Path(download_info.value.path()).read_text(encoding="utf-8")
            self.assertIn("{:,}".format(value), svg)
            self.assertEqual([], page_errors)
            self.assertEqual([], console_errors)
        finally:
            context.close()

    def test_destinations_session_cards_show_short_secondary_id(self):
        context, page, page_errors, console_errors = self.new_page(
            path=self._volume_path
        )
        try:
            self.wait_for_flow(page)
            data = page.evaluate("""
                () => {
                  const card=document.querySelector('#flow-map .dest-session');
                  const open=card.querySelector('.dest-card-open');
                  const sid=card.querySelector('.dest-sid');
                  const replay=card.querySelector('.dest-replay');
                  return {
                    sidText:sid.textContent,
                    sidTitle:sid.getAttribute('title'),
                    signalId:open.getAttribute('data-signal-id'),
                    replayId:replay.getAttribute('data-dest-replay'),
                    aliasShort:shortSid('Session-ABCDEFGHIJ'),
                    aliasProject:shortSid('Project-ABCDEFGHIJ'),
                    longId:shortSid('abcdefghijklmnopqrstuvwxyz'),
                  };
                }
            """)
            # anonymous aliases stay verbatim (never truncated)
            self.assertEqual("Session-ABCDEFGHIJ", data["aliasShort"])
            self.assertEqual("Project-ABCDEFGHIJ", data["aliasProject"])
            # real opaque ids truncated to first 10 chars + ellipsis
            self.assertEqual("abcdefghij\u2026", data["longId"])
            # card secondary id is the SHORT form, full id only as tooltip
            self.assertTrue(data["sidTitle"])
            self.assertNotEqual(data["sidTitle"], data["sidText"])
            self.assertEqual(data["sidTitle"][:10] + "\u2026", data["sidText"])
            # identity for signal + replay keeps the FULL sid
            self.assertEqual(data["sidTitle"], data["signalId"])
            self.assertEqual(data["sidTitle"], data["replayId"])
            self.assertEqual([], page_errors)
            self.assertEqual([], console_errors)
        finally:
            context.close()

    def test_destinations_legacy_payload_hides_missing_context_fields(self):
        context, page, page_errors, console_errors = self.new_page(
            path=self._volume_path
        )
        try:
            self.wait_for_flow(page)
            legacy = page.evaluate("""
                () => {
                  delete DATA.session_context;
                  renderFlow();
                  const card=document.querySelector('#flow-map .dest-session');
                  return {
                    sessions:document.querySelectorAll('#flow-map .dest-session').length,
                    meta:card.querySelector('.dest-meta').textContent.trim(),
                    title:card.querySelector('.dest-session-title').textContent,
                  };
                }
            """)
            self.assertGreater(legacy["sessions"], 0)
            self.assertTrue(legacy["meta"])
            self.assertEqual("未命名会话", legacy["title"])
            self.assertEqual([], page_errors)
            self.assertEqual([], console_errors)
        finally:
            context.close()

    def test_destinations_mobile_no_horizontal_overflow_all_locales(self):
        for width in (375, 390):
            for scheme in ("light", "dark"):
                for language in ("zh", "en"):
                    with self.subTest(width=width, scheme=scheme, language=language):
                        context, page, page_errors, console_errors = self.new_page(
                            viewport={"width": width, "height": 760},
                            color_scheme=scheme,
                            path=self._volume_path,
                        )
                        try:
                            self.wait_for_flow(page)
                            page.evaluate(
                                "lang => applyLanguage(lang,false)", language
                            )
                            overflow = page.evaluate("""
                                () => {
                                  const h = sel => {
                                    const el = document.querySelector('#flow-map ' + sel);
                                    return el ? Math.round(el.getBoundingClientRect().height) : null;
                                  };
                                  return {
                                    scroll:document.documentElement.scrollWidth,
                                    client:document.documentElement.clientWidth,
                                    sessions:document.querySelectorAll('#flow-map .dest-session').length,
                                    replay:h('.dest-replay'),
                                    chip:h('.dest-chip'),
                                    trail:h('.dest-trail'),
                                    viewswitch:h('.dest-viewswitch button'),
                                    pager:h('.dest-pager button'),
                                  };
                                }
                            """)
                            self.assertLessEqual(
                                overflow["scroll"], overflow["client"] + 1
                            )
                            self.assertGreater(overflow["sessions"], 0)
                            for name in ("replay", "chip", "trail", "viewswitch", "pager"):
                                self.assertIsNotNone(
                                    overflow[name], f"{name} button missing on mobile"
                                )
                                self.assertGreaterEqual(
                                    overflow[name], 44,
                                    f"{name} touch target below 44px: {overflow[name]}",
                                )
                            self.assertEqual([], page_errors)
                            self.assertEqual([], console_errors)
                        finally:
                            context.close()

    def test_destinations_svg_export_reports_theme_and_page(self):
        for scheme, expected in (("light", "#ffffff"), ("dark", "#0f1524")):
            with self.subTest(scheme=scheme):
                context, page, page_errors, console_errors = self.new_page(
                    color_scheme=scheme, path=self._volume_path
                )
                try:
                    self.wait_for_flow(page)
                    page.evaluate(
                        "theme => { applyTheme(theme); applyLanguage('en',false); renderLazy('flow',true); }",
                        scheme,
                    )
                    with page.expect_download() as download_info:
                        page.locator("#flow-save").click()
                    download = download_info.value
                    svg = Path(download.path()).read_text(encoding="utf-8")
                    self.assertIn("<svg", svg)
                    self.assertIn(expected, svg)
                    self.assertIn("Current page sessions", svg)
                    self.assertIn("page 1 /", svg)
                    self.assertIn("not all sessions", svg)
                    self.assertIn("Untitled session", svg)
                    self.assertNotIn("\u672a\u547d\u540d\u4f1a\u8bdd", svg)
                    self.assertEqual([], page_errors)
                    self.assertEqual([], console_errors)
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
            mobile = page.evaluate("""
                () => {
                  const grid=document.getElementById('flow-map');
                  return {
                    pageWidth:document.documentElement.scrollWidth,
                    viewportWidth:document.documentElement.clientWidth,
                    gridWidth:grid.getBoundingClientRect().width,
                    gridColumns:getComputedStyle(grid).gridTemplateColumns.split(' ').length,
                    gridScroll:grid.scrollWidth,
                    gridClient:grid.clientWidth,
                    sessions:grid.querySelectorAll('.dest-session').length,
                  };
                }
            """)
            self.assertLessEqual(mobile["pageWidth"], mobile["viewportWidth"] + 1)
            self.assertEqual(1, mobile["gridColumns"])
            self.assertLessEqual(mobile["gridScroll"], mobile["gridClient"] + 1)
            self.assertLessEqual(mobile["gridWidth"], mobile["viewportWidth"] + 1)
            self.assertGreater(mobile["sessions"], 0)
            # Session cards stay reachable by keyboard instead of hover-only.
            page.locator("#flow-map .dest-card-open").first.focus()
            page.keyboard.press("Enter")
            self.assertEqual(
                "session", page.evaluate("effectiveSignal() && effectiveSignal().type")
            )
            self.assertNotEqual(
                "hidden",
                page.locator("#flow-map .dest-session").first.evaluate(
                    "element => getComputedStyle(element).visibility"
                ),
            )
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

    def test_achievement_preview_pagination_and_secret_privacy(self):
        context, page, page_errors, console_errors = self.new_page()
        try:
            page.locator('#section-dock button[data-target="section-achievements"]').click()
            preview = page.locator('#ach-preview .badge.on')
            self.assertGreater(preview.count(), 0)
            preview.first.click()
            self.assertTrue(page.locator('#ach-modal').evaluate("el => el.classList.contains('open')"))
            self.assertNotEqual('', page.locator('#ach-detail .ach-story').inner_text())
            self.assertIn('达成条件：', page.locator('#ach-detail .ach-condition').inner_text())
            page.keyboard.press('Escape')
            page.wait_for_function("!document.getElementById('ach-modal').classList.contains('open')")
            self.assertTrue(preview.first.evaluate('el => document.activeElement === el'))

            page.locator('#ach-view-earned').click()
            total = page.evaluate('getBadgeData().got')
            self.assertGreater(total, 24)
            self.assertEqual(24, page.locator('#ach-earned-grid .badge.on').count())
            self.assertEqual(0, page.locator('#ach-body .badge').count())
            while page.locator('#ach-earned-more').is_visible():
                page.locator('#ach-earned-more').click()
            self.assertEqual(total, page.locator('#ach-earned-grid .badge.on').count())
            self.assertLess(page.locator('#ach-earned-grid .badge.on').count(), page.evaluate('getBadgeData().all.length'))
            self.assertIn(str(total), page.locator('#ach-earned-count').inner_text())
            page.locator('#ach-earned-grid .badge.on').last.click()
            self.assertNotEqual('', page.locator('#ach-detail .ach-story').inner_text())
            self.assertIn('达成条件：', page.locator('#ach-detail .ach-condition').inner_text())
            page.locator('#ach-filter').select_option('secret')
            self.assertTrue(page.locator('#ach-earned').is_hidden())
            masked = page.locator('#ach-body .badge.secret[disabled]')
            self.assertGreater(masked.count(), 0)
            self.assertTrue(all('???' in text and '隐藏' in text for text in masked.all_inner_texts()))
            self.assertEqual({'隐藏成就，达成自动揭晓'}, set(masked.evaluate_all('els => els.map(el => el.getAttribute("aria-label"))')))
            secret = page.evaluate("getBadgeData().all.find(b => b.secret && !b.ok && b.n.length > 3).n")
            page.locator('#ach-search').fill(secret)
            self.assertEqual(0, page.locator('#ach-body .badge.secret[disabled]').count())
            page.locator('#ach-search').fill('')
            page.keyboard.press('Escape')
            page.wait_for_function("!document.getElementById('ach-modal').classList.contains('open')")
            page.locator('#ach-view-earned').click()
            self.assertFalse(page.locator('#ach-earned').is_hidden())
            self.assertEqual('all', page.locator('#ach-filter').input_value())
            self.assertEqual('', page.locator('#ach-search').input_value())
            self.assertEqual(total, page.locator('#ach-earned-grid .badge.on').count())
            page.evaluate("""() => {
              const all=_ach.all.map(b=>({...b,ok:false}));
              _ach={..._ach,all,got:0,cats:_ach.cats.map(c=>({...c,items:c.items.map(b=>({...b,ok:false}))}))};
              renderAchievements('');
            }""")
            self.assertIn('当前报告没有已解锁成就', page.locator('#ach-earned-grid').inner_text())
            self.assertEqual(0, page.locator('#ach-earned-grid .badge').count())
            self.assertTrue(page.locator('#ach-earned-more').is_hidden())
            self.assertEqual([], page_errors)
            self.assertEqual([], console_errors)
        finally:
            context.close()

    def test_achievement_archive_language_switch_updates_badges_and_details(self):
        context, page, page_errors, console_errors = self.new_page()
        try:
            page.evaluate("applyLanguage('en',false)")
            page.locator('#ach-view-earned').scroll_into_view_if_needed()
            page.locator('#ach-view-earned').click()
            badge = page.locator('#ach-earned-grid .badge.on').first
            self.assertFalse(badge.evaluate('el => /[㐀-鿿]/.test(el.innerText + el.getAttribute("aria-label"))'))
            badge.click()
            self.assertIn('Unlock condition:', page.locator('#ach-detail').inner_text())
            self.assertFalse(page.locator('#ach-detail').evaluate('el => /[㐀-鿿]/.test(el.innerText)'))
            page.evaluate("applyLanguage('zh',false)")
            self.assertIn('达成条件：', page.locator('#ach-detail').inner_text())
            self.assertIn('已解锁', page.locator('#ach-earned-grid .badge.on').first.get_attribute('aria-label'))
            self.assertEqual([], page_errors)
            self.assertEqual([], console_errors)
        finally:
            context.close()

    def test_achievement_archive_rendered_before_first_scroll(self):
        for width in (1280, 390, 320):
            context, page, page_errors, console_errors = self.new_page(
                viewport={"width": width, "height": 820}, freeze_lazy=True,
            )
            try:
                result = page.evaluate("""() => {
                  const card=document.getElementById('section-achievements');
                  const next=document.getElementById('section-project');
                  const before=next.getBoundingClientRect().y;
                  const ready=lazyState.badges.status==='ready' &&
                    !card.classList.contains('lazy-pending');
                  renderLazy('badges',true);
                  return {ready,shift:Math.abs(next.getBoundingClientRect().y-before),
                    preview:card.querySelectorAll('#ach-preview .badge.on').length};
                }""")
                self.assertTrue(result['ready'], result)
                self.assertGreater(result['preview'], 0)
                self.assertLess(result['shift'], 2, result)
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
                      const picker=project.querySelector('.project-picker');
                      return {
                        pageWidth:document.documentElement.scrollWidth,
                        viewportWidth:document.documentElement.clientWidth,
                        projectWidth:project.scrollWidth,
                        projectClientWidth:project.clientWidth,
                        pickerRight:picker.getBoundingClientRect().right,
                        selectRight:picker.querySelector('select').getBoundingClientRect().right,
                        minControlHeight:Math.min(...controls.map(el=>el.getBoundingClientRect().height)),
                        sheetWidth:document.querySelector('#ach-modal .ach-sheet').getBoundingClientRect().width,
                        deltaRight:delta.right,
                      };
                    }
                    """
                )
                self.assertGreaterEqual(metrics["minControlHeight"], 43.9)
                self.assertLessEqual(metrics["selectRight"], metrics["pickerRight"] + 1, metrics)
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
        context, page, page_errors, console_errors = self.new_page(freeze_lazy=True)
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

    def test_other_names_are_visible_beside_filters_and_follow_period(self):
        context, page, page_errors, console_errors = self.new_page(path=self._visible_other_path)
        try:
            summary = page.locator("#other-model-summary")
            self.assertTrue(summary.is_visible())
            self.assertIn("glm-5.3-flash", summary.inner_text())
            self.assertIn("20 Token", summary.inner_text())
            self.assertIn("共用 Other 颜色和筛选", summary.inner_text())
            self.assertEqual(0, summary.locator("details, button, input, img").count())
            self.assertIsNone(page.evaluate("window.__otherXss"))
            self.assertIn("未识别的剩余量", summary.inner_text())
            page.locator('#donut-legend [data-model-toggle="other"]').click()
            self.assertIn("Other 分组未选中", summary.inner_text())
            self.assertIn("20 Token", summary.inner_text())
            page.evaluate("() => { state.focusPeriod='2026-01-01'; renderDataViews(); }")
            self.assertIn("13 Token", summary.inner_text())
            self.assertNotIn("20 Token", summary.inner_text())
            page.evaluate("() => { state.focusPeriod='2026-02-01'; renderDataViews(); }")
            self.assertIn("7 Token", summary.inner_text())
            self.assertNotIn("13 Token", summary.inner_text())
            page.evaluate("setGran('day')")
            page.evaluate("() => { state.focusPeriod='2026-01-07'; renderDataViews(); }")
            self.assertIn("13 Token", summary.inner_text())
            page.evaluate("setGran('week')")
            page.evaluate("() => { state.focusPeriod='2026-01-05'; renderDataViews(); }")
            self.assertIn("13 Token", summary.inner_text())
            page.evaluate("applyLanguage('en', false)")
            self.assertIn("share the Other color and filter", summary.inner_text())
            self.assertIn("Other group is not selected", summary.inner_text())
            page.evaluate("applyLanguage('zh', false)")
            self.assertIn("共用 Other 颜色和筛选", summary.inner_text())
            page.evaluate("() => { DATA.other_models=[]; renderDataViews(); }")
            self.assertNotIn("glm-5.3-flash", summary.inner_text())
            self.assertIn("暂无可展示的具体模型名", summary.inner_text())
            self.assertEqual([], page_errors)
            self.assertEqual([], console_errors)
        finally:
            context.close()

    def test_other_summary_mobile_themes_and_no_other(self):
        for width in (320, 390):
            context, page, page_errors, console_errors = self.new_page(
                path=self._visible_other_path, viewport={"width": width, "height": 760}
            )
            try:
                for theme in ("light", "dark"):
                    page.evaluate("theme => applyTheme(theme)", theme)
                    page.evaluate("applyLanguage('en', false)")
                    summary = page.locator("#other-model-summary")
                    self.assertIn("glm-5.3-flash", summary.inner_text())
                    self.assertIn("older-<img", summary.inner_text())
                    self.assertEqual(0, summary.locator("img").count())
                    self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"), width + 1)
                self.assertEqual([], page_errors)
                self.assertEqual([], console_errors)
            finally:
                context.close()
        context, page, page_errors, console_errors = self.new_page()
        try:
            self.assertFalse(page.locator("#other-model-summary").is_visible())
            self.assertEqual([], page_errors)
            self.assertEqual([], console_errors)
        finally:
            context.close()

    def test_other_model_names_match_windows_and_escape_html(self):
        context, page, page_errors, console_errors = self.new_page(path=self._overflow_path)
        name = "older-<img src=x onerror=window.__otherXss=1>"
        try:
            self.assertEqual(0, page.locator("#donut-legend img, #delta-list img").count())
            self.assertIsNone(page.evaluate("window.__otherXss"))
            page.locator("#donut-legend .other-model-details summary").click()
            self.assertGreaterEqual(
                page.locator("#donut-legend .other-model-details summary").evaluate(
                    "el => el.getBoundingClientRect().height"
                ),
                44,
            )
            self.assertIn(name, page.locator("#donut-legend .other-model-details").inner_text())
            self.assertIn("70 Token", page.locator("#donut-legend .other-model-details").inner_text())
            page.evaluate("setGran('month')")
            details = page.locator("#delta-list .delta-other-details")
            self.assertEqual(
                ["listitem"] * page.locator("#delta-list > *").count(),
                page.locator("#delta-list > *").evaluate_all(
                    "items => items.map(item => item.getAttribute('role'))"
                ),
            )
            self.assertGreaterEqual(
                details.locator("summary").evaluate("el => el.getBoundingClientRect().height"),
                44,
            )
            details.locator("summary").click()
            row = details.locator("tbody tr", has=page.locator("th", has_text=name))
            self.assertEqual(["60", "10", "-50"], row.locator("td").all_inner_texts())
            remainder = details.locator("tbody tr", has_text="未识别的剩余量")
            self.assertEqual(["5", "5", "0"], remainder.locator("td").all_inner_texts())
            self.assertEqual(0, details.locator("button[data-delta-model]").count())
            self.assertIsNone(page.evaluate("window.__otherXss"))
            page.locator("#donut-legend .other-model-details summary").click()
            self.assertIn(name, page.locator("#donut-legend .other-model-details").text_content())
            self.assertEqual([], page_errors)
            self.assertEqual([], console_errors)
        finally:
            context.close()

    def test_other_details_follow_filter_and_degrade_without_names(self):
        context, page, page_errors, console_errors = self.new_page(path=self._overflow_path)
        try:
            page.evaluate("setGran('month')")
            page.locator('#donut-legend [data-model-toggle="other"]').click()
            self.assertIn("70 Token", page.locator("#donut-legend .other-model-details").text_content())
            self.assertEqual(0, page.locator("#delta-list .delta-other-details").count())
            page.locator('#donut-legend [data-model-toggle="other"]').click()
            page.evaluate("() => { DATA.other_models = []; renderDonut(); renderAttribution(); }")
            self.assertIn("暂无可展示的具体模型名", page.locator("#donut-legend").inner_text())
            self.assertEqual(0, page.locator("#delta-list .delta-other-details").count())
            page.evaluate("applyLanguage('en', false)")
            page.evaluate("renderDonut()")
            self.assertIn("Specific names are unavailable", page.locator("#donut-legend").inner_text())
            self.assertEqual([], page_errors)
            self.assertEqual([], console_errors)
        finally:
            context.close()

    def test_other_details_mobile_and_english(self):
        for width in (320, 390):
            context, page, page_errors, console_errors = self.new_page(
                path=self._overflow_path, viewport={"width": width, "height": 760}
            )
            try:
                page.evaluate("applyLanguage('en', false)")
                page.locator("#donut-legend .other-model-details summary").click()
                page.locator("#delta-list .delta-other-details summary").click()
                self.assertIn("Models within Other", page.locator("#delta-list").inner_text())
                self.assertIn("Unidentified remainder", page.locator("#delta-list").inner_text())
                self.assertEqual(0, page.locator("#delta-list img, #donut-legend img").count())
                metrics = page.evaluate("""() => ({page:document.documentElement.scrollWidth,
                    viewport:document.documentElement.clientWidth})""")
                self.assertLessEqual(metrics["page"], metrics["viewport"] + 1)
                self.assertEqual([], page_errors)
                self.assertEqual([], console_errors)
            finally:
                context.close()

    def test_card_tilt_removed_and_theme_refreshes_inline_model_colors(self):
        context, page, page_errors, console_errors = self.new_page(path=self._overflow_path)
        try:
            page.evaluate("setGran('month')")
            page.evaluate("applyMotion('full')")
            card = page.locator("#section-delta")
            card.hover(position={"x": 22, "y": 22})
            page.wait_for_timeout(80)
            self.assertEqual("", card.evaluate("el => el.style.transform"))
            page.locator("#delta-list button[data-delta-model]").first.click()
            self.assertFalse(page.locator("#delta-evidence").is_hidden())
            before = page.locator("#delta-list .delta-name i").first.evaluate("el => el.style.background")
            page.evaluate("applyTheme('dark')")
            after = page.locator("#delta-list .delta-name i").first.evaluate("el => el.style.background")
            self.assertNotEqual(before, after)
            self.assertFalse(page.locator("#delta-evidence").is_hidden())
            self.assertEqual([], page_errors)
            self.assertEqual([], console_errors)
        finally:
            context.close()


    def test_url_theme_first_frame_and_saved_preference(self):
        html = self._path.read_text(encoding="utf-8")
        marker = "</head>"
        self.assertEqual(1, html.count(marker))
        probe = Path(self._tmp.name) / "synthetic-dashboard-theme-probe.html"
        probe.write_text(
            html.replace(marker, "<script>window.__preTheme=document.documentElement.getAttribute('data-theme')</script>" + marker),
            encoding="utf-8",
        )
        for query, saved, scheme, expected in (
            ("dark", "light", "light", "dark"),
            ("light", "dark", "dark", "light"),
            ("auto", "dark", "light", "light"),
            ("auto", "light", "dark", "dark"),
        ):
            context = self._browser.new_context(color_scheme=scheme)
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.add_init_script(f"localStorage.setItem('tk-theme', '{saved}')")
            try:
                page.goto(probe.as_uri() + "?t=" + query, wait_until="load")
                actual = page.evaluate("""() => ({first:window.__preTheme,
                    selected:currentTheme(),effective:effectiveTheme(),saved:localStorage.getItem('tk-theme'),
                    query:new URLSearchParams(location.search).get('t')})""")
                self.assertEqual(None if query == "auto" else query, actual["first"])
                self.assertEqual(query, actual["selected"])
                self.assertEqual(expected, actual["effective"])
                self.assertEqual(saved, actual["saved"])
                self.assertEqual(query, actual["query"])
                self.assertEqual([], errors)
                if query == "auto" and scheme == "light":
                    page.locator("#theme-btn").click()
                    self.assertEqual("light", page.evaluate("currentTheme()"))
                    self.assertEqual("light", page.evaluate("localStorage.getItem('tk-theme')"))
            finally:
                context.close()

    def test_other_zero_net_change_keeps_model_churn_visible(self):
        context, page, page_errors, console_errors = self.new_page(path=self._overflow_path)
        try:
            page.evaluate("""() => {
              const older='older-<img src=x onerror=window.__otherXss=1>';
              DATA.other_models.push({day:'2026-02-04',models:{[older]:50}});
              DATA.month.find(row=>row.period==='2026-02-01').models.other+=50;
              DATA.month.find(row=>row.period==='2026-02-01').total+=50;
              DATA.day.find(row=>row.period==='2026-02-04').models.other+=50;
              DATA.day.find(row=>row.period==='2026-02-04').total+=50;
              invalidateDerived();renderAttribution();
            }""")
            self.assertEqual(0, page.locator('#delta-list [data-delta-model="other"]').count())
            details = page.locator("#delta-list .delta-other-details")
            self.assertEqual(1, details.count())
            details.locator("summary").click()
            self.assertIn("older-<img", details.inner_text())
            self.assertEqual([], page_errors)
            self.assertEqual([], console_errors)
        finally:
            context.close()

    def test_other_change_has_no_misleading_project_evidence_button(self):
        context, page, page_errors, console_errors = self.new_page(path=self._overflow_path)
        try:
            page.evaluate("""() => {
              DATA.month.find(row=>row.period==='2026-02-01').models.other+=60;
              DATA.month.find(row=>row.period==='2026-02-01').total+=60;
              DATA.day.find(row=>row.period==='2026-02-04').models.other+=60;
              DATA.day.find(row=>row.period==='2026-02-04').total+=60;
              DATA.other_models.push({day:'2026-02-04',models:{'older-<img src=x onerror=window.__otherXss=1>':60}});
              invalidateDerived();renderAttribution();
            }""")
            self.assertEqual(0, page.locator('#delta-list button[data-delta-model="other"]').count())
            other_row = page.locator("#delta-list .delta-row", has=page.locator(".delta-name", has_text="Other"))
            self.assertEqual(1, other_row.count())
            self.assertIn("+10", other_row.inner_text())
            self.assertEqual(1, page.locator("#delta-list .delta-other-details").count())
            page.evaluate("() => {deltaEvidenceState.model='other';renderAttribution();}")
            self.assertTrue(page.locator("#delta-evidence").is_hidden())
            self.assertIsNone(page.evaluate("deltaEvidenceState.model"))
            self.assertEqual([], page_errors)
            self.assertEqual([], console_errors)
        finally:
            context.close()

    def test_untimed_overflow_matches_open_window_without_negative_remainder(self):
        context, page, page_errors, console_errors = self.new_page(
            path=self._untimed_overflow_path
        )
        try:
            page.evaluate("setGran('month')")
            details = page.locator("#delta-list .delta-other-details")
            self.assertEqual(1, details.count())
            details.locator("summary").click()
            rows = details.locator("tbody tr")
            self.assertGreaterEqual(rows.count(), 1)
            for row in rows.all():
                for cell in row.locator("td").all_inner_texts()[:2]:
                    self.assertGreaterEqual(int(cell.replace(",", "")), 0)
            self.assertEqual("65", page.evaluate("""() => {
              const result=attributionFor(selectedRows());
              return String(result.parts.find(part=>part.model==='other').curr);
            }"""))
            self.assertIn("60", details.inner_text())
            self.assertEqual([], page_errors)
            self.assertEqual([], console_errors)
        finally:
            context.close()

    def test_sol_variants_are_independently_selectable(self):
        context, page, page_errors, console_errors = self.new_page(path=self._sol_path)
        try:
            legend = page.locator("#donut-legend")
            legend_text = legend.inner_text()
            # Both Sol generations show up as literal, distinct identities.
            self.assertIn("gpt-6-sol", legend_text)
            self.assertIn("gpt-6.1-sol", legend_text)
            old_toggle = legend.locator('[data-model-toggle="gpt-6-sol"]')
            new_toggle = legend.locator('[data-model-toggle="gpt-6.1-sol"]')
            self.assertEqual(1, old_toggle.count())
            self.assertEqual(1, new_toggle.count())
            # Distinct legend swatches prove the two are never merged.
            self.assertNotEqual(
                old_toggle.locator(".ldot").get_attribute("style"),
                new_toggle.locator(".ldot").get_attribute("style"),
            )
            # The newer backend is selectable on its own and stays visible.
            self.assertEqual("true", new_toggle.get_attribute("aria-pressed"))
            new_toggle.click()
            self.assertEqual("false", new_toggle.get_attribute("aria-pressed"))
            self.assertIn("gpt-6.1-sol", page.locator("#donut-legend").inner_text())
            new_toggle.click()
            self.assertEqual("true", new_toggle.get_attribute("aria-pressed"))
            # The command palette lists both as literal, independently runnable rows.
            page.evaluate("openPalette()")
            palette_text = page.locator("#palette-list").inner_text()
            self.assertIn("gpt-6-sol", palette_text)
            self.assertIn("gpt-6.1-sol", palette_text)
            page.evaluate("closePalette()")
            self.assertEqual([], page_errors)
            self.assertEqual([], console_errors)
        finally:
            context.close()

    def test_long_backend_name_wraps_without_horizontal_overflow(self):
        context, page, page_errors, console_errors = self.new_page(
            path=self._sol_path, viewport={"width": 390, "height": 760}
        )
        try:
            name = self._long_backend_name
            selector = f'#donut-legend [data-model-toggle="{name}"]'
            toggle = page.locator(selector)
            self.assertEqual(1, toggle.count())
            # The whole identity survives in the DOM text: nothing is hidden or
            # merged into Other just because the label is long.
            self.assertIn(name, toggle.inner_text())
            metrics = page.evaluate(
                """
                name => {
                  const button = [...document.querySelectorAll('#donut-legend [data-model-toggle]')]
                    .find(node => node.dataset.modelToggle === name);
                  const span = button.querySelector('span:not(.ldot)');
                  const em = button.querySelector('em');
                  const legend = document.querySelector('#donut-legend');
                  const doc = document.documentElement;
                  return {
                    docScroll: doc.scrollWidth, docClient: doc.clientWidth,
                    legendScroll: legend.scrollWidth, legendClient: legend.clientWidth,
                    buttonRight: button.getBoundingClientRect().right,
                    spanRight: span.getBoundingClientRect().right,
                    emRight: em.getBoundingClientRect().right,
                    spanScroll: span.scrollWidth, spanClient: span.clientWidth,
                  };
                }
                """,
                name,
            )
            # The name wraps onto extra lines inside the button instead of
            # spilling past its right edge (that spill is what widened the page).
            self.assertLessEqual(metrics["spanRight"], metrics["buttonRight"] + 1)
            self.assertLessEqual(metrics["emRight"], metrics["buttonRight"] + 1)
            # Wrapping, not clipping: the full label is laid out, no ellipsis cut.
            self.assertLessEqual(metrics["spanScroll"], metrics["spanClient"] + 1)
            # Neither the legend nor the document scrolls sideways at 390px.
            self.assertLessEqual(metrics["legendScroll"], metrics["legendClient"] + 1)
            self.assertLessEqual(metrics["docScroll"], metrics["docClient"] + 1)
            # The long-named model still filters on its own and keeps its seat.
            self.assertEqual("true", toggle.get_attribute("aria-pressed"))
            toggle.click()
            self.assertEqual("false", toggle.get_attribute("aria-pressed"))
            self.assertIn(name, page.locator("#donut-legend").inner_text())
            self.assertIn("gpt-6.1-sol", page.locator("#donut-legend").inner_text())
            toggle.click()
            self.assertEqual("true", toggle.get_attribute("aria-pressed"))
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
                mode_ratio = page.evaluate(
                    """() => {
                      const rgb = value => value.match(/[\\d.]+/g).slice(0, 3).map(Number);
                      const linear = channel => channel <= .04045
                        ? channel / 12.92 : Math.pow((channel + .055) / 1.055, 2.4);
                      const lum = color => rgb(color).reduce((sum, channel, index) =>
                        sum + linear(channel > 1 ? channel / 255 : channel) * [.2126,.7152,.0722][index], 0);
                      const ratio = (first, second) => {
                        const a = lum(first), b = lum(second);
                        return (Math.max(a, b) + .05) / (Math.min(a, b) + .05);
                      };
                      const scope = getComputedStyle(document.querySelector('.mode-scope'));
                      const selected = getComputedStyle(document.querySelector('.tabs button.on'));
                      const logo = getComputedStyle(document.querySelector('.logo'));
                      return {
                        scope:ratio(scope.color, scope.backgroundColor),
                        tab:ratio(selected.color, selected.backgroundColor),
                        logo:ratio(logo.color, logo.backgroundColor),
                      };
                    }"""
                )
                for name, contrast in mode_ratio.items():
                    self.assertGreaterEqual(contrast, 4.5, f"{name} contrast in {theme} theme")
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

    def test_delta_evidence_exact_windows_keyboard_navigation_and_privacy(self):
        context, page, page_errors, console_errors = self.new_page(
            path=self.interval_url()
        )
        try:
            page.locator("#interval-btn").click()
            for period in ("2026-02-01", "2026-03-01", "2026-04-01"):
                self.click_bar(page, period)
            before = page.evaluate("viewParams().toString()")
            button = page.locator('#delta-list button[data-delta-model="model-a"]')
            button.focus()
            page.keyboard.press("Enter")
            self.assertEqual("true", button.get_attribute("aria-expanded"))
            self.assertEqual(before, page.evaluate("viewParams().toString()"))
            self.assertEqual(None, page.evaluate("state.focusPeriod"))
            self.assertEqual(
                [["2026-02-01", "2026-03-01"], ["2026-04-01", "2026-05-01"]],
                page.evaluate(
                    """() => [
                      deltaEvidenceState.scope && attributionScope(intervalResult()).a.map(x => x.period),
                      attributionScope(intervalResult()).b.map(x => x.period)
                    ]"""
                ),
            )
            windows = page.locator(".delta-evidence-window")
            self.assertEqual(2, windows.count())
            self.assertIn("900 Token", windows.nth(0).inner_text())
            self.assertIn("350 Token", windows.nth(1).inner_text())
            self.assertIn("2026-02-01 → 2026-03-31", windows.nth(0).inner_text())
            self.assertEqual(2, windows.nth(0).locator("[data-delta-period]").count())
            self.assertEqual(2, windows.nth(1).locator("[data-delta-period]").count())
            self.assertIn("interval-fixture", windows.nth(0).inner_text())
            self.assertIn("不能证明项目导致了模型变化", page.inner_text("#delta-evidence"))
            self.assertNotIn("/synthetic/interval-fixture", before)
            self.assertFalse(page.evaluate("Object.keys(localStorage).some(k => k.includes('delta'))"))
            page.locator("#delta-evidence").locator("[data-delta-period='2026-03-01']").click()
            self.assertEqual("2026-03-01", page.evaluate("state.focusPeriod"))
            page.evaluate("renderAttribution()")
            self.assertEqual("2026-03-01", page.evaluate("state.focusPeriod"))
            self.assertEqual([], page_errors)
            self.assertEqual([], console_errors)
        finally:
            context.close()

    def test_delta_evidence_partial_missing_english_escape_and_project_lens(self):
        context, page, page_errors, console_errors = self.new_page(
            path=self.interval_url()
        )
        try:
            page.evaluate("applyLanguage('en',false)")
            page.locator("#interval-btn").click()
            for period in ("2026-02-01", "2026-03-01", "2026-04-01"):
                self.click_bar(page, period)
            page.evaluate(
                """() => {
                  const march = DATA.day_details['2026-03-05'];
                  delete march.cwds;
                  march.top_cwds = [];
                  const april = DATA.day_details['2026-04-07'];
                  delete april.cwds;
                  delete april.top_cwds;
                }"""
            )
            button = page.locator('#delta-list button[data-delta-model="model-a"]')
            button.focus()
            page.keyboard.press("Space")
            self.assertEqual("true", button.get_attribute("aria-expanded"))
            self.assertIn("Some dates retain only top projects", page.inner_text("#delta-evidence"))
            self.assertIn("Some dates lack project details", page.inner_text("#delta-evidence"))
            self.assertIn("cannot be broken down by project", page.inner_text("#delta-evidence"))
            page.evaluate("delete DATA.day_details['2026-04-07']")
            page.evaluate("renderDeltaEvidence(attributionScope(intervalResult()),intervalResult().parts)")
            self.assertTrue(page.evaluate("deltaEvidenceWindow('model-a',['2026-04-07'],100).missing"))
            self.assertIn("Some dates lack project details", page.inner_text("#delta-evidence"))
            self.assertEqual("true", page.locator("#interval-btn").get_attribute("aria-pressed"))
            untranslated = page.evaluate(
                """() => {
                  const root = document.getElementById('section-delta'), out = [];
                  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
                  while (walker.nextNode()) if (walker.currentNode.parentElement?.getClientRects().length &&
                    /[㐀-鿿]/.test(walker.currentNode.nodeValue)) out.push(walker.currentNode.nodeValue.trim());
                  for (const el of root.querySelectorAll('[aria-label],[title]'))
                    for (const name of ['aria-label','title']) if (/[㐀-鿿]/.test(el.getAttribute(name)||''))
                      out.push(el.getAttribute(name));
                  return out;
                }"""
            )
            self.assertEqual([], untranslated)
            page.keyboard.press("Escape")
            self.assertTrue(page.locator("#delta-evidence").is_hidden())
            self.assertEqual("false", button.get_attribute("aria-expanded"))
            self.assertEqual("true", page.locator("#interval-btn").get_attribute("aria-pressed"))
            self.assertEqual("model-a", button.get_attribute("data-delta-model"))
            self.assertEqual([], page_errors)
            self.assertEqual([], console_errors)
        finally:
            context.close()

    def test_delta_evidence_project_navigation_preserves_global_filters(self):
        context, page, page_errors, console_errors = self.new_page(
            path=self.interval_url()
        )
        try:
            page.locator("#interval-btn").click()
            for period in ("2026-02-01", "2026-03-01", "2026-04-01"):
                self.click_bar(page, period)
            page.locator('#delta-list button[data-delta-model="model-a"]').click()
            previous = page.evaluate("[...state.models].sort()")
            page.locator("#delta-evidence [data-delta-project]").first.click()
            self.assertEqual(previous, page.evaluate("[...state.models].sort()"))
            self.assertEqual(None, page.evaluate("state.focusPeriod"))
            self.assertIn("interval-fixture", page.locator("#project-select").input_value())
            self.assertTrue(page.locator("#section-project").is_visible())
            self.assertEqual([], page_errors)
            self.assertEqual([], console_errors)
        finally:
            context.close()

    def test_delta_evidence_uses_open_period_elapsed_days(self):
        context, page, page_errors, console_errors = self.new_page(
            path=self.interval_url()
        )
        try:
            page.evaluate("""() => {
              DATA.generated = '2026-06-10T12:00:00';
              renderAttribution();
            }""")
            page.locator('#delta-list button[data-delta-model="model-b"]').click()
            evidence = page.evaluate("""() => {
              const scope = attributionScope(null);
              return {
                aDays:scope.aDays,
                bDays:scope.bDays,
                a:deltaEvidenceWindow('model-b',scope.aDays,200).total,
                b:deltaEvidenceWindow('model-b',scope.bDays,210).total,
              };
            }""")
            self.assertEqual("2026-05-01", evidence["aDays"][0])
            self.assertEqual("2026-05-09", evidence["aDays"][-1])
            self.assertEqual("2026-06-01", evidence["bDays"][0])
            self.assertEqual("2026-06-09", evidence["bDays"][-1])
            self.assertEqual((200, 210), (evidence["a"], evidence["b"]))
            windows = page.locator(".delta-evidence-window")
            self.assertIn("2026-05-01 → 2026-05-09", windows.first.inner_text())
            self.assertIn("2026-06-01 → 2026-06-09", windows.last.inner_text())
            self.assertEqual([], page_errors)
            self.assertEqual([], console_errors)
        finally:
            context.close()

    def test_delta_evidence_mobile_geometry(self):
        for width in (320, 390):
            context, page, page_errors, console_errors = self.new_page(
                path=self.interval_url(), viewport={"width": width, "height": 800}
            )
            try:
                page.evaluate("""() => {
                  intervalState.active = true;
                  intervalState.start = '2026-02-01';
                  intervalState.end = '2026-03-01';
                  intervalState.bStart = '2026-04-01';
                  renderAttribution();
                }""")
                page.locator('#delta-list button[data-delta-model="model-a"]').click()
                self.assertTrue(page.locator("#delta-evidence").is_visible())
                self.assertEqual(
                    1,
                    page.evaluate(
                        "getComputedStyle(document.querySelector('.delta-evidence-grid')).gridTemplateColumns.split(' ').length"
                    ),
                )
                self.assertLessEqual(
                    page.evaluate("document.documentElement.scrollWidth"), width
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
