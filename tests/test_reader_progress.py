"""Observer must not change reader results or failure contracts."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from tokens_cli import config, readers


class ReaderProgressTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        for name, value in (('CACHE_DIR', str(self.root / 'cache')),
                            ('CACHE_FILE', str(self.root / 'cache' / 'records.json'))):
            patcher = mock.patch.object(config, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = mock.patch.object(readers, '_ccr_signature', return_value='synthetic-router')
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_cold_and_warm_report_aggregate_events_without_paths(self):
        path = self.root / 'session-synthetic.json'
        path.write_text('{}')
        parse = mock.Mock(return_value=[])
        events = []
        with mock.patch.dict(readers.SOURCES, {'gemini': (lambda: [str(path)], parse)}), \
                mock.patch.object(config, 'timezone_name', return_value='UTC'):
            first = readers.read_all(['gemini'], observer=lambda *event: events.append(event))
            cold = list(events)
            events.clear()
            second = readers.read_all(['gemini'], observer=lambda *event: events.append(event))
        self.assertEqual(first, second)
        self.assertEqual([('discovered', 'gemini'), ('processed_parsed', 'gemini')], cold)
        self.assertEqual([('discovered', 'gemini'), ('processed_cached', 'gemini')], events)
        self.assertEqual(1, parse.call_count)
        self.assertNotIn(str(path), json.dumps(cold + events))

    def test_observer_exception_cannot_change_collection_result(self):
        path = self.root / 'session-synthetic.json'
        path.write_text('{}')
        def observer(*args):
            raise RuntimeError('private observer text')
        with mock.patch.dict(readers.SOURCES, {'gemini': (lambda: [str(path)], lambda p: [])}):
            expected = readers.read_all(['gemini'], use_cache=False)
            actual = readers.read_all(['gemini'], use_cache=False, observer=observer)
        self.assertEqual(expected, actual)

    def test_gemini_skipped_stat_and_parse_are_not_counted_as_success(self):
        path = self.root / 'session-synthetic.json'
        path.write_text('{}')
        missing = self.root / 'session-missing.json'
        def parse(path):
            raise ValueError('synthetic bad record')
        events = []
        with mock.patch.dict(readers.SOURCES, {'gemini': (lambda: [str(missing), str(path)], parse)}):
            self.assertEqual([], readers.read_all(['gemini'], use_cache=False,
                              observer=lambda *event: events.append(event)))
        self.assertEqual([('discovered', 'gemini'), ('skipped', 'gemini'),
                          ('discovered', 'gemini'), ('skipped', 'gemini')], events)

    def test_strict_failure_has_discovered_but_no_processed_event(self):
        path = self.root / 'rollout-synthetic.jsonl'
        path.write_text('{}\n')
        def parse(path):
            raise readers.CollectionIncompleteError('codex', 'usage_conflict')
        events = []
        with mock.patch.dict(readers.SOURCES, {'codex': (lambda: [str(path)], parse)}):
            with self.assertRaises(readers.CollectionIncompleteError) as raised:
                readers.read_all(['codex'], use_cache=False,
                                 observer=lambda *event: events.append(event))
        self.assertEqual('usage_conflict', raised.exception.reason)
        self.assertEqual([('discovered', 'codex')], events)

    def test_candidate_generator_is_not_preconsumed(self):
        path = self.root / 'session-synthetic.json'
        path.write_text('{}')
        order = []
        def files():
            order.append('discover')
            yield str(path)
            order.append('after-first')
        def parse(path):
            order.append('parse')
            return []
        with mock.patch.dict(readers.SOURCES, {'gemini': (files, parse)}):
            readers.read_all(['gemini'], use_cache=False, observer=lambda *event: None)
        self.assertEqual(['discover', 'parse', 'after-first'], order)


if __name__ == '__main__':
    unittest.main()
