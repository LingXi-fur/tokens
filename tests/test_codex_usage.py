"""Synthetic Codex collection contracts; never inspect real application data."""
import json
from datetime import timezone
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from tokens_cli import config, readers, _claude_json, codex_usage, live_dashboard, doctor, dashboard_payload


USAGE = {"input_tokens": 100, "cached_input_tokens": 30,
         "cache_write_input_tokens": 0, "output_tokens": 50,
         "reasoning_output_tokens": 20, "total_tokens": 150}


def event(kind, payload, timestamp="2026-10-28T09:00:00Z"):
    return {"type": kind, "timestamp": timestamp, "payload": payload}


def header():
    return [event("session_meta", {"id": "synthetic-thread"}),
            event("turn_context", {"model": "synthetic-codex"})]


def modern(response="r1", usage=None):
    return event("token_usage_record", {"response_id": response,
        "session_id": "synthetic-thread", "thread_id": "synthetic-thread",
        "usage": dict(USAGE if usage is None else usage)})


def legacy(total=150, usage=None):
    return event("event_msg", {"type": "token_count", "info": {
        "last_token_usage": dict(USAGE if usage is None else usage),
        "total_token_usage": dict(USAGE, total_tokens=total)}})


class CodexUsageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        # All filesystem boundaries stay synthetic, including implicit live reads.
        patches = [mock.patch.multiple(config,
            HOME=str(self.root),
            CLAUDE_PROJECTS=str(self.root / "claude"),
            GEMINI_TMP=str(self.root / "gemini"),
            CODEX_SESSIONS=str(self.root / "sessions"),
            CODEX_ARCHIVED_SESSIONS=str(self.root / "archive"),
            CACHE_DIR=str(self.root / "cache"),
            CACHE_FILE=str(self.root / "cache" / "records.json"),
            OUT_DIR=str(self.root / "out"),
            SESSION_SUMMARY_FILE=str(self.root / "out" / "titles.json"),
            CCR_ROUTER_FILE=str(self.root / "router.js"),
            TZ=timezone.utc),
            mock.patch.object(readers, "_ccr_signature", return_value=None),
            mock.patch.object(readers, "load_session_summaries", return_value={}),
            mock.patch.object(readers, "build_session_index", return_value={}),
            mock.patch.object(readers, "session_title", return_value="")]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def write(self, events, name="rollout-synthetic.jsonl"):
        p = self.root / name
        p.write_text("\n".join(json.dumps(e) for e in events) + "\n")
        return str(p)

    def test_modern_and_legacy_mirrors_count_once_and_model_context_is_top_level(self):
        records = readers.codex_parse(self.write(header() + [modern(), legacy()]))
        self.assertEqual(1, len(records))
        self.assertEqual("synthetic-codex", records[0]["model"])
        self.assertEqual((100, 50, 30, 150), tuple(records[0][k] for k in ("input", "output", "cache_read", "total")))

    def test_equal_usage_distinct_responses_are_not_deduplicated(self):
        records = readers.codex_parse(self.write(header() + [modern(), legacy(), modern("r2"), legacy(300)]))
        self.assertEqual(2, len(records))
        self.assertEqual(300, sum(r["total"] for r in records))

    def test_duplicate_responses_and_legacy_totals_do_not_inflate(self):
        for events in ([modern(), modern()], [legacy(), legacy()]):
            with self.subTest(modern=events[0]["type"]):
                self.assertEqual(1, len(readers.codex_parse(self.write(header() + events))))

    def test_reverse_mirror_order_is_supported_without_summing(self):
        records = readers.codex_parse(self.write(header() + [legacy(), modern()]))
        self.assertEqual(1, len(records))

    def test_interleaved_mixed_formats_estimate_and_mirrors_count_once(self):
        # Real producer shape: modern persist is not ordered against legacy
        # accounting; union accounting never double-counts mirrored values.
        def ledger(events):
            return sorted(record["total"]
                          for record in readers.codex_parse(self.write(events)))
        self.assertEqual([150, 150], ledger(
            header() + [legacy(), modern(), modern("r2"), legacy(300)]))
        # An estimate between consumptions is accepted without adding a record.
        estimate = legacy(usage=dict(dict.fromkeys(USAGE, 0), total_tokens=75))
        events = header() + [legacy(), modern(), estimate, modern("r2"), legacy(300)]
        self.assertEqual([150, 150], ledger(events))
        # Modern-first interleaving of the same consumptions still passes.
        swapped = header() + [modern(), legacy(), estimate, legacy(300), modern("r2")]
        self.assertEqual([150, 150], ledger(swapped))

    def test_legacy_ledger_with_partial_modern_projection_counts_union(self):
        # Real producer shape: modern persist is a partial value projection of
        # the legacy ledger. The union counts legacy entries plus modern-only
        # consumptions; mirrored values are never double-counted.
        usage2 = dict(USAGE, output_tokens=51, total_tokens=151)
        events = header() + [legacy(), legacy(151, usage=usage2), modern()]
        records = readers.codex_parse(self.write(events))
        self.assertEqual([150, 151], sorted(
            record["total"] for record in records))
        # Duplicate-value mirrors need matching legacy copies; identical
        # cumulative anchors dedupe, so growth provides three ledger entries.
        growth = [event("event_msg", {"type": "token_count", "info": {
            "last_token_usage": dict(USAGE),
            "total_token_usage": {key: value * index for key, value in USAGE.items()}}})
            for index in (1, 2, 3)]
        events = header() + growth + [modern(), modern("r2")]
        self.assertEqual([150, 150, 150], sorted(
            record["total"] for record in readers.codex_parse(self.write(events))))

    def test_modern_only_consumptions_count_as_independent_ledger_entries(self):
        # v14 union accounting: modern records mirroring a legacy value are
        # absorbed; modern records with no legacy counterpart are independent
        # consumptions and are counted once with their own evidence.
        changed = dict(USAGE, output_tokens=51, total_tokens=151)
        events = header() + [legacy(), modern(), modern("r2", usage=changed)]
        records = readers.codex_parse(self.write(events))
        self.assertEqual([150, 151], sorted(
            record["total"] for record in records))
        self.assertTrue(all(not record["billing"]["uncertain"]
                            for record in records))
        # Over-issued copies count each extra occurrence once.
        events = header() + [legacy(), modern(), modern("r2"), modern("r3")]
        self.assertEqual([150, 150, 150], sorted(
            record["total"] for record in readers.codex_parse(self.write(events))))
        # A differing legacy anchor repeat after an accepted estimate keeps the
        # first sight (v16) instead of failing; the estimate is ignored either way.
        estimate = legacy(usage=dict(dict.fromkeys(USAGE, 0), total_tokens=75))
        records = readers.codex_parse(self.write(header() + [
            legacy(), modern(), estimate,
            legacy(usage=dict(USAGE, output_tokens=51, total_tokens=151))]))
        self.assertEqual([150], sorted(record["total"] for record in records))
        # Duplicate modern identity with differing usage is rejected outright.
        with self.assertRaises(readers.CollectionIncompleteError) as raised:
            readers.codex_parse(self.write(header() + [legacy(), modern(),
                                                       modern(usage=changed)]))
        self.assertEqual("modern_response_mismatch", raised.exception.conflict_kind)

    def test_legacy_adjacency_survives_modern_records_and_model_boundaries(self):
        # Modern records between a consumption and its zero update no longer
        # reset adjacency; the legacy ledger counts consumptions once.
        update = legacy(usage=dict(dict.fromkeys(USAGE, 0), total_tokens=75))
        events = header() + [legacy(), modern(), update, update,
                             legacy(300), modern("r2")]
        records = readers.codex_parse(self.write(events))
        self.assertEqual([150, 150], sorted(record["total"] for record in records))
        self.assertEqual(300, sum(record["total"] for record in records))
        # A model round-trip resets adjacency; under first-sight accounting the
        # same anchor then counts as a new ledger entry instead of failing.
        between = [modern("m1")]
        events = header() + [legacy(), modern(), update, between[0],
                             event("turn_context", {"model": "other"}),
                             event("turn_context", {"model": "synthetic-codex"}), update]
        records = readers.codex_parse(self.write(events))
        self.assertEqual([150, 150], sorted(record["total"] for record in records))
        # A null or missing info likewise breaks adjacency; the anchor was
        # already seen, so first sight wins and the update is ignored.
        null = event("event_msg", {"type": "token_count", "info": None})
        events = header() + [legacy(), null, update]
        records = readers.codex_parse(self.write(events))
        self.assertEqual([150], [record["total"] for record in records])

    def test_model_or_usage_differences_count_as_independent_consumptions(self):
        # Union accounting absorbs only exact value mirrors. A modern record
        # whose model or usage differs from every legacy entry has no mirror;
        # it joins the ledger as its own consumption and keeps its own model.
        records = readers.codex_parse(self.write(
            header() + [legacy(), event("turn_context", {"model": "other"}), modern()]))
        self.assertEqual([150, 150], sorted(record["total"] for record in records))
        self.assertEqual(["other", "synthetic-codex"], sorted(record["model"] for record in records))
        records = readers.codex_parse(self.write(
            header() + [modern(), event("turn_context", {"model": "other"}), legacy()]))
        self.assertEqual([150, 150], sorted(record["total"] for record in records))
        self.assertEqual(["other", "synthetic-codex"], sorted(record["model"] for record in records))
        partial = dict(USAGE, cached_input_tokens=0)
        del partial["cached_input_tokens"]
        full = dict(USAGE, cached_input_tokens=0)
        records = readers.codex_parse(self.write(header() + [modern(usage=partial), legacy(usage=full)]))
        self.assertEqual([150, 150], sorted(record["total"] for record in records))

    def test_unmatched_mixed_format_counts_legacy_without_dropping_calls(self):
        # Union accounting: legacy entries always count; a modern record whose
        # value matches a legacy entry is absorbed rather than duplicated.
        records = readers.codex_parse(
            self.write(header() + [legacy(), modern(), legacy(300)]))
        self.assertEqual([150, 150], sorted(record["total"] for record in records))

    def test_projection_discards_content_and_unselected_keys(self):
        parser = _claude_json.ProjectionParser(profile="codex")
        parser.feed(json.dumps(event("turn_context", {"model": "x", "instructions": "private-synthetic"})).encode())
        projected = parser.finish_line()
        self.assertEqual({"type": "turn_context", "timestamp": "2026-10-28T09:00:00Z", "payload": {"model": "x"}}, projected)

    def test_large_file_is_eligible_and_giant_nonusage_line_does_not_hide_usage(self):
        path = Path(self.write(header() + [modern()]))
        with path.open("ab") as f:
            f.write(b'{"type":"response_item","payload":{"content":"')
            for _ in range(66):
                f.write(b"x" * (1024 * 1024))
            f.write(b'"}}\n')
        self.assertTrue(readers._safe_to_parse(str(path), path.stat(), source="codex"))
        self.assertEqual(1, len(readers.codex_parse(str(path))))

    def test_unknown_cache_write_never_claims_trusted_billing(self):
        rec = readers.codex_parse(self.write(header() + [modern(usage=dict(USAGE, cache_write_input_tokens=2))]))[0]
        self.assertTrue(rec["billing"]["uncertain"])

    def test_symbolic_link_rejected(self):
        path = self.write(header() + [modern()])
        alias = self.root / "alias.jsonl"
        alias.symlink_to(path)
        with self.assertRaises(readers.CollectionIncompleteError):
            readers.codex_parse(str(alias))

    def test_archive_discovery_and_cross_file_response_dedup_cold_and_warm(self):
        sessions, archive = self.root / "sessions", self.root / "archive"
        sessions.mkdir(); archive.mkdir()
        events = header() + [modern()]
        p = Path(self.write(events)); p.rename(sessions / p.name)
        (archive / "rollout-copy.jsonl").write_text((sessions / p.name).read_text())
        with mock.patch.object(config, "CODEX_SESSIONS", str(sessions)), mock.patch.object(config, "CODEX_ARCHIVED_SESSIONS", str(archive), create=True), mock.patch.object(config, "CACHE_DIR", str(self.root / "cache")), mock.patch.object(config, "CACHE_FILE", str(self.root / "cache" / "records.json")), mock.patch.object(readers, "_ccr_signature", return_value=None):
            self.assertEqual(2, len(readers.codex_files()))
            cold = readers.read_all(["codex"])
            self.assertEqual(1, len(cold))
            self.assertEqual(cold, readers.read_all(["codex"]))

    def test_cross_file_response_conflict_preserves_cold_and_warm_cache_and_snapshot(self):
        for warm in (False, True):
            with self.subTest(warm=warm):
                root = self.root / ("warm" if warm else "cold")
                sessions, archive = root / "sessions", root / "archive"
                sessions.mkdir(parents=True); archive.mkdir()
                cache = root / "cache" / "records.json"
                cache.parent.mkdir()
                active = self.write(header() + [modern()],
                                    str(sessions / "rollout-active.jsonl"))
                with mock.patch.multiple(config,
                        CODEX_SESSIONS=str(sessions),
                        CODEX_ARCHIVED_SESSIONS=str(archive),
                        CACHE_DIR=str(cache.parent), CACHE_FILE=str(cache)):
                    if warm:
                        dashboard = live_dashboard.LiveDashboard(["codex"])
                        self.assertTrue(dashboard.refresh())
                        before = dashboard.response()
                        self.assertTrue(before["has_snapshot"])
                        self.assertIsNotNone(before["snapshot"])
                        self.assertIsNotNone(before["wire"])
                        self.assertIsNone(before["error"])
                    else:
                        # No parsed entries: cold collection must not replace bytes.
                        cache.write_bytes(b"{}\n")
                    good_cache = cache.read_bytes()
                    archived = self.write(header() + [modern(usage=dict(
                        USAGE, output_tokens=51, total_tokens=151))],
                        str(archive / "rollout-conflict.jsonl"))
                    active_records = readers.codex_parse(active)
                    archived_records = readers.codex_parse(archived)
                    self.assertEqual([150], [r["total"] for r in active_records])
                    self.assertEqual([151], [r["total"] for r in archived_records])
                    self.assertFalse(active_records[0]["billing"]["uncertain"])
                    self.assertFalse(archived_records[0]["billing"]["uncertain"])
                    self.assertEqual({active, archived}, set(readers.codex_files()))
                    observed = []
                    with self.assertRaises(readers.CollectionIncompleteError) as raised:
                        readers.read_all(["codex"], observer=lambda kind, source:
                                         observed.append((kind, source)))
                    self.assertEqual("codex", raised.exception.source)
                    self.assertEqual("usage_conflict", raised.exception.reason)
                    self.assertEqual("cross_file_identity_mismatch", raised.exception.conflict_kind)
                    self.assertEqual([
                        ("discovered", "codex"),
                        ("processed_cached" if warm else "processed_parsed", "codex"),
                        ("discovered", "codex"),
                    ], observed)
                    self.assertEqual(good_cache, cache.read_bytes())
                    if warm:
                        self.assertFalse(dashboard.refresh())
                        after = dashboard.response()
                        self.assertTrue(after["has_snapshot"])
                        self.assertEqual(before["snapshot"], after["snapshot"])
                        self.assertEqual(before["wire"], after["wire"])
                        self.assertTrue(after["error"])
                        self.assertEqual({"stage": "collection", "source": "codex",
                                          "reason": "usage_conflict",
                                          "conflict_kind": "cross_file_identity_mismatch"},
                                         after["error_details"])
                        self.assertEqual(good_cache, cache.read_bytes())

    @unittest.skipUnless(shutil.which("zstd"), "zstd unavailable")
    def test_zstd_archive_streams_and_corruption_is_not_empty_success(self):
        path = self.write(header() + [modern()])
        archive = self.root / "rollout-synthetic.jsonl.zst"
        with archive.open("wb") as f:
            subprocess.run([shutil.which("zstd"), "-q", "-c", "--", path], stdout=f, check=True)
        self.assertEqual(1, len(readers.codex_parse(str(archive))))
        archive.write_bytes(b"not-zstd")
        with self.assertRaises(readers.CollectionIncompleteError):
            readers.codex_parse(str(archive))


    def test_existing_nondirectory_root_is_not_empty_success(self):
        path = self.write([])
        with mock.patch.object(config, "CODEX_SESSIONS", path), \
                mock.patch.object(config, "CODEX_ARCHIVED_SESSIONS", str(self.root / "missing")):
            with self.assertRaises(readers.CollectionIncompleteError):
                readers.codex_files()

    def test_pipeline_keeps_totals_billing_and_private_identity_separate(self):
        records = readers.codex_parse(self.write(header() + [modern(), legacy(), modern("r2"), legacy(300)]))
        payload = dashboard_payload.build_payload(records, sources=["codex"], session_titles={})
        self.assertEqual(["codex"], payload["source"])
        self.assertIn("synthetic-codex", payload["models"])
        rows = payload["cost"]["rows"]
        self.assertEqual(300, sum(row[3] for row in rows))
        self.assertEqual(2, sum(row[4] for row in rows))
        self.assertEqual([140, 100, 60, 0, 0], [sum(row[2][i] for row in rows) for i in range(5)])
        self.assertFalse(any(row[5] for row in rows))
        encoded = json.dumps(payload)
        for private in ("synthetic-thread", "response_id", "root_turn_id", str(self.root)):
            self.assertNotIn(private, encoded)

    def test_cache_repair_append_and_archive_move_preserve_usage(self):
        sessions, archive = self.root / "sessions", self.root / "archive"
        sessions.mkdir(); archive.mkdir()
        path = sessions / "rollout-active.jsonl"
        path.write_text("\n".join(json.dumps(e) for e in header() + [modern()]) + "\n")
        cache = self.root / "cache" / "records.json"
        with mock.patch.object(config, "CODEX_SESSIONS", str(sessions)), \
                mock.patch.object(config, "CODEX_ARCHIVED_SESSIONS", str(archive)), \
                mock.patch.object(config, "CACHE_DIR", str(cache.parent)), \
                mock.patch.object(config, "CACHE_FILE", str(cache)):
            first = readers.read_all(["codex"])
            data = json.loads(cache.read_text())
            entry = next(v for k, v in data.items() if k.startswith("codex::"))
            entry["dedup"] = ["not-a-hash"]
            cache.write_text(json.dumps(data))
            self.assertEqual(first, readers.read_all(["codex"]))
            with path.open("a") as f:
                f.write(json.dumps(modern("r2")) + "\n")
            second = readers.read_all(["codex"])
            self.assertEqual(300, sum(r["total"] for r in second))
            path.rename(archive / "rollout-moved.jsonl")
            self.assertEqual(second, readers.read_all(["codex"]))
            self.assertEqual(second, readers.read_all(["codex"]))
            data = json.loads(cache.read_text())
            self.assertEqual(1, sum(k.startswith("codex::") for k in data))

    def test_doctor_reports_incomplete_discovery_without_reading_contents(self):
        error = readers.CollectionIncompleteError("codex", "discovery_failed")
        with mock.patch.dict(readers.SOURCES, {"codex": (mock.Mock(side_effect=error), readers.codex_parse)}):
            report = doctor.collect(["codex"])
        self.assertEqual("discovery_failed", report["sources"][0]["error"])
        self.assertEqual(0, report["sources"][0]["files"])

    def test_malformed_new_usage_is_not_silent_zero(self):
        for value in (None, [], {}, "invalid"):
            obj = modern(); obj["payload"]["usage"] = value
            with self.subTest(value=value), self.assertRaises(readers.CollectionIncompleteError):
                readers.codex_parse(self.write(header() + [obj]))

    def test_explicit_zero_update_preserves_original_usage_and_billing(self):
        for cache_write in (False, True):
            zero = {key: 0 for key in USAGE if cache_write or key != "cache_write_input_tokens"}
            for repeats in (1, 3):
                with self.subTest(cache_write=cache_write, repeats=repeats):
                    expected = readers.codex_parse(self.write(header() + [legacy()]))
                    events = header() + [legacy()] + [legacy(usage=zero)] * repeats
                    self.assertEqual(expected, readers.codex_parse(self.write(events)))

    def test_zero_update_allows_later_growth_and_exact_replays(self):
        zero = {key: 0 for key in USAGE}
        growth = legacy(300)
        growth["payload"]["info"]["total_token_usage"] = {key: value * 2 for key, value in USAGE.items()}
        baseline = readers.codex_parse(self.write(header() + [legacy(), growth]))
        events = header() + [legacy(), legacy(usage=zero), legacy(), growth]
        self.assertEqual(baseline, readers.codex_parse(self.write(events)))
        self.assertEqual([0], [r["total"] for r in
            readers.codex_parse(self.write(header() + [legacy(usage=zero)]))])

    def test_zero_update_requires_explicit_exact_integer_usage(self):
        # Field-level validation keeps only what it always rejected on legacy
        # display values: None on a required counter. False/0.0/-1 pass the
        # loose legacy value check and then follow v16 first-sight accounting,
        # where the differing anchor repeat is ignored instead of failing.
        zero = {key: 0 for key in USAGE}
        for key in USAGE:
            for value in (None, False, 0.0, -1):
                usage = dict(zero, **{key: value})
                # None fails on every counter except the two nullable display
                # fields (input re-derives total; cached just marks billing).
                fails = value is None and key != "cached_input_tokens"
                if fails:
                    with self.subTest(field=key, value=repr(value)), self.assertRaises(
                            readers.CollectionIncompleteError):
                        readers.codex_parse(self.write(header() + [legacy(), legacy(usage=usage)]))
                else:
                    with self.subTest(field=key, value=repr(value)):
                        records = readers.codex_parse(
                            self.write(header() + [legacy(), legacy(usage=usage)]))
                        self.assertEqual([150], [record["total"] for record in records])
            if key != "cache_write_input_tokens":
                usage = dict(zero)
                del usage[key]
                with self.subTest(missing=key):
                    records = readers.codex_parse(self.write(header() + [legacy(), legacy(usage=usage)]))
                    self.assertEqual([150], [record["total"] for record in records])

    def test_zero_update_does_not_bridge_usage_or_context_boundaries(self):
        zero = legacy(usage={key: 0 for key in USAGE})
        unanchored = legacy()
        del unanchored["payload"]["info"]["total_token_usage"]
        incomplete = event("event_msg", {"type": "token_count", "info": {}})
        other_session = event("session_meta", {"id": "other-thread"})
        original_session = event("session_meta", {"id": "synthetic-thread"})
        # Modern persist is unordered and never resets legacy adjacency, so a
        # modern record between a consumption and its zero update is legal;
        # the modern record itself joins the union ledger.
        records = readers.codex_parse(self.write(header() + [
            legacy(), modern(usage=dict(USAGE, output_tokens=51, total_tokens=151)), zero]))
        self.assertEqual([150, 151], sorted(record["total"] for record in records))
        # v16: broken adjacency makes the zero update a repeated anchor under
        # the same session/model (ignored, first sight wins) or a distinct
        # new-session anchor without prior evidence (kept as its own entry);
        # only these succeed instead of the old failure paths.
        records = readers.codex_parse(self.write(header() + [legacy(), zero]))
        self.assertEqual([150], [record["total"] for record in records])
        events = header() + [legacy(), other_session, original_session, zero]
        records = readers.codex_parse(self.write(events))
        self.assertEqual([150], [record["total"] for record in records])

    def test_zero_update_does_not_hide_later_modern_conflicts(self):
        zero = legacy(usage={key: 0 for key in USAGE})
        changed = legacy(usage=dict(USAGE, output_tokens=51, total_tokens=151))
        # v16 first-sight wins: a later differing legacy anchor repeat is
        # ignored, so the earlier record's evidence is what counts.
        records = readers.codex_parse(self.write(header() + [legacy(), zero, changed]))
        self.assertEqual([150], [record["total"] for record in records])
        with self.assertRaises(readers.CollectionIncompleteError) as raised:
            readers.codex_parse(self.write(header() + [modern(), modern(usage={key: 0 for key in USAGE})]))
        self.assertEqual("modern_response_mismatch", raised.exception.conflict_kind)

    def test_zero_update_requires_complete_previous_cumulative_evidence(self):
        # v16: missing cumulative fields leave the event unanchored, so the
        # pair degenerates to first-sight accounting and no longer fails.
        positive = dict(USAGE, cached_input_tokens=0, reasoning_output_tokens=0)
        for field in ("cached_input_tokens", "reasoning_output_tokens"):
            for missing_on in ("first", "second"):
                first, second = legacy(usage=positive), legacy(usage={key: 0 for key in USAGE})
                for item in (first, second):
                    item["payload"]["info"]["total_token_usage"] = dict(positive)
                item = first if missing_on == "first" else second
                del item["payload"]["info"]["total_token_usage"][field]
                with self.subTest(field=field, missing_on=missing_on):
                    records = readers.codex_parse(self.write(header() + [first, second]))
                    self.assertEqual([150], [record["total"] for record in records])
        uncertain = legacy()
        del uncertain["payload"]["info"]["last_token_usage"]["cached_input_tokens"]
        records = readers.codex_parse(self.write(
            header() + [uncertain, legacy(usage={key: 0 for key in USAGE})]))
        self.assertEqual([150], [record["total"] for record in records])
        self.assertTrue(records[0]["billing"]["uncertain"])

    def test_context_estimate_preserves_original_usage_and_billing(self):
        expected = readers.codex_parse(self.write(header() + [legacy()]))
        for cache_write in (False, True):
            estimate = {key: 0 for key in USAGE if cache_write or key != "cache_write_input_tokens"}
            estimate["total_tokens"] = 75
            for totals in ((1,), (149,), (75,), (75, 75, 75), (75, 40, 60)):
                with self.subTest(cache_write=cache_write, totals=totals):
                    updates = [legacy(usage=dict(estimate, total_tokens=total)) for total in totals]
                    self.assertEqual(expected, readers.codex_parse(self.write(header() + [legacy()] + updates)))

    def test_context_estimate_allows_replay_zero_and_later_growth(self):
        zero = dict.fromkeys(USAGE, 0)
        estimate = legacy(usage=dict(zero, total_tokens=75))
        growth = legacy(300)
        growth["payload"]["info"]["total_token_usage"] = {key: value * 2 for key, value in USAGE.items()}
        expected = readers.codex_parse(self.write(header() + [legacy(), growth]))
        events = header() + [legacy(), estimate, legacy(), estimate, legacy(usage=zero), growth]
        self.assertEqual(expected, readers.codex_parse(self.write(events)))

    def test_context_estimate_is_not_a_global_total_only_filter(self):
        estimate = legacy(usage=dict(dict.fromkeys(USAGE, 0), total_tokens=75))
        for events in ([estimate], [legacy(), legacy(300, estimate["payload"]["info"]["last_token_usage"])]):
            with self.subTest(count=len(events)):
                records = readers.codex_parse(self.write(header() + events))
                self.assertEqual(len(events), len(records))
                self.assertEqual(75, records[-1]["total"])
                self.assertTrue(records[-1]["billing"]["uncertain"])
                self.assertEqual(["total_mismatch"], records[-1]["billing"]["reasons"])

    def test_context_estimate_requires_complete_integer_zero_components_and_bounds(self):
        # v16 first-sight wins: an estimate shape that used to fail the anchor
        # comparison is now ignored as a differing anchor repeat; only the
        # field-level value checks (None on required counters) still fail.
        estimate = dict(dict.fromkeys(USAGE, 0), total_tokens=75)
        cases = [dict(estimate, total_tokens=value) for value in (150, 151, 301)]
        for key in USAGE:
            cases.extend(dict(estimate, **{key: value}) for value in (None, False, 0.0, -1))
            if key != "total_tokens":
                cases.append(dict(estimate, **{key: 1}))
            if key != "cache_write_input_tokens":
                missing = dict(estimate)
                del missing[key]
                cases.append(missing)
        for usage in cases:
            # None fails on the counters that must be present (output/
            # reasoning/cache_write/total re-derivation paths); input=None and
            # cached=None survive value checks. Everything else is v16
            # first-sight accounting: a variant cumulative signature is a
            # fresh anchor kept next to the first record.
            required_none = any(key in usage and usage[key] is None for key in USAGE
                                if key not in ("input_tokens", "cached_input_tokens"))
            with self.subTest(usage=usage):
                if required_none:
                    with self.assertRaises(readers.CollectionIncompleteError):
                        readers.codex_parse(self.write(header() + [legacy(), legacy(usage=usage)]))
                else:
                    records = readers.codex_parse(self.write(header() + [legacy(), legacy(usage=usage)]))
                    self.assertEqual(150, max(record["total"] for record in records))
        # Isolate the cumulative bound from the original-last bound: the
        # out-of-bound estimate repeats the same cumulative anchor, so
        # first-sight accounting ignores it and the first record counts.
        previous = legacy(usage={key: value * 2 for key, value in USAGE.items()})
        records = readers.codex_parse(
            self.write(header() + [previous, legacy(usage=dict(estimate, total_tokens=200))]))
        self.assertEqual([300], [record["total"] for record in records])

    def test_context_estimate_requires_trusted_original_and_only_total_mismatch(self):
        # v16: an untrusted original or extra billing uncertainty makes the
        # estimate a differing anchor repeat that is ignored (first sight
        # wins); the original record's evidence is what counts.
        estimate = legacy(usage=dict(dict.fromkeys(USAGE, 0), total_tokens=75))
        original = legacy()
        del original["payload"]["info"]["last_token_usage"]["cached_input_tokens"]
        records = readers.codex_parse(self.write(header() + [original, estimate]))
        self.assertEqual([150], [record["total"] for record in records])
        self.assertTrue(records[0]["billing"]["uncertain"])
        billing = readers._codex_billing
        def extra_reason(usage):
            result = billing(usage)
            if result["uncertain"]:
                result["reasons"].append("synthetic_unconfirmed")
            return result
        with mock.patch.object(readers, "_codex_billing", side_effect=extra_reason):
            records = readers.codex_parse(self.write(header() + [legacy(), estimate]))
            self.assertEqual([150], [record["total"] for record in records])

    def test_context_estimate_requires_complete_adjacent_cumulative_evidence(self):
        estimate = legacy(usage=dict(dict.fromkeys(USAGE, 0), total_tokens=75))
        unanchored = legacy()
        del unanchored["payload"]["info"]["total_token_usage"]
        incomplete = event("event_msg", {"type": "token_count", "info": {}})
        # Modern persist never resets legacy adjacency, so an intervening
        # modern record keeps the estimate legal: the same-anchor estimate
        # is still absorbed instead of failing the anchor check, and the
        # modern record counts independently.
        records = readers.codex_parse(self.write(header() + [
            legacy(), modern(usage=dict(USAGE, output_tokens=51, total_tokens=151)), estimate]))
        self.assertEqual([150, 151], sorted(record["total"] for record in records))
        boundaries = (
            ([unanchored], "fresh"), ([incomplete], "anchorless"),
            ([event("turn_context", {"model": "other"})], "model"),
            ([event("turn_context", {"model": "other"}), header()[1]], "roundtrip"),
            ([event("session_meta", {"id": "other-thread"}), header()[0]], "roundtrip"),
        )
        for between, kind in boundaries:
            if kind == "model":
                # v17 first sight wins across model boundaries too: the
                # estimate repeats an already-seen anchor and is ignored.
                with self.subTest(between=between):
                    records = readers.codex_parse(
                        self.write(header() + [legacy()] + between + [estimate]))
                    self.assertEqual([150], [record["total"] for record in records])
            elif kind == "fresh":
                # The unanchored record counts on its own (no cumulative
                # anchor); the estimate then repeats the first record's
                # anchor value, so first sight ignores it.
                with self.subTest(between=between):
                    records = readers.codex_parse(
                        self.write(header() + [legacy()] + between + [estimate]))
                    self.assertEqual([150, 150], sorted(record["total"] for record in records))
            elif kind == "anchorless":
                # An empty info carries nothing at all; the estimate is a
                # first-sight anchor repeat under the same session and model,
                # so it is ignored and only the original record counts.
                with self.subTest(between=between):
                    records = readers.codex_parse(
                        self.write(header() + [legacy()] + between + [estimate]))
                    self.assertEqual([150], [record["total"] for record in records])
            else:
                # The estimate lands on an already-seen anchor under the same
                # session and model: first sight wins and it is ignored.
                with self.subTest(between=between):
                    records = readers.codex_parse(
                        self.write(header() + [legacy()] + between + [estimate]))
                    self.assertEqual([150], [record["total"] for record in records])
        for field in ("cached_input_tokens", "reasoning_output_tokens"):
            for missing_on in (0, 1):
                positive = dict(USAGE, cached_input_tokens=0, reasoning_output_tokens=0)
                pair = [legacy(usage=positive), legacy(usage=estimate["payload"]["info"]["last_token_usage"])]
                for item in pair:
                    item["payload"]["info"]["total_token_usage"] = dict(positive)
                del pair[missing_on]["payload"]["info"]["total_token_usage"][field]
                with self.subTest(field=field, missing_on=missing_on):
                    records = readers.codex_parse(self.write(header() + pair))
                    self.assertEqual([150], [record["total"] for record in records])

    def test_context_estimate_does_not_hide_later_modern_conflicts(self):
        usage = dict(dict.fromkeys(USAGE, 0), total_tokens=75)
        changed = legacy(usage=dict(USAGE, output_tokens=51, total_tokens=151))
        # v16 first-sight wins: a later differing legacy anchor repeat after an
        # accepted estimate is ignored; the first record's evidence counts.
        records = readers.codex_parse(self.write(header() + [legacy(), legacy(usage=usage), changed]))
        self.assertEqual([150], [record["total"] for record in records])
        with self.assertRaises(readers.CollectionIncompleteError) as raised:
            readers.codex_parse(self.write(header() + [modern(), modern(usage=usage)]))
        self.assertEqual("modern_response_mismatch", raised.exception.conflict_kind)

    def test_repeated_anchor_with_differing_evidence_keeps_first_sight(self):
        # First sight wins: a repeated cumulative anchor with differing
        # usage/billing evidence is ignored rather than failing (real
        # producers rewrite the same snapshot after a resume). The anchor
        # still counts exactly once and keeps the first record's evidence.
        first = legacy()
        replayed = legacy(usage=dict(USAGE, output_tokens=51, total_tokens=151))
        records = readers.codex_parse(self.write(header() + [first, replayed]))
        self.assertEqual([150], [record["total"] for record in records])
        first = legacy(); first["payload"]["info"]["last_token_usage"].pop("cached_input_tokens")
        second = legacy(usage=dict(USAGE, cached_input_tokens=0))
        records = readers.codex_parse(self.write(header() + [first, second]))
        self.assertEqual([150], [record["total"] for record in records])
        # The first record keeps its own (uncertain) billing evidence.
        self.assertTrue(records[0]["billing"]["uncertain"])

    def test_same_legacy_anchor_keeps_first_sight_across_model_boundary(self):
        # v17: first sight wins unconditionally — a repeated anchor under a
        # different model is ignored instead of failing; real producers
        # resume with a different model while re-writing the same snapshot.
        # The first record's model stays on the ledger entry.
        events = [legacy(), event("turn_context", {"model": "other"}), legacy()]
        records = readers.codex_parse(self.write(header() + events))
        self.assertEqual([150], [record["total"] for record in records])
        self.assertEqual("synthetic-codex", records[0]["model"])

    def test_legacy_anchor_repeats_always_keep_first_sight(self):
        # v17: every combination of usage/model/billing divergence at a
        # repeated anchor is ignored; the first record's evidence counts.
        for bits in range(1, 8):
            groups = [name for bit, name in ((1, "usage"), (2, "model"), (4, "billing"))
                      if bits & bit]
            second = legacy(usage=dict(USAGE, output_tokens=51, total_tokens=151)) if bits & 1 else legacy()
            events = [legacy()]
            if bits & 2:
                events.append(event("turn_context", {"model": "other"}))
            events.append(second)
            # Isolate the three comparisons; real billing-presence coverage is above.
            billing = [{"synthetic": 0}, {"synthetic": int(bool(bits & 4))}]
            with self.subTest(groups=groups), mock.patch.object(
                    readers, "_codex_billing", side_effect=billing):
                records = readers.codex_parse(self.write(header() + events))
                self.assertEqual([150], [record["total"] for record in records])
        self.assertEqual(1, len(readers.codex_parse(self.write(header() + [legacy(), legacy()]))))

    def test_mismatch_kind_accepts_only_exact_legacy_anchor_codes(self):
        kinds = {"usage", "model", "billing", "usage_model", "usage_billing",
                 "model_billing", "usage_model_billing"}
        self.assertEqual(kinds, readers.CollectionIncompleteError.MISMATCH_KINDS)
        for kind in kinds:
            error = readers.CollectionIncompleteError("codex", "usage_conflict",
                conflict_kind="legacy_anchor_mismatch", mismatch_kind=kind)
            self.assertEqual(kind, error.mismatch_kind)
            self.assertEqual("Collection incomplete (codex: usage_conflict)", str(error))
        class StringSubclass(str):
            pass
        for value in (None, "private-mismatch-sentinel", "", [], {}, ["model"],
                      {"kind": "model"}, True, 1, StringSubclass("model")):
            with self.subTest(value_type=type(value).__name__):
                error = readers.CollectionIncompleteError("codex", "usage_conflict",
                    conflict_kind="legacy_anchor_mismatch", mismatch_kind=value)
                self.assertIsNone(error.mismatch_kind)
        for source, reason, conflict in (("claude", "usage_conflict", "legacy_anchor_mismatch"),
                ("codex", "usage_invalid", "legacy_anchor_mismatch"),
                ("codex", "usage_conflict", "modern_response_mismatch"),
                ("codex", "usage_conflict", None)):
            error = readers.CollectionIncompleteError(source, reason,
                conflict_kind=conflict, mismatch_kind="model")
            self.assertIsNone(error.mismatch_kind)
        self.assertIsNone(readers.CollectionIncompleteError("codex", "usage_conflict").mismatch_kind)

    def test_same_modern_response_rejects_valid_output_and_total_increment(self):
        first = modern()
        second = modern(usage=dict(USAGE, output_tokens=51, total_tokens=151))
        for item in (first, second):
            self.assertEqual(1, len(readers.codex_parse(self.write(header() + [item]))))
        with self.assertRaises(readers.CollectionIncompleteError) as raised:
            readers.codex_parse(self.write(header() + [first, second]))
        self.assertEqual("codex", raised.exception.source)
        self.assertEqual("usage_conflict", raised.exception.reason)
        self.assertEqual("modern_response_mismatch", raised.exception.conflict_kind)

    def test_legacy_cumulative_decrease_starts_a_new_ledger_baseline(self):
        # Real producers recompute cumulative counters downward mid-session;
        # a lower cumulative value is a new baseline, not a conflict. Each
        # distinct cumulative anchor still counts its own consumption once.
        first, second = legacy(300), legacy(150)
        first["payload"]["info"]["total_token_usage"] = {
            key: value * 2 for key, value in USAGE.items()}
        for item in (first, second):
            self.assertEqual([150], [r["total"] for r in
                readers.codex_parse(self.write(header() + [item]))])
        records = readers.codex_parse(self.write(header() + [first, second]))
        self.assertEqual([150, 150], sorted(record["total"] for record in records))
        # A repeated anchor inside the lower baseline keeps the first sight
        # (first-sight wins under v16): the changed record is the first sight
        # on the lower anchor, and the later duplicate is ignored.
        changed = legacy(150, usage=dict(USAGE, output_tokens=51, total_tokens=151))
        records = readers.codex_parse(self.write(header() + [first, changed, second]))
        self.assertEqual([150, 151], sorted(record["total"] for record in records))

    def test_collection_error_preserves_legacy_args_and_text(self):
        error = readers.CollectionIncompleteError("codex", "usage_conflict")
        text = "Collection incomplete (codex: usage_conflict)"
        self.assertEqual((text,), error.args)
        self.assertEqual(text, str(error))
        self.assertIsNone(error.conflict_kind)
        with self.assertRaises(TypeError):
            readers.CollectionIncompleteError("codex", "usage_conflict", "modern_response_mismatch")

    def test_collection_error_keeps_only_four_exact_conflict_codes(self):
        kinds = {"modern_response_mismatch", "legacy_cumulative_rollback",
                 "legacy_anchor_mismatch", "cross_file_identity_mismatch"}
        self.assertEqual(kinds, readers.CollectionIncompleteError.CONFLICT_KINDS)
        for kind in kinds:
            with self.subTest(kind=kind):
                error = readers.CollectionIncompleteError("codex", "usage_conflict",
                                                          conflict_kind=kind)
                self.assertEqual(kind, error.conflict_kind)
                self.assertEqual(("Collection incomplete (codex: usage_conflict)",), error.args)
                self.assertEqual(error.args[0], str(error))

    def test_collection_error_ignores_invalid_diagnostics_without_replacing_failure(self):
        class StringLike:
            def __str__(self):
                return "modern_response_mismatch"

        class StringSubclass(str):
            pass

        for value in (None, "unknown-private-sentinel", "", [], {},
                      ["modern_response_mismatch"], {"kind": "modern_response_mismatch"},
                      True, 1, StringLike(), StringSubclass("modern_response_mismatch")):
            with self.subTest(value_type=type(value).__name__):
                error = readers.CollectionIncompleteError("codex", "usage_conflict",
                                                          conflict_kind=value)
                self.assertIsNone(error.conflict_kind)
                self.assertEqual("usage_conflict", error.reason)
        for source, reason in (("claude", "usage_conflict"), ("gemini", "usage_conflict"),
                               ("all", "usage_conflict"), ("codex", "usage_invalid")):
            with self.subTest(source=source, reason=reason):
                error = readers.CollectionIncompleteError(source, reason,
                    conflict_kind="modern_response_mismatch")
                self.assertIsNone(error.conflict_kind)

    def test_collection_error_still_rejects_invalid_source_and_reason(self):
        for source, reason in (("private-source", "usage_conflict"), ("codex", "private-reason"),
                               (None, "usage_conflict"), ("codex", None),
                               ([], "usage_conflict"), ("codex", {})):
            with self.subTest(source_type=type(source).__name__, reason_type=type(reason).__name__):
                with self.assertRaisesRegex(ValueError, "^invalid collection error code$"):
                    readers.CollectionIncompleteError(source, reason,
                        conflict_kind="modern_response_mismatch")

    def test_missing_identity_invalid_new_tokens_and_conflicts_fail(self):
        cases = []
        missing = modern(); missing["payload"].pop("response_id")
        cases.append([missing])
        for value in (True, -1, 2.5, None, 9007199254740992):
            cases.append([modern(usage=dict(USAGE, input_tokens=value))])
        cases.append([modern(), modern(usage={"total_tokens": 150})])
        for events in cases:
            with self.subTest(case=cases.index(events)):
                with self.assertRaises(readers.CollectionIncompleteError):
                    readers.codex_parse(self.write(header() + events))

    def test_same_response_cannot_hide_changed_billing_evidence(self):
        first = modern(); first["payload"]["usage"].pop("cached_input_tokens")
        second = modern(usage=dict(USAGE, cached_input_tokens=0))
        with self.assertRaises(readers.CollectionIncompleteError):
            readers.codex_parse(self.write(header() + [first, second]))

    def test_budget_failures_are_controlled(self):
        path = self.write(header() + [modern(), modern("r2")])
        for name, value in (("MAX_RECORDS", 1), ("MAX_RETAINED_BYTES", 1)):
            with self.subTest(budget=name), mock.patch.object(codex_usage, name, value):
                with self.assertRaises(readers.CollectionIncompleteError):
                    readers.codex_parse(path)
        path = self.write(header() + [event("other", {"x": [0] * 100})])
        real = _claude_json.ProjectionParser
        with mock.patch.object(_claude_json, "ProjectionParser",
                               side_effect=lambda **kw: real(max_tokens=30, **kw)):
            with self.assertRaises(readers.CollectionIncompleteError):
                readers.codex_parse(path)

    def test_bad_lines_utf8_and_incomplete_tail_do_not_hide_complete_usage(self):
        path = Path(self.write(header() + [modern()]))
        with path.open("ab") as f:
            f.write(b'not-json\n{"bad":"\xff"}\n{"type":')
        records = readers.codex_parse(str(path))
        self.assertEqual([150], [r["total"] for r in records])

    def test_append_reads_only_initial_length_and_does_not_mark_stable(self):
        path = self.write(header() + [modern()])
        original = readers._SafeReader.read_chunk
        appended = False
        def read(reader):
            nonlocal appended
            if not appended:
                with open(path, "ab") as f:
                    f.write((json.dumps(modern("r2")) + "\n").encode())
                appended = True
            return original(reader)
        with mock.patch.object(readers._SafeReader, "read_chunk", read):
            records, _, _, stable = codex_usage.parse_state(path)
        self.assertEqual(1, len(records))
        self.assertFalse(stable)
        self.assertEqual(2, len(readers.codex_parse(path)))

    def test_truncate_or_replace_during_read_is_not_partial_success(self):
        original = readers._SafeReader.read_chunk
        for replace in (False, True):
            path = self.write(header() + [modern()])
            def read(reader):
                data = original(reader)
                if replace:
                    other = self.root / "replacement"
                    other.write_bytes(Path(path).read_bytes())
                    other.replace(path)
                else:
                    Path(path).write_bytes(b"")
                return data
            with self.subTest(replace=replace), mock.patch.object(readers._SafeReader, "read_chunk", read):
                with self.assertRaises(readers.CollectionIncompleteError):
                    readers.codex_parse(path)

    def test_live_failure_keeps_previous_snapshot_and_good_cache(self):
        path = self.write(header() + [modern()])
        cache = self.root / "cache" / "records.json"
        with mock.patch.dict(readers.SOURCES, {"codex": (lambda: [path], readers.codex_parse)}), \
                mock.patch.object(config, "CACHE_DIR", str(cache.parent)), \
                mock.patch.object(config, "CACHE_FILE", str(cache)):
            dashboard = live_dashboard.LiveDashboard(["codex"])
            self.assertTrue(dashboard.refresh())
            before, good_cache = dashboard.response(), cache.read_bytes()
            Path(path).write_text(json.dumps(modern(usage=dict(USAGE, input_tokens=-1))) + "\n")
            self.assertFalse(dashboard.refresh())
            after = dashboard.response()
            self.assertEqual(before["snapshot"], after["snapshot"])
            self.assertEqual(before["wire"], after["wire"])
            self.assertTrue(after["error"])
            self.assertEqual(good_cache, cache.read_bytes())

    def test_archive_missing_tool_reports_safe_error_without_starting_process(self):
        archive = self.root / "rollout-missing-tool.jsonl.zst"
        archive.write_bytes(b"synthetic archive bytes")
        with mock.patch.object(codex_usage.shutil, "which", return_value=None), \
                mock.patch.object(codex_usage.subprocess, "Popen") as popen:
            with self.assertRaises(readers.CollectionIncompleteError) as raised:
                readers.codex_parse(str(archive))
        self.assertEqual("codex", raised.exception.source)
        self.assertEqual("decompressor_unavailable", raised.exception.reason)
        popen.assert_not_called()

    @unittest.skipUnless(shutil.which("zstd"), "zstd unavailable")
    def test_archive_limits_and_initial_length(self):
        path = self.write(header() + [modern()])
        archive = self.root / "rollout-boundary.jsonl.zst"
        with archive.open("wb") as f:
            subprocess.run([shutil.which("zstd"), "-q", "-c", "--", path], stdout=f, check=True)
        original_bytes = archive.read_bytes()
        with mock.patch.object(codex_usage, "MAX_DECOMPRESSED_BYTES", 1):
            with self.assertRaises(readers.CollectionIncompleteError):
                readers.codex_parse(str(archive))
        with mock.patch.object(codex_usage, "ARCHIVE_TIMEOUT", 0):
            with self.assertRaises(readers.CollectionIncompleteError):
                readers.codex_parse(str(archive))
        popen = subprocess.Popen
        def append_after_open(*args, **kw):
            self.assertIs(kw["stdin"], subprocess.PIPE,
                          "feed verified initial bytes, not an unbounded live descriptor")
            with archive.open("ab") as f:
                f.write(original_bytes)
            return popen(*args, **kw)
        with mock.patch.object(codex_usage.subprocess, "Popen", append_after_open):
            records, _, _, stable = codex_usage.parse_state(str(archive))
        self.assertEqual(1, len(records))
        self.assertFalse(stable)


if __name__ == "__main__":
    unittest.main()
