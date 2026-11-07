"""Live-runtime browser tests for the background-snapshot dashboard.

Independent of ``tests/test_dashboard_runtime.py`` (no inheritance): it builds
its own fixtures, serves a live page from a loopback HTTP server that scripts the
fixed lightweight ``/api/status`` protocol and conditional ``/api/snapshot``
protocol, then drives it in Chromium. Old-backend scenarios default status to
404, while status scenarios queue independent responses and count both paths.

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
from datetime import datetime, timezone
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
_CONFLICT_GUIDANCE = (
    ("modern_response_mismatch",
     "同一现代 response 的用量、模型或计费信息不一致。",
     "Usage, model, or billing information is inconsistent for the same modern response."),
    ("legacy_cumulative_rollback",
     "旧格式累计 total_tokens 回退。",
     "Legacy cumulative total_tokens decreased."),
    ("legacy_anchor_mismatch",
     "同一旧累计锚点的用量、模型或计费信息不一致。",
     "Usage, model, or billing information is inconsistent for the same legacy cumulative anchor."),
    ("cross_file_identity_mismatch",
     "同一用量身份在跨文件记录中的用量、模型或计费信息不一致。",
     "Usage, model, or billing information is inconsistent for the same usage identity across files."),
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


def _build_wire(records, since="2026-07-01", until="2026-07-02"):
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
            since=since,
            until=until,
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


def _scan(**changes):
    scan = {
        "id": 7, "stage": "collection", "outcome": "running",
        "started_at": "2026-07-02T04:59:55+00:00",
        "updated_at": _CHECKED_AT, "elapsed_seconds": 5.25,
        "stage_seconds": {"discovery": 1.25, "collection": 4.0,
                          "payload": 0.0, "encoding": 0.0},
        "discovered": 12, "processed": 8, "cache_hits": 5,
        "parsed": 3, "skipped": 1,
    }
    scan.update(changes)
    return scan


def _status(snapshot, *, refreshing=False, scan=None, **changes):
    body = {
        "snapshot": snapshot, "error": None, "error_details": None,
        "has_snapshot": snapshot is not None, "refreshing": refreshing,
        "checked_at": _CHECKED_AT, "revision": 1, "restored": False,
        "storage_warning": None, "scan": scan,
    }
    body.update(changes)
    return {"body": body}


class _SnapshotState:
    def __init__(self, html):
        self.html = html.encode("utf-8")
        self.queue = []
        self.default = None
        self.count = 0
        self.status_queue = []
        self.status_default = None  # Existing tests exercise the session 404 fallback.
        self.status_count = 0
        self.status_if_none_match = []
        self.force_hangup = False
        self.if_none_match = []
        self._lock = threading.Lock()

    def take(self, status=False):
        with self._lock:
            if status:
                self.status_count += 1
                if self.status_queue:
                    return self.status_queue.pop(0)
                return self.status_default
            self.count += 1
            if self.queue:
                return self.queue.pop(0)
            return self.default

    def push_status(self, *responses):
        with self._lock:
            self.status_queue.extend(responses)

    def status_requests(self):
        with self._lock:
            return self.status_count

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
            path = self.path.split("?")[0]
            if path in ("/api/snapshot", "/api/status"):
                self._snapshot(status=path == "/api/status")
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

        def _snapshot(self, status=False):
            if state.force_hangup:
                return self._drop()
            conditional = self.headers.get("If-None-Match")
            response = state.take(status=status)
            with state._lock:
                (state.status_if_none_match if status else state.if_none_match).append(conditional)
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
            payload = json.dumps(response.get("body"), ensure_ascii=False).encode("utf-8")
            try:
                self.send_response(response.get("status", 200))
                self.send_header("Cache-Control", "no-store")
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
    def _open(self, html, default, viewport=None, clock=False, status_default=None):
        state, httpd = _start_server(html)
        state.default = default
        state.status_default = status_default
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
            and not (message.location.get("url", "").split("?")[0].endswith("/api/status")
                     and "404" in message.text)
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

    def _wait_requests(self, page, state, count, timeout=6.0):
        deadline = time.monotonic() + timeout
        while state.requests() < count and time.monotonic() < deadline:
            # Pump Playwright events, including loopback request routing, while
            # waiting for the server thread to observe the requested count.
            page.wait_for_timeout(20)
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

    def _wait_status(self, page, state, count):
        deadline = time.monotonic() + 6
        while state.status_requests() < count and time.monotonic() < deadline:
            page.wait_for_timeout(20)
        self.assertGreaterEqual(state.status_requests(), count)

    def test_status_same_identity_is_lightweight_and_preserves_chart_nodes(self):
        state, page, errors, console = self._open(
            self._ready_html, None,
            status_default=_status(self._snap1_id, refreshing=True, scan=_scan()),
        )
        self._wait_status(page, state, 1)
        page.wait_for_function("()=>document.getElementById('live-progress')?.hidden===false")
        self.assertEqual(0, state.requests())
        page.evaluate("window.__heldRow=document.querySelector('#tbody tr[data-period]')")
        self._force_check(page)
        self._wait_status(page, state, 2)
        self.assertEqual(0, state.requests())
        self.assertTrue(page.evaluate("window.__heldRow===document.querySelector('#tbody tr[data-period]')"))
        self.assertTrue(all(value is None for value in state.status_if_none_match))
        self.assertEqual([], errors + console)

    def test_status_initial_wire_fetch_uses_actual_snapshot_identity_in_race(self):
        state, page, errors, console = self._open(
            self._prepare_html,
            _ready(self._snap2_wire, self._snap2_id, etag='"actual-b"', revision=3),
            status_default=_status(self._snap1_id),
        )
        self._wait_rows(page)
        self.assertEqual(self._snap2_id, page.evaluate("DATA.snapshot.id"))
        self.assertEqual(1, state.requests())
        state.status_default = _status(self._snap2_id, revision=3)
        before = state.status_requests()
        self._force_check(page)
        self._wait_status(page, state, before + 1)
        self.assertEqual(1, state.requests())
        self.assertEqual([], errors + console)

    def test_status_same_identity_updates_restored_checked_and_storage_without_redraw(self):
        state, page, errors, console = self._open(
            self._ready_html, None, status_default=_status(self._snap1_id),
        )
        self._wait_status(page, state, 1)
        self._wait_kind(page, "live")
        page.evaluate("window.__heldRow=document.querySelector('#tbody tr[data-period]')")
        state.push_status(_status(
            self._snap1_id, restored=True, storage_warning="write_failed",
            checked_at="2026-07-02T05:01:02+00:00", refreshing=True, scan=_scan(),
        ))
        self._force_check(page)
        page.wait_for_function("()=>document.getElementById('live-checked').textContent.includes('05:01:02')")
        self.assertIn("上次成功快照，正在重新验证", page.locator("#live-restored").inner_text())
        self.assertTrue(page.locator("#live-storage-warning").is_visible())
        self.assertTrue(page.evaluate("window.__heldRow===document.querySelector('#tbody tr[data-period]')"))
        page.evaluate("applyLanguage('en',false)")
        self.assertIn("Last successful snapshot, revalidating", page.locator("#live-restored").inner_text())
        self.assertIn("could not be saved", page.locator("#live-storage-warning").inner_text())
        state.push_status(_status(self._snap1_id))
        self._force_check(page)
        page.wait_for_function("()=>document.getElementById('live-restored').hidden")
        self.assertFalse(page.locator("#live-storage-warning").is_visible())
        self.assertEqual(0, state.requests())
        self.assertEqual([], errors + console)

    def test_progress_is_aggregate_quiet_bilingual_and_mobile_safe(self):
        state, page, errors, console = self._open(
            self._prepare_html, None,
            viewport={"width": 390, "height": 844}, clock=True,
            status_default=_status(None, refreshing=True, scan=_scan()),
        )
        self._wait_status(page, state, 1)
        progress = page.locator("#live-progress")
        page.wait_for_function("()=>document.getElementById('live-progress')?.hidden===false")
        self.assertEqual("off", progress.get_attribute("aria-live"))
        self.assertFalse(progress.evaluate("e=>!!e.parentElement.closest('[role=status],[aria-live=polite]')"))
        self.assertIn("已成功处理 8", progress.inner_text())
        self.assertIn("截至当前发现 12", progress.inner_text())
        self.assertIn("UTC", progress.inner_text())
        self.assertNotRegex(progress.inner_text(), r"%|ETA|预计|百分比")
        before = progress.inner_text()
        page.select_option("#live-refresh", "0")
        page.clock.run_for(6000)
        self.assertEqual(before, progress.inner_text())  # no invented local timer
        self.assertFalse(page.locator("#section-overview").is_visible())
        page.locator("#live-progress-details summary").click()
        self.assertIn("warm", progress.inner_text())
        self.assertIn("cold", progress.inner_text())
        self.assertIn("skip", progress.inner_text())
        for language in ("zh", "en"):
            page.evaluate("l=>applyLanguage(l,false)", language)
            for theme in ("light", "dark"):
                page.evaluate("t=>document.documentElement.dataset.theme=t", theme)
                self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth-innerWidth"), 1)
                self.assertTrue(progress.is_visible())
        self.assertIn("Successfully processed 8", progress.inner_text())
        self.assertIn("Discovered so far 12", progress.inner_text())
        self.assertEqual(0, state.requests())
        self.assertEqual([], errors + console)

    def test_error_retry_keeps_error_and_updates_scan_stage_without_reannouncing_counts(self):
        status = _status(self._snap1_id, error=_SCAN_ERROR,
                         refreshing=True, scan=_scan(stage="collection"))
        state, page, errors, console = self._open(self._ready_html, None, status_default=status)
        self._wait_kind(page, "error")
        self.assertIn("上次成功快照", page.locator("#live-prepare").inner_text())
        self.assertIn("采集", page.locator("#live-progress-stage").inner_text())
        page.evaluate("""() => {
            window.__stageChanges=0;
            new MutationObserver(m=>window.__stageChanges+=m.length).observe(
                document.getElementById('live-progress-stage'), {childList:true,subtree:true,characterData:true});
        }""")
        state.push_status(_status(self._snap1_id, error=_SCAN_ERROR, refreshing=True,
                                  scan=_scan(processed=9, elapsed_seconds=6.0)))
        self._force_check(page)
        page.wait_for_function("()=>document.getElementById('live-progress').textContent.includes('已成功处理 9')")
        self.assertEqual("error", self._kind(page))
        self.assertEqual(0, page.evaluate("window.__stageChanges"))
        state.push_status(_status(self._snap1_id, error=_SCAN_ERROR, refreshing=True,
                                  scan=_scan(stage="encoding")))
        self._force_check(page)
        page.wait_for_function("()=>document.getElementById('live-progress-stage').textContent.includes('编码')")
        self.assertEqual(0, state.requests())
        self.assertEqual([], errors + console)

    def test_status_404_falls_back_once_for_the_session(self):
        state, page, errors, console = self._open(
            self._ready_html,
            _ready(self._snap1_wire, self._snap1_id, etag='"live-1"', revision=1),
        )
        self._wait_requests(page, state, 1)
        self.assertEqual(1, state.status_requests())
        self._force_check(page)
        self._wait_requests(page, state, 2)
        self.assertEqual(1, state.status_requests())
        self.assertFalse(page.locator("#live-progress").is_visible())
        self.assertEqual([], errors)

    def test_status_server_error_does_not_enable_legacy_snapshot_polling(self):
        state, page, errors, console = self._open(
            self._ready_html, None, status_default={"status": 503, "body": {}},
        )
        self._wait_kind(page, "offline")
        self.assertEqual(0, state.requests())
        state.status_default = _status(self._snap1_id)
        self._force_check(page)
        self._wait_kind(page, "live")
        self.assertEqual(2, state.status_requests())
        self.assertEqual(0, state.requests())
        self.assertEqual([], errors)

    def test_status_bad_snapshot_wire_rejects_etag_and_retries_actual_wire(self):
        state, page, errors, console = self._open(
            self._ready_html,
            _ready("not-a-wire", self._snap2_id, etag='"bad"', revision=2),
            status_default=_status(self._snap2_id),
        )
        self._wait_kind(page, "error")
        self.assertEqual(self._snap1_id, page.evaluate("DATA.snapshot.id"))
        state.default = _ready(self._snap2_wire, self._snap2_id, etag='"good"', revision=2)
        self._force_check(page)
        page.wait_for_function("id=>DATA.snapshot.id===id", arg=self._snap2_id)
        self.assertEqual('"live-1"', state.last_if_none_match())
        state.status_default = _status(self._snap1_id)
        state.default = _ready(self._snap1_wire, self._snap1_id, etag='"next"', revision=3)
        self._force_check(page)
        page.wait_for_function("id=>DATA.snapshot.id===id", arg=self._snap1_id)
        self.assertEqual('"good"', state.last_if_none_match())
        self.assertEqual([], errors + console)

    def test_status_timeout_never_enables_snapshot_fallback(self):
        state, page, errors, console = self._open(
            self._ready_html, None, clock=True,
            status_default={"delay": 30, **_status(self._snap1_id)},
        )
        self._wait_status(page, state, 1)
        page.clock.run_for(10000)
        self._wait_kind(page, "offline")
        self.assertEqual(0, state.requests())
        state.status_default = _status(self._snap1_id)
        self._force_check(page)
        self._wait_kind(page, "live")
        self.assertEqual(2, state.status_requests())
        self.assertEqual(0, state.requests())
        self.assertEqual([], errors)

    def test_status_pause_and_hidden_cancel_before_snapshot_or_metadata_commit(self):
        state, page, errors, console = self._open(
            self._ready_html,
            _ready(self._snap2_wire, self._snap2_id, etag='"new"', revision=2),
            status_default={"delay": 0.3, **_status(self._snap2_id, restored=True)},
        )
        self._wait_status(page, state, 1)
        page.select_option("#live-refresh", "0")
        page.wait_for_timeout(450)
        self.assertEqual(0, state.requests())
        self.assertEqual(self._snap1_id, page.evaluate("DATA.snapshot.id"))
        self.assertFalse(page.locator("#live-restored").is_visible())
        self.assertEqual("paused", self._kind(page))
        page.select_option("#live-refresh", "60")
        self._wait_status(page, state, 2)
        page.evaluate("""() => {
            Object.defineProperty(document,'hidden',{configurable:true,get:()=>true});
            document.dispatchEvent(new Event('visibilitychange'));
        }""")
        page.wait_for_timeout(450)
        self.assertEqual(0, state.requests())
        self.assertEqual(self._snap1_id, page.evaluate("DATA.snapshot.id"))
        state.status_default = _status(self._snap2_id)
        page.evaluate("""() => {
            Object.defineProperty(document,'hidden',{configurable:true,get:()=>false});
            document.dispatchEvent(new Event('visibilitychange'));
        }""")
        page.wait_for_function("id=>DATA.snapshot.id===id", arg=self._snap2_id)
        self.assertEqual(1, state.requests())
        self.assertEqual([], errors + console)

    def test_initial_live_scan_and_restored_metadata_render_before_status_response(self):
        live = {"enabled": True, "has_snapshot": True, "refreshing": True,
                "snapshot": self._snap1_id, "restored": True,
                "storage_warning": "write_failed", "scan": _scan()}
        html = report_dashboard.render_dashboard(self._snap1_wire, live=live)
        state, page, errors, console = self._open(
            html, None, status_default={"delay": 30, **_status(self._snap1_id)},
        )
        page.select_option("#live-refresh", "0")
        self.assertIn("上次成功快照，正在重新验证", page.locator("#live-restored").inner_text())
        self.assertIn("已成功处理 8", page.locator("#live-progress").inner_text())
        self.assertTrue(page.locator("#live-storage-warning").is_visible())
        self.assertEqual(0, state.requests())
        self.assertEqual([], errors + console)

    def test_restored_without_successful_snapshot_never_manufactures_usage(self):
        state, page, errors, console = self._open(
            self._prepare_html, None,
            status_default=_status(None, restored=True, scan=_scan(), refreshing=True),
        )
        self._wait_status(page, state, 1)
        page.wait_for_function("()=>document.getElementById('live-progress')?.hidden===false")
        self.assertFalse(page.locator("#live-restored").is_visible())
        self.assertFalse(page.locator("#section-overview").is_visible())
        self.assertNotRegex(page.text_content("#k-total").strip(), r"\d")
        self.assertEqual(0, state.requests())
        self.assertEqual([], errors + console)

    def test_status_fast_polling_never_refetches_unchanged_wire(self):
        state, page, errors, console = self._open(
            self._ready_html, None, clock=True,
            status_default=_status(self._snap1_id, refreshing=True, scan=_scan()),
        )
        self._wait_status(page, state, 1)
        self._wait_kind(page, "scanning")
        page.evaluate("""() => {
            window.__liveAnnouncements=0;
            new MutationObserver(m=>window.__liveAnnouncements+=m.length).observe(
                document.getElementById('live-beacon'), {childList:true,subtree:true,characterData:true});
        }""")
        page.clock.run_for(1000)
        self._wait_status(page, state, 2)
        self._wait_kind(page, "scanning")
        page.clock.run_for(1000)
        self._wait_status(page, state, 3)
        self._wait_kind(page, "scanning")
        self.assertEqual(0, page.evaluate("window.__liveAnnouncements"))
        self.assertEqual(0, state.requests())
        self.assertEqual([], errors + console)

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
        ] + [dict(base, model="overflow-small", total=13, session="synthetic-flash")])
        payload, wire = _build_wire(records)
        state.push(_ready(wire, payload["snapshot"]["id"], etag='"live-2"', revision=2))
        self._force_check(page)
        page.wait_for_function(
            "()=>document.getElementById('other-model-summary')?.textContent.includes('overflow-small')"
        )
        self.assertTrue(page.locator("#other-model-summary").is_visible())
        self.assertIn("13 Token", page.locator("#other-model-summary").inner_text())
        self.assertEqual([], errors)
        self.assertEqual([], console)

    def test_first_scan_failure_shows_actionable_notice_without_fake_usage(self):
        failed = _prepare()
        failed["body"].update(error=_SCAN_ERROR, refreshing=False,
                               error_details={"stage": "collection", "source": "codex", "reason": "usage_conflict"})
        state, page, errors, console = self._open(self._prepare_html, failed)
        self._wait_kind(page, "error")
        self.assertIn("尚无可用快照", page.locator("#live-prepare").inner_text())
        self.assertIn("codex", page.locator("#live-prepare").inner_text())
        self.assertIn("usage_conflict", page.locator("#live-prepare").inner_text())
        self.assertIsNone(page.eval_on_selector("#section-overview", "e=>e.offsetParent"))
        page.evaluate("applyLanguage('en',false)")
        self.assertIn("No snapshot available", page.locator("#live-prepare").inner_text())
        self.assertEqual([], errors + console)

    def _assert_conflict_notice(self, page, kind, zh, en):
        notice = page.locator("#live-prepare")
        self.assertTrue(notice.is_visible())
        for language, explanation in (("zh", zh), ("en", en)):
            page.evaluate("l=>applyLanguage(l,false)", language)
            text = notice.inner_text()
            self.assertIn("collection · codex · usage_conflict · " + kind, text)
            self.assertIn(explanation, text)
            for other_kind, other_zh, other_en in _CONFLICT_GUIDANCE:
                if other_kind != kind:
                    self.assertNotIn(other_kind, text)
                    self.assertNotIn(other_zh if language == "zh" else other_en, text)
            self.assertNotIn("synthetic-private-sentinel", page.locator("body").inner_text())
            self.assertNotIn("tokens doctor --source codex", text)
            self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth-innerWidth"), 1)

    def test_anchor_mismatch_groups_initial_live_and_safe_fallbacks(self):
        groups = (
            ("usage", "用量", "usage"), ("model", "模型", "model"),
            ("billing", "计费", "billing"), ("usage_model", "用量、模型", "usage, model"),
            ("usage_billing", "用量、计费", "usage, billing"),
            ("model_billing", "模型、计费", "model, billing"),
            ("usage_model_billing", "用量、模型、计费", "usage, model, billing"),
        )
        base = {"stage": "collection", "source": "codex", "reason": "usage_conflict",
                "conflict_kind": "legacy_anchor_mismatch"}
        for kind, zh, en in groups:
            with self.subTest(kind=kind):
                details = dict(base, mismatch_kind=kind)
                live = {"enabled": True, "has_snapshot": False, "refreshing": False,
                        "error": _SCAN_ERROR, "error_details": details}
                html = report_dashboard.render_dashboard(_build_wire([])[1], live=live)
                state, page, errors, console = self._open(
                    html, None, viewport={"width": 390, "height": 844},
                    status_default={"delay": 30, **_status(None)})
                for language, expected in (("zh", "差异组别：" + zh + "。"),
                                           ("en", "Differing groups: " + en + ".")):
                    page.evaluate("l=>applyLanguage(l,false)", language)
                    self.assertIn(expected, page.locator("#live-prepare").inner_text())
                self.assertFalse(page.locator("#section-overview").is_visible())
                self.assertNotRegex(page.text_content("#k-total").strip(), r"\d")
                self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth-innerWidth"), 1)
                self.assertEqual([], errors + console)
        # Exercise non-JSON values directly; protocol JSON cannot carry prototypes or boxed strings.
        results = page.evaluate("""base => {
          const original=liveDiagnostic(base);
          const values=[undefined,null,'','private-mismatch-sentinel <img src=x>',
            '__proto__','constructor',7,true,['model'],{kind:'model'},new String('model')];
          const invalid=values.every(value=>liveDiagnostic({...base,mismatch_kind:value})===original);
          const inherited=Object.keys({...base,mismatch_kind:'model'}).every(key=>{
            const fields={...base,mismatch_kind:'model'};const value=fields[key];delete fields[key];
            const details=Object.assign(Object.create({[key]:value}),fields);
            return !liveDiagnostic(details).includes('Differing groups:');
          });
          const containers=[null,undefined,[],7,true,'collection'].every(value=>liveDiagnostic(value)==='');
          const wrong=[{conflict_kind:'modern_response_mismatch'},
            {conflict_kind:'legacy_cumulative_rollback'},{conflict_kind:'cross_file_identity_mismatch'},
            {stage:'payload'},{source:'claude'},{reason:'read_failed'}]
            .every(fields=>!liveDiagnostic({...base,...fields,mismatch_kind:'model'}).includes('Differing groups:'));
          return {invalid,inherited,containers,wrong};
        }""", base)
        self.assertEqual({"invalid": True, "inherited": True, "containers": True, "wrong": True}, results)

    def test_anchor_mismatch_groups_status_and_fallback_preserve_then_clear(self):
        kinds = ("usage", "model", "billing", "usage_model", "usage_billing",
                 "model_billing", "usage_model_billing")
        for entry in ("status", "snapshot"):
            with self.subTest(entry=entry):
                state, page, errors, console = self._open(
                    self._ready_html,
                    _ready(self._snap1_wire, self._snap1_id, etag='"live-1"', revision=1),
                    status_default=_status(self._snap1_id) if entry == "status" else None)
                self._wait_kind(page, "live")
                before = (self._rows(page), self._total(page), page.evaluate("liveUi.checkedAt"))
                page.evaluate("window.__mismatchRow=document.querySelector('#tbody tr[data-period]')")
                for revision, kind in enumerate(kinds, 2):
                    details = {"stage": "collection", "source": "codex", "reason": "usage_conflict",
                               "conflict_kind": "legacy_anchor_mismatch", "mismatch_kind": kind}
                    if entry == "status":
                        state.push_status(_status(self._snap1_id, error=_SCAN_ERROR,
                                                  error_details=details, revision=revision))
                    else:
                        reply = _error(self._snap1_wire, self._snap1_id,
                                       etag='"mismatch-%s"' % revision, revision=revision)
                        reply["body"]["error_details"] = details
                        state.push(reply)
                    self._force_check(page)
                    page.wait_for_function("d=>JSON.stringify(liveUi.errorDetails)===d",
                                           arg=json.dumps(details, separators=(",", ":")), polling=50)
                    for language, expected in (("zh", "差异组别："), ("en", "Differing groups:")):
                        page.evaluate("l=>applyLanguage(l,false)", language)
                        self.assertIn(expected, page.locator("#live-prepare").inner_text())
                    self.assertEqual(before, (self._rows(page), self._total(page),
                                              page.evaluate("liveUi.checkedAt")))
                    self.assertEqual(self._snap1_id, page.evaluate("DATA.snapshot.id"))
                    self.assertTrue(page.evaluate("window.__mismatchRow===document.querySelector('#tbody tr[data-period]')"))
                if entry == "status":
                    self.assertEqual(0, state.requests())
                    state.push_status(_status(self._snap1_id, revision=9))
                else:
                    state.push(_ready(self._snap1_wire, self._snap1_id, etag='"live-9"', revision=9))
                self._force_check(page)
                self._wait_kind(page, "live")
                self.assertIsNone(page.evaluate("liveUi.errorDetails"))
                self.assertNotIn("Differing groups:", page.locator("#live-prepare").text_content())
                self.assertEqual([], errors + console)

    def test_usage_conflict_initial_live_is_bilingual_without_fake_usage(self):
        for kind, zh, en in _CONFLICT_GUIDANCE:
            with self.subTest(kind=kind):
                details = {"stage": "collection", "source": "codex", "reason": "usage_conflict",
                           "conflict_kind": kind, "path": "/synthetic-private-sentinel/log.jsonl",
                           "identity": "synthetic-private-sentinel-response"}
                live = {"enabled": True, "has_snapshot": False, "refreshing": False,
                        "error": _SCAN_ERROR, "error_details": details}
                html = report_dashboard.render_dashboard(_build_wire([])[1], live=live)
                state, page, errors, console = self._open(
                    html, None, viewport={"width": 390, "height": 844},
                    status_default={"delay": 30, **_status(None)},
                )
                # The first status reply is held: these details must come from initial LIVE.
                self.assertEqual("error", self._kind(page))
                self.assertEqual(details, page.evaluate("liveUi.errorDetails"))
                self._assert_conflict_notice(page, kind, zh, en)
                self.assertFalse(page.locator("#section-overview").is_visible())
                self.assertNotRegex(page.text_content("#k-total").strip(), r"\d")
                self.assertEqual(0, self._rows(page))
                self.assertEqual(0, state.requests())
                self.assertEqual([], errors + console)

    def test_usage_conflict_status_and_snapshot_fallback_preserve_then_clear(self):
        for entry in ("status", "snapshot"):
            with self.subTest(entry=entry):
                state, page, errors, console = self._open(
                    self._ready_html,
                    _ready(self._snap1_wire, self._snap1_id, etag='"live-1"', revision=1),
                    viewport={"width": 390, "height": 844},
                    status_default=_status(self._snap1_id) if entry == "status" else None,
                )
                self._wait_kind(page, "live")
                before = (self._rows(page), self._total(page), page.evaluate("liveUi.checkedAt"))
                page.evaluate("window.__conflictRow=document.querySelector('#tbody tr[data-period]')")
                for revision, (kind, zh, en) in enumerate(_CONFLICT_GUIDANCE, 2):
                    with self.subTest(kind=kind):
                        details = {"stage": "collection", "source": "codex", "reason": "usage_conflict",
                                   "conflict_kind": kind, "hash": "synthetic-private-sentinel-hash",
                                   "token": "synthetic-private-sentinel-token"}
                        if entry == "status":
                            state.push_status(_status(self._snap1_id, error=_SCAN_ERROR,
                                                      error_details=details, revision=revision))
                        else:
                            failed = _error(self._snap1_wire, self._snap1_id,
                                            etag='"live-%s"' % revision, revision=revision)
                            failed["body"]["error_details"] = details
                            state.push(failed)
                        self._force_check(page)
                        page.wait_for_function("d=>JSON.stringify(liveUi.errorDetails)===d",
                                               arg=json.dumps(details, separators=(",", ":")), polling=50)
                        self._wait_kind(page, "error")
                        self._assert_conflict_notice(page, kind, zh, en)
                        self.assertEqual(before, (self._rows(page), self._total(page),
                                                  page.evaluate("liveUi.checkedAt")))
                        self.assertEqual(self._snap1_id, page.evaluate("DATA.snapshot.id"))
                        self.assertTrue(page.evaluate(
                            "window.__conflictRow===document.querySelector('#tbody tr[data-period]')"))
                        self.assertIn("last successful snapshot", page.locator("#live-prepare").inner_text())
                if entry == "status":
                    self.assertEqual(0, state.requests())
                    state.push_status(_status(self._snap1_id, revision=6))
                else:
                    self.assertEqual(1, state.status_requests())  # The original harness defaults status to 404.
                    state.push(_ready(self._snap1_wire, self._snap1_id, etag='"live-6"', revision=6))
                self._force_check(page)
                self._wait_kind(page, "live")
                self.assertIsNone(page.evaluate("liveUi.errorDetails"))
                self.assertFalse(page.locator("#live-prepare").is_visible())
                for kind, zh, en in _CONFLICT_GUIDANCE:
                    self.assertNotIn(kind, page.locator("body").inner_text())
                    self.assertNotIn(en, page.locator("#live-prepare").text_content())
                self.assertEqual([], errors + console)

    def test_usage_conflict_unknown_types_and_wrong_combinations_are_generic(self):
        base = {"stage": "collection", "source": "codex", "reason": "usage_conflict"}
        unknown = "synthetic-private-sentinel <img src=x onerror=alert(1)>"
        invalid = [None, "", unknown, "__proto__", "constructor", "prototype", "toString",
                   "valueOf", "hasOwnProperty", "__defineGetter__", 7, True,
                   ["modern_response_mismatch"], {"modern_response_mismatch": True}]
        cases = [dict(base), *(dict(base, conflict_kind=value) for value in invalid)]
        cases.extend(dict(base, conflict_kind=kind, **changes)
                     for kind, _, _ in _CONFLICT_GUIDANCE
                     for changes in ({"stage": "payload"}, {"source": "claude"},
                                     {"reason": "decompression_failed"}))
        for entry in ("status", "snapshot"):
            with self.subTest(entry=entry):
                state, page, errors, console = self._open(
                    self._ready_html,
                    _ready(self._snap1_wire, self._snap1_id, etag='"live-1"', revision=1),
                    status_default=_status(self._snap1_id) if entry == "status" else None,
                )
                self._wait_kind(page, "live")
                for revision, details in enumerate(cases, 2):
                    with self.subTest(details=details):
                        if entry == "status":
                            state.push_status(_status(self._snap1_id, error=_SCAN_ERROR,
                                                      error_details=details, revision=revision))
                        else:
                            failed = _error(self._snap1_wire, self._snap1_id,
                                            etag='"generic-%s"' % revision, revision=revision)
                            failed["body"]["error_details"] = details
                            state.push(failed)
                        self._force_check(page)
                        page.wait_for_function("d=>JSON.stringify(liveUi.errorDetails)===d",
                                               arg=json.dumps(details, separators=(",", ":")), polling=50)
                        expected = " · ".join(details[key] for key in ("stage", "source", "reason"))
                        for language in ("zh", "en"):
                            page.evaluate("l=>applyLanguage(l,false)", language)
                            self.assertEqual(expected, page.evaluate("d=>liveDiagnostic(d)", details))
                            text = page.locator("#live-prepare").inner_text()
                            self.assertTrue(text.endswith(expected))
                            self.assertNotIn("synthetic-private-sentinel", page.locator("body").inner_text())
                            self.assertEqual(0, page.locator('#live-prepare img').count())
                # Boxed strings must not be coerced to a fixed code, either.
                self.assertEqual("collection · codex · usage_conflict", page.evaluate("""() =>
                    liveDiagnostic({stage:'collection',source:'codex',reason:'usage_conflict',
                                    conflict_kind:new String('modern_response_mismatch')})"""))
                self.assertEqual([], errors + console)

    def test_usage_conflict_unknown_initial_live_stays_generic(self):
        base = {"stage": "collection", "source": "codex", "reason": "usage_conflict"}
        cases = [dict(base), *(dict(base, conflict_kind=value) for value in (
            "synthetic-private-sentinel <img src=x onerror=alert(1)>", "__proto__", "constructor",
            ["modern_response_mismatch"], {"modern_response_mismatch": True},
        )), dict(base, conflict_kind="modern_response_mismatch", source="claude"),
            dict(base, conflict_kind="legacy_anchor_mismatch", stage="payload"),
            dict(base, conflict_kind="cross_file_identity_mismatch", reason="decompression_failed")]
        for details in cases:
            with self.subTest(details=details):
                live = {"enabled": True, "has_snapshot": False, "refreshing": False,
                        "error": _SCAN_ERROR, "error_details": details}
                html = report_dashboard.render_dashboard(_build_wire([])[1], live=live)
                state, page, errors, console = self._open(
                    html, None, status_default={"delay": 30, **_status(None)},
                )
                expected = " · ".join(details[key] for key in ("stage", "source", "reason"))
                for language in ("zh", "en"):
                    page.evaluate("l=>applyLanguage(l,false)", language)
                    self.assertTrue(page.locator("#live-prepare").inner_text().endswith(expected))
                    self.assertNotIn("synthetic-private-sentinel", page.locator("body").inner_text())
                    self.assertEqual(0, page.locator('#live-prepare img').count())
                self.assertEqual("error", self._kind(page))
                self.assertEqual(0, state.requests())
                self.assertEqual([], errors + console)

    def test_codex_decompressor_notice_is_bilingual_and_clears_on_recovery(self):
        failed = _prepare()
        failed["body"].update(error=_SCAN_ERROR, refreshing=False,
                               error_details={"stage": "collection", "source": "codex",
                                              "reason": "decompressor_unavailable"})
        state, page, errors, console = self._open(
            self._prepare_html, failed, viewport={"width": 390, "height": 844}
        )
        self._wait_kind(page, "error")
        notice = page.locator("#live-prepare")
        self.assertIn("运行环境未找到 zstd", notice.inner_text())
        self.assertIn("tokens doctor --source codex", notice.inner_text())
        self.assertIn("不代表常驻服务", notice.inner_text())
        self.assertIsNone(page.eval_on_selector("#section-overview", "e=>e.offsetParent"))
        page.evaluate("applyLanguage('en',false)")
        self.assertIn("cannot find zstd", notice.inner_text())
        self.assertIn("not necessarily the background service", notice.inner_text())
        self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth-innerWidth"), 1)
        state.push(_ready(self._snap1_wire, self._snap1_id, etag='"live-2"', revision=2))
        self._force_check(page)
        self._wait_rows(page)
        self.assertFalse(notice.is_visible())
        self.assertNotIn("cannot find zstd", notice.inner_text())
        self.assertEqual([], errors + console)

    def test_decompressor_guidance_requires_exact_codes_and_keeps_old_snapshot(self):
        state, page, errors, console = self._open(
            self._ready_html,
            _ready(self._snap1_wire, self._snap1_id, etag='"live-1"', revision=1),
        )
        self._wait_rows(page)
        before = self._rows(page)
        for revision, details in enumerate((
            {"stage": "collection", "source": "codex", "reason": "decompressor_unavailable"},
            {"stage": "collection", "source": "codex", "reason": "decompression_failed"},
            {"stage": "payload", "source": "codex", "reason": "decompressor_unavailable"},
            {"stage": "collection", "source": "claude", "reason": "decompressor_unavailable"},
        ), 2):
            with self.subTest(details=details):
                failed = _error(self._snap1_wire, self._snap1_id,
                                etag='"live-%s"' % revision, revision=revision)
                failed["body"]["error_details"] = details
                state.push(failed)
                self._force_check(page)
                self._wait_kind(page, "error")
                page.wait_for_function(
                    "d=>liveUi.errorDetails?.stage===d.stage&&liveUi.errorDetails?.source===d.source"
                    "&&liveUi.errorDetails?.reason===d.reason", arg=details
                )
                text = page.locator("#live-prepare").inner_text()
                self.assertIn("上次成功快照", text)
                self.assertEqual(revision == 2, "tokens doctor --source codex" in text)
                self.assertEqual(before, self._rows(page))
        self.assertEqual([], errors + console)

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
        self.assertIn("上次成功快照", page.locator("#live-prepare").inner_text())

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
        self._wait_requests(page, state, start + 1)
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
        self._wait_requests(page, state, start + 1)
        time.sleep(0.4)
        # Same snapshot identity: the table node is reused wholesale, so the
        # expando survives and the lens the user set is untouched.
        self.assertEqual(1, page.evaluate("document.getElementById('tbody').__keep||0"))
        self.assertEqual(summary, page.text_content("#filter-summary"))
        self.assertEqual([], errors)

    def test_custom_range_scope_survives_live_snapshot_update(self):
        state, page, errors, console = self._open(
            self._ready_html,
            _ready(self._snap1_wire, self._snap1_id, etag='"live-1"', revision=1),
        )
        self._wait_rows(page)
        # Applying the range through the real #range-date change listener (the
        # native picker and keyboard dismissal are covered by the runtime suite).
        page.evaluate(
            """() => {
                const input = document.getElementById('range-date');
                input.value = '2026-07-01';
                input.dispatchEvent(new Event('change', {bubbles: true}));
            }"""
        )
        page.wait_for_function(
            "()=>state.range==='custom'&&state.rangeDate==='2026-07-01'"
        )
        page.bring_to_front()
        page.wait_for_function("()=>document.visibilityState==='visible'")
        self._wait_kind(page, "live")
        self.assertIn("2026-07-01", page.locator("#daily-tbody").inner_text())
        self.assertNotIn("2026-07-02", page.locator("#daily-tbody").inner_text())
        models_before = page.evaluate("DATA.models.slice()")

        start = state.requests()
        state.push(
            _ready(self._snap2_wire, self._snap2_id, etag='"live-2"', revision=2)
        )
        self._force_check(page)
        self._wait_requests(page, state, start + 1)
        page.wait_for_function("id=>DATA.snapshot.id===id", arg=self._snap2_id)

        self.assertEqual("custom", page.evaluate("state.range"))
        self.assertEqual("2026-07-01", page.evaluate("state.rangeDate"))
        daily = page.locator("#daily-tbody").inner_text()
        self.assertIn("2026-07-01", daily)
        self.assertNotIn("2026-07-02", daily)
        self.assertEqual(models_before, page.evaluate("DATA.models.slice()"))
        self.assertIn("未出现", page.locator("#glm-compare").inner_text())
        self.assertEqual([], errors)
        self.assertEqual([], console)

    def test_relative_range_rolls_over_on_unchanged_live_responses(self):
        state, page, errors, console = self._open(
            self._ready_html,
            _ready(self._snap1_wire, self._snap1_id, etag='"live-1"', revision=1),
        )
        self._wait_rows(page)
        page.bring_to_front()
        page.wait_for_function("()=>document.visibilityState==='visible'")
        self._wait_requests(page, state, 1)
        self._wait_kind(page, "live")
        # Keep the reporting calendar deterministic without changing snapshot
        # identity or replacing the production range/check implementations.
        page.evaluate("DATA.snapshot.timezone='UTC'")
        page.clock.set_fixed_time(datetime(2026, 7, 2, 23, 59, tzinfo=timezone.utc))
        page.locator('#range-presets [data-range="today"]').click()
        page.wait_for_function("()=>state.range==='today'&&rangeInfo().since==='2026-07-02'")
        page.evaluate("document.getElementById('daily-table-details').open=true")
        self.assertIn("2026-07-02", page.locator("#daily-tbody").inner_text())
        self.assertNotIn("2026-07-01", page.locator("#daily-tbody").inner_text())
        models_before = page.evaluate("[...state.models]")

        for day, response in (
            (3, {"status": 304, "etag": '"live-1"', "body": None}),
            (4, _ready(self._snap1_wire, self._snap1_id, etag='"live-1"', revision=1)),
        ):
            page.clock.set_fixed_time(datetime(2026, 7, day, 0, 1, tzinfo=timezone.utc))
            start = state.requests()
            state.push(response)
            self._force_check(page)
            self._wait_requests(page, state, start + 1)
            expected = "2026-07-%02d" % day
            page.wait_for_function(
                "day=>state.renderedRangeStateKey.includes('|'+day+'|'+day+'|')",
                arg=expected,
            )
            self._wait_kind(page, "live")
            self.assertIn(expected, page.locator("#range-ledger").inner_text())
            self.assertNotIn("2026-07-02", page.locator("#daily-tbody").inner_text())
            self.assertEqual(self._snap1_id, page.evaluate("DATA.snapshot.id"))
            self.assertEqual(models_before, page.evaluate("[...state.models]"))

        page.locator('#range-presets [data-range="yesterday"]').click()
        page.clock.set_fixed_time(datetime(2026, 7, 5, 0, 1, tzinfo=timezone.utc))
        page.locator('#range-presets [data-range="yesterday"]').click()
        self.assertIn("2026-07-04", page.locator("#range-ledger").inner_text())
        self.assertEqual([], errors)
        self.assertEqual([], console)

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
        self._wait_requests(page, state, paused + 1)  # resume checks at once

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
        self._wait_requests(page, state, hidden + 1)
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
        self._wait_requests(page, state, 2)
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
        self._wait_requests(page, state, start + 1)
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
            self._wait_requests(page, state, start + 1)  # an explicit change checks at once
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
        self._wait_requests(page, state, start + 1)
        time.sleep(0.4)
        for seconds in (300, 900, 1800, 60):
            arm = state.requests()
            page.select_option("#live-refresh", str(seconds))
            self._wait_requests(page, state, arm + 1)
            time.sleep(0.4)
            baseline = state.requests()
            page.clock.fast_forward(seconds * 1000 - 1000)
            time.sleep(0.4)
            self.assertEqual(baseline, state.requests())
            page.clock.fast_forward(2000)
            self._wait_requests(page, state, baseline + 1)
        self.assertEqual([], errors)


    @staticmethod
    def _force_check_without_focus(page):
        # Same poll trigger as _force_check, but without focusing the select,
        # so a live re-render can be checked for in-calendar focus restoration.
        page.evaluate(
            """() => {
              const select=document.getElementById('live-refresh');
              select.value = select.value === '60' ? '300' : '60';
              select.dispatchEvent(new Event('change', {bubbles: true}));
            }"""
        )

    @staticmethod
    def _calendar_record(day, model, total, session):
        quarter = total // 4
        return {
            "source": "claude",
            "ts": day + "T09:00:00+08:00",
            "date": day,
            "model": model,
            "input": total - 2 * quarter,
            "output": quarter,
            "cache_read": quarter,
            "cache_write": 0,
            "total": total,
            "session": session,
            "cwd": "/synthetic/calendar-fixture",
        }

    def test_calendar_live_snapshot_updates_visible_month_without_jumping(self):
        records = [
            self._calendar_record("2026-05-05", "model-a", 7, "synthetic-cal-may"),
            self._calendar_record("2026-05-05", "model-b", 3, "synthetic-cal-may-b"),
            self._calendar_record("2026-06-02", "model-a", 100, "synthetic-cal-june"),
            self._calendar_record("2026-06-02", "model-b", 5, "synthetic-cal-june-b"),
            self._calendar_record("2026-06-10", "model-a", 50, "synthetic-cal-focus"),
            self._calendar_record("2026-06-10", "model-b", 4, "synthetic-cal-focus-b"),
        ]
        payload, wire = _build_wire(records, since="2026-05-01", until="2026-06-30")
        snapshot_id = payload["snapshot"]["id"]
        html = report_dashboard.render_dashboard(
            wire,
            live={
                "enabled": True, "interval": 300, "poll_interval": 60,
                "has_snapshot": True, "refreshing": False,
                "checked_at": _CHECKED_AT, "error": None,
                "snapshot": snapshot_id, "revision": 1, "etag": '"cal-1"',
            },
        )
        state, page, errors, console = self._open(
            html,
            _ready(wire, snapshot_id, etag='"cal-1"', revision=1),
        )
        page.wait_for_function(
            "()=>typeof calendarState!=='undefined'&&"
            "calendarState.month==='2026-06'&&"
            "calendarState.stripEnd==='2026-06-10'&&"
            "document.querySelectorAll('#daily-date-strip [data-strip-day]')"
            ".length===7"
        )
        self.assertFalse(
            page.locator("#daily-calendar-picker").evaluate("e=>e.open")
        )
        initial_strip = page.evaluate(
            "({end:calendarState.stripEnd,days:[...document.querySelectorAll("
            "'#daily-date-strip [data-strip-day]')].map(e=>e.dataset.stripDay)})"
        )
        self.assertEqual(
            ["2026-06-04", "2026-06-05", "2026-06-06", "2026-06-07",
             "2026-06-08", "2026-06-09", "2026-06-10"],
            initial_strip["days"],
        )
        page.evaluate("setModels(new Set(['model-a']))")
        page.wait_for_function(
            "()=>state.models.size===1&&state.models.has('model-a')"
        )
        self.assertEqual(
            initial_strip,
            page.evaluate(
                "({end:calendarState.stripEnd,days:[...document.querySelectorAll("
                "'#daily-date-strip [data-strip-day]')].map(e=>e.dataset.stripDay)})"
            ),
            "model filtering must not re-anchor the strip",
        )
        page.locator("#daily-calendar-toggle").click()
        page.wait_for_function(
            "()=>document.querySelector('#daily-calendar-picker').open&&"
            "calendarState.renderedMonth==='2026-06'"
        )
        before = page.evaluate(
            "()=>{const data=calendarMonthData(DATA.day,[...state.models],"
            "'2026-06',DATA.snapshot.coverage,rangeInfo());"
            "return {selectedModels:data.selectedModels,"
            "cell:data.cells.find(item=>item.day==='2026-06-10')};}"
        )
        self.assertEqual(["model-a"], before["selectedModels"])
        self.assertEqual("50", before["cell"]["tokens"])
        self.assertTrue(before["cell"]["tokensExact"])
        self.assertEqual("known", before["cell"]["tokenStatus"])
        page.evaluate(
            "window.__liveCalendarPickerForTest="
            "document.querySelector('#daily-calendar-picker')"
        )
        page.locator('[data-calendar-day="2026-06-10"]').focus()
        scope = page.evaluate(
            "({range:state.range,date:state.rangeDate,"
            "models:[...state.models].sort()})"
        )

        updated = records + [
            self._calendar_record(
                "2026-06-10", "model-a", 25, "synthetic-cal-focus"
            ),
            self._calendar_record(
                "2026-06-20", "model-a", 20, "synthetic-cal-late"
            ),
            self._calendar_record(
                "2026-06-20", "model-b", 30, "synthetic-cal-late-b"
            ),
        ]
        payload2, wire2 = _build_wire(
            updated, since="2026-05-01", until="2026-06-30"
        )
        snapshot_id2 = payload2["snapshot"]["id"]
        state.push(
            _ready(wire2, snapshot_id2, etag='"cal-2"', revision=2)
        )
        self._force_check_without_focus(page)
        page.wait_for_function(
            "id=>DATA.snapshot&&DATA.snapshot.id===id", arg=snapshot_id2
        )
        page.wait_for_function(
            "()=>{const cell=document.querySelector("
            "'[data-calendar-day=\"2026-06-10\"]');return cell&&"
            "((cell.getAttribute('aria-label')||'')+' '+"
            "(cell.getAttribute('title')||'')+' '+cell.textContent)"
            ".includes('75');}"
        )
        self.assertEqual("2026-06", page.evaluate("calendarState.month"))
        self.assertEqual("2026-06", page.evaluate("calendarState.renderedMonth"))
        self.assertFalse(page.evaluate("calendarState.manual"))
        self.assertEqual(
            initial_strip,
            page.evaluate(
                "({end:calendarState.stripEnd,days:[...document.querySelectorAll("
                "'#daily-date-strip [data-strip-day]')].map(e=>e.dataset.stripDay)})"
            ),
            "newer live records must not move an initialized strip",
        )
        self.assertTrue(
            page.locator("#daily-calendar-picker").evaluate("e=>e.open")
        )
        self.assertTrue(page.evaluate(
            "window.__liveCalendarPickerForTest==="
            "document.querySelector('#daily-calendar-picker')"
        ), "live redraw must retain the same native details node")
        self.assertIn("75", page.locator(
            '#daily-date-strip [data-strip-day="2026-06-10"]'
        ).get_attribute("aria-label"))
        self.assertEqual(
            "2026-06-10",
            page.evaluate("document.activeElement.dataset.calendarDay"),
            "live update must restore focus inside the visible month",
        )
        self.assertEqual(
            scope,
            page.evaluate(
                "({range:state.range,date:state.rangeDate,"
                "models:[...state.models].sort()})"
            ),
            "live data must not change range or model selection",
        )
        coverage = page.evaluate(
            "()=>({first:DATA.snapshot.coverage.first_day,"
            "last:DATA.snapshot.coverage.last_day})"
        )
        self.assertEqual("2026-05-05", coverage["first"])
        self.assertEqual("2026-06-20", coverage["last"])
        after = page.evaluate(
            "()=>{const data=calendarMonthData(DATA.day,[...state.models],"
            "'2026-06',DATA.snapshot.coverage,rangeInfo());"
            "return {selectedModels:data.selectedModels,"
            "cell:data.cells.find(item=>item.day==='2026-06-20')};}"
        )
        cell = after["cell"]
        self.assertEqual(["model-a"], after["selectedModels"])
        self.assertTrue(cell["hasRecord"])
        self.assertTrue(cell["inCoverage"])
        self.assertEqual("known", cell["tokenStatus"])
        self.assertTrue(cell["tokensExact"])
        self.assertEqual("20", cell["tokens"])
        self.assertIn("2026", page.locator("#daily-calendar-month").inner_text())
        self.assertEqual([], errors)
        self.assertEqual([], console)

    def test_calendar_live_reanchors_only_when_statistical_range_changes(self):
        records = [
            self._calendar_record("2026-05-05", "model-a", 7, "synthetic-cal-may"),
            self._calendar_record("2026-05-05", "model-b", 3, "synthetic-cal-may-b"),
            self._calendar_record("2026-06-02", "model-a", 100, "synthetic-cal-june"),
            self._calendar_record("2026-06-02", "model-b", 5, "synthetic-cal-june-b"),
            self._calendar_record("2026-06-10", "model-a", 50, "synthetic-cal-focus"),
            self._calendar_record("2026-06-10", "model-b", 4, "synthetic-cal-focus-b"),
        ]
        payload, wire = _build_wire(records, since="2026-05-01", until="2026-06-30")
        snapshot_id = payload["snapshot"]["id"]
        html = report_dashboard.render_dashboard(
            wire,
            live={
                "enabled": True, "interval": 300, "poll_interval": 60,
                "has_snapshot": True, "refreshing": False,
                "checked_at": _CHECKED_AT, "error": None,
                "snapshot": snapshot_id, "revision": 1, "etag": '"cal-1"',
            },
        )
        state, page, errors, console = self._open(
            html,
            _ready(wire, snapshot_id, etag='"cal-1"', revision=1),
        )
        page.wait_for_function(
            "()=>typeof calendarState!=='undefined'&&"
            "calendarState.month==='2026-06'&&"
            "calendarState.stripEnd==='2026-06-10'&&"
            "document.querySelectorAll('#daily-date-strip [data-strip-day]')"
            ".length===7"
        )
        self.assertFalse(
            page.locator("#daily-calendar-picker").evaluate("e=>e.open")
        )
        initial_strip = page.evaluate(
            "({end:calendarState.stripEnd,days:[...document.querySelectorAll("
            "'#daily-date-strip [data-strip-day]')].map(e=>e.dataset.stripDay)})"
        )
        self.assertEqual(
            ["2026-06-04", "2026-06-05", "2026-06-06", "2026-06-07",
             "2026-06-08", "2026-06-09", "2026-06-10"],
            initial_strip["days"],
        )
        page.evaluate("setModels(new Set(['model-a']))")
        page.wait_for_function(
            "()=>state.models.size===1&&state.models.has('model-a')"
        )
        self.assertEqual(
            initial_strip,
            page.evaluate(
                "({end:calendarState.stripEnd,days:[...document.querySelectorAll("
                "'#daily-date-strip [data-strip-day]')].map(e=>e.dataset.stripDay)})"
            ),
        )
        page.evaluate("applyRange('custom','2026-05-20')")
        page.wait_for_function(
            "()=>state.rangeDate==='2026-05-20'&&"
            "calendarState.month==='2026-05'&&!calendarState.manual&&"
            "calendarState.stripEnd==='2026-05-20'"
        )
        custom_strip = page.evaluate(
            "({end:calendarState.stripEnd,days:[...document.querySelectorAll("
            "'#daily-date-strip [data-strip-day]')].map(e=>e.dataset.stripDay)})"
        )
        self.assertEqual(
            ["2026-05-14", "2026-05-15", "2026-05-16", "2026-05-17",
             "2026-05-18", "2026-05-19", "2026-05-20"],
            custom_strip["days"],
        )
        self.assertFalse(
            page.locator("#daily-calendar-picker").evaluate("e=>e.open")
        )
        page.locator("#daily-calendar-toggle").click()
        page.wait_for_function(
            "()=>document.querySelector('#daily-calendar-picker').open&&"
            "calendarState.renderedMonth==='2026-05'"
        )
        page.locator("#daily-calendar-prev").click()
        page.wait_for_function(
            "()=>calendarState.month==='2026-04'&&calendarState.manual"
        )
        self.assertEqual(
            custom_strip,
            page.evaluate(
                "({end:calendarState.stripEnd,days:[...document.querySelectorAll("
                "'#daily-date-strip [data-strip-day]')].map(e=>e.dataset.stripDay)})"
            ),
            "manual month navigation must not move the strip",
        )
        page.evaluate(
            "window.__liveCalendarPickerForTest="
            "document.querySelector('#daily-calendar-picker')"
        )
        scope = page.evaluate(
            "({range:state.range,date:state.rangeDate,"
            "models:[...state.models].sort()})"
        )
        page.locator('[data-calendar-day="2026-04-15"]').focus()
        page.evaluate("applyTheme('dark')")
        page.evaluate("applyLanguage('en', false)")
        page.wait_for_function(
            "()=>calendarState.month==='2026-04'&&"
            "document.activeElement.dataset.calendarDay==='2026-04-15'"
        )
        self.assertEqual("2026-04", page.evaluate("calendarState.month"))
        self.assertTrue(
            page.locator("#daily-calendar-picker").evaluate("e=>e.open")
        )
        self.assertTrue(page.evaluate(
            "window.__liveCalendarPickerForTest==="
            "document.querySelector('#daily-calendar-picker')"
        ))
        self.assertEqual(
            custom_strip,
            page.evaluate(
                "({end:calendarState.stripEnd,days:[...document.querySelectorAll("
                "'#daily-date-strip [data-strip-day]')].map(e=>e.dataset.stripDay)})"
            ),
            "theme/language redraw must retain the date window",
        )
        self.assertEqual(
            "2026-04-15",
            page.evaluate("document.activeElement.dataset.calendarDay"),
            "theme/language must not move or defocus the browsed month",
        )

        payload2, wire2 = _build_wire(
            records + [
                self._calendar_record(
                    "2026-05-06", "model-b", 30, "synthetic-cal-new"
                )
            ],
            since="2026-05-01",
            until="2026-06-30",
        )
        snapshot_id2 = payload2["snapshot"]["id"]
        state.push(
            _ready(wire2, snapshot_id2, etag='"cal-2"', revision=2)
        )
        self._force_check_without_focus(page)
        page.wait_for_function(
            "id=>DATA.snapshot&&DATA.snapshot.id===id", arg=snapshot_id2
        )
        self.assertEqual("2026-04", page.evaluate("calendarState.month"))
        self.assertTrue(page.evaluate("calendarState.manual"))
        self.assertTrue(
            page.locator("#daily-calendar-picker").evaluate("e=>e.open")
        )
        self.assertTrue(page.evaluate(
            "window.__liveCalendarPickerForTest==="
            "document.querySelector('#daily-calendar-picker')"
        ))
        self.assertEqual(
            custom_strip,
            page.evaluate(
                "({end:calendarState.stripEnd,days:[...document.querySelectorAll("
                "'#daily-date-strip [data-strip-day]')].map(e=>e.dataset.stripDay)})"
            ),
            "live redraw must keep the range-anchored strip and open picker",
        )
        self.assertEqual(
            "2026-04-15",
            page.evaluate("document.activeElement.dataset.calendarDay"),
        )
        self.assertEqual(
            scope,
            page.evaluate(
                "({range:state.range,date:state.rangeDate,"
                "models:[...state.models].sort()})"
            ),
            "live data must not re-anchor or change the statistical scope",
        )

        # Re-applying the same effective range is not a range-key change, even
        # after a live refresh and a manual month browse.
        page.evaluate("applyRange('custom','2026-05-20')")
        self.assertEqual("2026-04", page.evaluate("calendarState.month"))
        self.assertTrue(page.evaluate("calendarState.manual"))
        self.assertEqual(
            custom_strip,
            page.evaluate(
                "({end:calendarState.stripEnd,days:[...document.querySelectorAll("
                "'#daily-date-strip [data-strip-day]')].map(e=>e.dataset.stripDay)})"
            ),
        )
        self.assertTrue(
            page.locator("#daily-calendar-picker").evaluate("e=>e.open")
        )

        page.evaluate("applyRange('custom','2026-06-02')")
        page.wait_for_function(
            "()=>state.rangeDate==='2026-06-02'&&"
            "calendarState.month==='2026-06'&&!calendarState.manual&&"
            "calendarState.stripEnd==='2026-06-02'"
        )
        self.assertEqual(
            ["2026-05-27", "2026-05-28", "2026-05-29", "2026-05-30",
             "2026-05-31", "2026-06-01", "2026-06-02"],
            page.locator("#daily-date-strip [data-strip-day]").evaluate_all(
                "els=>els.map(e=>e.dataset.stripDay)"
            ),
        )
        self.assertTrue(
            page.locator("#daily-calendar-picker").evaluate("e=>e.open"),
            "changing the range outside day activation must not close details",
        )
        self.assertEqual([], errors)
        self.assertEqual([], console)
if __name__ == "__main__":
    unittest.main()
