"""Live-runtime browser tests for the background-snapshot dashboard.

Independent of ``tests/test_dashboard_runtime.py`` (no inheritance): it builds
its own fixtures, serves a live page from a loopback HTTP server that scripts the
fixed ``/api/snapshot`` protocol (wire / snapshot / error / has_snapshot /
refreshing / checked_at / revision plus the ``ETag`` response header), then
drives it in Chromium.

Only synthetic records are used. Nothing here opens port 8765, the private
cache, raw session logs, or any upload path.
"""
import json
import os
import sys
import tempfile
import threading
import socket
import struct
import time
import unittest
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tokens_cli import dashboard_wire, report_dashboard

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None


_CHECKED_AT = "2026-07-02T05:00:00+00:00"
_SCAN_ERROR = (
    "The local log scan failed; the last successful snapshot is still shown."
)


def _records(extra=None):
    base = [
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
    return base + list(extra or [])


def _build_wire(records):
    # No raw-title entry point: every payload build here is synthetic.
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
            generated_at=datetime(2026, 7, 3, 0, 0),
        )
    return payload, dashboard_wire.encode_payload(payload)


# -- scripted /api/snapshot bodies -------------------------------------------
def _ready(wire, snapshot, *, etag, revision, refreshing=False, error=None,
           checked_at=_CHECKED_AT):
    return {
        "body": {
            "wire": wire,
            "snapshot": snapshot,
            "error": error,
            "has_snapshot": True,
            "refreshing": refreshing,
            "checked_at": checked_at,
            "revision": revision,
        },
        "etag": etag,
    }


def _prepare(revision=1, etag='"live-1"'):
    return {
        "body": {
            "wire": None,
            "snapshot": None,
            "error": None,
            "has_snapshot": False,
            "refreshing": True,
            "checked_at": None,
            "revision": revision,
        },
        "etag": etag,
    }


def _error(wire, snapshot, *, etag, revision):
    return _ready(wire, snapshot, etag=etag, revision=revision, error=_SCAN_ERROR)


def _legacy(wire, snapshot):
    # Older backend contract: no has_snapshot / refreshing / checked_at / revision.
    return {"body": {"wire": wire, "snapshot": snapshot, "error": None}, "etag": None}


class _SnapshotState:
    def __init__(self, html):
        self.html = html.encode("utf-8")
        self.queue = []
        self.default = None
        self.count = 0
        self.force_hangup = False
        self.if_none_match = []
        self._lock = threading.Lock()

    def take(self):
        with self._lock:
            self.count += 1
            if self.queue:
                return self.queue.pop(0)
            return self.default

    def push(self, *responses):
        with self._lock:
            self.queue.extend(responses)

    def requests(self):
        with self._lock:
            return self.count

    def last_if_none_match(self):
        with self._lock:
            return self.if_none_match[-1] if self.if_none_match else None


def _start_server(html):
    state = _SnapshotState(html)

    class _Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "tokens-live-test"
        sys_version = ""

        def log_message(self, *args):
            return

        def do_GET(self):
            if self.path.split("?")[0] == "/api/snapshot":
                self._snapshot()
                return
            body = state.html
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _drop(self):
            # Abort with a TCP reset: no reply bytes and no graceful FIN, so the
            # browser cannot transparently retry an idle keep-alive.
            try:
                self.connection.setsockopt(
                    socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0)
                )
            except OSError:
                pass
            self.close_connection = True
            self.connection.close()

        def _snapshot(self):
            if state.force_hangup:
                return self._drop()
            conditional = self.headers.get("If-None-Match")
            response = state.take()
            with state._lock:
                state.if_none_match.append(conditional)
            if response is None:
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if response.get("delay"):
                time.sleep(float(response["delay"]))
            if response.get("hangup"):
                return self._drop()
            etag = response.get("etag")
            if response.get("status") == 304:
                self.send_response(304)
                if etag:
                    self.send_header("ETag", etag)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            payload = json.dumps(response["body"], ensure_ascii=False).encode("utf-8")
            try:
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                if etag:
                    self.send_header("ETag", etag)
                self.end_headers()
                self.wfile.write(payload)
            except OSError:
                pass  # the page aborted this request (watchdog / cancel)

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    httpd.daemon_threads = True
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return state, httpd


@unittest.skipIf(sync_playwright is None, "Playwright is not installed")
class DashboardLiveRuntimeTests(unittest.TestCase):
    # Same binding as tests/test_dashboard_crossbrowser.py: override with
    # TOKENS_DASHBOARD_BROWSER=webkit|firefox to reuse this suite cross-engine.
    BROWSER = os.environ.get("TOKENS_DASHBOARD_BROWSER", "chromium")

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls._snap1_payload, cls._snap1_wire = _build_wire(_records())
        cls._snap2_payload, cls._snap2_wire = _build_wire(
            _records([{
                "source": "claude",
                "ts": "2026-07-02T14:00:00+08:00",
                "date": "2026-07-02",
                "model": "model-b",
                "input": 200,
                "output": 60,
                "cache_read": 40,
                "cache_write": 0,
                "total": 300,
                "session": "synthetic-session-d",
                "cwd": "/synthetic/project-b",
            }])
        )
        cls._snap1_id = cls._snap1_payload["snapshot"]["id"]
        cls._snap2_id = cls._snap2_payload["snapshot"]["id"]
        assert cls._snap1_id != cls._snap2_id
        placeholder = _build_wire([])[1]

        prepare_live = {
            "enabled": True,
            "interval": 300,
            "poll_interval": 60,
            "has_snapshot": False,
            "refreshing": True,
            "checked_at": None,
            "error": None,
            "snapshot": None,
            "revision": 0,
            "etag": '"live-0"',
        }
        ready_live = {
            "enabled": True,
            "interval": 300,
            "poll_interval": 60,
            "has_snapshot": True,
            "refreshing": False,
            "checked_at": _CHECKED_AT,
            "error": None,
            "snapshot": cls._snap1_id,
            "revision": 1,
            "etag": '"live-1"',
        }
        cls._prepare_html = report_dashboard.render_dashboard(
            placeholder, live=dict(prepare_live)
        )
        cls._prepare_en_html = report_dashboard.render_dashboard(
            placeholder, live=dict(prepare_live), language="en"
        )
        cls._ready_html = report_dashboard.render_dashboard(
            cls._snap1_wire, live=dict(ready_live)
        )
        refreshing_live = dict(ready_live)
        refreshing_live.update({"refreshing": True, "has_snapshot": True,
                                "checked_at": _CHECKED_AT, "revision": 1})
        cls._refreshing_html = report_dashboard.render_dashboard(
            cls._snap1_wire, live=refreshing_live
        )
        # Legacy live page: backend omits has_snapshot, so the client must infer it.
        cls._legacy_html = report_dashboard.render_dashboard(
            cls._snap1_wire, live={"enabled": True, "interval": 300}
        )
        cls._static_html = report_dashboard.render_dashboard(cls._snap1_wire)

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

    # -- harness --------------------------------------------------------------
    def _open(self, html, default, viewport=None, clock=False):
        state, httpd = _start_server(html)
        state.default = default
        self._httpd = httpd
        self.addCleanup(httpd.shutdown)
        self.addCleanup(httpd.server_close)
        context = self._browser.new_context(
            viewport=viewport or {"width": 1280, "height": 820},
            color_scheme="light",
            reduced_motion="reduce",
        )
        self.addCleanup(context.close)
        page = context.new_page()
        if clock:
            page.clock.install()
        errors, console = [], []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on(
            "console",
            lambda message: console.append(message.text)
            if message.type == "error"
            else None,
        )
        page.goto(
            "http://127.0.0.1:%d/" % httpd.server_port,
            wait_until="load",
        )
        return state, page, errors, console

    @staticmethod
    def _kind(page):
        return page.eval_on_selector(
            "#live-beacon",
            "e=>e.className.replace('seg live-beacon','').trim()",
        )

    def _wait_kind(self, page, kind, timeout=8000):
        page.wait_for_function(
            "(k)=>document.getElementById('live-beacon').className.includes('live-beacon '+k)",
            arg=kind,
            timeout=timeout,
        )

    def _wait_requests(self, state, count, timeout=6.0):
        deadline = time.monotonic() + timeout
        while state.requests() < count and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertGreaterEqual(state.requests(), count)

    @staticmethod
    def _body_live(page):
        return page.eval_on_selector("body", "b=>b.dataset.live||''")

    @staticmethod
    def _rows(page):
        return page.locator("#tbody tr[data-period]").count()

    @staticmethod
    def _force_check(page):
        current = page.eval_on_selector("#live-refresh", "e=>e.value")
        page.select_option("#live-refresh", "60" if current != "60" else "300")

    @staticmethod
    def _total(page):
        text = page.text_content("#k-total").strip().replace(",", "")
        digits = "".join(ch for ch in text if ch.isdigit())
        return int(digits) if digits else 0

    def _wait_rows(self, page, timeout=8000):
        page.wait_for_function(
            "()=>document.querySelectorAll('#tbody tr[data-period]').length>0",
            timeout=timeout,
        )

    # -- 1. first round: shell, then the real snapshot ------------------------
    def test_first_round_prepare_shell_then_live_snapshot(self):
        state, page, errors, console = self._open(self._prepare_html, _prepare())
        page.wait_for_function("()=>document.body.dataset.live==='prepare'")
        self.assertEqual("prepare", self._body_live(page))
        self.assertEqual("正在准备", page.text_content("#live-text").strip())
        self.assertIsNotNone(page.eval_on_selector("#live-prepare", "e=>e.offsetParent"))
        self.assertEqual("false", page.get_attribute("#live-prepare", "aria-hidden"))
        # The data shell must not surface any fake zero: the overview is hidden and
        # no KPI value is painted.
        self.assertIsNone(page.eval_on_selector("#section-overview", "e=>e.offsetParent"))
        self.assertNotRegex(page.text_content("#k-total").strip(), r"\d")
        self.assertGreaterEqual(state.requests(), 1)

        state.push(
            _ready(self._snap1_wire, self._snap1_id, etag='"live-2"', revision=2)
        )
        page.wait_for_function("()=>document.body.dataset.live==='ready'")
        self._wait_rows(page)
        self.assertIsNotNone(page.eval_on_selector("#section-overview", "e=>e.offsetParent"))
        self.assertGreater(int(page.text_content("#k-total").strip().replace(",", "")), 0)
        page.wait_for_function("()=>!document.getElementById('live-checked').hidden")
        self.assertIn("05:00:00", page.text_content("#live-checked"))
        self.assertEqual([], errors)
        self.assertEqual([], console)

    # -- 2. slow background scan over a fast endpoint -------------------------
    def test_slow_background_scan_keeps_endpoint_fast_and_never_offline(self):
        state, page, errors, console = self._open(self._prepare_html, _prepare())
        seen = set()
        deadline = time.monotonic() + 3.2
        while time.monotonic() < deadline:
            seen.add(self._kind(page))
            time.sleep(0.1)
        # The endpoint always answered promptly, so a long scan must never be
        # misreported as a connection failure.
        self.assertNotIn("offline", seen)
        self.assertNotIn("error", seen)
        self.assertTrue(seen <= {"prepare", "scanning"}, seen)
        self.assertGreaterEqual(state.requests(), 3)  # fast 1s poll while preparing
        self.assertEqual("prepare", self._body_live(page))
        self.assertEqual([], errors)

    # -- 3. scan error keeps the last snapshot, then recovers -----------------
    def test_live_snapshot_updates_visible_other_names(self):
        state, page, errors, console = self._open(
            self._ready_html,
            _ready(self._snap1_wire, self._snap1_id, etag='"live-1"', revision=1),
        )
        self._wait_rows(page)
        self.assertFalse(page.locator("#other-model-summary").is_visible())
        base = _records()[0]
        records = _records([
            dict(base, model=f"major-{index}", total=1000,
                 session=f"synthetic-major-{index}") for index in range(7)
        ] + [dict(base, model="glm-5.3-flash", total=13, session="synthetic-flash")])
        payload, wire = _build_wire(records)
        state.push(_ready(wire, payload["snapshot"]["id"], etag='"live-2"', revision=2))
        self._force_check(page)
        page.wait_for_function(
            "()=>document.getElementById('other-model-summary')?.textContent.includes('glm-5.3-flash')"
        )
        self.assertTrue(page.locator("#other-model-summary").is_visible())
        self.assertIn("13 Token", page.locator("#other-model-summary").inner_text())
        self.assertEqual([], errors)
        self.assertEqual([], console)

    def test_scan_error_keeps_last_snapshot_then_recovers(self):
        state, page, errors, console = self._open(
            self._ready_html,
            _ready(self._snap1_wire, self._snap1_id, etag='"live-1"', revision=1),
        )
        self._wait_rows(page)
        before = self._rows(page)
        self.assertGreater(before, 0)

        state.push(
            _error(self._snap1_wire, self._snap1_id, etag='"live-3"', revision=3)
        )
        self._force_check(page)
        self._wait_kind(page, "error")
        self.assertEqual("同步错误", page.text_content("#live-text").strip())
        self.assertEqual(before, self._rows(page))  # last snapshot still shown
        self.assertNotEqual("prepare", self._body_live(page))

        state.push(
            _ready(self._snap2_wire, self._snap2_id, etag='"live-4"', revision=4)
        )
        self._force_check(page)
        page.wait_for_function(
            "()=>{const c=document.getElementById('live-beacon').className;"
            "return c.includes('live-beacon updated')||c.includes('live-beacon live');}"
        )
        self.assertGreater(self._rows(page), 0)
        self.assertEqual([], errors)

    # -- 4. ETag comes from the response header, not from DATA.snapshot.id ----
    def test_response_header_etag_drives_conditional_304(self):
        state, page, errors, console = self._open(
            self._ready_html,
            _ready(self._snap1_wire, self._snap1_id, etag='"live-1"', revision=1),
        )
        self._wait_rows(page)
        # The page embeds the current live etag, so even the first check is
        # conditional and carries the header value (not DATA.snapshot.id).
        self.assertEqual('"live-1"', state.if_none_match[0])

        start = state.requests()
        state.push({"status": 304, "etag": '"live-1"', "body": None})
        self._force_check(page)
        self._wait_requests(state, start + 1)
        sent = state.last_if_none_match()
        self.assertEqual('"live-1"', sent)
        self.assertNotEqual('"%s"' % self._snap1_id, sent)  # header value, not id
        self._wait_kind(page, "live")  # 304 reuses the last body's status
        self.assertGreater(self._rows(page), 0)
        self.assertEqual([], errors)

    # -- 5. unchanged identity: no re-render, filters preserved ---------------
    def test_unchanged_identity_skips_rerender_and_keeps_filter(self):
        state, page, errors, console = self._open(
            self._ready_html,
            _ready(self._snap1_wire, self._snap1_id, etag='"live-1"', revision=1),
        )
        self._wait_rows(page)
        page.wait_for_selector("#filter-none")
        page.click("#filter-none")
        summary = page.text_content("#filter-summary")
        page.evaluate("document.getElementById('tbody').__keep=1")

        start = state.requests()
        state.push(
            _ready(self._snap1_wire, self._snap1_id, etag='"live-1"', revision=1)
        )
        self._force_check(page)
        self._wait_requests(state, start + 1)
        time.sleep(0.4)
        # Same snapshot identity: the table node is reused wholesale, so the
        # expando survives and the lens the user set is untouched.
        self.assertEqual(1, page.evaluate("document.getElementById('tbody').__keep||0"))
        self.assertEqual(summary, page.text_content("#filter-summary"))
        self.assertEqual([], errors)

    # -- 6. pause / resume / hidden tab --------------------------------------
    def test_pause_resume_and_hidden_tab_cancel(self):
        state, page, errors, console = self._open(
            self._ready_html,
            _ready(self._snap1_wire, self._snap1_id, etag='"live-1"', revision=1),
        )
        self._wait_rows(page)

        page.select_option("#live-refresh", "0")
        self._wait_kind(page, "paused")
        self.assertEqual("刷新已暂停", page.text_content("#live-text").strip())
        paused = state.requests()
        time.sleep(1.3)
        self.assertEqual(paused, state.requests())  # pause stops this page polling

        page.select_option("#live-refresh", "60")
        self._wait_requests(state, paused + 1)  # resume checks at once

        page.evaluate(
            "Object.defineProperty(document,'hidden',{configurable:true,get:()=>true});"
            "document.dispatchEvent(new Event('visibilitychange'));"
        )
        hidden = state.requests()
        self._force_check(page)  # a change while hidden must not fetch
        time.sleep(0.8)
        self.assertEqual(hidden, state.requests())

        page.evaluate(
            "Object.defineProperty(document,'hidden',{configurable:true,get:()=>false});"
            "document.dispatchEvent(new Event('visibilitychange'));"
        )
        self._wait_requests(state, hidden + 1)
        self.assertEqual([], errors)

    # -- 7. legacy and static pages ------------------------------------------
    def test_legacy_live_page_without_has_snapshot_field(self):
        state, page, errors, console = self._open(
            self._legacy_html, _legacy(self._snap1_wire, self._snap1_id)
        )
        self._wait_rows(page)
        self.assertEqual("", self._body_live(page))  # never the prepare shell
        self.assertNotEqual("static", self._kind(page))
        self.assertIsNotNone(
            page.eval_on_selector("#live-refresh", "e=>e.offsetParent")
        )
        self.assertEqual([], errors)

    def test_static_page_never_polls_and_shows_static_beacon(self):
        state, page, errors, console = self._open(self._static_html, None)
        self._wait_kind(page, "static")
        self.assertEqual(0, state.requests())
        self.assertIsNone(page.eval_on_selector("#live-refresh", "e=>e.offsetParent"))
        self.assertEqual("", self._body_live(page))
        self.assertEqual("静态快照", page.text_content("#live-text").strip())
        self.assertEqual([], errors)

    # -- 8. bilingual + mobile ------------------------------------------------
    def test_prepare_shell_language_and_mobile_layout(self):
        _s, en_page, en_errors, _c = self._open(self._prepare_en_html, _prepare())
        en_page.wait_for_function("()=>document.body.dataset.live==='prepare'")
        self.assertEqual("Preparing", en_page.text_content("#live-text").strip())
        self.assertIn("Preparing data", en_page.text_content("#live-prepare"))
        self.assertEqual([], en_errors)

        _zs, zh_page, zh_errors, _zc = self._open(self._prepare_html, _prepare())
        zh_page.wait_for_function("()=>document.body.dataset.live==='prepare'")
        self.assertEqual("正在准备", zh_page.text_content("#live-text").strip())
        self.assertNotIn("Preparing", zh_page.text_content("#live-text"))
        self.assertEqual([], zh_errors)

        _ms, mob_page, mob_errors, _mc = self._open(
            self._prepare_html, _prepare(), viewport={"width": 390, "height": 780}
        )
        mob_page.wait_for_function("()=>document.body.dataset.live==='prepare'")
        self.assertTrue(
            mob_page.evaluate(
                "document.documentElement.scrollWidth"
                " <= document.documentElement.clientWidth + 1"
            )
        )
        self.assertIsNotNone(
            mob_page.eval_on_selector("#live-prepare", "e=>e.offsetParent")
        )
        self.assertEqual([], mob_errors)

    # -- 9. regression: strict initial state before the first body arrives ----
    def test_prepare_first_response_304_stays_preparing(self):
        state, page, errors, console = self._open(
            self._prepare_html, {"status": 304, "etag": '"live-0"', "body": None}
        )
        self._wait_requests(state, 2)
        time.sleep(1.2)
        self.assertEqual("prepare", self._kind(page))
        self.assertEqual("prepare", self._body_live(page))
        self.assertEqual("正在准备", page.text_content("#live-text").strip())
        self.assertEqual([], errors)

    def test_ready_refreshing_first_304_keeps_scanning_state(self):
        state, page, errors, console = self._open(
            self._refreshing_html, {"status": 304, "etag": '"live-1"', "body": None}
        )
        self._wait_kind(page, "scanning")
        self.assertEqual("后台扫描中", page.text_content("#live-text").strip())
        self.assertNotIn(self._kind(page), ("live", "prepare"))
        self.assertNotEqual("prepare", self._body_live(page))
        self.assertEqual([], errors)

    def test_ready_frequency_change_before_first_response_keeps_ready(self):
        state, page, errors, console = self._open(
            self._ready_html,
            dict(
                {"delay": 5.0},
                **_ready(self._snap1_wire, self._snap1_id, etag='"live-1"', revision=1)
            ),
        )
        self._wait_rows(page)
        # The ready shell paints at once; while the first check is still in flight
        # the beacon may say "syncing", but never the preparing state.
        self.assertIn(self._kind(page), ("live", "syncing", "updated"))
        page.select_option("#live-refresh", "900")
        time.sleep(0.4)
        self.assertIn(self._kind(page), ("live", "syncing", "updated"))
        self.assertNotEqual("prepare", self._body_live(page))
        self.assertNotEqual("正在准备", page.text_content("#live-text").strip())
        self.assertEqual([], errors)

    # -- 10. unreadable wire: keep last data, reject the bad ETag ------------
    def test_unreadable_wire_keeps_last_data_and_rejects_etag(self):
        state, page, errors, console = self._open(
            self._ready_html,
            _ready(self._snap1_wire, self._snap1_id, etag='"live-1"', revision=1),
        )
        self._wait_rows(page)
        before_rows, before_total = self._rows(page), self._total(page)

        state.push({
            "body": {
                "wire": "not-a-wire",
                "snapshot": self._snap2_id,
                "error": None,
                "has_snapshot": True,
                "refreshing": False,
                "checked_at": _CHECKED_AT,
                "revision": 5,
            },
            "etag": '"live-5"',
        })
        self._force_check(page)
        self._wait_kind(page, "error")
        self.assertEqual("同步错误", page.text_content("#live-text").strip())
        self.assertEqual(before_rows, self._rows(page))  # last data kept
        self.assertEqual(before_total, self._total(page))

        # The corrupt response's ETag must never be adopted.
        start = state.requests()
        self._force_check(page)
        self._wait_requests(state, start + 1)
        self.assertEqual('"live-1"', state.last_if_none_match())

        # ...and a later good snapshot still recovers.
        state.push(_ready(self._snap2_wire, self._snap2_id, etag='"live-6"', revision=6))
        self._force_check(page)
        page.wait_for_function(
            "()=>{const c=document.getElementById('live-beacon').className;"
            "return c.includes('live-beacon updated')||c.includes('live-beacon live');}"
        )
        self.assertGreater(self._rows(page), 0)
        self.assertNotEqual(before_total, self._total(page))
        self.assertEqual([], errors)

    # -- 11. real network failure: keep data, report the disconnect ----------
    def test_network_failure_keeps_last_data_and_reports_disconnect(self):
        state, page, errors, console = self._open(
            self._ready_html,
            _ready(self._snap1_wire, self._snap1_id, etag='"live-1"', revision=1),
        )
        self._wait_rows(page)
        before = self._rows(page)
        state.force_hangup = True  # every request is now reset
        try:
            self._force_check(page)
            self._wait_kind(page, "offline", timeout=10000)
        finally:
            state.force_hangup = False
        self.assertEqual("暂时断开", page.text_content("#live-text").strip())
        self.assertNotIn("同步错误", page.text_content("#live-text"))
        self.assertIn(
            "连接失败", page.get_attribute("#live-beacon", "title")
        )
        self.assertEqual(before, self._rows(page))  # last data kept
        self.assertEqual([], errors)

    # -- 12. fixed 10s watchdog: cancel, then back off -----------------------
    def test_ten_second_watchdog_cancels_the_request_then_backs_off(self):
        state, page, errors, console = self._open(
            self._ready_html,
            dict(
                {"delay": 30.0},
                **_ready(self._snap1_wire, self._snap1_id, etag='"live-1"', revision=1)
            ),
        )
        self._wait_rows(page)
        self._wait_kind(page, "offline", timeout=14000)  # watchdog aborts at 10s
        self.assertEqual(
            "暂时断开（连接超时）", page.get_attribute("#live-beacon", "title")
        )
        cancelled = state.requests()
        time.sleep(2.5)  # backoff (>=30s) must not re-poll immediately
        self.assertEqual(cancelled, state.requests())
        self.assertEqual([], errors)

    # -- 13. idle cadence: default poll_interval and explicit selection ------
    def test_idle_cadence_defaults_to_poll_interval_and_follows_selection(self):
        state, page, errors, console = self._open(
            self._ready_html,
            _ready(self._snap1_wire, self._snap1_id, etag='"live-1"', revision=1),
        )
        self._wait_rows(page)
        self.assertEqual("60", page.eval_on_selector("#live-refresh", "e=>e.value"))
        for seconds in (300, 900, 1800, 60):
            start = state.requests()
            page.select_option("#live-refresh", str(seconds))
            self._wait_requests(state, start + 1)  # an explicit change checks at once
            time.sleep(0.3)
            baseline = state.requests()
            time.sleep(2.6)
            self.assertEqual(
                baseline,
                state.requests(),
                "idle polling for %ss must not be clamped to a faster cadence"
                % seconds,
            )
        self.assertEqual([], errors)

    def test_idle_cadence_is_exact_in_virtual_browser_time(self):
        state, page, errors, console = self._open(
            self._ready_html,
            _ready(self._snap1_wire, self._snap1_id, etag='"live-1"', revision=1),
            clock=True,
        )
        self._wait_rows(page)
        try:
            page.clock.install()
        except Exception as exc:  # pragma: no cover - engine without a clock
            self.skipTest("browser clock is unavailable: %s" % exc)
        start = state.requests()
        self._force_check(page)  # re-arm the idle timer under the virtual clock
        self._wait_requests(state, start + 1)
        time.sleep(0.4)
        for seconds in (300, 900, 1800, 60):
            arm = state.requests()
            page.select_option("#live-refresh", str(seconds))
            self._wait_requests(state, arm + 1)
            time.sleep(0.4)
            baseline = state.requests()
            page.clock.fast_forward(seconds * 1000 - 1000)
            time.sleep(0.4)
            self.assertEqual(baseline, state.requests())
            page.clock.fast_forward(2000)
            self._wait_requests(state, baseline + 1)
        self.assertEqual([], errors)


if __name__ == "__main__":
    unittest.main()
