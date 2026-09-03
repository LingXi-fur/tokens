import http.client
import json
import threading
import unittest
from unittest import mock

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tokens_cli import dashboard_payload, live_dashboard


class _FakeDashboard:
    def __init__(self):
        self.calls = 0

    def page(self, interval):
        return "<html>live</html>"

    def response(self):
        self.calls += 1
        return {"wire": {"v": 1, "s": [], "d": {}}, "snapshot": "snap-1", "error": None}


class LiveDashboardTests(unittest.TestCase):
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

    def start_server(self):
        dashboard = _FakeDashboard()
        server = live_dashboard.LiveDashboardServer(0, dashboard, 5)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.addCleanup(thread.join, 2)
        return server, dashboard

    def request(self, server, path, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=2)
        connection.request("GET", path, headers=headers or {})
        response = connection.getresponse()
        body = response.read()
        connection.close()
        return response, body

    def test_server_is_loopback_only_and_has_private_headers(self):
        server, _ = self.start_server()
        self.assertEqual("127.0.0.1", server.server_address[0])
        response, body = self.request(server, "/")
        self.assertEqual(200, response.status)
        self.assertEqual(b"<html>live</html>", body)
        self.assertEqual("no-store", response.getheader("Cache-Control"))
        self.assertEqual("nosniff", response.getheader("X-Content-Type-Options"))
        self.assertEqual("no-referrer", response.getheader("Referrer-Policy"))
        self.assertEqual("same-origin", response.getheader("Cross-Origin-Resource-Policy"))
        self.assertEqual("frame-ancestors 'none'", response.getheader("Content-Security-Policy"))

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
        self.assertEqual('"snap-1"', response.getheader("ETag"))
        self.assertEqual("snap-1", json.loads(body)["snapshot"])
        response, body = self.request(
            server,
            "/api/snapshot",
            {"If-None-Match": '"snap-1"'},
        )
        self.assertEqual(304, response.status)
        self.assertEqual(b"", body)
        self.assertEqual(2, dashboard.calls)

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

    def test_live_page_enables_polling_without_changing_static_page(self):
        dashboard = live_dashboard.LiveDashboard(["claude"])
        with mock.patch.object(dashboard, "refresh"), \
                mock.patch.object(dashboard, "_wire", {"v": 1, "s": [], "d": {}}):
            live = dashboard.page(5)
        self.assertIn('"enabled": true', live)
        self.assertIn('"interval": 5', live)
        self.assertIn("initLiveDashboard()", live)



if __name__ == "__main__":
    unittest.main()
