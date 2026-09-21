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
                "cwd": "/synthetic/project-a",
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
                "cwd": "/synthetic/project-a",
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

    def test_flow_is_visible_recovers_and_stays_inside_mobile_viewport(self):
        context = self._browser.new_context(
            viewport={"width": 1280, "height": 820},
            color_scheme="light",
            reduced_motion="no-preference",
        )
        page = context.new_page()
        page_errors = []
        console_errors = []
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        page.on(
            "console",
            lambda message: console_errors.append(message.text)
            if message.type == "error"
            else None,
        )
        page.goto(self._path.as_uri(), wait_until="load")
        flow = page.locator("#section-flow")
        flow.scroll_into_view_if_needed()
        page.wait_for_function(
            "document.querySelectorAll('#flow-map .flow-node').length > 0 && "
            "document.querySelectorAll('#flow-map .flow-link').length > 0"
        )

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
        self.assertEqual([], page_errors)
        self.assertEqual([], console_errors)

        for theme in ("light", "dark", "auto"):
            with self.subTest(theme=theme):
                page.evaluate("theme => { applyTheme(theme); renderLazy('flow',true); }", theme)
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

        retry_result = page.evaluate("""
            () => {
              const svg=document.getElementById('flow-map');
              window.__detachedFlowMap=svg;
              svg.remove();
              return renderLazy('flow',true);
            }
        """)
        self.assertFalse(retry_result)
        self.assertTrue(flow.locator(".lazy-error-state").is_visible())
        self.assertTrue(flow.locator("[data-lazy-retry]").is_visible())
        failed_state = page.evaluate("lazyState.flow")
        self.assertTrue(failed_state["dirty"])
        self.assertFalse(failed_state["rendered"])
        self.assertTrue(failed_state["error"])
        self.assertEqual("error", failed_state["status"])
        self.assertEqual([], page_errors)

        page.evaluate("""
            () => {
              const shell=document.querySelector('#section-flow .flow-shell');
              shell.insertBefore(
                window.__detachedFlowMap,
                document.getElementById('flow-panel')
              );
            }
        """)
        page.evaluate(
            "document.querySelector('[data-lazy-retry]').click()"
        )
        page.wait_for_function(
            "!document.querySelector('#section-flow .lazy-error-state') && "
            "document.querySelectorAll('#flow-map .flow-node').length > 0 && "
            "lazyState.flow.status === 'ready'"
        )
        self.assertFalse(flow.evaluate("element => element.classList.contains('lazy-error')"))

        page.set_viewport_size({"width": 390, "height": 760})
        flow.scroll_into_view_if_needed()
        mobile = page.evaluate("""
            () => {
              const shell=document.querySelector('#section-flow .flow-shell');
              const svg=document.getElementById('flow-map');
              return {
                pageWidth:document.documentElement.scrollWidth,
                viewportWidth:document.documentElement.clientWidth,
                shellClient:shell.clientWidth,
                shellScroll:shell.scrollWidth,
                svgWidth:svg.getBoundingClientRect().width,
                nodes:svg.querySelectorAll('.flow-node').length,
              };
            }
        """)
        self.assertLessEqual(mobile["pageWidth"], mobile["viewportWidth"] + 1)
        self.assertGreater(mobile["shellScroll"], mobile["shellClient"])
        self.assertGreater(mobile["svgWidth"], mobile["shellClient"])
        self.assertGreater(mobile["nodes"], 0)
        context.close()


if __name__ == "__main__":
    unittest.main()
