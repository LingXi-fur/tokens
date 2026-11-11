import http.client
import json
import threading
import time
import tempfile
import unittest
from unittest import mock

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tokens_cli import config, dashboard_payload, live_dashboard


class _FakeDashboard:
    """Deterministic dashboard used to exercise only the HTTP layer.

    ``start``/``stop`` are no-ops so the real background thread never runs;
    ``refresh`` exists for interface compatibility and is never invoked.
    """

    def __init__(self):
        self.calls = 0
        self.started = []
        self.stopped = 0
        self.revision = 1
        self.error = None
        self.refreshing = False

    def start(self, interval):
        self.started.append(interval)

    def stop(self, timeout=None):
        self.stopped += 1

    def refresh(self):
        self.calls += 1

    def page(self, interval):
        return "<html>live</html>"

    def response(self):
        self.calls += 1
        return {
            "wire": {"v": 1, "s": [], "d": {}},
            "snapshot": "snap-1",
            "error": self.error,
            "has_snapshot": True,
            "refreshing": self.refreshing,
            "checked_at": "2026-10-12T00:00:00+00:00",
            "revision": self.revision,
            "etag": f'"live-{self.revision}"',
        }


class LiveDashboardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        # No test may touch a real source root, cache, router or raw title entry.
        patches = (
            mock.patch.multiple(config,
                HOME=str(root), CLAUDE_PROJECTS=str(root / "claude"),
                GEMINI_TMP=str(root / "gemini"), CODEX_SESSIONS=str(root / "codex"),
                CODEX_ARCHIVED_SESSIONS=str(root / "archive"),
                CACHE_DIR=str(root / "cache"), CACHE_FILE=str(root / "cache" / "records.json"),
                OUT_DIR=str(root / "out"), SESSION_SUMMARY_FILE=str(root / "out" / "titles.json"),
                CCR_ROUTER_FILE=str(root / "router.js")),
            mock.patch("tokens_cli.readers._ccr_signature", return_value=None),
            mock.patch("tokens_cli.dashboard_payload.readers.load_session_summaries",
                       return_value={}),
            mock.patch("tokens_cli.dashboard_payload.readers.build_session_index",
                       return_value={}),
            mock.patch("tokens_cli.dashboard_payload.readers.session_title",
                       return_value=""),
        )
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)

    @staticmethod
    def record(date, model="model-a", session="session-a", cwd="/synthetic/project"):
        return {
            "source": "claude",
            "ts": f"{date}T08:00:00+00:00",
            "date": date,
            "model": model,
            "input": 70,
            "output": 20,
            "cache_read": 10,
            "cache_write": 0,
            "total": 100,
            "session": session,
            "cwd": cwd,
        }

    @staticmethod
    def blocking_read_all(entered, release):
        def read_all(**kwargs):
            entered.set()
            release.wait(5)
            return []
        return read_all

    def start_server(self, dashboard=None):
        dashboard = dashboard or _FakeDashboard()
        server = live_dashboard.LiveDashboardServer(0, dashboard, 300)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.addCleanup(thread.join, 2)
        return server, dashboard

    def start_real_server(self, dashboard):
        server = live_dashboard.LiveDashboardServer(0, dashboard, 300)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.addCleanup(thread.join, 2)
        return server

    def request(self, server, path, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=2)
        connection.request("GET", path, headers=headers or {})
        response = connection.getresponse()
        body = response.read()
        connection.close()
        return response, body

    # -- HTTP surface and security -------------------------------------------
    def test_server_is_loopback_only_and_has_private_headers(self):
        server, dashboard = self.start_server()
        self.assertEqual("127.0.0.1", server.server_address[0])
        self.assertEqual([300], dashboard.started)
        response, body = self.request(server, "/")
        self.assertEqual(200, response.status)
        self.assertEqual(b"<html>live</html>", body)
        self.assertEqual("no-store", response.getheader("Cache-Control"))
        self.assertEqual("nosniff", response.getheader("X-Content-Type-Options"))
        self.assertEqual("no-referrer", response.getheader("Referrer-Policy"))
        self.assertEqual("same-origin", response.getheader("Cross-Origin-Resource-Policy"))
        self.assertEqual("frame-ancestors 'none'", response.getheader("Content-Security-Policy"))

    def test_page_allows_view_query_without_expanding_route_surface(self):
        server, _ = self.start_server()
        response, body = self.request(
            server,
            "/?gran=month&models=model-a&focus=2026-08",
        )
        self.assertEqual(200, response.status)
        self.assertEqual(b"<html>live</html>", body)
        response, _ = self.request(server, "/unknown?gran=month")
        self.assertEqual(404, response.status)
        response, _ = self.request(server, "/api/snapshot/extra?gran=month")
        self.assertEqual(404, response.status)

    def test_server_rejects_foreign_host_origin_and_unknown_paths(self):
        server, _ = self.start_server()
        response, _ = self.request(server, "/", {"Host": "attacker.example"})
        self.assertEqual(403, response.status)
        response, _ = self.request(server, "/", {"Origin": "https://attacker.example"})
        self.assertEqual(403, response.status)
        response, _ = self.request(server, "/../../etc/passwd")
        self.assertEqual(404, response.status)

    def test_snapshot_endpoint_uses_etag_and_304(self):
        server, dashboard = self.start_server()
        response, body = self.request(server, "/api/snapshot")
        self.assertEqual(200, response.status)
        self.assertEqual('"live-1"', response.getheader("ETag"))
        self.assertEqual("snap-1", json.loads(body)["snapshot"])
        response, body = self.request(
            server,
            "/api/snapshot",
            {"If-None-Match": '"live-1"'},
        )
        self.assertEqual(304, response.status)
        self.assertEqual(b"", body)
        self.assertEqual(2, dashboard.calls)

    def test_etag_tracks_revision_and_error_prevents_304(self):
        server, dashboard = self.start_server()
        response, body = self.request(server, "/api/snapshot")
        self.assertEqual('"live-1"', response.getheader("ETag"))
        self.assertEqual(1, json.loads(body)["revision"])
        dashboard.revision = 2
        response, _ = self.request(server, "/api/snapshot", {"If-None-Match": '"live-1"'})
        self.assertEqual(200, response.status)
        self.assertEqual('"live-2"', response.getheader("ETag"))
        # Same revision, but an error on the wire must still be delivered.
        dashboard.error = "The local log scan failed; the last successful snapshot is still shown."
        response, body = self.request(server, "/api/snapshot", {"If-None-Match": '"live-2"'})
        self.assertEqual(200, response.status)
        self.assertIn("local log scan failed", json.loads(body)["error"])

    def test_client_cancel_is_silenced_but_other_errors_propagate(self):
        dashboard = _FakeDashboard()
        server = live_dashboard.LiveDashboardServer(0, dashboard, 300)
        errors = []
        server.handle_error = lambda *args: errors.append(args)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.addCleanup(thread.join, 2)

        def request_quietly(path):
            try:
                self.request(server, path)
            except (http.client.HTTPException, OSError):
                pass

        with mock.patch.object(dashboard, "page", side_effect=BrokenPipeError("client gone")):
            request_quietly("/")
            time.sleep(0.05)
        self.assertEqual([], errors)
        with mock.patch.object(dashboard, "page", side_effect=ValueError("boom")):
            request_quietly("/")
            deadline = time.monotonic() + 2
            while not errors and time.monotonic() < deadline:
                time.sleep(0.01)
        self.assertEqual(1, len(errors))

    def test_default_server_interval_is_five_minutes(self):
        with mock.patch(
            "tokens_cli.live_dashboard.LiveDashboardServer",
            return_value=mock.sentinel.server,
        ) as server_class, mock.patch(
            "tokens_cli.live_dashboard.create_snapshot_store",
            return_value=None,
        ) as store_factory:
            server = live_dashboard.create_server(0, ["claude"])
        self.assertIs(mock.sentinel.server, server)
        self.assertEqual(300.0, server_class.call_args.args[2])
        self.assertEqual(mock.call(["claude"], None, None, anonymize=False, use_cache=True),
                         store_factory.call_args)

    # -- refresh semantics ---------------------------------------------------
    @mock.patch("tokens_cli.live_dashboard.readers.read_all", return_value=[])
    def test_unchanged_file_signature_skips_reaggregation(self, read_all):
        dashboard = live_dashboard.LiveDashboard(["claude"])
        with mock.patch.object(dashboard, "_file_signature", return_value=(("claude", "x", 1, 2),)):
            dashboard.refresh(force=True)
            dashboard.refresh()
        self.assertEqual(1, read_all.call_count)
        self.assertIsNotNone(dashboard.response()["wire"])

    @mock.patch("tokens_cli.live_dashboard.readers.read_all")
    def test_failed_refresh_keeps_last_successful_snapshot(self, read_all):
        read_all.side_effect = [[], RuntimeError("private path should not escape")]
        dashboard = live_dashboard.LiveDashboard(["claude"])
        with mock.patch.object(dashboard, "_file_signature", side_effect=[(), (("claude", "x", 1, 2),), (("claude", "x", 1, 2),)]):
            dashboard.refresh(force=True)
            snapshot = dashboard.response()["snapshot"]
            dashboard.refresh()
            response = dashboard.response()
        self.assertEqual(snapshot, response["snapshot"])
        self.assertIn("local log scan failed", response["error"])
        self.assertNotIn("private path", response["error"])

    @mock.patch("tokens_cli.live_dashboard.readers.read_all")
    def test_first_scan_failure_keeps_no_snapshot_and_generic_error(self, read_all):
        read_all.side_effect = RuntimeError("private path should not escape")
        dashboard = live_dashboard.LiveDashboard(["claude"])
        with mock.patch.object(dashboard, "_file_signature", return_value=(("claude", "x", 1, 2),)):
            self.assertFalse(dashboard.refresh(force=True))
            response = dashboard.response()
        self.assertIsNone(response["wire"])
        self.assertIsNone(response["snapshot"])
        self.assertFalse(response["has_snapshot"])
        self.assertFalse(response["refreshing"])
        self.assertIsNone(response["checked_at"])
        self.assertIn("local log scan failed", response["error"])
        self.assertNotIn("private path", response["error"])
        self.assertIn('"has_snapshot": false', dashboard.page(300))

    @mock.patch("tokens_cli.live_dashboard.readers.read_all")
    def test_scan_failure_exposes_only_whitelisted_stage_and_codes(self, read_all):
        error = live_dashboard.readers.CollectionIncompleteError("codex", "usage_conflict")
        read_all.side_effect = error
        dashboard = live_dashboard.LiveDashboard(["claude", "codex"])
        with mock.patch.object(dashboard, "_file_signature", return_value=()):
            dashboard.refresh()
        response = dashboard.response()
        self.assertEqual({"stage": "collection", "source": "codex", "reason": "usage_conflict"},
                         response["error_details"])
        self.assertIn("no successful snapshot", response["error"])
        self.assertIn('"error_details":', dashboard.page(300))
        response["error_details"]["reason"] = "private mutation"
        self.assertEqual("usage_conflict", dashboard.response()["error_details"]["reason"])
        read_all.side_effect = None
        read_all.return_value = []
        with mock.patch.object(dashboard, "_file_signature", return_value=()):
            dashboard.refresh()
        self.assertIsNone(dashboard.response()["error_details"])

    def assert_error_details_exports(self, dashboard, expected):
        response = dashboard.response()
        status = dashboard.status()
        with mock.patch.object(live_dashboard.report_dashboard, "render_dashboard",
                               return_value="synthetic-page") as render:
            self.assertEqual("synthetic-page", dashboard.page(300))
        page_live = render.call_args.kwargs["live"]
        for exported in (response, status, page_live):
            self.assertEqual(expected, exported["error_details"])
            exported["error_details"]["reason"] = "private-copy-mutation"
        self.assertEqual(expected, dashboard.status()["error_details"])
        return response, status, page_live

    @mock.patch("tokens_cli.live_dashboard.readers.read_all")
    def test_anchor_mismatch_groups_are_projected_and_cleared(self, read_all):
        kinds = ("usage", "model", "billing", "usage_model", "usage_billing",
                 "model_billing", "usage_model_billing")
        for kind in kinds:
            with self.subTest(kind=kind):
                dashboard = live_dashboard.LiveDashboard(["codex"])
                read_all.side_effect = None
                read_all.return_value = []
                with mock.patch.object(dashboard, "_file_signature", return_value=()):
                    self.assertTrue(dashboard.refresh())
                    before = dashboard.response()
                    error = live_dashboard.readers.CollectionIncompleteError(
                        "codex", "usage_conflict", conflict_kind="legacy_anchor_mismatch")
                    error.mismatch_kind = kind
                    read_all.side_effect = error
                    with mock.patch.object(dashboard, "_file_signature", return_value=("changed",)):
                        self.assertFalse(dashboard.refresh())
                    self.assert_error_details_exports(dashboard, {
                        "stage": "collection", "source": "codex", "reason": "usage_conflict",
                        "conflict_kind": "legacy_anchor_mismatch", "mismatch_kind": kind})
                    after = dashboard.response()
                    self.assertEqual(before["wire"], after["wire"])
                    self.assertEqual(before["checked_at"], after["checked_at"])
                    read_all.side_effect = None
                    self.assertFalse(dashboard.refresh())  # Same data, successful revalidation.
                    self.assertEqual("success", dashboard.status()["scan"]["outcome"])
                    self.assertIsNone(dashboard.status()["error_details"])

    @mock.patch("tokens_cli.live_dashboard.readers.read_all")
    def test_mismatch_metadata_rejects_missing_invalid_and_wrong_context(self, read_all):
        class StringSubclass(str):
            pass
        for value in (None, "private-mismatch-sentinel", [], {}, ["model"],
                      {"kind": "model"}, True, 1, StringSubclass("model"), "missing"):
            with self.subTest(value_type=type(value).__name__):
                error = live_dashboard.readers.CollectionIncompleteError(
                    "codex", "usage_conflict", conflict_kind="legacy_anchor_mismatch")
                error.mismatch_kind = value
                if value == "missing":
                    del error.mismatch_kind
                read_all.side_effect = error
                dashboard = live_dashboard.LiveDashboard(["codex"])
                with mock.patch.object(dashboard, "_file_signature", return_value=()):
                    self.assertFalse(dashboard.refresh())
                self.assert_error_details_exports(dashboard, {
                    "stage": "collection", "source": "codex", "reason": "usage_conflict",
                    "conflict_kind": "legacy_anchor_mismatch"})
        for kind in (None, "modern_response_mismatch", "legacy_cumulative_rollback",
                     "cross_file_identity_mismatch"):
            error = live_dashboard.readers.CollectionIncompleteError(
                "codex", "usage_conflict", conflict_kind=kind)
            error.mismatch_kind = "model"
            read_all.side_effect = error
            dashboard = live_dashboard.LiveDashboard(["codex"])
            with mock.patch.object(dashboard, "_file_signature", return_value=()):
                self.assertFalse(dashboard.refresh())
            self.assertNotIn("mismatch_kind", dashboard.status()["error_details"])

    @mock.patch("tokens_cli.live_dashboard.readers.read_all")
    def test_four_conflict_codes_are_copied_to_all_exports_and_cleared_on_recovery(self, read_all):
        for kind in ("modern_response_mismatch", "legacy_cumulative_rollback",
                     "legacy_anchor_mismatch", "cross_file_identity_mismatch"):
            with self.subTest(kind=kind):
                error = live_dashboard.readers.CollectionIncompleteError(
                    "codex", "usage_conflict", conflict_kind=kind)
                error.private_path = "/synthetic/private-path-sentinel"
                error.identity = "private-identity-sentinel"
                error.hash = "private-hash-sentinel"
                error.token = "private-token-sentinel"
                error.args = ("private-exception-text-sentinel",)
                read_all.side_effect = error
                dashboard = live_dashboard.LiveDashboard(["codex"])
                with mock.patch.object(dashboard, "_file_signature", return_value=()):
                    self.assertFalse(dashboard.refresh())
                    expected = {"stage": "collection", "source": "codex",
                                "reason": "usage_conflict", "conflict_kind": kind}
                    self.assert_error_details_exports(dashboard, expected)
                    public = json.dumps([dashboard.response(), dashboard.status()]) + dashboard.page(300)
                    for private in (*error.args, error.private_path, error.identity,
                                    error.hash, error.token):
                        self.assertNotIn(private, public)
                    self.assertFalse(dashboard.status()["has_snapshot"])
                    self.assertIsNone(dashboard.response()["wire"])
                    self.assertIsNone(dashboard.status()["checked_at"])
                    read_all.side_effect = None
                    read_all.return_value = []
                    self.assertTrue(dashboard.refresh())
                    self.assertEqual("success", dashboard.status()["scan"]["outcome"])
                    self.assertIsNone(dashboard.response()["error_details"])
                    self.assertIsNone(dashboard.status()["error_details"])
                    self.assertFalse(dashboard.refresh())
                    self.assertEqual("unchanged", dashboard.status()["scan"]["outcome"])
                    with mock.patch.object(live_dashboard.report_dashboard, "render_dashboard") as render:
                        dashboard.page(300)
                    self.assertIsNone(render.call_args.kwargs["live"]["error_details"])

    @mock.patch("tokens_cli.live_dashboard.readers.read_all")
    def test_old_exception_and_tampered_conflict_diagnostics_are_omitted(self, read_all):
        class StringSubclass(str):
            pass

        for value in (None, "private-diagnostic-sentinel", [], {},
                      ["modern_response_mismatch"], {"kind": "modern_response_mismatch"},
                      7, True, "missing-attribute", StringSubclass("modern_response_mismatch")):
            with self.subTest(value_type=type(value).__name__):
                error = live_dashboard.readers.CollectionIncompleteError("codex", "usage_conflict")
                error.conflict_kind = value
                if value == "missing-attribute":
                    del error.conflict_kind
                read_all.side_effect = error
                dashboard = live_dashboard.LiveDashboard(["codex"])
                with mock.patch.object(dashboard, "_file_signature", return_value=()):
                    self.assertFalse(dashboard.refresh())
                self.assert_error_details_exports(dashboard, {
                    "stage": "collection", "source": "codex", "reason": "usage_conflict"})
                self.assertNotIn("private-diagnostic-sentinel", dashboard.page(300))

    @mock.patch("tokens_cli.live_dashboard.readers.read_all")
    def test_conflict_kind_requires_collection_stage_and_exact_codex_reason(self, read_all):
        cases = (("collection", "claude", "usage_conflict"),
                 ("collection", "gemini", "usage_conflict"),
                 ("collection", "all", "usage_conflict"),
                 ("collection", "codex", "usage_invalid"),
                 ("discovery", "codex", "usage_conflict"),
                 ("payload", "codex", "usage_conflict"),
                 ("encoding", "codex", "usage_conflict"))
        for stage, source, reason in cases:
            with self.subTest(stage=stage, source=source, reason=reason):
                error = live_dashboard.readers.CollectionIncompleteError(source, reason)
                error.conflict_kind = "modern_response_mismatch"
                dashboard = live_dashboard.LiveDashboard(["codex"])
                target, method = {
                    "collection": (live_dashboard.readers, "read_all"),
                    "discovery": (dashboard, "_file_signature"),
                    "payload": (dashboard_payload, "build_payload"),
                    "encoding": (live_dashboard.dashboard_wire, "encode_payload"),
                }[stage]
                read_all.side_effect = None
                read_all.return_value = []
                with mock.patch.object(dashboard, "_file_signature", return_value=()), \
                        mock.patch.object(target, method, side_effect=error):
                    self.assertFalse(dashboard.refresh())
                self.assert_error_details_exports(dashboard, {
                    "stage": stage, "source": source, "reason": reason})

    @mock.patch("tokens_cli.live_dashboard.readers.read_all")
    def test_container_or_unknown_source_reason_never_breaks_error_publication(self, read_all):
        for attribute in ("source", "reason"):
            for value in ([], {}, ["codex"], {"reason": "usage_conflict"},
                          None, "private-source-reason-sentinel"):
                with self.subTest(attribute=attribute, value_type=type(value).__name__):
                    error = live_dashboard.readers.CollectionIncompleteError("codex", "usage_conflict")
                    error.conflict_kind = "modern_response_mismatch"
                    setattr(error, attribute, value)
                    read_all.side_effect = error
                    dashboard = live_dashboard.LiveDashboard(["codex"])
                    with mock.patch.object(dashboard, "_file_signature", return_value=()):
                        self.assertFalse(dashboard.refresh())
                    self.assertFalse(dashboard.status()["refreshing"])
                    self.assertEqual("failed", dashboard.status()["scan"]["outcome"])
                    self.assert_error_details_exports(dashboard, {"stage": "collection"})
                    self.assertNotIn("private-source-reason-sentinel", dashboard.page(300))

    @mock.patch("tokens_cli.live_dashboard.readers.read_all", return_value=[])
    def test_unknown_build_error_never_exposes_private_text(self, read_all):
        dashboard = live_dashboard.LiveDashboard(["claude"])
        with mock.patch.object(dashboard, "_file_signature", return_value=()), mock.patch(
            "tokens_cli.live_dashboard.dashboard_payload.build_payload",
            side_effect=RuntimeError("/private/project secret-session"),
        ):
            dashboard.refresh()
        response = dashboard.response()
        self.assertEqual({"stage": "payload"}, response["error_details"])
        self.assertNotIn("secret-session", json.dumps(response))
        self.assertNotIn("/private/project", dashboard.page(300))

    @mock.patch("tokens_cli.live_dashboard.readers.read_all", return_value=[])
    def test_mutated_collection_codes_are_not_exposed(self, read_all):
        error = live_dashboard.readers.CollectionIncompleteError("claude", "file_changed")
        error.source = "/private/project"
        error.reason = "secret-session"
        read_all.side_effect = error
        dashboard = live_dashboard.LiveDashboard(["claude"])
        with mock.patch.object(dashboard, "_file_signature", return_value=()):
            dashboard.refresh()
        self.assertEqual({"stage": "collection"}, dashboard.response()["error_details"])

    @mock.patch("tokens_cli.live_dashboard.readers.read_all")
    def test_successful_scan_publishes_snapshot_and_checked_at(self, read_all):
        read_all.return_value = [self.record("2026-08-25")]
        dashboard = live_dashboard.LiveDashboard(["claude"])
        with mock.patch.object(dashboard, "_file_signature", return_value=(("claude", "x", 1, 1),)):
            self.assertTrue(dashboard.refresh(force=True))
            response = dashboard.response()
        self.assertTrue(response["has_snapshot"])
        self.assertIsNotNone(response["snapshot"])
        self.assertIsNotNone(response["wire"])
        self.assertIsNone(response["error"])
        self.assertFalse(response["refreshing"])
        self.assertRegex(response["checked_at"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00$")

    @mock.patch("tokens_cli.live_dashboard.readers.read_all")
    def test_failure_then_recovery_retries_even_when_signature_is_unchanged(self, read_all):
        read_all.side_effect = [[], RuntimeError("boom"), []]
        dashboard = live_dashboard.LiveDashboard(["claude"])
        with mock.patch.object(
            dashboard,
            "_file_signature",
            side_effect=[
                (("claude", "x", 1, 1),),
                (("claude", "x", 2, 2),),
                (("claude", "x", 1, 1),),
            ],
        ):
            self.assertTrue(dashboard.refresh(force=True))
            self.assertFalse(dashboard.refresh())
            failed = dashboard.response()
            self.assertIn("local log scan failed", failed["error"])
            # Reverting to the last successful signature is not recovery proof:
            # a pending scan failure must retry collection before clearing error.
            self.assertFalse(dashboard.refresh())
            recovered = dashboard.response()
        self.assertEqual(3, read_all.call_count)
        self.assertIsNone(recovered["error"])
        self.assertTrue(recovered["has_snapshot"])
        self.assertIsNotNone(recovered["checked_at"])

    @mock.patch("tokens_cli.live_dashboard.readers.read_all", return_value=[])
    def test_signature_failure_is_contained_and_recovers(self, read_all):
        calls = {"n": 0}

        def signature():
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("stat exploded")  # non-OSError must not escape
            return (("claude", "x", 1, 1),)

        dashboard = live_dashboard.LiveDashboard(["claude"])
        with mock.patch.object(dashboard, "_file_signature", side_effect=signature):
            self.assertFalse(dashboard.refresh(force=True))
            failed = dashboard.response()
            self.assertFalse(failed["refreshing"])
            self.assertIn("local log scan failed", failed["error"])
            self.assertIsNone(failed["wire"])
            self.assertTrue(dashboard.refresh(force=True))
            recovered = dashboard.response()
        self.assertIsNone(recovered["error"])
        self.assertTrue(recovered["has_snapshot"])

    @mock.patch("tokens_cli.live_dashboard.readers.read_all", return_value=[])
    def test_encode_failure_keeps_signature_for_retry(self, read_all):
        # Build the object first (the __init__ placeholder also encodes), then
        # make the encoder explode so only the scan path fails.
        dashboard = live_dashboard.LiveDashboard(["claude"])
        signature = (("claude", "x", 1, 1),)
        with mock.patch.object(dashboard, "_file_signature", return_value=signature), \
                mock.patch(
                    "tokens_cli.live_dashboard.dashboard_wire.encode_payload",
                    side_effect=RuntimeError("encoder exploded"),
                ):
            self.assertFalse(dashboard.refresh(force=True))
            self.assertIsNone(dashboard._signature)  # not advanced, so retry rescans
            failed = dashboard.response()
            self.assertFalse(failed["has_snapshot"])
            self.assertIn("local log scan failed", failed["error"])
        # With the encoder healthy again the same work succeeds and publishes.
        with mock.patch.object(dashboard, "_file_signature", return_value=signature):
            self.assertTrue(dashboard.refresh(force=True))
        self.assertTrue(dashboard.response()["has_snapshot"])
        self.assertEqual(signature, dashboard._signature)

    @mock.patch("tokens_cli.live_dashboard.readers.read_all")
    def test_anonymized_aliases_stay_stable_across_refreshes(self, read_all):
        first = self.record(
            "2026-08-25",
            session="private-session-a",
            cwd="/private/project-a",
        )
        second = self.record(
            "2026-08-26",
            model="model-b",
            session="private-session-b",
            cwd="/private/project-b",
        )
        read_all.side_effect = [[first], [first, second]]
        dashboard = live_dashboard.LiveDashboard(["claude"], anonymize=True)
        with mock.patch.object(
            dashboard,
            "_file_signature",
            side_effect=[(("claude", "x", 1, 1),), (("claude", "x", 2, 2),)],
        ), mock.patch.object(
            dashboard_payload,
            "build_payload",
            wraps=dashboard_payload.build_payload,
        ) as build_payload:
            dashboard.refresh(force=True)
            dashboard.refresh()

        first_aliases = build_payload.call_args_list[0].kwargs["aliases"]
        second_aliases = build_payload.call_args_list[1].kwargs["aliases"]
        self.assertIs(first_aliases, second_aliases)
        self.assertIs(dashboard._aliases, first_aliases)

    @mock.patch("tokens_cli.live_dashboard.readers.read_all")
    def test_fixed_until_ignores_newer_records_for_snapshot_identity(self, read_all):
        in_range = self.record("2026-08-25")
        outside_range = self.record("2026-08-26", model="model-b")
        read_all.side_effect = [[in_range], [in_range, outside_range]]
        dashboard = live_dashboard.LiveDashboard(["claude"], until="2026-08-25")
        with mock.patch.object(
            dashboard,
            "_file_signature",
            side_effect=[(("claude", "x", 1, 1),), (("claude", "x", 2, 2),)],
        ):
            self.assertTrue(dashboard.refresh(force=True))
            snapshot = dashboard._snapshot_id
            self.assertFalse(dashboard.refresh())

        self.assertEqual(snapshot, dashboard._snapshot_id)
        self.assertEqual(2, read_all.call_count)

    # -- request reads never scan --------------------------------------------
    def test_response_reads_snapshot_state_under_lock(self):
        dashboard = live_dashboard.LiveDashboard(["claude"])
        dashboard._wire = {"v": 1, "s": [], "d": {}}
        dashboard._snapshot_id = "snap-1"
        lock = mock.MagicMock()
        dashboard._lock = lock
        with mock.patch.object(dashboard, "refresh"):
            response = dashboard.response()
        self.assertEqual("snap-1", response["snapshot"])
        lock.__enter__.assert_called_once_with()
        lock.__exit__.assert_called_once()

    @mock.patch("tokens_cli.live_dashboard.readers.read_all")
    def test_page_and_response_never_scan_logs(self, read_all):
        dashboard = live_dashboard.LiveDashboard(["claude"])
        with mock.patch.object(dashboard, "_file_signature") as signature:
            dashboard.page(300)
            dashboard.response()
            signature.assert_not_called()
        read_all.assert_not_called()

    @mock.patch("tokens_cli.dashboard_payload.readers.session_title", return_value="")
    @mock.patch("tokens_cli.dashboard_payload.readers.build_session_index", return_value={})
    @mock.patch("tokens_cli.dashboard_payload.readers.load_session_summaries", return_value={})
    def test_placeholder_shell_never_reads_raw_titles(self, load_summaries, build_index, session_title):
        dashboard = live_dashboard.LiveDashboard(["claude"])
        dashboard.page(300)
        dashboard.response()
        load_summaries.assert_not_called()
        build_index.assert_not_called()
        session_title.assert_not_called()

    @mock.patch("tokens_cli.live_dashboard.readers.read_all")
    def test_page_and_response_return_while_scan_blocked(self, read_all):
        entered = threading.Event()
        release = threading.Event()
        read_all.side_effect = self.blocking_read_all(entered, release)
        dashboard = live_dashboard.LiveDashboard(["claude"])
        with mock.patch.object(dashboard, "_file_signature", return_value=(("claude", "x", 1, 1),)):
            worker = threading.Thread(target=lambda: dashboard.refresh(force=True), daemon=True)
            worker.start()
            self.assertTrue(entered.wait(3), "scan should reach read_all")
            started = time.monotonic()
            page = dashboard.page(300)
            response = dashboard.response()
            elapsed = time.monotonic() - started
            self.assertLess(elapsed, 1.0)
            self.assertIn("html", page.lower())
            self.assertIsNone(response["wire"])
            self.assertFalse(response["has_snapshot"])
            self.assertTrue(response["refreshing"])
            self.assertEqual(1, read_all.call_count)
            release.set()
            worker.join(3)

    @mock.patch("tokens_cli.live_dashboard.readers.read_all")
    def test_http_requests_do_not_wait_for_blocked_background_scan(self, read_all):
        entered = threading.Event()
        release = threading.Event()
        read_all.side_effect = self.blocking_read_all(entered, release)
        dashboard = live_dashboard.LiveDashboard(["claude"])
        with mock.patch.object(dashboard, "_file_signature", return_value=(("claude", "x", 1, 1),)):
            server = self.start_real_server(dashboard)
            self.assertTrue(entered.wait(3), "background scan should start immediately")

            started = time.monotonic()
            response, body = self.request(server, "/")
            page_elapsed = time.monotonic() - started
            self.assertEqual(200, response.status)
            self.assertIn(b"<html", body)
            self.assertLess(page_elapsed, 1.0)

            started = time.monotonic()
            response, body = self.request(server, "/api/snapshot")
            snapshot_elapsed = time.monotonic() - started
            self.assertEqual(200, response.status)
            self.assertLess(snapshot_elapsed, 1.0)
            payload = json.loads(body)
            self.assertIsNone(payload["wire"])
            self.assertFalse(payload["has_snapshot"])
            self.assertTrue(payload["refreshing"])
            self.assertEqual(1, read_all.call_count)
            release.set()

    # -- scan mutual exclusion -----------------------------------------------
    @mock.patch("tokens_cli.live_dashboard.readers.read_all")
    def test_concurrent_scan_is_dropped_not_queued(self, read_all):
        entered = threading.Event()
        release = threading.Event()
        read_all.side_effect = self.blocking_read_all(entered, release)
        dashboard = live_dashboard.LiveDashboard(["claude"])
        with mock.patch.object(dashboard, "_file_signature", return_value=(("claude", "x", 1, 1),)):
            worker = threading.Thread(target=lambda: dashboard.refresh(force=True), daemon=True)
            worker.start()
            self.assertTrue(entered.wait(3))
            started = time.monotonic()
            self.assertFalse(dashboard.refresh(force=True))
            self.assertLess(time.monotonic() - started, 1.0)
            self.assertEqual(1, read_all.call_count)
            release.set()
            worker.join(3)

    # -- background lifecycle -------------------------------------------------
    @mock.patch("tokens_cli.live_dashboard.readers.read_all", return_value=[])
    def test_background_loop_scans_immediately_then_stops(self, read_all):
        dashboard = live_dashboard.LiveDashboard(["claude"])

        def signature():
            return (("claude", "x", time.monotonic_ns(), 0),)

        with mock.patch.object(dashboard, "_file_signature", side_effect=signature):
            started = time.monotonic()
            dashboard.start(60)
            deadline = started + 2
            while read_all.call_count < 1 and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertGreaterEqual(read_all.call_count, 1)
            self.assertLess(time.monotonic() - started, 2)  # not waiting the 60 s interval
            dashboard.stop(timeout=2)
            self.assertIsNone(dashboard._scan_thread)
            settled = read_all.call_count
            time.sleep(0.2)
            self.assertEqual(settled, read_all.call_count)

            # The same instance can restart and keeps scanning on a short loop.
            dashboard.start(0.05)
            deadline = time.monotonic() + 2
            while read_all.call_count < settled + 2 and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertGreaterEqual(read_all.call_count, settled + 2)
            dashboard.stop(timeout=2)
            steady = read_all.call_count
            time.sleep(0.25)
            self.assertEqual(steady, read_all.call_count)

    @mock.patch("tokens_cli.live_dashboard.readers.read_all", return_value=[])
    def test_server_close_stops_background_scan(self, read_all):
        dashboard = live_dashboard.LiveDashboard(["claude"])
        with mock.patch.object(dashboard, "_file_signature", return_value=(("claude", "x", 1, 1),)):
            server = live_dashboard.LiveDashboardServer(0, dashboard, 300)
            deadline = time.monotonic() + 2
            while read_all.call_count < 1 and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertGreaterEqual(read_all.call_count, 1)
            server.server_close()
            self.assertIsNone(dashboard._scan_thread)
            settled = read_all.call_count
            time.sleep(0.2)
            self.assertEqual(settled, read_all.call_count)

    @mock.patch("tokens_cli.live_dashboard.readers.read_all")
    def test_background_loop_survives_signature_error(self, read_all):
        read_all.return_value = []
        calls = {"n": 0}
        first_failed = threading.Event()

        def signature():
            calls["n"] += 1
            if calls["n"] == 1:
                first_failed.set()
                raise RuntimeError("stat exploded")
            return (("claude", "x", 1, 1),)

        dashboard = live_dashboard.LiveDashboard(["claude"])
        with mock.patch.object(dashboard, "_file_signature", side_effect=signature):
            dashboard.start(0.02)
            try:
                self.assertTrue(first_failed.wait(3), "first scan should run immediately")
                deadline = time.monotonic() + 3
                while not dashboard.response()["has_snapshot"] and time.monotonic() < deadline:
                    time.sleep(0.01)
                # A later round recovered; the loop did not die on the error.
                self.assertTrue(dashboard.response()["has_snapshot"])
                self.assertIsNone(dashboard.response()["error"])
                self.assertTrue(dashboard._scan_thread.is_alive())
            finally:
                dashboard.stop(timeout=2)
        self.assertIsNone(dashboard._scan_thread)

    @mock.patch("tokens_cli.live_dashboard.readers.read_all")
    def test_blocked_stop_then_start_does_not_spawn_second_thread(self, read_all):
        entered = threading.Event()
        release = threading.Event()
        read_all.side_effect = self.blocking_read_all(entered, release)
        dashboard = live_dashboard.LiveDashboard(["claude"])

        def fresh_signature():
            return (("claude", "x", time.monotonic_ns(), 0),)

        with mock.patch.object(dashboard, "_file_signature", side_effect=fresh_signature):
            dashboard.start(60)
            self.assertTrue(entered.wait(3))
            first = dashboard._scan_thread
            self.assertIsNotNone(first)
            dashboard.stop(timeout=0.05)  # returns despite the blocked scan
            self.assertTrue(first.is_alive())
            self.assertIs(dashboard._scan_thread, first)  # reference retained
            dashboard.start(60)  # must refuse instead of clearing the stop event
            self.assertIs(dashboard._scan_thread, first)
            release.set()
            first.join(3)
            self.assertFalse(first.is_alive())
            self.assertEqual(1, read_all.call_count)  # old loop exited, no rescan
            time.sleep(0.1)
            self.assertEqual(1, read_all.call_count)
            # Once the old thread is gone a fresh start works normally.
            read_all.side_effect = None
            read_all.return_value = []
            dashboard.start(0.02)
            deadline = time.monotonic() + 2
            while read_all.call_count < 2 and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertGreaterEqual(read_all.call_count, 2)
            second = dashboard._scan_thread
            self.assertIsNotNone(second)
            self.assertIsNot(second, first)
            dashboard.stop(timeout=1)
            self.assertFalse(second.is_alive())

    # -- page metadata --------------------------------------------------------
    def test_live_page_enables_polling_without_changing_static_page(self):
        dashboard = live_dashboard.LiveDashboard(["claude"])
        html = dashboard.page(300)
        self.assertIn('"enabled": true', html)
        self.assertIn('"interval": 300', html)
        self.assertIn('"poll_interval": 60', html)
        self.assertIn('"has_snapshot": false', html)
        self.assertNotIn("__LIVE__", html)

    def test_page_publishes_background_and_poll_metadata(self):
        dashboard = live_dashboard.LiveDashboard(["claude"])
        with mock.patch(
            "tokens_cli.live_dashboard.report_dashboard.render_dashboard",
            return_value="<html>live</html>",
        ) as render:
            out = dashboard.page(300)
        self.assertEqual("<html>live</html>", out)
        self.assertIs(render.call_args.args[0], dashboard._placeholder_wire)
        live = render.call_args.kwargs["live"]
        self.assertTrue(live["enabled"])
        self.assertEqual(300, live["interval"])
        self.assertEqual(60, live["poll_interval"])
        self.assertFalse(live["has_snapshot"])
        self.assertFalse(live["refreshing"])
        self.assertIsNone(live["checked_at"])
        self.assertIsNone(live["error"])
        self.assertIsNone(live["snapshot"])
        self.assertEqual(0, live["revision"])
        self.assertEqual('"live-0"', live["etag"])

    def test_poll_interval_is_capped_at_sixty_seconds(self):
        dashboard = live_dashboard.LiveDashboard(["claude"])
        with mock.patch(
            "tokens_cli.live_dashboard.report_dashboard.render_dashboard",
            return_value="<html>",
        ) as render:
            dashboard.page(30)
            self.assertEqual(30, render.call_args.kwargs["live"]["poll_interval"])
            dashboard.page(900)
            self.assertEqual(60, render.call_args.kwargs["live"]["poll_interval"])

    def test_page_reflects_published_snapshot_state(self):
        dashboard = live_dashboard.LiveDashboard(["claude"])
        dashboard._wire = {"v": 1, "s": [], "d": {}}
        dashboard._snapshot_id = "snap-9"
        dashboard._has_snapshot = True
        dashboard._checked_at = "2026-10-12T08:00:00+00:00"
        dashboard._revision = 7
        with mock.patch(
            "tokens_cli.live_dashboard.report_dashboard.render_dashboard",
            return_value="<html>",
        ) as render:
            dashboard.page(300)
        self.assertIs(render.call_args.args[0], dashboard._wire)
        live = render.call_args.kwargs["live"]
        self.assertTrue(live["has_snapshot"])
        self.assertEqual("snap-9", live["snapshot"])
        self.assertEqual(7, live["revision"])
        self.assertEqual('"live-7"', live["etag"])
        self.assertEqual("2026-10-12T08:00:00+00:00", live["checked_at"])


if __name__ == "__main__":
    unittest.main()
