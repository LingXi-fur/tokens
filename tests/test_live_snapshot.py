"""Only synthetic payloads and temporary files exercise the snapshot boundary."""
import copy
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest import mock
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tokens_cli import config, dashboard_payload, dashboard_wire, live_snapshot


CHECKED_AT = "2026-10-29T10:00:00+00:00"


def canonical_digest(value):
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode()).hexdigest()


def identify(payload):
    value = copy.deepcopy(payload)
    value.pop("generated", None)
    value.pop("calendar_day", None)
    value["snapshot"].pop("id", None)
    payload["snapshot"]["id"] = dashboard_payload._snapshot_identity(value)
    return dashboard_wire.encode_payload(payload)


class SnapshotStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tokens-snapshot-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.directory = self.root / "live-snapshot"
        patches = {
            "TZ": ZoneInfo("UTC"),
            "CACHE_DIR": str(self.root / "cache"),
            "CLAUDE_PROJECTS": str(self.root / "claude"),
            "GEMINI_TMP": str(self.root / "gemini"),
            "CODEX_SESSIONS": str(self.root / "codex"),
            "CODEX_ARCHIVED_SESSIONS": str(self.root / "codex-archive"),
            "CCR_ROUTER_FILE": str(self.root / "router.js"),
            "SESSION_SUMMARY_FILE": str(self.root / "titles.json"),
        }
        patcher = mock.patch.multiple(config, **patches)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.store = live_snapshot.SnapshotStore(["claude"], directory=self.directory)
        self.payload = dashboard_payload.build_payload(
            [{"source": "claude", "ts": CHECKED_AT, "date": "2026-10-29",
              "model": "synthetic-model", "input": 7, "output": 3,
              "cache_read": 0, "cache_write": 0, "total": 10,
              "session": "synthetic-session", "cwd": "/synthetic/project"}],
            sources=["claude"], session_titles={},
        )
        self.wire = dashboard_wire.encode_payload(self.payload)

    @property
    def target(self):
        return self.directory / "last.json"

    def save(self):
        self.assertTrue(self.store.save(self.wire, CHECKED_AT))
        return self.target.read_bytes()

    def rewrite(self, change):
        document = json.loads(self.target.read_bytes())
        change(document)
        if "wire" in document:
            document["wire_sha256"] = canonical_digest(document["wire"])
        self.target.write_text(json.dumps(document), encoding="utf-8")

    def assert_rejected_wire(self, wire):
        old = self.save()
        self.assertFalse(self.store.save(wire, CHECKED_AT))
        self.assertEqual(old, self.target.read_bytes())

    @unittest.skipUnless(live_snapshot._supported(),
                         'requires POSIX snapshot-store capabilities')
    def test_round_trip_uses_one_private_file_and_returns_original_wire(self):
        self.assertIsNone(self.store.load())
        self.assertFalse(self.directory.exists())
        self.save()
        self.assertEqual({"wire": self.wire, "checked_at": CHECKED_AT}, self.store.load())
        self.assertEqual(0o700, stat.S_IMODE(self.directory.stat().st_mode))
        self.assertEqual(0o600, stat.S_IMODE(self.target.stat().st_mode))
        self.assertEqual(["last.json"], sorted(p.name for p in self.directory.iterdir()))
        document = json.loads(self.target.read_bytes())
        self.assertEqual({"schema", "fingerprint", "wire_sha256", "wire", "checked_at"}, set(document))
        self.assertEqual(64, len(document["fingerprint"]))
        self.assertEqual(canonical_digest(self.wire), document["wire_sha256"])

    def test_constructor_and_factory_do_not_touch_filesystem(self):
        with mock.patch.object(live_snapshot.os, "open", side_effect=AssertionError), \
             mock.patch.object(live_snapshot.os, "stat", side_effect=AssertionError), \
             mock.patch("builtins.open", side_effect=AssertionError):
            store = live_snapshot.SnapshotStore(["claude"], directory=self.directory)
            self.assertIsNotNone(store)
            factory = live_snapshot.create_store(["claude"])
            if live_snapshot._supported():
                self.assertIsNotNone(factory)
            else:
                self.assertIsNone(factory)

    def test_anonymous_and_no_cache_factory_are_zero_disk_access(self):
        with mock.patch.object(live_snapshot.os, "open", side_effect=AssertionError), \
             mock.patch.object(live_snapshot.os, "stat", side_effect=AssertionError), \
             mock.patch("builtins.open", side_effect=AssertionError):
            self.assertIsNone(live_snapshot.create_store(["claude"], anonymize=True))
            self.assertIsNone(live_snapshot.create_store(["claude"], use_cache=False))
        self.assertFalse((self.root / "cache").exists())

    def test_windows_and_ambiguous_timezone_disable_all_disk_access(self):
        for patcher in (mock.patch.object(live_snapshot.sys, "platform", "win32"),
                        mock.patch.object(config, "TZ", config._SYSTEM_LOCAL_TIMEZONE)):
            with patcher, mock.patch.object(live_snapshot.os, "open", side_effect=AssertionError), \
                 mock.patch.object(live_snapshot.os, "stat", side_effect=AssertionError):
                store = live_snapshot.SnapshotStore(["claude"], directory=self.directory)
                self.assertIsNone(live_snapshot.create_store(["claude"]))
                self.assertIsNone(store.load())
                self.assertFalse(store.save(self.wire, CHECKED_AT))

    @unittest.skipUnless(live_snapshot._supported(),
                         'requires POSIX snapshot-store capabilities')
    def test_default_location_and_missing_parent_are_created_only_on_save(self):
        store = live_snapshot.SnapshotStore(["claude"])
        self.assertIsNone(store.load())
        self.assertFalse((self.root / "cache").exists())
        self.assertTrue(store.save(self.wire, CHECKED_AT))
        self.assertTrue((self.root / "cache" / "live-snapshot" / "last.json").is_file())

    @unittest.skipUnless(live_snapshot._supported(),
                         'requires POSIX snapshot-store capabilities')
    def test_unsafe_directory_is_not_repaired(self):
        self.directory.mkdir(mode=0o755)
        self.assertIsNone(self.store.load())
        self.assertFalse(self.store.save(self.wire, CHECKED_AT))
        self.assertEqual(0o755, stat.S_IMODE(self.directory.stat().st_mode))
        self.assertFalse(self.target.exists())

    @unittest.skipUnless(live_snapshot._supported(),
                         'requires POSIX snapshot-store capabilities')
    def test_unsafe_file_modes_are_neither_loaded_nor_replaced(self):
        old = self.save()
        for mode in (0o644, 0o400, 0o660, 0o1600):
            with self.subTest(mode=oct(mode)):
                self.target.chmod(mode)
                self.assertIsNone(self.store.load())
                self.assertFalse(self.store.save(self.wire, CHECKED_AT))
                self.assertEqual(mode, stat.S_IMODE(self.target.stat().st_mode))
                self.assertEqual(old, self.target.read_bytes())
        self.target.chmod(0o600)

    @unittest.skipUnless(live_snapshot._supported(),
                         'requires POSIX snapshot-store capabilities')
    def test_directory_and_target_symlinks_are_refused(self):
        other = self.root / "other"
        other.mkdir(mode=0o700)
        self.directory.symlink_to(other, target_is_directory=True)
        self.assertIsNone(self.store.load())
        self.assertFalse(self.store.save(self.wire, CHECKED_AT))
        self.directory.unlink()
        self.directory.mkdir(mode=0o700)
        victim = self.root / "victim"
        victim.write_bytes(b"preserve")
        self.target.symlink_to(victim)
        self.assertIsNone(self.store.load())
        self.assertFalse(self.store.save(self.wire, CHECKED_AT))
        self.assertEqual(b"preserve", victim.read_bytes())
        self.assertTrue(self.target.is_symlink())

    @unittest.skipUnless(live_snapshot._supported(),
                         'requires POSIX snapshot-store capabilities')
    def test_symlink_parent_and_group_writable_parent_are_refused(self):
        actual = self.root / "actual"
        actual.mkdir(mode=0o700)
        alias = self.root / "alias"
        alias.symlink_to(actual, target_is_directory=True)
        store = live_snapshot.SnapshotStore(["claude"], directory=alias / "private")
        self.assertFalse(store.save(self.wire, CHECKED_AT))
        actual.chmod(0o777)
        store = live_snapshot.SnapshotStore(["claude"], directory=actual / "private")
        self.assertFalse(store.save(self.wire, CHECKED_AT))
        self.assertFalse((actual / "private").exists())

    @unittest.skipUnless(live_snapshot._supported(),
                         'requires POSIX snapshot-store capabilities')
    def test_hardlinked_or_nonregular_target_is_refused(self):
        self.save()
        link = self.root / "hardlink"
        os.link(self.target, link)
        self.assertIsNone(self.store.load())
        self.assertFalse(self.store.save(self.wire, CHECKED_AT))
        self.target.unlink()
        self.target.mkdir(mode=0o700)
        self.assertIsNone(self.store.load())
        self.assertFalse(self.store.save(self.wire, CHECKED_AT))
        self.assertTrue(link.exists())

    @unittest.skipUnless(live_snapshot._supported(),
                         'requires POSIX snapshot-store capabilities')
    def test_wrong_owner_is_refused_without_permission_repair(self):
        old = self.save()
        with mock.patch.object(live_snapshot.os, "getuid", return_value=os.getuid() + 1):
            self.assertIsNone(self.store.load())
            self.assertFalse(self.store.save(self.wire, CHECKED_AT))
        self.assertEqual(old, self.target.read_bytes())

    @unittest.skipUnless(live_snapshot._supported(),
                         'requires POSIX snapshot-store capabilities')
    def test_symlinked_router_and_titles_invalidate_when_referent_changes(self):
        for name in ('CCR_ROUTER_FILE', 'SESSION_SUMMARY_FILE'):
            with self.subTest(config=name):
                link = Path(getattr(config, name))
                referent = self.root / (name.lower() + '-referent')
                referent.write_text('synthetic-before')
                link.symlink_to(referent)
                self.save()
                self.assertIsNotNone(self.store.load())
                referent.write_text('synthetic-after-longer')
                self.assertIsNone(self.store.load())

    def test_non_utf8_json_is_rejected_before_stdlib_allocation(self):
        value = '["∀崀",' + ('{},' * 20) + '"嬀∀"]'
        for encoding in ('utf-16', 'utf-16le', 'utf-16be',
                         'utf-32', 'utf-32le', 'utf-32be'):
            with self.subTest(encoding=encoding):
                with mock.patch.object(live_snapshot.json, 'loads') as decode:
                    with self.assertRaises(ValueError):
                        live_snapshot._parsed(value.encode(encoding))
                decode.assert_not_called()

    @unittest.skipUnless(live_snapshot._supported(),
                         'requires POSIX snapshot-store capabilities')
    def test_digest_tampering_and_invalid_json_are_cache_misses(self):
        self.save()
        document = json.loads(self.target.read_bytes())
        document["wire_sha256"] = "0" * 64
        self.target.write_text(json.dumps(document))
        self.assertIsNone(self.store.load())
        for raw in (b"{", b'null', b'{"schema":1,"schema":1}', b'NaN', b'"\\ud800"'):
            self.target.write_bytes(raw)
            self.assertIsNone(self.store.load())

    @unittest.skipUnless(live_snapshot._supported(),
                         'requires POSIX snapshot-store capabilities')
    def test_snapshot_identity_is_verified_even_with_resealed_wire_digest(self):
        self.save()
        bad = copy.deepcopy(self.payload)
        bad["n_sessions"] += 1
        self.rewrite(lambda document: document.update(wire=dashboard_wire.encode_payload(bad)))
        self.assertIsNone(self.store.load())

    @unittest.skipUnless(live_snapshot._supported(),
                         'requires POSIX snapshot-store capabilities')
    def test_identity_matches_payload_algorithm_and_ignores_calendar_metadata(self):
        payload = copy.deepcopy(self.payload)
        payload["generated"] = "2026-10-30 00:00"
        payload["calendar_day"] = "2026-10-30"
        wire = dashboard_wire.encode_payload(payload)
        self.assertTrue(self.store.save(wire, CHECKED_AT))
        self.assertEqual(wire, self.store.load()["wire"])

    @unittest.skipUnless(live_snapshot._supported(),
                         'requires POSIX snapshot-store capabilities')
    def test_cache_limit_depth_and_node_budget_are_enforced(self):
        old = self.save()
        with mock.patch.object(live_snapshot, "MAX_BYTES", len(old) - 1):
            self.assertIsNone(self.store.load())
            self.assertFalse(self.store.save(self.wire, CHECKED_AT))
        self.assertEqual(old, self.target.read_bytes())
        self.target.write_bytes(b"[" * 65 + b"0" + b"]" * 65)
        self.assertIsNone(self.store.load())
        with mock.patch.object(live_snapshot, "MAX_NODES", 20):
            self.target.write_bytes(b"[" + b"0," * 100 + b"0]")
            self.assertIsNone(self.store.load())

    @unittest.skipUnless(live_snapshot._supported(),
                         'requires POSIX snapshot-store capabilities')
    def test_deep_cyclic_nonfinite_or_non_json_wire_does_not_replace_old_file(self):
        variants = []
        deep = {}
        cursor = deep
        for _ in range(65):
            cursor["x"] = {}
            cursor = cursor["x"]
        variants.append({"v": 1, "s": [], "d": deep})
        cycle = []
        cycle.append(cycle)
        variants.extend(({"v": 1, "s": [], "d": cycle},
                         {"v": 1, "s": [], "d": {"n": float("nan")}},
                         {"v": 1, "s": [], "d": {"n": object()}}))
        for wire in variants:
            with self.subTest(kind=type(wire["d"]).__name__):
                self.assert_rejected_wire(wire)

    @unittest.skipUnless(live_snapshot._supported(),
                         'requires POSIX snapshot-store capabilities')
    def test_invalid_refs_tables_and_decoded_key_collisions_are_rejected(self):
        variants = [
            {"v": 1, "s": [], "d": {"x": ref}}
            for ref in ("§", "§0", "§-1", "§+0", "§00", "§ 0", "§" + "z" * 100)
        ]
        variants.extend((
            {"v": 1, "s": [7], "d": {}},
            {"v": 1, "s": ["same", "same"], "d": {}},
            {"v": 1, "s": ["§marker"], "d": {}},
            {"v": 1, "s": ["same"], "d": {"same": 1, "§0": 2}},
            {"v": True, "s": [], "d": {}},
        ))
        for wire in variants:
            self.assert_rejected_wire(wire)

    @unittest.skipUnless(live_snapshot._supported(),
                         'requires POSIX snapshot-store capabilities')
    def test_reference_expansion_has_a_separate_decoded_byte_budget(self):
        wire = {"v": 1, "s": ["x" * 1024], "d": ["§0"] * 100}
        self.save()
        with mock.patch.object(live_snapshot, "MAX_DECODED_BYTES", 4096):
            self.assertFalse(self.store.save(wire, CHECKED_AT))
            self.rewrite(lambda document: document.update(wire=wire))
            self.assertIsNone(self.store.load())

    @unittest.skipUnless(live_snapshot._supported(),
                         'requires POSIX snapshot-store capabilities')
    def test_schema_sources_timezone_range_and_extra_private_fields_are_rejected(self):
        changes = [
            lambda p: p["snapshot"].update(snapshot_schema=True),
            lambda p: p["snapshot"].update(metric_schema=999),
            lambda p: p["snapshot"].update(timezone="Europe/Paris"),
            lambda p: p.update(source=["codex"]),
            lambda p: p.update(anonymized=True),
            lambda p: p.update(raw_messages=["never persist"]),
            lambda p: p.update(price_config={"secret": "never persist"}),
            lambda p: p["range"].update(since="2026-01-01"),
            lambda p: p["cost"].update(schema=999),
            lambda p: p["cost"]["models"][0].update(source="codex"),
        ]
        for change in changes:
            payload = copy.deepcopy(self.payload)
            change(payload)
            self.assert_rejected_wire(identify(payload))

    @unittest.skipUnless(live_snapshot._supported(),
                         'requires POSIX snapshot-store capabilities')
    def test_invalid_checked_at_and_changed_configuration_are_misses(self):
        self.save()
        for timestamp in (None, "private-text", "2026-10-29T10:00:00", 123):
            self.assertFalse(self.store.save(self.wire, timestamp))
        for key in ("CLAUDE_PROJECTS", "CODEX_ARCHIVED_SESSIONS", "SESSION_SUMMARY_FILE"):
            with mock.patch.object(config, key, str(self.root / "changed")):
                self.assertIsNone(self.store.load())
        with mock.patch.object(config, "TZ", ZoneInfo("Europe/Paris")):
            self.assertIsNone(self.store.load())
        other = live_snapshot.SnapshotStore(["codex"], directory=self.directory)
        self.assertIsNone(other.load())

    @unittest.skipUnless(live_snapshot._supported(),
                         'requires POSIX snapshot-store capabilities')
    def test_router_and_sidecar_signatures_invalidate_without_reading_contents(self):
        router = Path(config.CCR_ROUTER_FILE)
        sidecar = Path(config.SESSION_SUMMARY_FILE)
        router.write_text("synthetic router")
        sidecar.write_text("synthetic title sidecar")
        self.save()
        router.write_text("different synthetic router")
        self.assertIsNone(self.store.load())
        self.save()
        sidecar.write_text("different synthetic sidecar")
        self.assertIsNone(self.store.load())
        with mock.patch.object(live_snapshot, "_code_digest", wraps=live_snapshot._code_digest), \
             mock.patch("builtins.open", side_effect=AssertionError("no body reads")):
            self.assertTrue(self.store.save(self.wire, CHECKED_AT))

    @unittest.skipUnless(live_snapshot._supported(),
                         'requires POSIX snapshot-store capabilities')
    def test_source_code_digest_is_part_of_compatibility(self):
        self.save()
        with mock.patch.object(live_snapshot, "_code_digest", return_value="f" * 64):
            self.assertIsNone(self.store.load())
        code = self.root / "synthetic_reader.py"
        code.write_text("first synthetic implementation")
        with mock.patch.object(live_snapshot, "_CODE_FILES", (str(code),)):
            first = live_snapshot._code_digest()
            code.write_text("other synthetic implementation")
            second = live_snapshot._code_digest()
        self.assertNotEqual(first, second)

    @unittest.skipUnless(live_snapshot._supported(),
                         'requires POSIX snapshot-store capabilities')
    def test_write_fsync_and_replace_failures_preserve_previous_file(self):
        old = self.save()
        for name in ("write", "fsync", "replace"):
            with self.subTest(operation=name), \
                 mock.patch.object(live_snapshot.os, name, side_effect=OSError("synthetic failure")):
                self.assertFalse(self.store.save(self.wire, CHECKED_AT))
            self.assertEqual(old, self.target.read_bytes())
            self.assertEqual(["last.json"], sorted(p.name for p in self.directory.iterdir()))

    @unittest.skipUnless(live_snapshot._supported(),
                         'requires POSIX snapshot-store capabilities')
    def test_unused_table_entries_and_nested_private_fields_are_not_persisted(self):
        wire = copy.deepcopy(self.wire)
        wire["s"].append("unused private conversation")
        self.assert_rejected_wire(wire)
        for change in (
            lambda p: p["provenance"].update(raw_messages=["private text"]),
            lambda p: p["session_context"]["synthetic-session"].update(prices={"x": 1}),
            lambda p: p["day_details"]["2026-10-29"].update(raw_records=["private text"]),
            lambda p: p["day"][0].update(aliases={"real": "anonymous"}),
        ):
            payload = copy.deepcopy(self.payload)
            change(payload)
            self.assert_rejected_wire(identify(payload))

    @unittest.skipUnless(live_snapshot._supported(),
                         'requires POSIX snapshot-store capabilities')
    def test_target_replacement_during_load_is_detected(self):
        self.save()
        read = live_snapshot.os.read
        replaced = False
        def replacing_read(fd, size):
            nonlocal replaced
            data = read(fd, size)
            if not replaced and data.startswith(b'{"checked_at"'):
                replaced = True
                replacement = self.directory / "replacement"
                replacement.write_bytes(self.target.read_bytes())
                replacement.chmod(0o600)
                os.replace(replacement, self.target)
            return data
        with mock.patch.object(live_snapshot.os, "read", side_effect=replacing_read):
            self.assertIsNone(self.store.load())
        self.assertTrue(replaced)

    @unittest.skipUnless(live_snapshot._supported(),
                         'requires POSIX snapshot-store capabilities')
    def test_target_replacement_before_save_does_not_overwrite_new_target(self):
        self.save()
        fsync = live_snapshot.os.fsync
        replaced = False
        replacement_bytes = b"replacement by a different writer"
        def replacing_fsync(fd):
            nonlocal replaced
            fsync(fd)
            if not replaced:
                replaced = True
                replacement = self.directory / "replacement"
                replacement.write_bytes(replacement_bytes)
                replacement.chmod(0o600)
                os.replace(replacement, self.target)
        with mock.patch.object(live_snapshot.os, "fsync", side_effect=replacing_fsync):
            self.assertFalse(self.store.save(self.wire, CHECKED_AT))
        self.assertEqual(replacement_bytes, self.target.read_bytes())
        self.assertEqual(["last.json"], sorted(p.name for p in self.directory.iterdir()))

    @unittest.skipUnless(live_snapshot._supported(),
                         'requires POSIX snapshot-store capabilities')
    def test_close_errors_never_escape_public_interface(self):
        self.save()
        close = live_snapshot.os.close
        def failing_close(fd):
            close(fd)
            raise OSError("synthetic close failure")
        with mock.patch.object(live_snapshot.os, "close", side_effect=failing_close):
            result = self.store.load()
            self.assertIn(result is None, (True, False))
            self.assertIsInstance(self.store.save(self.wire, CHECKED_AT), bool)

    @unittest.skipUnless(live_snapshot._supported(),
                         'requires POSIX snapshot-store capabilities')
    def test_valid_empty_combined_sources_ranges_and_fixed_timezone(self):
        from datetime import timezone
        cases = [
            (["claude"], None, None),
            (["claude", "gemini", "codex"], "2026-10-01", "2026-10-31"),
        ]
        for sources, since, until in cases:
            directory = self.root / ("empty-" + str(len(sources)))
            store = live_snapshot.SnapshotStore(sources, since, until, directory=directory)
            with mock.patch.object(config, "TZ", timezone.utc):
                payload = dashboard_payload.build_payload(
                    [], sources=sources, since=since, until=until, session_titles={})
                wire = dashboard_wire.encode_payload(payload)
                self.assertTrue(store.save(wire, CHECKED_AT))
                self.assertEqual(wire, store.load()["wire"])

    @unittest.skipUnless(live_snapshot._supported(),
                         'requires POSIX snapshot-store capabilities')
    def test_wire_escaped_marker_round_trip_uses_payload_identity(self):
        payload = copy.deepcopy(self.payload)
        payload["pretty"][payload["models"][0]] = "§synthetic label"
        wire = identify(payload)
        self.assertTrue(self.store.save(wire, CHECKED_AT))
        self.assertEqual(wire, self.store.load()["wire"])

    @unittest.skipUnless(live_snapshot._supported(),
                         'requires POSIX snapshot-store capabilities')
    def test_request_models_shape_is_validated(self):
        records = [{
            "source": "claude", "ts": CHECKED_AT, "date": "2026-10-29",
            "model": "synthetic-backend", "request_model": "synthetic-alias",
            "input": 7, "output": 3, "cache_read": 0, "cache_write": 0,
            "total": 10, "session": "synthetic-session", "cwd": "/synthetic/project",
        }]
        payload = dashboard_payload.build_payload(
            records, sources=["claude"], session_titles={})
        self.assertEqual(
            {"synthetic-backend": {"synthetic-alias": 10}},
            payload["day"][0]["request_models"])
        self.assertEqual(
            [{"request": "synthetic-alias", "model": "synthetic-backend",
              "source": "claude", "total": 10}],
            payload["request_models"])
        wire = identify(payload)
        self.assertTrue(self.store.save(wire, CHECKED_AT))
        self.assertEqual(wire, self.store.load()["wire"])

        def bad_total(p):
            p["request_models"][0]["total"] = "10"

        def bad_name(p):
            p["request_models"][0]["request"] = 7

        def week_shape(p):
            p["week"][0]["request_models"] = {}

        # drop_entry（清空某条别名）是合法负载形状，不在此拒：形状校验不背
        # 一致性——identity digest 已覆盖整个 payload。非 str 键在 wire 编码
        # 边界已被 json 降级为 str 键（不可表达），故只测 str 类型违规。
        for change in (bad_total, bad_name, week_shape):
            tampered = copy.deepcopy(payload)
            change(tampered)
            self.assert_rejected_wire(identify(tampered))

    @unittest.skipUnless(live_snapshot._supported(),
                         'requires POSIX snapshot-store capabilities')
    def test_request_models_default_shapes_when_no_aliases(self):
        payload = copy.deepcopy(self.payload)
        self.assertEqual({}, payload["day"][0]["request_models"])
        self.assertEqual([], payload["request_models"])
        for row in payload["week"] + payload["month"]:
            self.assertNotIn("request_models", row)
        wire = identify(payload)
        self.assertTrue(self.store.save(wire, CHECKED_AT))
        self.assertEqual(wire, self.store.load()["wire"])

    def test_failed_validation_never_creates_directory(self):
        self.assertFalse(self.store.save({"v": 1, "s": [], "d": {}}, CHECKED_AT))
        self.assertFalse(self.directory.exists())

    def test_unknown_sources_and_invalid_ranges_disable_store(self):
        for kwargs in ({"sources": ["unknown"]}, {"sources": []},
                       {"sources": ["claude"], "since": "not-a-date"},
                       {"sources": ["claude"], "since": "2026-12-01", "until": "2026-01-01"}):
            self.assertIsNone(live_snapshot.create_store(**kwargs))


if __name__ == "__main__":
    unittest.main()
