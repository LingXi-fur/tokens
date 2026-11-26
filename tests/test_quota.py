"""Synthetic contracts for `tokens quota`.

All files and databases are temporary. Scanners receive synthetic JSONL with a
sentinel body string; tests assert the sentinel, cwd, and session never reach
text or JSON output.
"""
from tests import _hermetic  # noqa: F401
import io
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from tokens_cli import cli, config, quota  # noqa: E402

TZ = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 11, 10, 18, 0, tzinfo=TZ)
SECRET = "SECRET BODY SENTINEL"


def snapshot(observed, used, minutes=300, resets=None, plan="plus",
             limit_id="codex", limit_name=None):
    return {
        "observed_at": observed.timestamp(),
        "plan_type": plan,
        "limit_id": limit_id,
        "limit_name": limit_name,
        "window_minutes": minutes,
        "used_percent": used,
        "resets_at": None if resets is None else resets.timestamp(),
    }


def window_of(plans, minutes, limit_name=None, plan_type="plus"):
    for plan in plans:
        if plan["plan_type"] != plan_type:
            continue
        for limit in plan["limits"]:
            if limit["limit_name"] != limit_name:
                continue
            for window in limit["windows"]:
                if window["window_minutes"] == minutes:
                    return window
    raise AssertionError(f"missing window {minutes}/{limit_name}")


def claude_record(at, model="claude-opus-5.5", request="claude-opus-5-5", total=100):
    return {
        "source": "claude",
        "ts": at.isoformat(),
        "model": model,
        "request_model": request,
        "total": total,
    }


def write_lines(path, objects):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        for obj in objects:
            handle.write(obj if isinstance(obj, str) else json.dumps(obj))
            handle.write("\n")


class CodexQuotaTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(quota.config, "TZ", TZ)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_windows_follow_minutes_not_primary_secondary_labels(self):
        now = NOW
        snapshots = [
            snapshot(now - timedelta(minutes=10), 20, minutes=300),
            snapshot(now, 42, minutes=300),
            snapshot(now, 61, minutes=10080, resets=now + timedelta(days=4)),
            # A primary window that is actually weekly must still be weekly.
            snapshot(now - timedelta(minutes=5), 9, minutes=10080,
                     resets=now + timedelta(days=4)),
            snapshot(now, 3, minutes=10080, resets=now + timedelta(days=4),
                     limit_name="gpt-reserve"),
        ]
        plans = quota.summarize_codex(snapshots, now)
        self.assertEqual(42, window_of(plans, 300)["used_percent"])
        self.assertEqual(61, window_of(plans, 10080)["used_percent"])
        self.assertEqual(3, window_of(plans, 10080, limit_name="gpt-reserve")["used_percent"])
        self.assertEqual({"gpt-reserve", None},
                         {limit["limit_name"] for plan in plans for limit in plan["limits"]})

    def test_plan_type_null_and_plus_share_one_limit_group(self):
        now = NOW
        plans = quota.summarize_codex([
            snapshot(now - timedelta(days=5), 15, minutes=10080,
                     resets=now + timedelta(days=1), plan=None),
            snapshot(now, 94, minutes=10080,
                     resets=now + timedelta(days=1), plan="plus"),
        ], now)
        self.assertEqual(1, len(plans))
        self.assertEqual("plus", plans[0]["plan_type"])
        self.assertEqual(1, len(plans[0]["limits"]))
        self.assertEqual(94, window_of(plans, 10080)["used_percent"])
        self.assertTrue(window_of(plans, 10080)["observed_at"].startswith("2026-11-10T18:00"))

    def test_epoch_and_iso_resets_are_both_supported(self):
        now = NOW
        epoch_window = quota.summarize_codex(
            [snapshot(now, 10, resets=now + timedelta(hours=2))], now)[0]["limits"][0]["windows"][0]
        iso_snapshot = snapshot(now, 10)
        iso_snapshot["resets_at"] = (now + timedelta(hours=3)).isoformat()
        iso_window = quota.summarize_codex([iso_snapshot], now)[0]["limits"][0]["windows"][0]
        self.assertIsNotNone(epoch_window["resets_at"])
        self.assertIsNotNone(iso_window["resets_at"])
        self.assertTrue(epoch_window["resets_at"].startswith("2026-11-10T20:00"))
        self.assertTrue(iso_window["resets_at"].startswith("2026-11-10T21:00"))

    def test_expired_window_drops_the_stale_percentage(self):
        now = NOW
        plans = quota.summarize_codex(
            [snapshot(now - timedelta(minutes=10), 99, resets=now - timedelta(minutes=1))],
            now)
        window = window_of(plans, 300)
        self.assertEqual("expired", window["status"])
        self.assertIsNone(window["used_percent"])
        self.assertEqual("expired", window["projection"]["status"])

    def test_velocity_needs_two_snapshots_and_five_minutes(self):
        now = NOW
        one = quota.summarize_codex([snapshot(now, 40)], now)
        self.assertIsNone(window_of(one, 300)["velocity_per_hour"])
        self.assertEqual("insufficient", window_of(one, 300)["projection"]["status"])

        too_short = quota.summarize_codex([
            snapshot(now - timedelta(minutes=2), 40),
            snapshot(now, 41),
        ], now)
        self.assertIsNone(window_of(too_short, 300)["velocity_per_hour"])

    def test_projection_before_and_after_reset(self):
        now = NOW
        rows = [snapshot(now - timedelta(minutes=10), 40),
                snapshot(now, 50)]
        hit = quota.summarize_codex(
            [dict(row, resets_at=(now + timedelta(hours=5)).timestamp()) for row in rows], now)
        self.assertEqual("hit", window_of(hit, 300)["projection"]["status"])
        safe = quota.summarize_codex(
            [dict(row, resets_at=(now + timedelta(minutes=30)).timestamp()) for row in rows], now)
        self.assertEqual("safe", window_of(safe, 300)["projection"]["status"])
        self.assertGreater(
            quota._epoch(window_of(safe, 300)["projection"]["projected_at"]),
            now.timestamp() + 30 * 60,
        )

    def test_non_dict_rate_limits_and_missing_timestamp_are_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "rollout-a.jsonl")
            write_lines(path, [
                {"timestamp": NOW.isoformat(), "payload": {"rate_limits": "not-a-dict"}},
                {"payload": {"rate_limits": {"primary": {"window_minutes": 300,
                                                          "used_percent": 5}}}},
                {"timestamp": NOW.isoformat(), "payload": {"rate_limits": {
                    "plan_type": "plus", "limit_id": "codex",
                    "primary": {"window_minutes": 300, "used_percent": 42,
                                "resets_at": (NOW + timedelta(hours=1)).timestamp()},
                }}},
            ])
            snapshots = quota._scan_codex_file(path)
        self.assertEqual(1, len(snapshots))
        self.assertEqual(42, snapshots[0]["used_percent"])
        self.assertEqual(300, snapshots[0]["window_minutes"])


class ClaudeQuotaTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(quota.config, "TZ", TZ)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_scanner_reads_quota_fields_and_passes_types_through(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "session.jsonl")
            write_lines(path, [
                {"timestamp": NOW.isoformat(), "error": "rate_limit",
                 "isApiErrorMessage": True, "apiErrorStatus": 429,
                 "quotaLimits": {"rateLimitType": "seven_day", "status": "rejected",
                                 "resetsAt": int((NOW + timedelta(days=2)).timestamp())},
                 "message": {"content": SECRET}},
                {"timestamp": (NOW - timedelta(hours=1)).isoformat(), "error": "rate_limit",
                 "isApiErrorMessage": True, "apiErrorStatus": 429,
                 "apiErrorParams": {"rate_limit_info": {
                     "rateLimitType": "five_hour", "resetsAt":
                         int((NOW + timedelta(hours=1)).timestamp())}}},
                {"timestamp": (NOW - timedelta(hours=2)).isoformat(), "error": "rate_limit",
                 "isApiErrorMessage": True, "apiErrorStatus": 429},
                {"timestamp": NOW.isoformat(), "error": "other", "message": SECRET},
            ])
            events = quota._scan_claude_file(path)
        self.assertEqual(3, len(events))
        self.assertEqual("seven_day", events[0]["type"])
        self.assertIsNotNone(events[0]["resets_at"])
        self.assertEqual("five_hour", events[1]["type"])
        self.assertIsNotNone(events[1]["resets_at"])
        self.assertIsNone(events[2]["resets_at"])
        self.assertNotIn(SECRET, json.dumps(events))

    def test_direct_records_exclude_ccr_backends(self):
        rows = [
            claude_record(NOW - timedelta(hours=1), total=100),
            claude_record(NOW - timedelta(hours=1), model="glm-5.3",
                          request="claude-opus-5-5", total=9999),
            claude_record(NOW - timedelta(hours=1), model="claude-opus-5.5",
                          request="anthropic/claude-ccr-h00", total=8888),
        ]
        direct = quota.direct_claude_records(rows)
        self.assertEqual([100], [row["total"] for row in direct])

    def test_capacity_median_min_max_and_sample_count(self):
        direct = [
            {"at": (NOW - timedelta(hours=6)).timestamp(), "total": 100},
            {"at": (NOW - timedelta(hours=4)).timestamp(), "total": 200},
            {"at": (NOW - timedelta(hours=2)).timestamp(), "total": 400},
        ]
        events = [
            {"at": (NOW - timedelta(hours=3)).timestamp(), "type": "five_hour",
             "resets_at": (NOW - timedelta(hours=2)).timestamp()},
            {"at": (NOW - timedelta(hours=1)).timestamp(), "type": "five_hour",
             "resets_at": NOW.timestamp()},
        ]
        summary = quota.summarize_claude(events, direct, NOW)
        self.assertEqual(2, summary["samples"]["count"])
        self.assertEqual(450, summary["samples"]["median"])
        self.assertEqual(300, summary["samples"]["min"])
        self.assertEqual(600, summary["samples"]["max"])

    def test_duplicate_events_collapse_and_windows_count_once(self):
        reset = NOW - timedelta(hours=1)
        direct = [
            {"at": (NOW - timedelta(hours=4)).timestamp(), "total": 100},
            {"at": (NOW - timedelta(hours=2)).timestamp(), "total": 200},
        ]
        duplicate = {"at": (NOW - timedelta(hours=1)).timestamp(), "type": "five_hour",
                     "resets_at": reset.timestamp()}
        summary = quota.summarize_claude([
            duplicate,
            dict(duplicate),
            {"at": (NOW - timedelta(minutes=50)).timestamp(), "type": "five_hour",
             "resets_at": reset.timestamp()},
        ], direct, NOW)
        self.assertEqual(1, summary["samples"]["count"])
        self.assertEqual(300, summary["samples"]["median"])
        self.assertEqual(2, len(summary["events"]))

    def test_only_five_hour_events_feed_five_hour_capacity(self):
        reset = NOW - timedelta(hours=1)
        direct = [{"at": (NOW - timedelta(hours=2)).timestamp(), "total": 500}]
        summary = quota.summarize_claude([
            {"at": (NOW - timedelta(hours=1)).timestamp(), "type": "seven_day",
             "resets_at": reset.timestamp()},
            {"at": (NOW - timedelta(hours=1)).timestamp(), "type": "five_hour",
             "resets_at": reset.timestamp()},
            {"at": (NOW - timedelta(hours=1)).timestamp(), "type": None,
             "resets_at": (NOW - timedelta(minutes=30)).timestamp()},
        ], direct, NOW)
        self.assertEqual(2, summary["samples"]["count"])
        self.assertEqual(3, len(summary["events"]))

    def test_velocity_denominator_is_capped_at_one_hour(self):
        direct = [
            {"at": (NOW - timedelta(hours=2)).timestamp(), "total": 1},
            {"at": (NOW - timedelta(minutes=6)).timestamp(), "total": 100},
            {"at": (NOW - timedelta(minutes=3)).timestamp(), "total": 100},
            {"at": NOW.timestamp(), "total": 100},
        ]
        current = quota.summarize_claude([], direct, NOW)["current"]
        # 300 tokens over the capped one-hour denominator, not over six minutes.
        self.assertAlmostEqual(300, current["velocity_per_hour"])
        self.assertLessEqual(current["velocity_per_hour"], 300 * 10)

    def test_safe_floor_can_raise_capacity_above_hit_samples(self):
        direct = [
            {"at": (NOW - timedelta(hours=12)).timestamp(), "total": 100},
            {"at": (NOW - timedelta(hours=11)).timestamp(), "total": 50},
            {"at": (NOW - timedelta(hours=4)).timestamp(), "total": 10},
        ]
        events = [{"at": (NOW - timedelta(hours=3)).timestamp(), "type": "five_hour",
                   "resets_at": (NOW - timedelta(hours=2)).timestamp()}]
        summary = quota.summarize_claude(events, direct, NOW)
        samples = summary["samples"]
        self.assertEqual("safe_floor", samples["basis"])
        self.assertEqual(150, samples["safe_floor"])
        self.assertEqual(1, samples["safe_windows"])
        self.assertEqual(150, summary["current"]["capacity_tokens"])

    def test_beyond_estimate_without_current_hit_has_no_projection(self):
        direct = [
            {"at": (NOW - timedelta(hours=12)).timestamp(), "total": 10},
            {"at": (NOW - timedelta(hours=4)).timestamp(), "total": 200},
        ]
        events = [{"at": (NOW - timedelta(hours=10)).timestamp(), "type": "five_hour",
                   "resets_at": (NOW - timedelta(hours=9)).timestamp()}]
        current = quota.summarize_claude(events, direct, NOW)["current"]
        self.assertFalse(current["has_hit"])
        self.assertEqual("beyond_estimate", current["projection"]["status"])
        self.assertIsNone(current["projection"]["projected_at"])

    def test_safe_floor_forecast_uses_past_floor_without_warning(self):
        direct = [
            {"at": (NOW - timedelta(hours=14)).timestamp(), "total": 100},
            {"at": (NOW - timedelta(hours=6)).timestamp(), "total": 400},
            {"at": (NOW - timedelta(hours=5)).timestamp(), "total": 400},
            {"at": (NOW - timedelta(minutes=40)).timestamp(), "total": 100},
            {"at": (NOW - timedelta(minutes=20)).timestamp(), "total": 100},
        ]
        events = [{"at": (NOW - timedelta(hours=10)).timestamp(), "type": "five_hour",
                   "resets_at": (NOW - timedelta(hours=9)).timestamp()}]
        summary = quota.summarize_claude(events, direct, NOW)
        self.assertEqual("safe_floor", summary["samples"]["basis"])
        current = summary["current"]
        self.assertEqual("past_floor", current["projection"]["status"])
        self.assertIsNotNone(current["projection"]["projected_at"])
        report = {
            "generated_at": NOW.isoformat(), "timezone": "Asia/Shanghai",
            "sources": ["claude"], "unsupported": [],
            "codex": {"selected": False, "kind": "official", "snapshot_count": 0,
                      "files": 0, "plans": []},
            "claude": {"selected": True, "files": 1, **summary},
            "opencode": {"selected": False, "kind": "none", "available": False,
                         "reason": "no_official_quota_data"},
            "parsed_files": 1,
        }
        stdout = io.StringIO()
        with mock.patch("sys.stdout", stdout):
            quota.print_report(report, lang="zh")
        text = stdout.getvalue()
        self.assertIn("不代表会撞线", text)
        self.assertIn("ℹ", text)
        self.assertNotIn("⚠", text)
        self.assertIn("按最近 1 小时速度", text)

    def test_hits_basis_forecast_still_reports_hit(self):
        direct = [
            {"at": (NOW - timedelta(hours=14)).timestamp(), "total": 1000},
            {"at": (NOW - timedelta(minutes=40)).timestamp(), "total": 100},
            {"at": (NOW - timedelta(minutes=20)).timestamp(), "total": 100},
        ]
        events = [{"at": (NOW - timedelta(hours=10)).timestamp(), "type": "five_hour",
                   "resets_at": (NOW - timedelta(hours=9)).timestamp()}]
        current = quota.summarize_claude(events, direct, NOW)["current"]
        self.assertEqual("hit", current["projection"]["status"])

    def test_window_younger_than_fifteen_minutes_is_insufficient(self):
        young = [
            {"at": (NOW - timedelta(minutes=10)).timestamp(), "total": 100},
            {"at": (NOW - timedelta(minutes=5)).timestamp(), "total": 100},
            {"at": NOW.timestamp(), "total": 100},
        ]
        current = quota.summarize_claude([], young, NOW)["current"]
        self.assertTrue(current["window_too_new"])
        self.assertIsNone(current["velocity_per_hour"])
        self.assertEqual("insufficient", current["projection"]["status"])

        older = [
            {"at": (NOW - timedelta(hours=14)).timestamp(), "total": 1000},
            {"at": (NOW - timedelta(minutes=20)).timestamp(), "total": 10},
            {"at": (NOW - timedelta(minutes=10)).timestamp(), "total": 10},
            {"at": NOW.timestamp(), "total": 10},
        ]
        events = [{"at": (NOW - timedelta(hours=10)).timestamp(), "type": "five_hour",
                   "resets_at": (NOW - timedelta(hours=9)).timestamp()}]
        current = quota.summarize_claude(events, older, NOW)["current"]
        self.assertFalse(current["window_too_new"])
        self.assertIsNotNone(current["velocity_per_hour"])
        self.assertNotEqual("insufficient", current["projection"]["status"])

    def test_current_window_with_hit_event_reports_hit(self):
        direct = [{"at": (NOW - timedelta(hours=4)).timestamp(), "total": 200}]
        events = [{"at": (NOW - timedelta(hours=1)).timestamp(), "type": "five_hour",
                   "resets_at": (NOW + timedelta(hours=4)).timestamp()}]
        current = quota.summarize_claude(events, direct, NOW)["current"]
        self.assertTrue(current["has_hit"])
        self.assertEqual("hit", current["projection"]["status"])

    def test_no_reset_events_merge_within_sixty_seconds(self):
        start = (NOW - timedelta(hours=1)).timestamp()
        events = [
            {"at": start, "type": None, "resets_at": None},
            {"at": start + 30, "type": None, "resets_at": None},
            {"at": start + 90, "type": None, "resets_at": None},
            {"at": start + 30, "type": "five_hour", "resets_at": None},
        ]
        deduped = quota._dedupe_events(events)
        self.assertEqual(3, len(deduped))
        self.assertEqual([start, start + 30, start + 90],
                         [event["at"] for event in deduped])

    def test_window_split_opens_new_window_at_exactly_five_hours(self):
        start = (NOW - timedelta(hours=10)).timestamp()
        direct = [
            {"at": start, "total": 1},
            {"at": start + quota.CLAUDE_WINDOW_SECONDS - 1, "total": 1},
            {"at": start + quota.CLAUDE_WINDOW_SECONDS, "total": 1},
        ]
        windows = quota._claude_windows(direct, until=NOW.timestamp())
        self.assertEqual(2, len(windows))
        self.assertEqual(start, windows[0]["start"])
        self.assertEqual(start + quota.CLAUDE_WINDOW_SECONDS, windows[1]["start"])
        self.assertEqual(2, len(windows[0]["rows"]))
        self.assertEqual(1, len(windows[1]["rows"]))

    def test_no_samples_and_current_window_inference(self):
        summary = quota.summarize_claude([], [], NOW)
        self.assertEqual(0, summary["samples"]["count"])
        self.assertIsNone(summary["samples"]["median"])
        self.assertIsNone(summary["current"])

        direct = [{"at": (NOW - timedelta(hours=4)).timestamp(), "total": 100},
                  {"at": (NOW - timedelta(hours=1)).timestamp(), "total": 200}]
        current = quota.summarize_claude([], direct, NOW)["current"]
        self.assertTrue(current["start"].startswith("2026-11-10T14:00"))
        self.assertTrue(current["end"].startswith("2026-11-10T19:00"))
        self.assertEqual(300, current["direct_tokens"])


class QuotaCollectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.claude_root = self.root / "claude"
        self.codex_root = self.root / "codex"
        self.codex_archive = self.root / "codex-archive"
        self.cache_root = self.root / "cache"
        self.claude_file = self.claude_root / "project" / "session.jsonl"
        self.codex_file = self.codex_root / "2026" / "11" / "10" / "rollout-a.jsonl"
        self.claude_root.mkdir(parents=True)
        self.codex_root.mkdir(parents=True)
        self.codex_archive.mkdir()
        self.cache_root.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def _patches(self):
        return [
            mock.patch.object(config, "CLAUDE_PROJECTS", str(self.claude_root)),
            mock.patch.object(config, "CODEX_SESSIONS", str(self.codex_root)),
            mock.patch.object(config, "CODEX_ARCHIVED_SESSIONS", str(self.codex_archive)),
            mock.patch.object(config, "CACHE_DIR", str(self.cache_root)),
            mock.patch.object(quota.readers, "read_all", return_value=[]),
        ]

    def test_collection_output_is_private_and_covers_all_sources(self):
        write_lines(self.claude_file, [
            {"timestamp": (NOW - timedelta(minutes=10)).isoformat(),
             "error": "rate_limit", "isApiErrorMessage": True, "apiErrorStatus": 429,
             "sessionId": "ses_synthetic", "cwd": "/synthetic/private-project",
             "quotaLimits": {"rateLimitType": "five_hour", "status": "rejected",
                             "resetsAt": int((NOW + timedelta(hours=1)).timestamp())},
             "message": {"content": SECRET}},
            {"timestamp": (NOW - timedelta(minutes=5)).isoformat(),
             "message": {"content": SECRET}},
        ])
        write_lines(self.codex_file, [
            {"timestamp": NOW.isoformat(), "payload": {
                "rate_limits": {
                    "plan_type": "plus", "limit_id": "codex", "limit_name": None,
                    "primary": {"window_minutes": 300, "used_percent": 42,
                                "resets_at": (NOW + timedelta(hours=1)).timestamp()},
                    "secondary": {"window_minutes": 10080, "used_percent": 61,
                                  "resets_at": (NOW + timedelta(days=4)).timestamp()},
                },
                "content": SECRET,
            }},
        ])
        patches = self._patches()
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            report = quota.collect(sources=["claude", "codex", "opencode"],
                                   use_cache=True, now=NOW)
            stdout = io.StringIO()
            with mock.patch("sys.stdout", stdout):
                quota.print_report(report, lang="en")
        text = stdout.getvalue()
        payload = json.dumps(report)
        for private in (SECRET, "/synthetic/private-project", "ses_synthetic"):
            self.assertNotIn(private, text)
            self.assertNotIn(private, payload)
        self.assertIn("Codex · plus", text)
        self.assertIn("Claude (estimate", text)
        self.assertIn("OpenCode: no official quota data", text)
        self.assertEqual("official", report["codex"]["kind"])
        self.assertEqual("estimate", report["claude"]["kind"])
        self.assertEqual("none", report["opencode"]["kind"])

    def test_second_run_reuses_unchanged_file_cache(self):
        write_lines(self.claude_file, [
            {"timestamp": NOW.isoformat(), "error": "rate_limit",
             "isApiErrorMessage": True, "apiErrorStatus": 429,
             "quotaLimits": {"rateLimitType": "five_hour",
                             "resetsAt": int((NOW + timedelta(hours=1)).timestamp())}},
        ])
        patches = self._patches()
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            with mock.patch.object(quota, "_scan_claude_file",
                                   wraps=quota._scan_claude_file) as scanner:
                quota.collect(sources=["claude"], use_cache=True, now=NOW)
                quota.collect(sources=["claude"], use_cache=True, now=NOW)
        self.assertEqual(1, scanner.call_count)
        self.assertTrue((self.cache_root / "quota-v1.json").is_file())

    def test_prefilter_skips_json_loads_for_unrelated_lines(self):
        write_lines(self.claude_file, [
            {"timestamp": NOW.isoformat(), "message": {"content": SECRET}},
            {"timestamp": NOW.isoformat(), "error": "rate_limit",
             "isApiErrorMessage": True, "apiErrorStatus": 429},
        ])
        with mock.patch.object(quota.json, "loads", wraps=json.loads) as loads:
            events = quota._scan_claude_file(str(self.claude_file))
        self.assertEqual(1, loads.call_count)
        self.assertEqual(1, len(events))

    def test_text_and_json_share_the_same_numbers(self):
        snapshots = [
            snapshot(NOW - timedelta(minutes=10), 40, resets=NOW + timedelta(hours=5)),
            snapshot(NOW, 50, resets=NOW + timedelta(hours=5)),
        ]
        report = {
            "generated_at": NOW.isoformat(),
            "timezone": "Asia/Shanghai",
            "sources": ["codex"],
            "unsupported": [],
            "codex": {"selected": True, "kind": "official", "snapshot_count": 2,
                      "files": 1, "plans": quota.summarize_codex(snapshots, NOW)},
            "claude": {"selected": False, "kind": "estimate",
                       "samples": {"count": 0, "median": None, "min": None, "max": None},
                       "current": None, "events": [], "files": 0},
            "opencode": {"selected": False, "kind": "none", "available": False,
                         "reason": "no_official_quota_data"},
            "parsed_files": 1,
        }
        stdout = io.StringIO()
        with mock.patch("sys.stdout", stdout):
            quota.print_report(report, lang="zh")
        text = stdout.getvalue()
        self.assertIn("Codex · plus（官方）", text)
        self.assertIn("50%", text)
        self.assertIn("撞线", text)


class QuotaCliTests(unittest.TestCase):
    def test_quota_accepts_json_and_forwards_sources(self):
        report = {"generated_at": NOW.isoformat(), "timezone": "UTC",
                  "sources": ["codex"], "unsupported": [],
                  "codex": {"selected": True, "kind": "official", "snapshot_count": 0,
                            "files": 0, "plans": []},
                  "claude": {"selected": False, "kind": "estimate",
                             "samples": {"count": 0, "median": None, "min": None, "max": None},
                             "current": None, "events": [], "files": 0},
                  "opencode": {"selected": False, "kind": "none", "available": False,
                               "reason": "no_official_quota_data"},
                  "parsed_files": 0}
        stdout = io.StringIO()
        with mock.patch.object(cli.quota, "collect", return_value=report) as collect, \
                mock.patch("sys.stdout", stdout):
            result = cli.main(["quota", "--json", "--source", "codex"])
        self.assertEqual(0, result)
        collect.assert_called_once_with(sources=["codex"], use_cache=True)
        self.assertEqual([], json.loads(stdout.getvalue())["codex"]["plans"])

    def test_json_is_rejected_outside_quota_and_doctor_models(self):
        with mock.patch("sys.stderr", io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                cli.main(["day", "--json"])
        self.assertEqual(2, caught.exception.code)


if __name__ == "__main__":
    unittest.main()


class QuotaDashboardBlockTests(unittest.TestCase):
    """The HUD block must reuse quota's math and stay display-only."""

    def setUp(self):
        patcher = mock.patch.object(quota.config, "TZ", TZ)
        patcher.start()
        self.addCleanup(patcher.stop)

    def scan(self, snapshots=(), events=()):
        return {
            "claude_events": list(events),
            "codex_snapshots": list(snapshots),
            "claude_files": 1,
            "codex_files": 1,
            "parsed_files": len(snapshots) + len(events),
        }

    def test_collect_delegates_to_summarize_without_changing_the_report(self):
        scan = self.scan([
            snapshot(NOW - timedelta(minutes=10), 40, resets=NOW + timedelta(hours=5)),
        ])
        records = [claude_record(NOW - timedelta(minutes=30))]
        expected = quota.summarize_sources(["claude", "codex"], scan, records, NOW)
        with mock.patch.object(quota, "scan_rate_limits", return_value=scan), \
                mock.patch.object(quota.readers, "read_all", return_value=records):
            actual = quota.collect(sources=["claude", "codex"], now=NOW)
        self.assertEqual(expected, actual)

    def test_dashboard_snapshot_carries_codex_windows_and_statuses(self):
        snapshots = [
            snapshot(NOW - timedelta(minutes=10), 90,
                     resets=NOW + timedelta(hours=2)),
            snapshot(NOW - timedelta(minutes=5), 96,
                     resets=NOW + timedelta(hours=2)),
            snapshot(NOW - timedelta(minutes=5), 61, minutes=10080,
                     resets=NOW + timedelta(days=4)),
            # Eight days old: stale for a one-glance HUD, never for the CLI.
            snapshot(NOW - timedelta(days=8), 50, minutes=10080,
                     resets=NOW - timedelta(days=1)),
        ]
        block = quota.dashboard_snapshot({"codex"}, self.scan(snapshots), [], NOW)
        self.assertIsNotNone(block)
        self.assertIsNone(block["claude"])
        self.assertEqual(2, len(block["codex"]))
        five = block["codex"][0]
        self.assertEqual("5h", five["window"])
        self.assertEqual("current", five["status"])
        self.assertEqual("hit", five["projection"]["status"])
        self.assertEqual(96.0, five["used_percent"])
        week = block["codex"][1]
        self.assertEqual("week", week["window"])
        self.assertEqual(61.0, week["used_percent"])
        self.assertEqual("insufficient", week["projection"]["status"])

    def test_dashboard_snapshot_expired_and_empty(self):
        expired = snapshot(NOW - timedelta(minutes=10), 80,
                           resets=NOW - timedelta(minutes=1))
        block = quota.dashboard_snapshot({"codex"}, self.scan([expired]), [], NOW)
        row = block["codex"][0]
        self.assertEqual("expired", row["status"])
        self.assertIsNone(row["used_percent"])
        self.assertEqual("expired", row["projection"]["status"])
        self.assertIsNone(quota.dashboard_snapshot(
            {"codex", "claude"}, self.scan(), [], NOW))
        self.assertIsNone(quota.dashboard_snapshot(
            {"opencode"}, self.scan(), [], NOW))

    def test_dashboard_snapshot_has_claude_estimate_and_no_private_fields(self):
        scan = self.scan([], [])
        record = claude_record(NOW - timedelta(minutes=30), total=1234)
        record["cwd"] = "/synthetic/private-project"
        record["session"] = "ses_synthetic_private"
        block = quota.dashboard_snapshot({"claude"}, scan, [record], NOW)
        self.assertIsNotNone(block)
        self.assertEqual([], block["codex"])
        claude = block["claude"]
        self.assertEqual("safe_floor" if claude["basis"] == "safe_floor"
                         else claude["basis"], claude["basis"])
        self.assertIn("projection", claude)
        self.assertIn(claude["projection"]["status"],
                      {"hit", "safe", "flat", "insufficient", "past_floor",
                       "beyond_estimate", "no_estimate"})
        rendered = json.dumps(block, ensure_ascii=False)
        self.assertNotIn("/synthetic/private-project", rendered)
        self.assertNotIn("ses_synthetic_private", rendered)
        self.assertNotIn(SECRET, rendered)
