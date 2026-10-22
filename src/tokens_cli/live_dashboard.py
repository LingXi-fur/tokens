"""Loopback-only live Dashboard server.

The server never scans logs while answering a request. A single background
daemon thread owns the periodic scan; the HTTP handlers only read the most
recently published in-memory snapshot under a short state lock, so ``/`` and
``/api/snapshot`` stay fast even while a scan is running or blocked.
"""
import json
import os
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from . import dashboard_payload, dashboard_wire, readers, report_dashboard


_SCAN_FAILED_ERROR = (
    "The local log scan failed; the last successful snapshot is still shown."
)
_SCAN_THREAD_NAME = "tokens-live-scan"
_STOP_JOIN_TIMEOUT = 5.0
_MAX_CLIENT_POLL_SECONDS = 60


def _utc_timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class LiveDashboard:
    def __init__(self, sources, since=None, until=None, anonymize=False, use_cache=True):
        self.sources = list(sources)
        self.since = since
        self.until = until
        self.anonymize = anonymize
        self.use_cache = use_cache
        self._aliases = dashboard_payload._ReportAliases() if anonymize else None
        self._signature = None
        self._wire = None
        self._snapshot_id = None
        self._error = None
        self._checked_at = None
        self._has_snapshot = False
        self._refreshing = False
        self._revision = 0
        # ``_lock`` only guards the atomic publish/read of the small state above.
        # ``_work_lock`` serializes the heavy scan and is taken non-blocking so a
        # new scan request is dropped instead of queueing behind a running one.
        self._lock = threading.Lock()
        self._work_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._scan_thread = None
        # Render shell for the very first page before any real scan succeeded.
        # Built with explicit empty records and an explicit empty title map, so
        # it never reads raw session titles. It is never published as a snapshot.
        self._placeholder_wire = dashboard_wire.encode_payload(
            dashboard_payload.build_payload(
                [],
                since=self.since,
                until=self.until,
                sources=self.sources,
                anonymize=self.anonymize,
                aliases=self._aliases,
                session_titles={},
            )
        )

    # -- background lifecycle -------------------------------------------------
    def start(self, interval):
        """Start the single scan thread; the first scan runs immediately."""
        if self._scan_thread is not None and self._scan_thread.is_alive():
            return
        self._stop_event.clear()
        self._scan_thread = threading.Thread(
            target=self._scan_loop,
            args=(float(interval),),
            name=_SCAN_THREAD_NAME,
            daemon=True,
        )
        self._scan_thread.start()

    def stop(self, timeout=_STOP_JOIN_TIMEOUT):
        """Wake the scan thread and stop scheduling new scans.

        A scan already blocked inside file parsing is not forcibly cancelled;
        the daemon thread is joined with a bounded timeout and will not start
        another scan once the in-flight one returns.
        """
        self._stop_event.set()
        thread = self._scan_thread
        if thread is not None:
            thread.join(timeout)
            # Keep the reference while the daemon is still alive so a later
            # ``start`` cannot clear the stop event and spawn a second loop.
            if not thread.is_alive():
                self._scan_thread = None

    def _scan_loop(self, interval):
        while not self._stop_event.is_set():
            self.refresh()
            if self._stop_event.wait(interval):
                break

    # -- scanning -------------------------------------------------------------
    def _file_signature(self):
        entries = []
        for source in self.sources:
            files_fn, _ = readers.SOURCES[source]
            try:
                paths = files_fn()
            except OSError:
                if source == "claude":
                    raise readers.CollectionIncompleteError(source, "discovery_failed") from None
                paths = []
            for path in paths:
                if source == "claude":
                    try:
                        stat_result = os.lstat(path)
                    except OSError:
                        raise readers.CollectionIncompleteError(source, "stat_failed") from None
                    # Include rejected Claude objects too: their replacement or
                    # removal must invalidate the last successful scan.
                    entries.append((source, path, stat_result.st_mtime_ns,
                                    stat_result.st_size, stat_result.st_dev,
                                    stat_result.st_ino, stat_result.st_mode,
                                    stat_result.st_ctime_ns,
                                    readers._safe_to_parse(path, stat_result, source=source)))
                    continue
                try:
                    stat_result = os.stat(path)
                except OSError:
                    continue
                if not readers._safe_to_parse(path, stat_result, source=source):
                    continue
                entries.append((source, path, stat_result.st_mtime_ns, stat_result.st_size))
        return tuple(sorted(entries))

    def refresh(self, force=False):
        """Run one scan and publish it atomically.

        Returns ``True`` when the published snapshot identity changed. Returns
        ``False`` when the work lock is already held (no queueing), when the
        file signature is unchanged, or when the scan failed.
        """
        if not self._work_lock.acquire(blocking=False):
            return False
        try:
            with self._lock:
                self._refreshing = True
                self._revision += 1
            try:
                # stat / read / build / encode all happen outside the state
                # lock, and any failure here (not just OSError) is contained so
                # the background loop can never die on a bad signature.
                signature = self._file_signature()
                with self._lock:
                    if (not force and self._error is None
                            and signature == self._signature and self._wire is not None):
                        # Unchanged files are still a successful check: clear
                        # any stale error and advance the time and revision.
                        self._error = None
                        self._checked_at = _utc_timestamp()
                        self._refreshing = False
                        self._revision += 1
                        return False
                records = readers.read_all(sources=self.sources, use_cache=self.use_cache)
                payload = dashboard_payload.build_payload(
                    records,
                    since=self.since,
                    until=self.until,
                    sources=self.sources,
                    anonymize=self.anonymize,
                    aliases=self._aliases,
                )
                wire = dashboard_wire.encode_payload(payload)
                snapshot_id = payload["snapshot"]["id"]
            except Exception:
                # Keep the last successful wire/snapshot; only a generic local
                # message is exposed so private paths never leak.
                with self._lock:
                    self._error = _SCAN_FAILED_ERROR
                    self._refreshing = False
                    self._revision += 1
                return False
            with self._lock:
                changed = snapshot_id != self._snapshot_id
                self._signature = signature
                self._error = None
                self._checked_at = _utc_timestamp()
                self._has_snapshot = True
                if changed or self._wire is None:
                    self._wire = wire
                    self._snapshot_id = snapshot_id
                self._refreshing = False
                self._revision += 1
            return changed
        finally:
            self._work_lock.release()

    # -- request-time reads (never scan) -------------------------------------
    def page(self, interval):
        with self._lock:
            wire = self._wire if self._wire is not None else self._placeholder_wire
            live = {
                "enabled": True,
                "interval": interval,
                "poll_interval": min(_MAX_CLIENT_POLL_SECONDS, interval),
                "has_snapshot": self._has_snapshot,
                "refreshing": self._refreshing,
                "checked_at": self._checked_at,
                "error": self._error,
                "snapshot": self._snapshot_id,
                "revision": self._revision,
                "etag": f'"live-{self._revision}"',
            }
        # Rendering happens outside the state lock, on an already-captured wire.
        return report_dashboard.render_dashboard(wire, live=live)

    def response(self):
        with self._lock:
            revision = self._revision
            return {
                "wire": self._wire,
                "snapshot": self._snapshot_id,
                "error": self._error,
                "has_snapshot": self._has_snapshot,
                "refreshing": self._refreshing,
                "checked_at": self._checked_at,
                "revision": revision,
                "etag": f'"live-{revision}"',
            }


class LiveDashboardServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, port, dashboard, interval):
        self.dashboard = dashboard
        self.interval = interval
        super().__init__(("127.0.0.1", port), LiveDashboardHandler)
        dashboard.start(interval)

    def server_close(self):
        try:
            self.dashboard.stop()
        finally:
            super().server_close()


class LiveDashboardHandler(BaseHTTPRequestHandler):
    server_version = "tokens-live"
    sys_version = ""

    def _allowed_request(self):
        expected = f"127.0.0.1:{self.server.server_port}"
        if self.headers.get("Host") != expected:
            return False
        origin = self.headers.get("Origin")
        return origin is None or origin == f"http://{expected}"

    def _headers(self, status, content_type, length=0, etag=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Content-Security-Policy", "frame-ancestors 'none'")
        if etag:
            self.send_header("ETag", etag)
        self.end_headers()

    def do_GET(self):
        # A client that navigates away cancels its request; drop that quietly at
        # this boundary without masking any other error.
        try:
            self._handle_get()
        except (BrokenPipeError, ConnectionResetError):
            return

    def _handle_get(self):
        if not self._allowed_request():
            self._headers(403, "text/plain; charset=utf-8")
            return
        path = urlsplit(self.path).path
        if path == "/":
            body = self.server.dashboard.page(self.server.interval).encode("utf-8")
            self._headers(200, "text/html; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        if path == "/api/snapshot":
            response = self.server.dashboard.response()
            etag = response.get("etag") or f'"live-{response.get("revision", 0)}"'
            if self.headers.get("If-None-Match") == etag and not response.get("error"):
                self._headers(304, "application/json; charset=utf-8", etag=etag)
                return
            body = json.dumps(response, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            self._headers(200, "application/json; charset=utf-8", len(body), etag)
            self.wfile.write(body)
            return
        self._headers(404, "text/plain; charset=utf-8")

    def log_message(self, format_string, *args):
        return


def create_server(port, sources, since=None, until=None, anonymize=False,
                  use_cache=True, interval=300.0):
    dashboard = LiveDashboard(
        sources,
        since=since,
        until=until,
        anonymize=anonymize,
        use_cache=use_cache,
    )
    return LiveDashboardServer(port, dashboard, interval)
