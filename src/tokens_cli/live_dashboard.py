"""Loopback-only live Dashboard server.

The server never scans logs while answering a request. A single background
daemon thread owns the periodic scan; the HTTP handlers only read the most
recently published in-memory snapshot under a short state lock, so ``/`` and
``/api/snapshot`` stay fast even while a scan is running or blocked.
"""
import json
import os
import sys
import threading
import time
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
_SCAN_STAGES = ("discovery", "collection", "payload", "encoding")
_PROGRESS_PUBLISH_SECONDS = 0.25


class _ScanProgress:
    """Scan-thread counters; only detached, bounded summaries get published."""
    def __init__(self, scan_id, publish):
        self.started = self.stage_started = time.monotonic()
        self.last_published = self.started
        self.publish = publish
        self.state = {
            "id": scan_id, "stage": "discovery", "outcome": "running",
            "started_at": _utc_timestamp(), "updated_at": _utc_timestamp(),
            "elapsed_seconds": 0.0,
            "stage_seconds": dict.fromkeys(_SCAN_STAGES, 0.0),
            "discovered": 0, "processed": 0, "cache_hits": 0,
            "parsed": 0, "skipped": 0,
        }
        self.flush(force=True)

    def _sample(self, now):
        state = dict(self.state)
        state["stage_seconds"] = dict(self.state["stage_seconds"])
        state["elapsed_seconds"] = max(0.0, now - self.started)
        state["stage_seconds"][state["stage"]] += max(0.0, now - self.stage_started)
        return state

    def flush(self, force=False):
        now = time.monotonic()
        if not force and now - self.last_published < _PROGRESS_PUBLISH_SECONDS:
            return
        self.last_published = now
        self.publish(self._sample(now), now)

    def transition(self, stage):
        now = time.monotonic()
        self.state["stage_seconds"][self.state["stage"]] += max(0.0, now - self.stage_started)
        self.state["stage"] = stage
        self.state["updated_at"] = _utc_timestamp()
        self.stage_started = now
        self.flush(force=True)

    def observe(self, event, source):
        if source not in ("claude", "codex", "gemini"):
            return
        if event == "discovered":
            self.state["discovered"] += 1
        elif event == "skipped":
            self.state["skipped"] += 1
        elif event in ("processed_cached", "processed_parsed"):
            self.state["processed"] += 1
            self.state["cache_hits" if event == "processed_cached" else "parsed"] += 1
        else:
            return
        self.state["updated_at"] = _utc_timestamp()
        self.flush()

    def finish(self, outcome):
        # Caller commits this detached terminal sample with the snapshot state.
        self.state["outcome"] = outcome
        self.state["updated_at"] = _utc_timestamp()
        now = time.monotonic()
        return self._sample(now), now


def _utc_timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class LiveDashboard:
    def __init__(self, sources, since=None, until=None, anonymize=False, use_cache=True,
                 snapshot_store=None):
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
        self._error_details = None
        self._checked_at = None
        self._has_snapshot = False
        self._refreshing = False
        self._revision = 0
        self._scan_id = 0
        self._scan = None
        self._scan_sampled_at = None
        self._restored = False
        self._storage_warning = None
        self._snapshot_store = snapshot_store if use_cache and not anonymize else None
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
        if self._snapshot_store is not None:
            try:
                restored = self._snapshot_store.load()
                if restored is not None:
                    wire = restored["wire"]
                    payload = dashboard_wire.decode_payload(wire)
                    self._snapshot_id = payload["snapshot"]["id"]
                    self._wire = wire
                    self._checked_at = restored["checked_at"]
                    self._has_snapshot = True
                    self._restored = True
            except Exception:
                pass  # 本机快照无效只能是 miss，不阻止首次真实扫描。

    def _publish_progress(self, state, sampled_at):
        with self._lock:
            self._scan = state
            self._scan_sampled_at = sampled_at

    def _scan_state_locked(self):
        if self._scan is None:
            return None
        state = dict(self._scan)
        state["stage_seconds"] = dict(state["stage_seconds"])
        if state["outcome"] == "running":
            elapsed = max(0.0, time.monotonic() - self._scan_sampled_at)
            state["elapsed_seconds"] += elapsed
            state["stage_seconds"][state["stage"]] += elapsed
        state["elapsed_seconds"] = round(state["elapsed_seconds"], 3)
        state["stage_seconds"] = {key: round(value, 3) for key, value in state["stage_seconds"].items()}
        return state

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
                if source in ("claude", "codex"):
                    raise readers.CollectionIncompleteError(source, "discovery_failed") from None
                paths = []
            for path in paths:
                if source in ("claude", "codex"):
                    try:
                        stat_result = os.lstat(path)
                    except OSError:
                        raise readers.CollectionIncompleteError(source, "stat_failed") from None
                    # Include rejected objects too: their replacement or
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
                self._scan_id += 1
                scan_id = self._scan_id
            progress = _ScanProgress(scan_id, self._publish_progress)
            stage = "discovery"
            try:
                # stat / read / build / encode all happen outside the state
                # lock, and any failure here (not just OSError) is contained so
                # the background loop can never die on a bad signature.
                signature = self._file_signature()
                with self._lock:
                    unchanged = (not force and self._error is None
                                 and signature == self._signature and self._wire is not None)
                if unchanged:
                    terminal_scan, sampled_at = progress.finish("unchanged")
                    with self._lock:
                        self._scan = terminal_scan
                        self._scan_sampled_at = sampled_at
                        self._error = None
                        self._error_details = None
                        self._checked_at = _utc_timestamp()
                        self._refreshing = False
                        self._revision += 1
                    return False
                stage = "collection"
                progress.transition(stage)
                records = readers.read_all(sources=self.sources, use_cache=self.use_cache,
                                           observer=progress.observe)
                stage = "payload"
                progress.transition(stage)
                payload = dashboard_payload.build_payload(
                    records,
                    since=self.since,
                    until=self.until,
                    sources=self.sources,
                    anonymize=self.anonymize,
                    aliases=self._aliases,
                )
                stage = "encoding"
                progress.transition(stage)
                wire = dashboard_wire.encode_payload(payload)
                snapshot_id = payload["snapshot"]["id"]
            except Exception as exc:
                # Only fixed stage names and validated collection codes cross
                # the HTTP boundary; exception text may contain private data.
                details = {"stage": stage}
                if isinstance(exc, readers.CollectionIncompleteError):
                    source = getattr(exc, "source", None)
                    reason = getattr(exc, "reason", None)
                    if (isinstance(source, str) and isinstance(reason, str)
                            and source in readers.CollectionIncompleteError.SOURCES
                            and reason in readers.CollectionIncompleteError.REASONS):
                        details.update(source=source, reason=reason)
                        conflict_kind = getattr(exc, "conflict_kind", None)
                        if (stage == "collection" and source == "codex" and reason == "usage_conflict"
                                and type(conflict_kind) is str
                                and conflict_kind in readers.CollectionIncompleteError.CONFLICT_KINDS):
                            details["conflict_kind"] = conflict_kind
                            mismatch_kind = getattr(exc, "mismatch_kind", None)
                            if (conflict_kind == "legacy_anchor_mismatch"
                                    and type(mismatch_kind) is str
                                    and mismatch_kind in readers.CollectionIncompleteError.MISMATCH_KINDS):
                                details["mismatch_kind"] = mismatch_kind
                terminal_scan, sampled_at = progress.finish("failed")
                with self._lock:
                    self._scan = terminal_scan
                    self._scan_sampled_at = sampled_at
                    self._error = (_SCAN_FAILED_ERROR if self._has_snapshot else
                                   "The local log scan failed; no successful snapshot is available yet.")
                    self._error_details = details
                    self._refreshing = False
                    self._revision += 1
                return False
            terminal_scan, sampled_at = progress.finish("success")
            checked_at = _utc_timestamp()
            with self._lock:
                self._scan = terminal_scan
                self._scan_sampled_at = sampled_at
                changed = snapshot_id != self._snapshot_id
                self._signature = signature
                self._error = None
                self._error_details = None
                self._checked_at = checked_at
                self._has_snapshot = True
                self._restored = False
                self._storage_warning = None
                if changed or self._wire is None:
                    self._wire = wire
                    self._snapshot_id = snapshot_id
                published_wire = self._wire
                self._refreshing = False
                self._revision += 1
            if self._snapshot_store is not None:
                try:
                    saved = self._snapshot_store.save(published_wire, checked_at)
                except Exception:
                    saved = False
                if not saved:
                    with self._lock:
                        self._storage_warning = "write_failed"
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
                "error_details": dict(self._error_details) if self._error_details else None,
                "restored": self._restored,
                "storage_warning": self._storage_warning,
                "scan": self._scan_state_locked(),
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
                "error_details": dict(self._error_details) if self._error_details else None,
                "restored": self._restored,
                "storage_warning": self._storage_warning,
                "has_snapshot": self._has_snapshot,
                "refreshing": self._refreshing,
                "checked_at": self._checked_at,
                "revision": revision,
                "etag": f'"live-{revision}"',
            }

    def status(self):
        """Small, uncached telemetry; never copy or serialize the published wire."""
        with self._lock:
            return {
                "snapshot": self._snapshot_id,
                "error": self._error,
                "error_details": dict(self._error_details) if self._error_details else None,
                "has_snapshot": self._has_snapshot,
                "refreshing": self._refreshing,
                "checked_at": self._checked_at,
                "revision": self._revision,
                "restored": self._restored,
                "storage_warning": self._storage_warning,
                "scan": self._scan_state_locked(),
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
        if path == "/api/status":
            body = json.dumps(self.server.dashboard.status(), ensure_ascii=False,
                              separators=(",", ":")).encode("utf-8")
            self._headers(200, "application/json; charset=utf-8", len(body))
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


def create_snapshot_store(sources, since=None, until=None, anonymize=False, use_cache=True):
    """serve 专属注入点；返回 None 即完全不读写私有恢复快照。"""
    if anonymize or not use_cache or sys.platform == "win32":
        return None
    from . import live_snapshot
    return live_snapshot.create_store(sources, since=since, until=until)


def create_server(port, sources, since=None, until=None, anonymize=False,
                  use_cache=True, interval=300.0):
    dashboard = LiveDashboard(
        sources,
        since=since,
        until=until,
        anonymize=anonymize,
        use_cache=use_cache,
        snapshot_store=create_snapshot_store(sources, since, until,
                                             anonymize=anonymize, use_cache=use_cache),
    )
    return LiveDashboardServer(port, dashboard, interval)
