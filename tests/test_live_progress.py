"""Synthetic scan telemetry and restored-snapshot contracts."""
import http.client
import json
from pathlib import Path
import sys
import threading
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from tokens_cli import config, dashboard_payload, live_dashboard, readers


class LiveProgressTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        patches = (
            mock.patch.multiple(config,
                HOME=str(root), CLAUDE_PROJECTS=str(root / 'claude'),
                GEMINI_TMP=str(root / 'gemini'), CODEX_SESSIONS=str(root / 'codex'),
                CODEX_ARCHIVED_SESSIONS=str(root / 'archive'),
                CACHE_DIR=str(root / 'cache'), CACHE_FILE=str(root / 'cache' / 'records.json'),
                OUT_DIR=str(root / 'out'), SESSION_SUMMARY_FILE=str(root / 'out' / 'titles.json'),
                CCR_ROUTER_FILE=str(root / 'router.js')),
            mock.patch.object(readers, '_ccr_signature', return_value=None),
        )
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)
        for name, value in (('load_session_summaries', {}), ('build_session_index', {}),
                            ('session_title', '')):
            patcher = mock.patch.object(dashboard_payload.readers, name, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_status_is_small_and_progress_does_not_change_snapshot_revision(self):
        dashboard = live_dashboard.LiveDashboard(['claude'])
        entered, release = threading.Event(), threading.Event()
        now = [10.0]
        def collect(**kwargs):
            observer = kwargs['observer']
            observer('discovered', 'claude')
            observer('processed_parsed', 'claude')
            now[0] = 12.0
            observer('discovered', 'claude')
            entered.set()
            release.wait(5)
            return []
        with mock.patch.object(dashboard, '_file_signature', return_value=()), \
                mock.patch.object(readers, 'read_all', side_effect=collect), \
                mock.patch.object(live_dashboard.time, 'monotonic', side_effect=lambda: now[0]):
            thread = threading.Thread(target=dashboard.refresh)
            thread.start()
            try:
                self.assertTrue(entered.wait(3))
                status = dashboard.status()
                self.assertNotIn('wire', status)
                self.assertNotIn('etag', status)
                self.assertEqual('collection', status['scan']['stage'])
                self.assertEqual(2, status['scan']['discovered'])
                self.assertEqual(1, status['scan']['processed'])
                self.assertEqual(1, status['scan']['parsed'])
                revision = status['revision']
                now[0] = 15.0
                self.assertEqual(5.0, dashboard.status()['scan']['elapsed_seconds'])
                self.assertEqual(revision, dashboard.status()['revision'])
                self.assertFalse(dashboard.refresh())
                self.assertEqual(status['scan']['id'], dashboard.status()['scan']['id'])
            finally:
                release.set()
                thread.join(5)
        final = dashboard.status()
        self.assertEqual('success', final['scan']['outcome'])
        self.assertFalse(final['refreshing'])
        self.assertEqual({'discovery', 'collection', 'payload', 'encoding'},
                         set(final['scan']['stage_seconds']))
        final['scan']['stage_seconds']['discovery'] = 999
        self.assertNotEqual(999, dashboard.status()['scan']['stage_seconds']['discovery'])

    def test_failure_retains_error_and_terminal_counts_on_retry(self):
        dashboard = live_dashboard.LiveDashboard(['codex'])
        def collect(**kwargs):
            kwargs['observer']('discovered', 'codex')
            raise readers.CollectionIncompleteError('codex', 'usage_conflict',
                conflict_kind='modern_response_mismatch')
        with mock.patch.object(dashboard, '_file_signature', return_value=()), \
                mock.patch.object(readers, 'read_all', side_effect=collect):
            self.assertFalse(dashboard.refresh())
        status = dashboard.status()
        self.assertEqual('failed', status['scan']['outcome'])
        self.assertEqual(0, status['scan']['processed'])
        self.assertEqual(0, status['scan']['parsed'])
        self.assertEqual(0, status['scan']['cache_hits'])
        self.assertEqual(1, status['scan']['discovered'])
        self.assertFalse(status['has_snapshot'])
        expected = {'stage': 'collection', 'source': 'codex', 'reason': 'usage_conflict',
                    'conflict_kind': 'modern_response_mismatch'}
        self.assertEqual(expected, status['error_details'])
        retry_status = []
        def retry(**kwargs):
            kwargs['observer']('discovered', 'codex')
            retry_status.append(dashboard.status())
            raise readers.CollectionIncompleteError('codex', 'usage_conflict',
                conflict_kind='legacy_anchor_mismatch')
        with mock.patch.object(dashboard, '_file_signature', return_value=()), \
                mock.patch.object(readers, 'read_all', side_effect=retry):
            self.assertFalse(dashboard.refresh())
        self.assertEqual(1, len(retry_status))
        self.assertTrue(retry_status[0]['refreshing'])
        self.assertEqual('running', retry_status[0]['scan']['outcome'])
        self.assertEqual(expected, retry_status[0]['error_details'])
        self.assertEqual(0, retry_status[0]['scan']['processed'])
        final = dashboard.status()
        self.assertEqual('failed', final['scan']['outcome'])
        self.assertEqual(0, final['scan']['processed'])
        self.assertEqual('legacy_anchor_mismatch', final['error_details']['conflict_kind'])

    def test_status_endpoint_uses_same_request_boundary_without_wire_or_etag(self):
        dashboard = live_dashboard.LiveDashboard(['claude'])
        with mock.patch.object(dashboard, 'start'):
            server = live_dashboard.LiveDashboardServer(0, dashboard, 300)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        connection = http.client.HTTPConnection(*server.server_address, timeout=2)
        self.addCleanup(connection.close)
        with mock.patch.object(dashboard, 'refresh') as refresh:
            connection.request('GET', '/api/status', headers={'If-None-Match': '"live-0"'})
            response = connection.getresponse()
            body = json.loads(response.read())
            self.assertEqual(200, response.status)
            self.assertEqual('no-store', response.getheader('Cache-Control'))
            self.assertIsNone(response.getheader('ETag'))
            self.assertNotIn('wire', body)
            self.assertFalse(body['has_snapshot'])
            refresh.assert_not_called()
        connection.request('GET', '/api/status', headers={'Origin': 'https://untrusted.invalid'})
        response = connection.getresponse()
        response.read()
        self.assertEqual(403, response.status)

    def test_restore_requires_full_success_even_when_identity_is_unchanged(self):
        store = mock.Mock()
        payload = dashboard_payload.build_payload([], sources=['claude'], session_titles={})
        wire = live_dashboard.dashboard_wire.encode_payload(payload)
        store.load.return_value = {'wire': wire, 'checked_at': '2026-10-29T00:00:00+00:00'}
        store.save.return_value = True
        dashboard = live_dashboard.LiveDashboard(['claude'], snapshot_store=store)
        self.assertTrue(dashboard.status()['restored'])
        self.assertTrue(dashboard.response()['has_snapshot'])
        self.assertIsNone(dashboard._signature)
        with mock.patch.object(dashboard, '_file_signature', return_value=()), \
                mock.patch.object(readers, 'read_all', return_value=[]) as collect, \
                mock.patch.object(dashboard_payload, 'build_payload', return_value=payload):
            dashboard.refresh()
        collect.assert_called_once()
        self.assertFalse(dashboard.status()['restored'])
        self.assertEqual('success', dashboard.status()['scan']['outcome'])
        store.save.assert_called_once()

    def test_restore_failure_keeps_old_wire_and_does_not_save_partial_data(self):
        store = mock.Mock()
        payload = dashboard_payload.build_payload([], sources=['codex'], session_titles={})
        wire = live_dashboard.dashboard_wire.encode_payload(payload)
        store.load.return_value = {'wire': wire, 'checked_at': '2026-10-29T00:00:00+00:00'}
        dashboard = live_dashboard.LiveDashboard(['codex'], snapshot_store=store)
        with mock.patch.object(dashboard, '_file_signature', return_value=()), \
                mock.patch.object(readers, 'read_all', side_effect=
                                  readers.CollectionIncompleteError('codex', 'usage_conflict',
                                      conflict_kind='cross_file_identity_mismatch')):
            self.assertFalse(dashboard.refresh())
        status = dashboard.status()
        self.assertTrue(status['restored'])
        self.assertTrue(status['has_snapshot'])
        self.assertEqual(wire, dashboard.response()['wire'])
        self.assertEqual('2026-10-29T00:00:00+00:00', status['checked_at'])
        self.assertEqual('failed', status['scan']['outcome'])
        self.assertEqual(0, status['scan']['processed'])
        self.assertEqual({'stage': 'collection', 'source': 'codex', 'reason': 'usage_conflict',
                          'conflict_kind': 'cross_file_identity_mismatch'}, status['error_details'])
        self.assertEqual(status['error_details'], dashboard.response()['error_details'])
        with mock.patch.object(live_dashboard.report_dashboard, 'render_dashboard') as render:
            dashboard.page(300)
        self.assertEqual(status['error_details'], render.call_args.kwargs['live']['error_details'])
        store.save.assert_not_called()

    def test_slow_store_does_not_hold_state_lock_or_queue_another_scan(self):
        store = mock.Mock()
        store.load.return_value = None
        entered, release = threading.Event(), threading.Event()
        def save(*args):
            entered.set()
            release.wait(5)
            return True
        store.save.side_effect = save
        dashboard = live_dashboard.LiveDashboard(['claude'], snapshot_store=store)
        with mock.patch.object(dashboard, '_file_signature', return_value=()), \
                mock.patch.object(readers, 'read_all', return_value=[]):
            thread = threading.Thread(target=dashboard.refresh)
            thread.start()
            try:
                self.assertTrue(entered.wait(3))
                self.assertTrue(dashboard.status()['has_snapshot'])
                self.assertEqual('success', dashboard.status()['scan']['outcome'])
                self.assertFalse(dashboard.refresh())
            finally:
                release.set()
                thread.join(5)

    def test_unchanged_scan_has_terminal_timing_and_keeps_snapshot_etag_contract(self):
        dashboard = live_dashboard.LiveDashboard(['claude'])
        with mock.patch.object(dashboard, '_file_signature', return_value=()), \
                mock.patch.object(readers, 'read_all', return_value=[]) as collect:
            self.assertTrue(dashboard.refresh())
            self.assertFalse(dashboard.refresh())
        self.assertEqual(1, collect.call_count)
        status = dashboard.status()
        self.assertEqual('unchanged', status['scan']['outcome'])
        self.assertEqual(0, status['scan']['discovered'])
        self.assertEqual(dashboard.response()['revision'], status['revision'])
        self.assertNotIn('scan', dashboard.response())

    def test_store_failure_does_not_turn_valid_memory_snapshot_into_scan_failure(self):
        store = mock.Mock()
        store.load.return_value = None
        store.save.side_effect = OSError('private storage text')
        dashboard = live_dashboard.LiveDashboard(['claude'], snapshot_store=store)
        with mock.patch.object(dashboard, '_file_signature', return_value=()), \
                mock.patch.object(readers, 'read_all', return_value=[]):
            self.assertTrue(dashboard.refresh())
        status = dashboard.status()
        self.assertTrue(status['has_snapshot'])
        self.assertIsNone(status['error'])
        self.assertEqual('write_failed', status['storage_warning'])
        self.assertNotIn('private storage text', json.dumps(status))

    def test_terminal_progress_is_published_atomically_with_business_state(self):
        for outcome in ('success', 'failed', 'unchanged'):
            with self.subTest(outcome=outcome):
                dashboard = live_dashboard.LiveDashboard(['claude'])
                with mock.patch.object(dashboard, '_file_signature', return_value=()), \
                        mock.patch.object(readers, 'read_all', return_value=[]):
                    if outcome == 'unchanged':
                        dashboard.refresh()
                    observed = []
                    original_finish = live_dashboard._ScanProgress.finish
                    def finish(progress, result):
                        value = original_finish(progress, result)
                        observed.append(dashboard.status())
                        return value
                    failure = (readers.CollectionIncompleteError('claude', 'stat_failed')
                               if outcome == 'failed' else None)
                    with mock.patch.object(live_dashboard._ScanProgress, 'finish', finish), \
                            mock.patch.object(readers, 'read_all', return_value=[],
                                              side_effect=failure):
                        dashboard.refresh()
                self.assertEqual(1, len(observed))
                self.assertTrue(observed[0]['refreshing'])
                self.assertEqual('running', observed[0]['scan']['outcome'])
                self.assertFalse(dashboard.status()['refreshing'])
                self.assertEqual(outcome, dashboard.status()['scan']['outcome'])

    def test_no_cache_or_anonymous_dashboard_does_not_access_injected_store(self):
        for kwargs in ({'use_cache': False}, {'anonymize': True}):
            store = mock.Mock()
            dashboard = live_dashboard.LiveDashboard(['claude'], snapshot_store=store, **kwargs)
            with mock.patch.object(dashboard, '_file_signature', return_value=()), \
                    mock.patch.object(readers, 'read_all', return_value=[]):
                dashboard.refresh()
            store.load.assert_not_called()
            store.save.assert_not_called()


if __name__ == '__main__':
    unittest.main()
