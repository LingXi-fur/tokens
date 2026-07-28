import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]

import sys
sys.path.insert(0, str(ROOT))

import dashboard_payload
import dashboard_wire
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

    def sensitive_records(self):
        records = self.synthetic_records()
        records[0].update({
            "session": "raw-session-7b0fd86f",
            "cwd": "/private/Users/alice/Customer-Zephyr",
        })
        records.append({
            "source": "claude",
            "ts": "2026-07-01T02:00:00+08:00",
            "date": "2026-07-01",
            "model": "model-a",
            "input": 30,
            "output": 10,
            "cache_read": 10,
            "cache_write": 0,
            "total": 50,
            "session": "raw-session-7b0fd86f",
            "cwd": "/private/Users/alice/Customer-Zephyr",
        })
        return records

    def test_dashboard_assets_are_split_and_loaded(self):
        self.assertIn("dashboard_assets", report_dashboard._ASSET_DIR)
        self.assertIn("__STYLE__", (ROOT / "dashboard_assets" / "template.html").read_text(encoding="utf-8"))
        self.assertIn("__SCRIPT__", (ROOT / "dashboard_assets" / "template.html").read_text(encoding="utf-8"))
        self.assertGreater((ROOT / "dashboard_assets" / "dashboard.css").stat().st_size, 10000)
        self.assertGreater((ROOT / "dashboard_assets" / "dashboard.js").stat().st_size, 50000)

    def test_compact_wire_round_trips_payload(self):
        payload = {
            "models": ["model-a", "model-b"],
            "day_details": {
                "2026-07-01": {
                    "model": "model-a",
                    "session": "session-a",
                    "repeated": ["model-a", "session-a", "model-a"],
                },
            },
            "literal": "§already-prefixed",
        }
        wire = dashboard_wire.encode_payload(payload)
        self.assertEqual(1, wire["v"])
        self.assertEqual(payload, dashboard_wire.decode_payload(wire))
        compact = json.dumps(wire, ensure_ascii=False, separators=(",", ":"))
        plain = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        self.assertLess(len(compact), len(plain) + 80)

    @mock.patch("dashboard_payload.readers.build_session_index", return_value={})
    @mock.patch("dashboard_payload.readers.session_title", return_value="")
    @mock.patch("dashboard_payload.readers.load_session_summaries", return_value={})
    def test_single_pass_payload_matches_facade(self, _summaries, _title, _index):
        records = self.synthetic_records()
        direct = dashboard_payload.build_payload(
            records,
            since="2026-07-01",
            until="2026-07-02",
            sources=["claude"],
        )
        facade = report_dashboard.build_payload(
            records,
            since="2026-07-01",
            until="2026-07-02",
            sources=["claude"],
        )
        self.assertEqual(direct, facade)

    @mock.patch("dashboard_payload.readers.build_session_index")
    @mock.patch("dashboard_payload.readers.session_title")
    @mock.patch("dashboard_payload.readers.load_session_summaries")
    def test_anonymized_payload_replaces_identifiers_without_reading_titles(
            self, summaries, title, index):
        records = self.sensitive_records()
        payload = report_dashboard.build_payload(
            records,
            since="2026-07-01",
            until="2026-07-02",
            sources=["claude"],
            anonymize=True,
        )
        serialized = json.dumps(payload, ensure_ascii=False)
        for sensitive in (
            "/private/Users/alice/Customer-Zephyr",
            "Customer-Zephyr",
            "raw-session-7b0fd86f",
            "secret sidecar summary",
            "secret first prompt",
        ):
            self.assertNotIn(sensitive, serialized)
        summaries.assert_not_called()
        title.assert_not_called()
        index.assert_not_called()
        self.assertTrue(payload["anonymized"])

        project_ids = {item[2] for item in payload["top_cwds"]}
        project_flow_ids = {item[1] for item in payload["flow"]["project_model"]}
        self.assertEqual(2, len(project_ids))
        self.assertEqual(project_ids, project_flow_ids)
        self.assertTrue(all(item.startswith("Project-") for item in project_ids))

        session_ids = {item[2] for item in payload["top_sessions"]}
        session_flow_ids = {item[2] for item in payload["flow"]["model_session"]}
        self.assertEqual(session_ids, session_flow_ids)
        self.assertEqual(session_ids, set(payload["session_series"]))
        self.assertTrue(all(item.startswith("Session-") for item in session_ids))
        for item in payload["top_sessions"]:
            self.assertEqual(item[0], item[2])

        day = payload["day_details"]["2026-07-01"]
        self.assertIn(next(item for item in project_ids if item in {row[2] for row in day["top_cwds"]}), project_ids)
        self.assertIn(next(item for item in session_ids if item in {row[2] for row in day["top_sessions"]}), session_ids)
        repeated = next(values for sid, values in payload["session_series"].items() if len(values) == 2)
        self.assertEqual([100, 50], repeated)

    @mock.patch("dashboard_payload.readers.build_session_index", return_value={})
    @mock.patch("dashboard_payload.readers.session_title", return_value="")
    @mock.patch("dashboard_payload.readers.load_session_summaries", return_value={})
    def test_anonymized_payload_preserves_numeric_aggregates(self, _summaries, _title, _index):
        records = self.sensitive_records()
        raw = report_dashboard.build_payload(records)
        anonymized = report_dashboard.build_payload(records, anonymize=True)
        for key in (
            "source", "range", "models", "pretty", "colors", "cache_read",
            "hourly", "block", "n_cwds", "n_sessions", "max_turns",
            "achievement_stats", "provenance", "reuse", "day", "week", "month",
        ):
            self.assertEqual(raw[key], anonymized[key], key)
        self.assertFalse(raw["anonymized"])

    def test_anonymized_payload_keeps_missing_identifiers_missing(self):
        records = [{
            "source": "codex", "ts": "2026-07-01T01:00:00+08:00",
            "date": "2026-07-01", "model": "model-a", "input": 1,
            "output": 2, "cache_read": 0, "cache_write": 0, "total": 3,
        }]
        payload = report_dashboard.build_payload(records, anonymize=True)
        self.assertEqual([], payload["top_cwds"])
        self.assertEqual([], payload["top_sessions"])
        self.assertEqual({}, payload["session_series"])
        self.assertEqual({"project_model": [], "model_session": []}, payload["flow"])

    def test_anonymized_builder_facade_matches_with_fixed_key(self):
        records = self.synthetic_records()
        with mock.patch("dashboard_payload.secrets.token_bytes", return_value=b"k" * 32):
            direct = dashboard_payload.build_payload(records, anonymize=True)
        with mock.patch("dashboard_payload.secrets.token_bytes", return_value=b"k" * 32):
            facade = report_dashboard.build_payload(records, anonymize=True)
        self.assertEqual(direct, facade)

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

    @mock.patch("dashboard_payload.readers.build_session_index", return_value={})
    @mock.patch("dashboard_payload.readers.session_title", return_value="")
    @mock.patch("dashboard_payload.readers.load_session_summaries", return_value={})
    def test_build_payload_has_flow_and_basic_fields(self, _summaries, _title, _index):
        payload = report_dashboard.build_payload(
            self.synthetic_records(),
            since="2026-07-01",
            until="2026-07-02",
            sources=["claude"],
        )
        for key in (
            "generated", "source", "range", "models", "colors", "hourly",
            "day_details", "top_cwds", "top_sessions", "session_series",
            "flow", "reuse", "day", "week", "month", "provenance", "achievement_stats",
            "achievement_daily",
        ):
            self.assertIn(key, payload)
        self.assertEqual(["claude"], payload["source"])
        reuse = payload["reuse"]["day"]
        self.assertEqual(300, sum(sum(parts) for _, models in reuse for parts in models.values()))
        self.assertIn("model-a", reuse[0][1])
        self.assertIn("model-b", reuse[1][1])
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
        self.assertEqual(
            [
                {
                    "day": "2026-07-01", "input": 70, "output": 20,
                    "cache_write": 0, "sources": {"claude": 100}, "max_turns": 1,
                },
                {
                    "day": "2026-07-02", "input": 120, "output": 60,
                    "cache_write": 0, "sources": {"claude": 200}, "max_turns": 1,
                },
            ],
            payload["achievement_daily"],
        )

    @mock.patch("dashboard_payload.readers.build_session_index", return_value={})
    @mock.patch("dashboard_payload.readers.session_title", return_value="")
    @mock.patch("dashboard_payload.readers.load_session_summaries", return_value={})
    def test_session_series_covers_every_flow_session(self, _summaries, _title, _index):
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
        self.assertIn(":root[data-motion=low] .flow-link.motion{animation:none!important}", template)
        self.assertIn("[id^=section-]{scroll-margin-top:112px}", template)
        self.assertIn(".probe{position:sticky;top:64px", template)
        self.assertIn("if(avg===0){if(last>0)", template)
        self.assertIn("本期与此前均值均为 0", template)
        self.assertIn("last/avg-1", template)
        self.assertIn("const W=1040,H=340,padL=56,padR=18,padT=34", template)
        self.assertIn("function barAnnotationLayout(barTop,compareTop)", template)
        self.assertIn("delta:Math.max(9,compareTop-21)", template)
        self.assertIn("y=\"'+annotation.peak.toFixed(1)+'\"", template)
        self.assertIn("y=\"'+annotation.value.toFixed(1)+'\"", template)
        self.assertIn("y=\"'+annotation.delta.toFixed(1)+'\"", template)
        self.assertIn("id=compare-btn type=button aria-pressed=false", template)
        self.assertIn("compare.setAttribute('aria-pressed',String(state.compare))", template)

    def test_module_preferences_migrate_city_and_orbit_to_flow(self):
        template = report_dashboard._TEMPLATE
        self.assertIn("flow:true", template)
        self.assertIn("hasOwnProperty.call(m,'orbit')", template)
        self.assertIn("hasOwnProperty.call(m,'city')", template)
        self.assertIn("m.flow=legacy", template)
        self.assertIn("delete m.orbit;delete m.city", template)
        self.assertIn("'orbit':()=>scrollToSection('section-flow')", template)
        self.assertIn("'city':()=>scrollToSection('section-flow')", template)

    @mock.patch("dashboard_payload.readers.build_session_index", return_value={})
    @mock.patch("dashboard_payload.readers.session_title", return_value="")
    @mock.patch("dashboard_payload.readers.load_session_summaries", return_value={})
    def test_generated_html_embeds_data_and_has_unique_key_ids(self, _summaries, _title, _index):
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
        self.assertIn("const WIRE = {", html)
        self.assertIn("const DATA = decodeWire(WIRE)", html)
        self.assertEqual("dashboard.html", path.name)
        ids = re.findall(r"\bid\s*=\s*(?:\"([^\"]+)\"|'([^']+)'|([^\s>]+))", html)
        flat_ids = [next(part for part in match if part) for match in ids]
        for key_id in (
            "section-dock", "section-overview", "section-trend", "section-rhythm",
            "section-flow", "section-reuse", "section-achievements", "section-top", "flow-map",
            "flow-panel", "flow-stats", "flow-save", "status-pulse", "view-capsule",
            "view-pop", "view-copy", "view-reset", "help-modal", "help-close",
            "share-modal", "share-close", "ach-modal", "ach-title", "ach-x",
            "discovery-card", "discovery-pos", "discovery-pin",
        ):
            self.assertEqual(1, flat_ids.count(key_id), key_id)

    def test_anonymized_html_uses_separate_filename_and_contains_no_raw_identifiers(self):
        records = self.sensitive_records()
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(report_dashboard.config, "OUT_DIR", tmp):
                path = Path(report_dashboard.write_dashboard(
                    records,
                    since="2026-07-01",
                    until="2026-07-02",
                    sources=["claude"],
                    anonymize=True,
                ))
            html = path.read_text(encoding="utf-8")
        self.assertEqual("dashboard-anonymized.html", path.name)
        for sensitive in (
            "/private/Users/alice/Customer-Zephyr",
            "Customer-Zephyr",
            "raw-session-7b0fd86f",
        ):
            self.assertNotIn(sensitive, html)
        self.assertIn("脱敏导出（标识已替换）", html)
        self.assertIn("Project-", html)
        self.assertIn("Session-", html)

    def test_anonymized_wire_round_trips_without_raw_identifiers(self):
        payload = report_dashboard.build_payload(self.sensitive_records(), anonymize=True)
        wire = dashboard_wire.encode_payload(payload)
        decoded = dashboard_wire.decode_payload(wire)
        self.assertEqual(payload, decoded)
        serialized = json.dumps(wire, ensure_ascii=False)
        self.assertNotIn("Customer-Zephyr", serialized)
        self.assertNotIn("raw-session-7b0fd86f", serialized)

    def test_view_links_help_and_flow_export_are_self_contained(self):
        template = report_dashboard._TEMPLATE
        self.assertIn("function viewParams()", template)
        self.assertIn("function portableViewURL()", template)
        self.assertIn("location.protocol!=='file:'", template)
        self.assertIn("location.pathname.split('/').pop()", template)
        self.assertIn("copyText(portableViewURL())", template)
        self.assertIn("function restoreViewFromURL()", template)
        self.assertIn("window.addEventListener('popstate'", template)
        self.assertIn("navigator.clipboard&&window.isSecureContext", template)
        self.assertIn("document.execCommand('copy')", template)
        self.assertIn("p.set('gran',state.gran)", template)
        self.assertIn("p.append('model',m)", template)
        self.assertIn("p.set('focus'", template)
        self.assertNotIn("p.set('cwd'", template)
        self.assertNotIn("p.set('session'", template)
        self.assertIn("else if(e.key==='?') openHelp()", template)
        self.assertIn("查看快捷键与隐藏操作", template)
        self.assertIn("function saveFlowSVG()", template)
        self.assertIn("svg.setAttribute('xmlns','http://www.w3.org/2000/svg')", template)
        self.assertIn("bg.setAttribute('fill','#0b1120')", template)
        self.assertIn("let barCursor=0", template)
        self.assertIn("role=\"button\" aria-label=\"'+esc(aria)", template)
        self.assertIn("e.key==='ArrowRight'||e.key==='ArrowLeft'", template)
        self.assertIn("id=filter-ledger", template)
        self.assertIn("id=filter-undo", template)
        self.assertIn("let previousModels=null", template)
        self.assertIn("覆盖 <b>'+pct(selected,all)", template)
        self.assertIn("当前模型筛选构成", template)
        self.assertIn("row.addEventListener('keydown'", template)
        self.assertIn("document.getElementById('replay-ecg').addEventListener('pointerdown'", template)
        self.assertIn("const days=DATA.day||[], total=days.reduce((a,d)=>a+(d.total||0),0), calls=days.reduce", template)
        self.assertIn("累计占比", template)
        self.assertIn("横轴为轮次，不代表真实耗时", template)
        self.assertIn("class=rscrub id=race-scrub type=range", template)
        self.assertIn("document.getElementById('race-scrub').addEventListener('input'", template)
        self.assertIn('class="bar-focus"', template)
        self.assertIn(".bar-hit{fill:transparent;pointer-events:all}", template)
        self.assertIn("previousModels=null;invalidateDerived();renderFilters();renderDataViews();announceViewChange('已恢复月度全景'", template)
        self.assertIn("modal.setAttribute('aria-hidden','false')", template)
        self.assertIn("role=dialog aria-modal=true aria-labelledby=replay-title", template)
        self.assertIn("scrub.max=String(s.length-1)", template)
        self.assertIn("drawECG(Number(e.target.value||0))", template)
        self.assertIn("box.onclick=e=>", template)
        self.assertIn("toggleFocus(el.dataset.period,true)", template)
        self.assertIn("document.getElementById('replay-modal').addEventListener('keydown',e=>trapModalFocus(e,e.currentTarget))", template)
        self.assertIn("data-lazy=flow", template)
        self.assertIn("data-lazy=badges", template)
        self.assertIn("function initLazyRendering()", template)
        self.assertIn("rootMargin:'500px 0px'", template)
        self.assertIn("function renderDataViews()", template)
        self.assertIn("function memoDerived(key,build)", template)
        self.assertIn("document.body.dataset.modelDelegated", template)
        self.assertIn("function motionDisabled()", template)
        self.assertIn("const reduce=window.matchMedia('(prefers-reduced-motion: reduce)').matches", template)
        self.assertIn("motionResizeT=setTimeout", template)
        self.assertIn("id=motion-select", template)
        self.assertIn("function defaultMotion()", template)
        self.assertIn("id=comet-canvas", template)
        self.assertIn("particles=Array.from({length:28}", template)
        self.assertNotIn("d.className='comet'", template)
        self.assertIn("active=e.target.closest('.card')", template)
        self.assertIn("document.addEventListener('visibilitychange'", template)
        self.assertNotIn("clearInterval(_stripT)", template)
        self.assertIn("data-lazy=reuse", template)
        self.assertIn("function selectedReuseRows()", template)
        self.assertIn("function renderReuseRiver()", template)
        self.assertIn("Context Reuse River", template)
        self.assertIn("reuse:true", template)
        self.assertNotIn("data-lazy=fingerprint", template)
        self.assertNotIn("function fingerprintModelHours()", template)
        self.assertNotIn("function renderFingerprint()", template)
        self.assertNotIn("fingerprint-save", template)
        self.assertNotIn("Token 脉冲指纹", template)
        self.assertNotIn("fingerprint:true", template)
        self.assertNotIn("section-fingerprint", template)
        self.assertIn("clearFocus(true)", template)

    def test_rhythm_uses_continuous_dates_filtered_hours_and_safe_state_updates(self):
        script = (ROOT / "dashboard_assets" / "dashboard.js").read_text(encoding="utf-8")
        self.assertIn("function recentCalendarDays(count=14)", script)
        self.assertIn("days=recentCalendarDays()", script)
        self.assertNotIn("const box=document.getElementById('rhythm'), days=(DATA.day||[]).slice(-14)", script)
        self.assertIn("Object.entries(DATA.day_details||{}).forEach(([day,det])", script)
        self.assertIn("if(fd&&!fd.has(day))return", script)
        self.assertNotIn("if(!fd) return DATA.hourly||[]", script)
        self.assertIn("function rhythmLevel(value,positiveValues)", script)
        self.assertIn("if(max<=min)return 4", script)
        self.assertIn("lv=rhythmLevel(v,vals)", script)
        self.assertIn("state.focusPeriod=cell.dataset.day;invalidateDerived();hideRhythmTip();renderDataViews()", script)
        self.assertNotIn("state.focusPeriod=c.dataset.day;hideRhythmTip();render();", script)

    def test_rhythm_helpers_handle_calendar_gaps_and_sparse_heat(self):
        script = (ROOT / "dashboard_assets" / "dashboard.js").read_text(encoding="utf-8")
        def extract_function(name):
            start = script.index(f"function {name}(")
            brace = script.index("{", start)
            depth = 0
            for index in range(brace, len(script)):
                if script[index] == "{":
                    depth += 1
                elif script[index] == "}":
                    depth -= 1
                    if depth == 0:
                        return script[start:index + 1]
            self.fail(f"未找到完整函数: {name}")

        helpers = "\n".join(
            extract_function(name)
            for name in ("localISO", "recentCalendarDays", "rhythmLevel")
        )
        node_script = helpers + r'''
const DATA={range:{until:'2026-07-20'},generated:'2026-07-27 12:00',day:[
  {period:'2026-07-01',total:10,calls:1,models:{}},
  {period:'2026-07-14',total:20,calls:1,models:{}}
]};
const days=recentCalendarDays();
if(days.length!==14)throw new Error('expected 14 days');
if(days[0].period!=='2026-07-07'||days[13].period!=='2026-07-20')throw new Error('wrong calendar endpoints');
if(days[1].period!=='2026-07-08'||days[1].total!==0)throw new Error('missing day was not filled');
if(rhythmLevel(0,[100])!==0)throw new Error('zero level');
if(rhythmLevel(100,[100])!==4)throw new Error('single peak must be hottest');
if(rhythmLevel(100,[100,100])!==4)throw new Error('tied peaks must be hottest');
if(rhythmLevel(4,[1,2,3,4])!==4)throw new Error('maximum must be hottest');
'''
        result = subprocess.run(
            ["node", "-e", node_script],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)

    def test_reuse_parts_are_exact_and_sum_to_total(self):
        cases = [
            ("claude", 150, 100, 30, 20, 0, [100, 30, 20, 0, 0]),
            ("gemini", 150, 100, 30, 20, 0, [100, 30, 20, 0, 0]),
            ("codex", 150, 120, 30, 20, 0, [100, 30, 20, 0, 0]),
            ("unknown", 10, 5, 3, 0, 0, [5, 3, 0, 0, 2]),
        ]
        for source, total, inp, out, read, write, expected in cases:
            with self.subTest(source=source):
                parts = dashboard_payload._reuse_parts(source, total, inp, out, read, write)
                self.assertEqual(expected, parts)
                self.assertEqual(total, sum(parts))

    @mock.patch("dashboard_payload.readers.build_session_index", return_value={})
    @mock.patch("dashboard_payload.readers.session_title", return_value="")
    @mock.patch("dashboard_payload.readers.load_session_summaries", return_value={})
    def test_payload_tracks_model_calls_cache_and_complete_daily_entities(self, _summaries, _title, _index):
        records = self.synthetic_records() + [{
            "source": "claude", "ts": "2026-07-01T02:00:00+08:00",
            "date": "2026-07-01", "model": "model-a", "input": 5,
            "output": 2, "cache_read": 3, "cache_write": 0, "total": 10,
            "session": "session-c", "cwd": "/tmp/project-c",
        }]
        payload = report_dashboard.build_payload(records)
        day = next(row for row in payload["day"] if row["period"] == "2026-07-01")
        self.assertEqual({"model-a": 2}, day["model_calls"])
        detail = payload["day_details"]["2026-07-01"]
        self.assertEqual({"model-a": 13}, detail["cache_read_models"])
        self.assertEqual(2, len(detail["cwds"]))
        self.assertEqual(2, len(detail["sessions"]))

    @mock.patch("dashboard_payload.readers.build_session_index", return_value={})
    @mock.patch("dashboard_payload.readers.session_title", return_value="")
    @mock.patch("dashboard_payload.readers.load_session_summaries", return_value={})
    def test_complete_daily_entities_preserve_cross_day_top_candidate(self, _summaries, _title, _index):
        records = []
        for day in ("2026-07-01", "2026-07-02"):
            records.append({
                "source": "claude", "ts": day + "T01:00:00+08:00", "date": day,
                "model": "model-a", "input": 9, "output": 0, "cache_read": 0,
                "cache_write": 0, "total": 9, "session": "shared-session",
                "cwd": "/tmp/shared-project",
            })
            for index in range(6):
                records.append({
                    "source": "claude", "ts": day + f"T{index + 2:02d}:00:00+08:00", "date": day,
                    "model": "model-a", "input": 10, "output": 0, "cache_read": 0,
                    "cache_write": 0, "total": 10,
                    "session": f"{day}-session-{index}", "cwd": f"/tmp/{day}-project-{index}",
                })
        payload = report_dashboard.build_payload(records)
        for day in ("2026-07-01", "2026-07-02"):
            detail = payload["day_details"][day]
            self.assertEqual(7, len(detail["cwds"]))
            self.assertNotIn("/tmp/shared-project", {row[2] for row in detail["top_cwds"]})
            self.assertIn("/tmp/shared-project", {row[2] for row in detail["cwds"]})

    def test_core_fixes_and_project_lens_contracts(self):
        template = report_dashboard._TEMPLATE
        for marker in (
            "model_calls", "cache_read_models", "function selectedCacheRead()",
            "function forecastForLatestMonth(rows)", "p.append('model',m)",
            "function markdownCell(value)", "function renderProjectLens()",
            "data-module=project", "id=section-project", "project:true",
            "project:renderProjectLens", "role=combobox", "role=listbox",
            "aria-activedescendant", "role=gridcell", "role','status",
        ):
            self.assertIn(marker, template)
        self.assertIn("input[data-mod]", template)
        self.assertNotIn(".mrow input{display:none}", template)
        self.assertIn("activateRhythmCell(c)", template)
        self.assertIn("无 Token 记录", template)

    def test_compare_annotation_layout_separates_peak_value_and_delta(self):
        script = (ROOT / "dashboard_assets" / "dashboard.js").read_text(encoding="utf-8")
        start = script.index("function barAnnotationLayout(")
        end = script.index("\nfunction renderBar()", start)
        helper = script[start:end]
        node_script = helper + r'''
const peak=barAnnotationLayout(34,34);
if(peak.peak-peak.delta<12)throw new Error('peak and delta overlap');
if(peak.value-peak.delta<12)throw new Error('value and delta overlap');
const previousHigher=barAnnotationLayout(90,34);
if(previousHigher.value-previousHigher.delta<12)throw new Error('previous-high comparison overlaps value');
const equal=barAnnotationLayout(60,60);
if(equal.peak-equal.delta<12)throw new Error('equal comparison overlaps');
'''
        result = subprocess.run(
            ["node", "-e", node_script],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)

        template = report_dashboard._TEMPLATE
        for marker in (
            "function openModal(modal,initialFocus)",
            "function closeModal(modal)",
            "function trapModalFocus(e,modal)",
            "function activeModal()",
            "openModal(document.getElementById('share-modal')",
            "openModal(document.getElementById('ach-modal')",
            "openModal(modal,document.getElementById('help-close'))",
            "openModal(modal,document.getElementById('replay-x'))",
            "role=dialog aria-modal=true aria-label=\"Token 分享卡\"",
            "role=dialog aria-modal=true aria-labelledby=ach-title",
            "class=table-scroll tabindex=0 role=region aria-label=\"Token 明细，可横向滚动\"",
            ".head-tools{display:flex;width:100%;min-width:0;flex-wrap:wrap}",
            ".passport{padding:22px;min-height:0}",
            ".ach-bar{flex-wrap:wrap}",
        ):
            self.assertIn(marker, template)
        key_handler = template.index("document.addEventListener('keydown',e=>{", template.index("function syncPal()"))
        self.assertLess(template.index("const modal=activeModal()", key_handler), template.index("state.focusPeriod", key_handler))
        self.assertIn("document.body.classList.add('modal-open')", template)
        self.assertIn("document.body.classList.remove('modal-open')", template)
        self.assertIn("aria-label=\"关闭分享卡\"", template)
        self.assertIn("aria-label=\"搜索成就\"", template)
        self.assertIn("aria-label=\"庆祝成就进度\"", template)

    def test_granularity_achievement_and_motion_contracts(self):
        template = report_dashboard._TEMPLATE
        self.assertIn('class=tabs id=tabs role=group aria-label="统计粒度"', template)
        self.assertNotIn("role=tablist", template)
        self.assertNotRegex(template, r"\brole=tab\b")
        self.assertIn("aria-pressed=true", template)
        self.assertIn("function syncGranControls()", template)
        self.assertIn("x.setAttribute('aria-pressed',String(on))", template)
        self.assertIn("<button type=button class=cat-h aria-expanded=", template)
        self.assertIn("aria-controls=", template)
        self.assertIn("h.setAttribute('aria-expanded','true')", template)
        self.assertIn("h.setAttribute('aria-expanded','false')", template)
        self.assertIn("function scrollBehavior()", template)
        self.assertNotIn("behavior:'smooth'", template)
        self.assertIn("if(motionDisabled())return", template)
        self.assertNotIn("runAchievementStrip", template)
        self.assertNotIn("_stripT", template)
        self.assertIn("function compareAchievementSnapshot(all)", template)
        self.assertIn("*,*::before,*::after{animation:none!important;transition:none!important}", template)
        self.assertIn("function provenanceHealth()", template)
        self.assertIn("function freshnessInfo()", template)
        self.assertIn("function capabilityInfo()", template)
        self.assertIn("function renderProvenance()", template)
        self.assertIn("function provenanceSummary()", template)
        self.assertIn("data-module=provenance", template)
        self.assertIn("id=section-provenance", template)
        self.assertIn("id=freshness-beacon", template)
        self.assertIn("provenance:true", template)
        self.assertIn("跳转 · 数据可信度实验室", template)
        self.assertIn("说明：解析器拒绝的原始事件不在分母；不包含 cwd、session 或逐轮 Token 明细。", template)


    def test_achievement_center_structured_progress_and_snapshot_contracts(self):
        template = report_dashboard._TEMPLATE
        for marker in (
            "Achievement Center · 成就中心",
            "id=ach-latest",
            "id=ach-timeline",
            "id=ach-goals",
            "id=ach-collection-summary",
            "id=ach-detail",
            "function achievementSnapshots()",
            "function finalizeAchievements(cats)",
            "function achievementTimeline(all)",
            "function nextAchievementGoals(all)",
            "function compareAchievementSnapshot(all)",
            "本报告范围内首次达到",
            "不是全球用户稀有度",
            "data-ach-id=",
            "aria-live=polite",
        ):
            self.assertIn(marker, template)
        self.assertNotIn("runAchievementStrip", template)
        self.assertNotIn("setInterval(roll,3500)", template)
        self.assertIn("document.documentElement.dataset.motion==='full')confetti()", template)

    @mock.patch("dashboard_payload.readers.build_session_index", return_value={})
    @mock.patch("dashboard_payload.readers.session_title", return_value="")
    @mock.patch("dashboard_payload.readers.load_session_summaries", return_value={})
    def test_achievement_daily_accumulates_session_turns_without_identifiers(
            self, _summaries, _title, _index):
        records = []
        for day, turns in (("2026-07-01", 2), ("2026-07-02", 3)):
            for index in range(turns):
                records.append({
                    "source": "claude", "ts": f"{day}T0{index}:00:00+08:00",
                    "date": day, "model": "model-a", "input": 2, "output": 1,
                    "cache_read": 1, "cache_write": 1, "total": 5,
                    "session": "secret-session", "cwd": "/tmp/secret-project",
                })
        payload = report_dashboard.build_payload(records)
        self.assertEqual([2, 5], [row["max_turns"] for row in payload["achievement_daily"]])
        serialized = json.dumps(payload["achievement_daily"], ensure_ascii=False)
        self.assertNotIn("secret-session", serialized)
        self.assertNotIn("secret-project", serialized)

    def test_provenance_counts_range_and_matches_anonymized_payload(self):
        records = self.synthetic_records() + [{
            "source": "codex", "ts": "not-a-time", "date": "2026-07-03",
            "model": "model-c", "input": 30, "output": 10,
            "cache_read": 5, "cache_write": 0, "total": 40,
        }]
        raw = report_dashboard.build_payload(records, since="2026-07-01", until="2026-07-03")
        anonymized = report_dashboard.build_payload(
            records, since="2026-07-01", until="2026-07-03", anonymize=True,
        )
        provenance = raw["provenance"]
        self.assertEqual(3, provenance["records"])
        self.assertEqual(340, provenance["total"])
        self.assertEqual(2, provenance["valid_ts"])
        self.assertEqual(2, provenance["with_cwd"])
        self.assertEqual(2, provenance["replay_eligible"])
        self.assertEqual(2, provenance["replay_retained"])
        self.assertEqual(3, provenance["with_components"])
        self.assertEqual("2026-07-01", provenance["first_day"])
        self.assertEqual("2026-07-03", provenance["last_day"])
        self.assertEqual(1, provenance["sources"]["codex"]["records"])
        self.assertEqual(provenance, anonymized["provenance"])
        serialized = json.dumps(provenance, ensure_ascii=False)
        self.assertNotIn("/tmp/project-a", serialized)
        self.assertNotIn("session-a", serialized)


    def test_standardized_component_coverage_requires_same_record(self):
        records = [
            {
                "source": "claude", "ts": "2026-07-01T01:00:00+08:00",
                "date": "2026-07-01", "model": "model-a",
                "input": 5, "output": 5, "total": 10,
            },
            {
                "source": "claude", "ts": "2026-07-01T02:00:00+08:00",
                "date": "2026-07-01", "model": "model-a",
                "cache_read": 5, "cache_write": 5, "total": 10,
            },
            {
                "source": "claude", "ts": "2026-07-01T03:00:00+08:00",
                "date": "2026-07-01", "model": "model-a",
                "input": 2, "output": 3, "cache_read": 4, "cache_write": 1,
                "total": 10,
            },
        ]
        provenance = report_dashboard.build_payload(records)["provenance"]
        self.assertEqual(2, provenance["with_input"])
        self.assertEqual(2, provenance["with_output"])
        self.assertEqual(2, provenance["with_cache_read"])
        self.assertEqual(2, provenance["with_cache_write"])
        self.assertEqual(1, provenance["with_components"])

    @mock.patch("dashboard_payload.readers.build_session_index", return_value={})
    @mock.patch("dashboard_payload.readers.session_title", return_value="")
    @mock.patch("dashboard_payload.readers.load_session_summaries", return_value={})
    def test_replay_provenance_distinguishes_eligible_and_retained(self, _summaries, _title, _index):
        records = []
        for i in range(250):
            records.append({
                "source": "claude", "ts": f"2026-07-{1 + i // 24:02d}T{i % 24:02d}:00:00+08:00",
                "date": f"2026-07-{1 + i // 24:02d}", "model": "model-a",
                "input": 1, "output": 0, "cache_read": 0, "cache_write": 0,
                "total": i + 1, "session": "session-a", "cwd": "/tmp/main",
            })
        payload = report_dashboard.build_payload(records)
        self.assertEqual(250, payload["provenance"]["replay_eligible"])
        self.assertEqual(200, payload["provenance"]["replay_retained"])
        self.assertEqual(200, len(payload["session_series"]["session-a"]))

        records[200]["session"] = "session-b"
        for index in range(201, 250):
            records[index]["session"] = "session-b"
        payload = report_dashboard.build_payload(records)
        self.assertEqual(250, payload["provenance"]["replay_eligible"])
        self.assertEqual(250, payload["provenance"]["replay_retained"])

    def test_provenance_helpers_cover_health_freshness_and_capabilities(self):
        script = (ROOT / "dashboard_assets" / "dashboard.js").read_text(encoding="utf-8")
        def extract_function(name):
            start = script.index(f"function {name}(")
            brace = script.index("{", start)
            depth = 0
            for index in range(brace, len(script)):
                if script[index] == "{": depth += 1
                elif script[index] == "}":
                    depth -= 1
                    if depth == 0: return script[start:index + 1]
            self.fail(name)
        helpers = "\n".join(extract_function(name) for name in (
            "coverageRatio", "standardizedComponentCount", "freshnessInfo", "provenanceHealth",
            "capabilityInfo",
        ))
        node_script = r'''
const DATA={generated:'2026-07-27 12:00',range:{since:null,until:null},provenance:{records:100,total:1000,valid_ts:100,with_cwd:80,with_session:90,replay_eligible:90,replay_retained:90,with_input:100,with_output:100,with_cache_read:100,with_cache_write:100,with_components:100,last_day:'2026-07-27',sources:{claude:{records:100,total:1000}}},session_series:{s:[1]}};
''' + helpers + r'''
if(freshnessInfo().key!=='fresh')throw new Error('freshness');
if(provenanceHealth().key!=='full')throw new Error('health');
if(capabilityInfo().find(x=>x.key==='project').status!=='partial')throw new Error('project capability');
DATA.provenance={records:100,valid_ts:100,with_cwd:80,with_session:1,replay_eligible:1,replay_retained:1,with_input:100,with_output:100,with_cache_read:100,with_cache_write:100,with_components:100,sources:{}};
const sparseReplay=capabilityInfo().find(x=>x.key==='session');if(sparseReplay.ratio!==.01||sparseReplay.status!=='partial')throw new Error('session capability denominator');
DATA.provenance={records:100,valid_ts:100,with_cwd:80,with_session:90,replay_eligible:90,replay_retained:90,with_input:100,with_output:100,with_cache_read:100,with_cache_write:100,with_components:0,sources:{}};
if(standardizedComponentCount(DATA.provenance)!==0)throw new Error('component minimum');
if(provenanceHealth().key==='full')throw new Error('cache fields must affect health');
if(capabilityInfo().find(x=>x.key==='reuse').status!=='off')throw new Error('cache fields must affect reuse');
DATA.range.until='2026-07-20';if(freshnessInfo().key!=='range')throw new Error('range freshness');
DATA.provenance={records:0,sources:{}};if(provenanceHealth().key!=='base')throw new Error('empty health');
'''
        result = subprocess.run(["node", "-e", node_script], capture_output=True, text=True, check=False)
        self.assertEqual(0, result.returncode, result.stderr)
    def test_data_moments_copy_and_contextual_empty_contracts(self):
        template = report_dashboard._TEMPLATE
        for marker in (
            "Data Moments · 数据时刻", "id=moments", "function emptyStateReason(kind)",
            "function contextEmptyHTML(kind)", "function copyExactValue(label,value)",
            "id=k-total-copy", "function selectedDailyRows()", "function continuousCalendar(rows,end,count)",
            "function currentActiveStreak(rows,end)", "function longestActiveStreak(rows)",
            "function activeStreakDays(rows,end)", "function trailingQuietDays(rows,end)",
            "function latestMilestone(rows)", "function latestModelRelay(rows)",
            "function projectFirstSeenInRange(projectId)", "function buildMomentEvents()",
            "function momentEventsForRows(rows,events=buildMomentEvents())", "function renderDataMoments()",
            "function focusMomentDay(day)", "copyExactValue('项目 Token',total)",
        ):
            self.assertIn(marker, template)
        self.assertNotIn("navigator.clipboard.writeText(String(lastTotal))", template)
        self.assertIn("data-empty-action", template)
        self.assertIn("handleEmptyAction", template)

    def test_data_moment_helpers_respect_calendar_gaps_and_events(self):
        script = (ROOT / "dashboard_assets" / "dashboard.js").read_text(encoding="utf-8")
        def extract_function(name):
            start = script.index(f"function {name}(")
            brace = script.index("{", start)
            depth = 0
            for index in range(brace, len(script)):
                if script[index] == "{": depth += 1
                elif script[index] == "}":
                    depth -= 1
                    if depth == 0: return script[start:index + 1]
            self.fail(name)
        helpers = "\n".join(extract_function(name) for name in (
            "localISO", "continuousCalendar", "currentActiveStreak", "activeStreakDays",
            "longestActiveStreak", "trailingQuietDays", "latestMilestone", "dominantModel",
            "latestModelRelay",
        ))
        node_script = r'''
const state={models:new Set(['a','b'])};const DATA={models:['a','b']};
''' + helpers + r'''
const rows=[
 {period:'2026-07-01',total:600,models:{a:600}},
 {period:'2026-07-02',total:500,models:{a:200,b:300}},
 {period:'2026-07-04',total:10,models:{b:10}}
];
if(currentActiveStreak(rows,'2026-07-04')!==1)throw new Error('gap must break current streak');
if(longestActiveStreak(rows)!==2)throw new Error('longest streak');
const quiet=trailingQuietDays(rows,'2026-07-06');if(quiet.kind!=='quiet'||quiet.days!==2)throw new Error('quiet tail');
const milestone=latestMilestone(rows);if(!milestone||milestone.day!=='2026-07-02'||milestone.value!==1000)throw new Error('milestone');
const relay=latestModelRelay(rows);if(!relay||relay.day!=='2026-07-02'||relay.from!=='a'||relay.to!=='b')throw new Error('relay');
const gapRelay=latestModelRelay([rows[0],rows[2]]);if(gapRelay)throw new Error('gap relay');
const tieRelay=latestModelRelay([{period:'2026-07-01',total:10,models:{a:10}},{period:'2026-07-02',total:20,models:{a:10,b:10}}]);if(tieRelay)throw new Error('tie relay');
state.models.clear();if(trailingQuietDays(rows,'2026-07-06').kind!=='no-observation')throw new Error('empty filter');
'''
        result = subprocess.run(["node", "-e", node_script], capture_output=True, text=True, check=False)
        self.assertEqual(0, result.returncode, result.stderr)
    def test_trend_annotation_rail_maps_merges_and_supports_keyboard(self):
        script = (ROOT / "dashboard_assets" / "dashboard.js").read_text(encoding="utf-8")
        for marker in (
            "function buildMomentEvents()", "function periodForMoment(day,gran)",
            "function momentEventsForRows(rows,events=buildMomentEvents())", "function handleMomentKey(e,markers,index)", 'class="moment-marker', 'class="moment-target"',
            'role="button" aria-label="数据时刻', "moment-marker.moment-active",
            "box.onclick=e=>", "focusMomentDay((marker||target).dataset.momentDay)", "handleMomentKey(e,markers,i)",
            "下一个数据时刻",
        ):
            self.assertIn(marker, report_dashboard._TEMPLATE)

        def extract_function(name):
            start = script.index(f"function {name}(")
            brace = script.index("{", start)
            depth = 0
            for index in range(brace, len(script)):
                if script[index] == "{": depth += 1
                elif script[index] == "}":
                    depth -= 1
                    if depth == 0: return script[start:index + 1]
            self.fail(name)

        helpers = "\n".join(extract_function(name) for name in (
            "localISO", "projectPeriod", "periodForMoment", "momentEventsForRows",
        ))
        node_script = r'''
const state={gran:'week'};
function buildMomentEvents(){return [
 {kind:'milestone',day:'2026-07-01',label:'A',description:'A',icon:'◆'},
 {kind:'project',day:'2026-07-02',label:'B',description:'B',icon:'◇'},
 {kind:'relay',day:'2026-07-08',label:'C',description:'C',icon:'↗'}
];}
''' + helpers + r'''
let rows=[{period:'2026-06-29'},{period:'2026-07-06'}],events=momentEventsForRows(rows);
if(events.length!==2||events[0].events.length!==2||events[1].events.length!==1)throw new Error('weekly merge');
if(events[0].description!=='A；B')throw new Error('merged description');
state.gran='month';rows=[{period:'2026-07-01'}];events=momentEventsForRows(rows);
if(events.length!==1||events[0].events.length!==3)throw new Error('monthly merge');
state.gran='day';rows=[{period:'2026-07-01'},{period:'2026-07-02'},{period:'2026-07-08'}];events=momentEventsForRows(rows);
if(events.length!==3)throw new Error('daily mapping');
'''
        result = subprocess.run(["node", "-e", node_script], capture_output=True, text=True, check=False)
        self.assertEqual(0, result.returncode, result.stderr)

        keyboard_helpers = "\n".join(extract_function(name) for name in (
            "describeMoment", "handleMomentKey",
        ))
        keyboard_script = r'''
let focused=null,activated=null,hint='';
const hintEl={set textContent(value){hint=value;},get textContent(){return hint;}};
const markers=[0,1,2].map(index=>({
  __moment:{day:'2026-07-0'+(index+1),description:'moment '+index},
  tabIndex:-1,
  setAttribute(name,value){if(name==='tabindex')this.tabIndex=Number(value);},
  focus(){focused=this;},
}));
const document={
  querySelectorAll(){return markers;},
  getElementById(){return hintEl;},
};
function focusMomentDay(day){activated=day;}
''' + keyboard_helpers + r'''
function event(key){return {key,prevented:false,preventDefault(){this.prevented=true;}};}
let e=event('ArrowRight');if(!handleMomentKey(e,markers,1)||focused!==markers[2]||!e.prevented)throw new Error('ArrowRight');
e=event('ArrowRight');if(!handleMomentKey(e,markers,2)||focused!==markers[2])throw new Error('right boundary');
e=event('ArrowLeft');if(!handleMomentKey(e,markers,0)||focused!==markers[0])throw new Error('left boundary');
e=event('Home');if(!handleMomentKey(e,markers,2)||focused!==markers[0])throw new Error('Home');
e=event('End');if(!handleMomentKey(e,markers,0)||focused!==markers[2])throw new Error('End');
e=event('Enter');if(!handleMomentKey(e,markers,1)||activated!=='2026-07-02'||!e.prevented)throw new Error('Enter');
activated=null;e=event(' ');if(!handleMomentKey(e,markers,0)||activated!=='2026-07-01'||!e.prevented)throw new Error('Space');
e=event('Tab');if(handleMomentKey(e,markers,1)||e.prevented)throw new Error('unhandled key');
'''
        result = subprocess.run(["node", "-e", keyboard_script], capture_output=True, text=True, check=False)
        self.assertEqual(0, result.returncode, result.stderr)

    def test_filtered_top_recomputes_complete_entities_and_drops_zero_rows(self):
        template = report_dashboard._TEMPLATE
        for marker in (
            "function aggregateEntities(days,kind)", "function selectedTopEntities(kind)",
            ".filter(row=>row[1]>0)", ".filter(x=>x.total>0)",
            "按当前模型筛选重新计算 Top", "回放展示完整会话 Token 序列",
        ):
            self.assertIn(marker, template)

        script = (ROOT / "dashboard_assets" / "dashboard.js").read_text(encoding="utf-8")
        start = script.index("function aggregateEntities(")
        end = script.index("\nfunction focusDetail()", start)
        aggregate_helper = script[start:end]
        node_script = r'''
const state={models:new Set(['a'])};
const DATA={day_details:{
  '2026-07-01':{cwds:[['Alpha',70,'alpha',{a:70}],['Beta',90,'beta',{b:90}]],sessions:[['Session Alpha',40,'sa',{a:40}],['Session Beta',80,'sb',{b:80}]]},
  '2026-07-02':{cwds:[['Gamma',80,'gamma',{a:80}],['Alpha',20,'alpha',{a:20,b:50}]],sessions:[['Session Gamma',75,'sg',{a:75}],['Session Alpha',20,'sa',{a:20,b:60}]]},
}};
''' + aggregate_helper + r'''
let projects=aggregateEntities(Object.keys(DATA.day_details),'project');
if(projects.length!==2)throw new Error('zero rows must be removed');
if(projects[0][2]!=='alpha'||projects[0][1]!==90)throw new Error('cross-day project aggregation');
if(projects[1][2]!=='gamma'||projects[1][1]!==80)throw new Error('project ranking');
let sessions=aggregateEntities(Object.keys(DATA.day_details),'session');
if(sessions.length!==2||sessions[0][2]!=='sg'||sessions[0][1]!==75||sessions[1][2]!=='sa'||sessions[1][1]!==60)throw new Error('session aggregation');
state.models=new Set(['b']);projects=aggregateEntities(Object.keys(DATA.day_details),'project');
if(projects.length!==2||projects[0][2]!=='beta'||projects[0][1]!==90||projects[1][2]!=='alpha'||projects[1][1]!==50)throw new Error('model switch ranking');
'''
        result = subprocess.run(["node", "-e", node_script], capture_output=True, text=True, check=False)
        self.assertEqual(0, result.returncode, result.stderr)
