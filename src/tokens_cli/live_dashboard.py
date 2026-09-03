"""Loopback-only live Dashboard server."""
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from . import dashboard_payload, dashboard_wire, readers, report_dashboard


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
        self._lock = threading.Lock()

    def _file_signature(self):
        entries = []
        for source in self.sources:
            files_fn, _ = readers.SOURCES[source]
            try:
                paths = files_fn()
            except OSError:
                paths = []
            for path in paths:
                try:
                    stat_result = os.stat(path)
                except OSError:
                    continue
                if not readers._safe_to_parse(path, stat_result):
                    continue
                entries.append((source, path, stat_result.st_mtime_ns, stat_result.st_size))
        return tuple(sorted(entries))

    def refresh(self, force=False):
        with self._lock:
            try:
                signature = self._file_signature()
                if not force and signature == self._signature and self._wire is not None:
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
                snapshot_id = payload["snapshot"]["id"]
                changed = snapshot_id != self._snapshot_id
                self._signature = signature
                self._error = None
                if changed or self._wire is None:
                    self._wire = dashboard_wire.encode_payload(payload)
                    self._snapshot_id = snapshot_id
                return changed
            except Exception:
                self._error = "The local log scan failed; the last successful snapshot is still shown."
                if self._wire is None:
                    payload = dashboard_payload.build_payload(
                        [],
                        since=self.since,
                        until=self.until,
                        sources=self.sources,
                        anonymize=self.anonymize,
                        aliases=self._aliases,
                    )
                    self._wire = dashboard_wire.encode_payload(payload)
                    self._snapshot_id = payload["snapshot"]["id"]
                return False

    def page(self, interval):
        self.refresh(force=self._wire is None)
        return report_dashboard.render_dashboard(
            self._wire,
            live={"enabled": True, "interval": interval},
        )

    def response(self):
        self.refresh()
        with self._lock:
            return {
                "wire": self._wire,
                "snapshot": self._snapshot_id,
                "error": self._error,
            }


class LiveDashboardServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, port, dashboard, interval):
        self.dashboard = dashboard
        self.interval = interval
        super().__init__(("127.0.0.1", port), LiveDashboardHandler)


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
            etag = f'"{response["snapshot"]}"'
            if self.headers.get("If-None-Match") == etag and not response["error"]:
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
