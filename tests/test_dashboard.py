import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]

import sys
sys.path.insert(0, str(ROOT))

import report_dashboard


class DashboardTests(unittest.TestCase):
    def synthetic_records(self):
        return [
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
                "session": "session-a",
                "cwd": "/tmp/project-a",
            },
            {
                "source": "claude",
                "ts": "2026-07-02T14:00:00+08:00",
                "date": "2026-07-02",
                "model": "model-b",
                "input": 120,
                "output": 60,
                "cache_read": 20,
                "cache_write": 0,
                "total": 200,
                "session": "session-b",
                "cwd": "/tmp/project-b",
            },
        ]

    def test_template_replaces_legacy_city_and_orbit_with_flow(self):
        template = report_dashboard._TEMPLATE
        for legacy in (
            "Token 城市", "Token City", "renderCity", "city-shell",
            "Token 轨道", "renderOrbit", "orbit-shell", ".orbit-",
            "data-module=orbit", "section-orbit",
        ):
            self.assertNotIn(legacy, template)
        self.assertIn("Token 流光图", template)
        self.assertIn("renderFlow", template)
        self.assertRegex(template, r"data-module=flow\b")
        self.assertIn("显示模块", template)
        self.assertRegex(template, r"data-mod=flow\b")

    @mock.patch("report_dashboard.readers.session_title", return_value="")
    @mock.patch("report_dashboard.readers.load_session_summaries", return_value={})
    def test_build_payload_has_flow_and_basic_fields(self, _summaries, _title):
        payload = report_dashboard.build_payload(
            self.synthetic_records(),
            since="2026-07-01",
            until="2026-07-02",
            sources=["claude"],
        )
        for key in (
            "generated", "source", "range", "models", "colors", "hourly",
            "day_details", "top_cwds", "top_sessions", "session_series",
            "flow", "day", "week", "month", "achievement_stats",
        ):
            self.assertIn(key, payload)
        self.assertEqual(["claude"], payload["source"])
        self.assertEqual(300, sum(row["total"] for row in payload["day"]))
        self.assertEqual(2, len(payload["top_cwds"]))
        self.assertEqual(2, len(payload["top_sessions"]))
        self.assertEqual({"model-a": 100}, payload["top_cwds"][1][3])
        self.assertEqual({"model-b": 200}, payload["top_sessions"][0][3])
        self.assertEqual({"session-a", "session-b"}, set(payload["session_series"]))
        self.assertEqual(
            {
                ("/tmp/project-a", "model-a", 100),
                ("/tmp/project-b", "model-b", 200),
            },
            {(row[1], row[2], row[3]) for row in payload["flow"]["project_model"]},
        )
        self.assertEqual(
            {
                ("model-a", "session-a", 100),
                ("model-b", "session-b", 200),
            },
            {(row[0], row[2], row[3]) for row in payload["flow"]["model_session"]},
        )
        self.assertIn("flow", payload["day_details"]["2026-07-01"])

    @mock.patch("report_dashboard.readers.session_title", return_value="")
    @mock.patch("report_dashboard.readers.load_session_summaries", return_value={})
    def test_session_series_covers_every_flow_session(self, _summaries, _title):
        records = []
        for i in range(9):
            records.append({
                "source": "claude", "ts": f"2026-07-01T0{i}:00:00+08:00",
                "date": "2026-07-01", "model": "model-a", "input": 0,
                "output": 0, "cache_read": 0, "cache_write": 0,
                "total": 1000 - i, "session": f"session-{i}", "cwd": "/tmp/main",
            })
        payload = report_dashboard.build_payload(records)
        flow_ids = {item[2] for item in payload["flow"]["model_session"]}
        self.assertEqual(flow_ids, set(payload["session_series"]))
        self.assertEqual([992], payload["session_series"]["session-8"])

    def test_template_filters_flow_and_keeps_mobile_targets_and_status_cases(self):
        template = report_dashboard._TEMPLATE
        self.assertIn("state.models.has(x[2])", template)
        self.assertIn("state.models.has(x[0])", template)
        self.assertIn("Math.min(100,selectedTotal?total/selectedTotal*100:0)", template)
        self.assertIn('class="flow-hit"', template)
        self.assertRegex(template, r"\.flow-hit\{[^}]*pointer-events:all")
        self.assertRegex(template, r"\.flow-map\{[^}]*min-width:900px")
        self.assertIn("width=\"172\" height=\"48\"", template)
        self.assertIn("project_model", template)
        self.assertIn("model_session", template)
        self.assertIn("flow-link motion", template)
        self.assertIn("openReplay(d.id,d.name)", template)
        self.assertIn("@media(prefers-reduced-motion:reduce)", template)
        self.assertIn(".flow-link{animation:none}", template)
        self.assertIn("[id^=section-]{scroll-margin-top:112px}", template)
        self.assertIn(".probe{position:sticky;top:64px", template)
        self.assertIn("if(avg===0){if(last>0)", template)
        self.assertIn("本期与此前均值均为 0", template)
        self.assertIn("last/avg-1", template)

    def test_module_preferences_migrate_city_and_orbit_to_flow(self):
        template = report_dashboard._TEMPLATE
        self.assertIn("flow:true", template)
        self.assertIn("hasOwnProperty.call(m,'orbit')", template)
        self.assertIn("hasOwnProperty.call(m,'city')", template)
        self.assertIn("m.flow=legacy", template)
        self.assertIn("delete m.orbit;delete m.city", template)
        self.assertIn("'orbit':()=>scrollToSection('section-flow')", template)
        self.assertIn("'city':()=>scrollToSection('section-flow')", template)

    @mock.patch("report_dashboard.readers.session_title", return_value="")
    @mock.patch("report_dashboard.readers.load_session_summaries", return_value={})
    def test_generated_html_embeds_data_and_has_unique_key_ids(self, _summaries, _title):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(report_dashboard.config, "OUT_DIR", tmp):
                path = Path(report_dashboard.write_dashboard(
                    self.synthetic_records(),
                    since="2026-07-01",
                    until="2026-07-02",
                    sources=["claude"],
                ))
            html = path.read_text(encoding="utf-8")
        self.assertNotIn("__DATA__", html)
        self.assertIn("const DATA = {", html)
        ids = re.findall(r"\bid\s*=\s*(?:\"([^\"]+)\"|'([^']+)'|([^\s>]+))", html)
        flat_ids = [next(part for part in match if part) for match in ids]
        for key_id in (
            "section-dock", "section-overview", "section-trend", "section-rhythm",
            "section-flow", "section-achievements", "section-top", "flow-map",
            "flow-panel", "flow-stats", "flow-save", "status-pulse", "view-capsule",
            "view-pop", "view-copy", "view-reset", "help-modal", "help-close",
            "discovery-card", "discovery-pos", "discovery-pin",
        ):
            self.assertEqual(1, flat_ids.count(key_id), key_id)

    def test_view_links_help_and_flow_export_are_self_contained(self):
        template = report_dashboard._TEMPLATE
        self.assertIn("function viewParams()", template)
        self.assertIn("function restoreViewFromURL()", template)
        self.assertIn("window.addEventListener('popstate'", template)
        self.assertIn("navigator.clipboard&&window.isSecureContext", template)
        self.assertIn("document.execCommand('copy')", template)
        self.assertIn("p.set('gran',state.gran)", template)
        self.assertIn("p.set('models'", template)
        self.assertIn("p.set('focus'", template)
        self.assertNotIn("p.set('cwd'", template)
        self.assertNotIn("p.set('session'", template)
        self.assertIn("else if(e.key==='?') openHelp()", template)
        self.assertIn("查看快捷键与隐藏操作", template)
        self.assertIn("function saveFlowSVG()", template)
        self.assertIn("svg.setAttribute('xmlns','http://www.w3.org/2000/svg')", template)
        self.assertIn("bg.setAttribute('fill','#0b1120')", template)
        self.assertIn(".help-grid{grid-template-columns:1fr}", template)


if __name__ == "__main__":
    unittest.main()
