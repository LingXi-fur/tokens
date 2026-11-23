"""Outcomes layer: git commits matched to sessions, measured read-only.

Every scenario uses a throwaway git repository and a pinned clock; no real
repository or real time is touched.  Only counts and ratios may leave the
module, so the assertions also check that no commit sha, file path, or
author identity leaks into the payload or the blame cache.
"""
from tests import _hermetic  # noqa: F401
from datetime import datetime, timedelta, timezone
import io
import json
import os
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

from tokens_cli import cli, config, dashboard_payload, live_snapshot, outcomes, readers

NOW = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
DAY = 86400
EMAIL = "synthetic-user@example.com"
NAME = "Synthetic User"
PRICED_MODEL = "claude-sonnet-5.5"


def _git(repo, *args, date_epoch=None, author=None, check=True):
    env = dict(os.environ)
    env.setdefault("GIT_AUTHOR_EMAIL", EMAIL)
    env.setdefault("GIT_AUTHOR_NAME", NAME)
    env.setdefault("GIT_COMMITTER_EMAIL", EMAIL)
    env.setdefault("GIT_COMMITTER_NAME", NAME)
    if date_epoch is not None:
        stamp = f"{int(date_epoch)} +0000"
        env["GIT_AUTHOR_DATE"] = stamp
        env["GIT_COMMITTER_DATE"] = stamp
    if author is not None:
        env["GIT_AUTHOR_EMAIL"] = author
        env["GIT_COMMITTER_EMAIL"] = author
        env["GIT_AUTHOR_NAME"] = "Someone Else"
        env["GIT_COMMITTER_NAME"] = "Someone Else"
    return subprocess.run(["git", "-C", str(repo), *args], env=env,
                          capture_output=True, check=check)


def _init_repo(path):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q")
    _git(path, "config", "user.email", EMAIL)
    _git(path, "config", "user.name", NAME)
    return path


def _commit(repo, files, date_epoch, message="synthetic", author=None):
    """Write files (dict path->text) and commit them at the given epoch."""
    for path, text in files.items():
        target = Path(repo) / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message, date_epoch=date_epoch, author=author)
    return _git(repo, "rev-parse", "HEAD", check=True).stdout.decode().strip()


def _record(ts, sid, cwd, model=PRICED_MODEL, total=2000, parts=(1000, 1000, 0, 0, 0)):
    return {
        "source": "claude",
        "ts": ts,
        "date": ts[:10],
        "model": model,
        "input": parts[0], "output": parts[1],
        "cache_read": parts[2], "cache_write": parts[3],
        "total": total,
        "session": sid,
        "cwd": cwd,
        "billing": {
            "v": 1,
            "present": {"input": True, "output": True, "cache_read": True,
                        "cache_write": True, "thoughts": True},
            "raw": {"input": parts[0], "output": parts[1], "cache_read": parts[2],
                    "cache_write": parts[3], "thoughts": parts[4]},
            "parts": list(parts),
            "uncertain": False,
            "reasons": [],
        },
    }


class OutcomesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        cache_dir = self.root / "cache"
        cache_dir.mkdir()
        for patch in (
            mock.patch.object(config, "CACHE_DIR", str(cache_dir)),
            mock.patch.object(config, "TZ", ZoneInfo("UTC")),
        ):
            patch.start()
            self.addCleanup(patch.stop)

    def build(self, records, **kwargs):
        return outcomes.build_outcomes(records, now=NOW, **kwargs)

    # ---- scenario: sessions, repos, attribution -----------------------------

    def test_session_commit_is_attributed_and_survives(self):
        repo = _init_repo(self.root / "proj")
        _commit(repo, {"app.py": "print('hello')\n" * 5},
                date_epoch=NOW.timestamp() - 8 * DAY)
        cwd = str(repo)
        records = [
            _record("2026-11-12T09:00:00Z", "ses-1", cwd),
            _record("2026-11-12T11:45:00Z", "ses-1", cwd),
        ]
        block = self.build(records, since="2026-11-10", until="2026-11-20")
        self.assertEqual("ok", block["status"])
        self.assertEqual(1, block["totals"]["commits"])
        self.assertEqual(5, block["totals"]["added"])
        self.assertEqual(5, block["totals"]["surviving"])
        self.assertEqual(0.0, block["totals"]["rework_tax"])
        project = block["projects"][0]
        self.assertEqual(os.path.realpath(cwd), project["project"])
        self.assertTrue(project["repo"])
        self.assertEqual(1, project["commits"])

    def test_commit_outside_sessions_counts_as_manual(self):
        repo = _init_repo(self.root / "proj")
        _commit(repo, {"app.py": "print('manual')\n"},
                date_epoch=NOW.timestamp() - 9 * DAY)
        records = [
            _record("2026-11-01T09:00:00Z", "ses-1", str(repo)),
        ]
        block = self.build(records, since="2026-11-01", until="2026-11-20")
        self.assertEqual(1, block["totals"]["no_session_commits"])
        self.assertEqual(1, block["totals"]["commits"])
        self.assertEqual(0, block["models"][0]["commits"])
        self.assertEqual(1, block["totals"]["sessions_without_commits"])
        self.assertEqual("ses-1", block["no_commit_sessions"][0]["session"])

    def test_rolled_back_lines_drive_rework_tax(self):
        repo = _init_repo(self.root / "proj")
        cwd = str(repo)
        # Session 1 pays $0.03 (1000 in + 1000 out at sonnet prices) and adds
        # lines that are later removed again by a manual commit.
        _commit(repo, {"feature.py": "keep = 1\nscratch = 2\nscratch = 3\n"},
                date_epoch=NOW.timestamp() - 10 * DAY)
        _commit(repo, {"feature.py": "keep = 1\n"},
                date_epoch=NOW.timestamp() - 2 * DAY)
        records = [
            _record("2026-11-10T11:45:00Z", "ses-1", cwd, total=60000,
                    parts=(30000, 30000, 0, 0, 0)),
        ]
        block = self.build(records, since="2026-11-01", until="2026-11-20")
        self.assertEqual(3, block["totals"]["added"])
        self.assertEqual(1, block["totals"]["surviving"])
        self.assertGreater(block["totals"]["rework_tax"], 0.0)
        self.assertEqual(1, block["totals"]["no_session_commits"])  # the removal
        # Sonnet 5.5 reference spend: 30k input * $2/M + 30k output * $10/M
        # = $0.36; reworked share (3-1)/3 of it -> $0.24.
        self.assertAlmostEqual(block["totals"]["cost"], 0.36, places=2)
        self.assertAlmostEqual(block["totals"]["rework_tax"], 0.24, places=2)

    def test_since_only_range_extends_to_today(self):
        repo = _init_repo(self.root / "proj")
        cwd = str(repo)
        # One commit on the --since day, one commit "today" (NOW's day).
        _commit(repo, {"old.py": "old = 1\n"},
                date_epoch=NOW.timestamp() - 7 * DAY)
        _commit(repo, {"new.py": "new = 1\n"},
                date_epoch=NOW.timestamp() - 3600)
        records = [
            _record("2026-11-13T10:00:00Z", "ses-1", cwd),
            _record(f"{NOW.date().isoformat()}T09:00:00Z", "ses-1", cwd),
        ]
        block = self.build(records, since="2026-11-13")
        # The window covers the since day through today (NOW's day), and the
        # real git log actually resolves that ISO range.
        self.assertEqual({"since": "2026-11-13",
                          "until": NOW.date().isoformat()}, block["range"])
        self.assertEqual(2, block["totals"]["commits"])
        self.assertEqual(2, block["totals"]["added"])
        # Both sessions' spend and both commits describe one same range.
        self.assertEqual(4000, block["totals"]["tokens"])

    def test_git_log_iso_boundaries_include_the_since_day(self):
        repo = _init_repo(self.root / "proj")
        cwd = str(repo)
        # The in.py commit sits on 2026-11-10 at 09:00 UTC, i.e. inside the
        # --since day boundary; out.py sits a day earlier and must stay
        # outside.  A bare epoch (git cannot parse it) would miss both.
        # Commit the older one first: git log --since prunes history as it
        # walks, so an out-of-window commit at HEAD would stop the walk.
        _commit(repo, {"out.py": "out = 1\n"},
                date_epoch=datetime(2026, 11, 9, 9, tzinfo=timezone.utc).timestamp())
        _commit(repo, {"in.py": "in = 1\n"},
                date_epoch=datetime(2026, 11, 10, 9, tzinfo=timezone.utc).timestamp())
        records = [_record("2026-11-10T10:00:00Z", "ses-1", cwd)]
        block = self.build(records, since="2026-11-10", until="2026-11-11")
        self.assertEqual(1, block["totals"]["commits"])
        self.assertEqual(1, block["totals"]["added"])
        self.assertNotIn("out.py", json.dumps(block))

    def test_recent_commits_are_pending_not_reworked(self):
        repo = _init_repo(self.root / "proj")
        _commit(repo, {"app.py": "fresh = 1\n"},
                date_epoch=NOW.timestamp() - 2 * DAY)
        records = [
            _record("2026-11-18T11:45:00Z", "ses-1", str(repo)),
        ]
        block = self.build(records, since="2026-11-10", until="2026-11-20")
        self.assertEqual(1, block["totals"]["added"])
        self.assertEqual(0, block["totals"]["surviving"])
        self.assertEqual(0.0, block["totals"]["rework_tax"])
        self.assertEqual(1, block["days"][0]["pending_added"])

    def test_lock_files_and_vendored_paths_are_excluded(self):
        repo = _init_repo(self.root / "proj")
        _commit(repo, {
            "app.py": "code = 1\n",
            "package-lock.json": '{"locked": true}\n',
            "yarn.lock": "# yarn lock\n",
            "app.min.js": "var a=1;\n",
            "dist/bundle.js": "var b=2;\n",
        }, date_epoch=NOW.timestamp() - 8 * DAY)
        records = [_record("2026-11-12T11:45:00Z", "ses-1", str(repo))]
        block = self.build(records, since="2026-11-10", until="2026-11-20")
        self.assertEqual(1, block["totals"]["added"])  # only app.py's line
        self.assertEqual(1, block["totals"]["files"])

    def test_worktree_cwd_resolves_to_its_repository(self):
        repo = _init_repo(self.root / "main")
        # The commit lives on the repository's main HEAD: worktrees share the
        # object store, and the repository is counted exactly once.
        _commit(repo, {"app.py": "base = 1\nextra = 2\n"},
                date_epoch=NOW.timestamp() - 8 * DAY)
        worktree = self.root / "wt"
        _git(repo, "worktree", "add", "-q", str(worktree))
        records = [_record("2026-11-12T11:45:00Z", "ses-1", str(worktree))]
        block = self.build(records, since="2026-11-10", until="2026-11-20")
        self.assertEqual(1, block["totals"]["commits"])
        self.assertEqual(2, block["totals"]["added"])
        # The session's project rolls up to the repository; the worktree
        # never becomes its own project row.
        self.assertEqual(os.path.realpath(str(repo)),
                         block["projects"][0]["project"])
        self.assertTrue(block["projects"][0]["repo"])

    def test_worktrees_of_one_repository_count_commits_once(self):
        repo = _init_repo(self.root / "main")
        _commit(repo, {"app.py": "first = 1\n"},
                date_epoch=NOW.timestamp() - 8 * DAY)
        _commit(repo, {"app.py": "first = 1\nsecond = 2\n"},
                date_epoch=NOW.timestamp() - 8 * DAY + 900)
        wt_one = self.root / "wt-one"
        wt_two = self.root / "wt-two"
        _git(repo, "worktree", "add", "-q", str(wt_one))
        _git(repo, "worktree", "add", "-q", str(wt_two))
        # One session per checkout: main plus both worktrees, all inside the
        # same session window.  One repository, two commits, three sessions.
        records = [
            _record("2026-11-12T11:45:00Z", "ses-main", str(repo)),
            _record("2026-11-12T11:45:00Z", "ses-wt-one", str(wt_one)),
            _record("2026-11-12T11:45:00Z", "ses-wt-two", str(wt_two)),
        ]
        block = self.build(records, since="2026-11-10", until="2026-11-20")
        # Each commit counted exactly once, never once per worktree.
        self.assertEqual(2, block["totals"]["commits"])
        self.assertEqual(0, block["totals"]["no_session_commits"])
        # 1 new line in the first commit + 1 more line in the second.
        self.assertEqual(2, block["totals"]["added"])
        self.assertEqual(1, len(block["projects"]))
        self.assertEqual(os.path.realpath(str(repo)),
                         block["projects"][0]["project"])
        # Per-day sums are invariant: sum(days) == totals.
        self.assertEqual(block["totals"]["commits"],
                         sum(row["commits"] for row in block["days"]))
        self.assertEqual(block["totals"]["added"],
                         sum(row["added"] for row in block["days"]))

    def test_non_git_directory_is_reported_without_git_calls(self):
        plain = self.root / "plain"
        plain.mkdir()
        records = [_record("2026-11-12T09:00:00Z", "ses-1", str(plain))]
        block = self.build(records, since="2026-11-10", until="2026-11-20")
        self.assertEqual(1, block["reasons"]["no_repo"])
        self.assertEqual("ok", block["status"])
        self.assertFalse(block["projects"][0]["repo"])
        self.assertEqual(0, block["totals"]["commits"])
        # A session outside any git repo is its own category, never a
        # "session without commits" (those can never match a commit anyway).
        self.assertEqual([], block["no_commit_sessions"])
        self.assertEqual(1, block["totals"]["no_repo_sessions"])
        self.assertEqual(0, block["totals"]["sessions_without_commits"])
        self.assertEqual("ses-1", block["no_repo_sessions"][0]["session"])
        self.assertNotIn("repo", block["no_repo_sessions"][0])

    def test_foreign_author_commits_are_ignored(self):
        repo = _init_repo(self.root / "proj")
        _commit(repo, {"own.py": "mine = 1\n"}, date_epoch=NOW.timestamp() - 9 * DAY)
        _commit(repo, {"other.py": "theirs = 1\n"},
                date_epoch=NOW.timestamp() - 9 * DAY + 3600,
                author="someone-else@example.com")
        records = [_record("2026-11-11T11:45:00Z", "ses-1", str(repo))]
        block = self.build(records, since="2026-11-10", until="2026-11-20")
        self.assertEqual(1, block["totals"]["commits"])
        self.assertEqual(1, block["totals"]["added"])

    def test_overlapping_sessions_go_to_the_latest_activity(self):
        repo = _init_repo(self.root / "proj")
        cwd = str(repo)
        _commit(repo, {"app.py": "line = 1\n"}, date_epoch=NOW.timestamp() - 8 * DAY)
        records = [
            _record("2026-11-12T08:00:00Z", "ses-old", cwd),
            # ses-new is active closer to the commit time.
            _record("2026-11-12T11:45:00Z", "ses-new", cwd),
        ]
        block = self.build(records, since="2026-11-10", until="2026-11-20")
        model_rows = {row["model"]: row for row in block["models"]}
        self.assertEqual(1, model_rows[PRICED_MODEL]["commits"])
        no_commit = {row["session"] for row in block["no_commit_sessions"]}
        self.assertIn("ses-old", no_commit)
        self.assertNotIn("ses-new", no_commit)

    def test_git_unavailable_degrades_without_failing(self):
        repo = _init_repo(self.root / "proj")
        _commit(repo, {"app.py": "x = 1\n"}, date_epoch=NOW.timestamp() - 8 * DAY)
        records = [_record("2026-11-12T09:00:00Z", "ses-1", str(repo))]
        with mock.patch.object(outcomes, "_git_executable", return_value=None):
            block = self.build(records, since="2026-11-10", until="2026-11-20")
        self.assertEqual("unavailable", block["status"])
        self.assertEqual(1, block["reasons"]["git_missing"])
        self.assertEqual(0, block["totals"]["commits"])
        self.assertEqual(1, block["totals"]["sessions"])

    # ---- cost, privacy, cache ----------------------------------------------

    def test_reference_price_amounts_and_unpriced_models(self):
        repo = _init_repo(self.root / "proj")
        _commit(repo, {"app.py": "x = 1\n"}, date_epoch=NOW.timestamp() - 8 * DAY)
        records = [
            _record("2026-11-12T11:45:00Z", "ses-1", str(repo)),
            _record("2026-11-12T11:45:00Z", "ses-2", str(repo),
                    model="totally-unknown-model", total=500,
                    parts=(250, 250, 0, 0, 0)),
        ]
        block = self.build(records, since="2026-11-10", until="2026-11-20")
        # sonnet 5.5: $2/M input + $10/M output -> 1000 in + 1000 out = $0.012
        self.assertAlmostEqual(block["totals"]["cost"], 0.01, places=2)
        self.assertEqual(1, block["reasons"]["unestimated_cost"])
        serialized = json.dumps(block, ensure_ascii=False)
        self.assertNotIn(EMAIL, serialized)
        self.assertNotIn(NAME, serialized)

    def test_blame_cache_is_reused_and_stays_count_only(self):
        repo = _init_repo(self.root / "proj")
        _commit(repo, {"app.py": "x = 1\n"}, date_epoch=NOW.timestamp() - 8 * DAY)
        records = [_record("2026-11-12T11:45:00Z", "ses-1", str(repo))]
        first = self.build(records, since="2026-11-10", until="2026-11-20")
        cache_path = Path(config.CACHE_DIR) / "outcomes-blame-v1.json"
        self.assertTrue(cache_path.exists())
        raw = cache_path.read_text(encoding="utf-8")
        self.assertNotIn("app.py", raw)
        self.assertNotIn(EMAIL, raw)
        data = json.loads(raw)
        self.assertTrue(all(set(entry) == {"s", "t"} for entry in data["entries"].values()))
        with mock.patch.object(outcomes, "_blame_surviving",
                               side_effect=AssertionError("cache must win")):
            second = self.build(records, since="2026-11-10", until="2026-11-20")
        self.assertEqual(first, second)

    def test_anonymized_payload_has_no_real_project_or_session(self):
        repo = _init_repo(self.root / "secret-project-name")
        _commit(repo, {"app.py": "x = 1\n"}, date_epoch=NOW.timestamp() - 8 * DAY)
        cwd = str(repo)
        records = [_record("2026-11-12T11:45:00Z", "secret-session-id", cwd)]
        aliases = dashboard_payload._ReportAliases()
        block = self.build(records, since="2026-11-10", until="2026-11-20",
                           anonymize=True, aliases=aliases)
        serialized = json.dumps(block, ensure_ascii=False)
        self.assertNotIn("secret-project-name", serialized)
        self.assertNotIn("secret-session-id", serialized)
        self.assertEqual(1, block["totals"]["commits"])
        self.assertTrue(block["projects"][0]["project"].startswith("Project-"))

    def test_outcomes_block_passes_live_snapshot_validation(self):
        repo = _init_repo(self.root / "proj")
        _commit(repo, {"app.py": "x = 1\n"}, date_epoch=NOW.timestamp() - 8 * DAY)
        records = [_record("2026-11-12T11:45:00Z", "ses-1", str(repo))]
        block = self.build(records, since="2026-11-10", until="2026-11-20")
        # live_snapshot validates the whole payload; outcomes is the new part.
        live_snapshot._outcomes_shape(block)
        payload = dashboard_payload.build_payload(
            records, since="2026-11-10", until="2026-11-20", sources=["claude"],
            generated_at=NOW)
        self.assertEqual(block["schema"], payload["outcomes"]["schema"])
        self.assertEqual(1, payload["outcomes"]["totals"]["commits"])

    def test_extra_email_and_exclude_config(self):
        repo = _init_repo(self.root / "proj")
        _commit(repo, {"app.py": "x = 1\n", "generated.out": "noise\n"},
                date_epoch=NOW.timestamp() - 8 * DAY)
        records = [_record("2026-11-12T11:45:00Z", "ses-1", str(repo))]
        with mock.patch.dict(os.environ, {
                "TOKENS_OUTCOME_EXCLUDE": "generated.out",
                "TOKENS_OUTCOME_EMAILS": "teammate@example.com"}):
            block = self.build(records, since="2026-11-10", until="2026-11-20")
        self.assertEqual(1, block["totals"]["added"])
        self.assertEqual(1, block["totals"]["files"])

    def test_cli_json_report_end_to_end(self):
        repo = _init_repo(self.root / "proj")
        _commit(repo, {"app.py": "x = 1\n"}, date_epoch=NOW.timestamp() - 8 * DAY)
        records = [_record("2026-11-12T11:45:00Z", "ses-1", str(repo))]
        stdout = io.StringIO()
        with mock.patch("tokens_cli.cli.readers.read_all", return_value=records), \
                mock.patch("sys.stdout", stdout):
            status = cli.main(["outcomes", "--json", "--source", "claude",
                               "--since", "2026-11-10", "--until", "2026-11-20"])
        self.assertEqual(0, status)
        block = json.loads(stdout.getvalue())
        self.assertEqual(1, block["totals"]["commits"])
        self.assertEqual(1, block["totals"]["surviving"])
        self.assertEqual("ok", block["status"])

    def test_days_sum_matches_totals_invariant(self):
        repo = _init_repo(self.root / "proj")
        cwd = str(repo)
        _commit(repo, {"a.py": "one = 1\n"}, date_epoch=NOW.timestamp() - 9 * DAY)
        _commit(repo, {"b.py": "two = 2\n"}, date_epoch=NOW.timestamp() - 5 * DAY)
        _commit(repo, {"c.py": "three = 3\n"}, date_epoch=NOW.timestamp() - 1 * DAY)
        records = [
            _record("2026-11-11T11:45:00Z", "ses-1", cwd),
            _record("2026-11-15T11:45:00Z", "ses-2", cwd),
            _record("2026-11-19T11:45:00Z", "ses-3", cwd),
        ]
        block = self.build(records, since="2026-11-10", until="2026-11-20")
        self.assertEqual(3, block["totals"]["commits"])
        self.assertEqual(block["totals"]["commits"],
                         sum(row["commits"] for row in block["days"]))
        self.assertEqual(block["totals"]["added"],
                         sum(row["added"] for row in block["days"]))
        self.assertEqual(block["totals"]["deleted"],
                         sum(row["deleted"] for row in block["days"]))

    def test_no_sessions_returns_empty_clean_block(self):
        block = self.build([], since="2026-11-10", until="2026-11-20")
        self.assertEqual("ok", block["status"])
        self.assertEqual({}, block["reasons"])
        self.assertEqual(0, block["totals"]["sessions"])

    # ---- terminal number formatting -----------------------------------------

    def test_fmt_ratio_one_decimal_with_thousands(self):
        self.assertEqual("0.0", outcomes._fmt_ratio(0))
        self.assertEqual("3.7", outcomes._fmt_ratio(3.711745))
        self.assertEqual("155.1", outcomes._fmt_ratio(155.094598))
        self.assertEqual("1,234.5", outcomes._fmt_ratio(1234.5))
        self.assertEqual("1,234,567.9", outcomes._fmt_ratio(1234567.89))

    def test_print_report_formats_settled_ratios_and_keeps_payload_raw(self):
        repo = _init_repo(self.root / "proj")
        _commit(repo, {"app.py": "x = 1\n" * 5}, date_epoch=NOW.timestamp() - 8 * DAY)
        records = [_record("2026-11-12T11:45:00Z", "ses-1", str(repo))]
        block = self.build(records, since="2026-11-10", until="2026-11-20")
        # The payload keeps the full 6-decimal ratio; only the terminal
        # formats it down to one decimal with thousands separators.
        expected = round(block["totals"]["surviving"] / block["totals"]["cost"], 6)
        self.assertEqual(expected, block["totals"]["retained_per_dollar"])
        out = io.StringIO()
        with mock.patch("sys.stdout", out):
            outcomes.print_report(block, lang="en")
        text = out.getvalue()
        self.assertIn(f"Retained lines per $1: {outcomes._fmt_ratio(expected)}", text)
        self.assertNotIn("—", text)

    def test_print_report_all_pending_shows_dash_not_zero(self):
        repo = _init_repo(self.root / "proj")
        _commit(repo, {"app.py": "fresh = 1\n"}, date_epoch=NOW.timestamp() - 2 * DAY)
        records = [_record("2026-11-18T11:45:00Z", "ses-1", str(repo))]
        block = self.build(records, since="2026-11-10", until="2026-11-20")
        self.assertEqual(0, block["totals"]["settled_cost"])
        out = io.StringIO()
        with mock.patch("sys.stdout", out):
            outcomes.print_report(block, lang="en")
        text = out.getvalue()
        self.assertIn("Retained lines per $1: — (all lines under 7 days old)", text)
        self.assertIn("Retained lines per $1 (settled only): —", text)
        self.assertNotIn("per $1: 0.0", text)
        # The pending count line still reports how many lines are waiting.
        self.assertIn("1 added lines are under 7 days old; survival pending", text)

    def test_print_report_zh_dash_note_localized(self):
        repo = _init_repo(self.root / "proj")
        _commit(repo, {"app.py": "fresh = 1\n"}, date_epoch=NOW.timestamp() - 2 * DAY)
        records = [_record("2026-11-18T11:45:00Z", "ses-1", str(repo))]
        block = self.build(records, since="2026-11-10", until="2026-11-20")
        out = io.StringIO()
        with mock.patch("sys.stdout", out):
            outcomes.print_report(block, lang="zh")
        text = out.getvalue()
        self.assertIn("每 $1 留存行: —（所有新增行都不满 7 天，留存待定）", text)
        self.assertIn("每 $1 留存行（仅满 7 天）: —", text)

    def test_print_report_no_commits_keeps_zero_ratio(self):
        # No commits at all: 0.0 is truthful (nothing was produced), so the
        # dash note must not appear.
        records = [_record("2026-11-12T11:45:00Z", "ses-1", str(self.root))]
        block = self.build(records, since="2026-11-10", until="2026-11-20")
        self.assertEqual(0, block["totals"]["commits"])
        out = io.StringIO()
        with mock.patch("sys.stdout", out):
            outcomes.print_report(block, lang="en")
        text = out.getvalue()
        self.assertIn("Retained lines per $1: 0.0", text)
        self.assertNotIn("(all lines under 7 days old)", text)

    def test_cli_json_payload_ratios_stay_unformatted(self):
        repo = _init_repo(self.root / "proj")
        _commit(repo, {"app.py": "x = 1\n"}, date_epoch=NOW.timestamp() - 8 * DAY)
        records = [_record("2026-11-12T11:45:00Z", "ses-1", str(repo))]
        stdout = io.StringIO()
        with mock.patch("tokens_cli.cli.readers.read_all", return_value=records), \
                mock.patch("sys.stdout", stdout):
            status = cli.main(["outcomes", "--json", "--source", "claude",
                               "--since", "2026-11-10", "--until", "2026-11-20"])
        self.assertEqual(0, status)
        raw = stdout.getvalue()
        block = json.loads(raw)
        ratio = block["totals"]["retained_per_dollar"]
        self.assertIsInstance(ratio, float)
        self.assertEqual(round(block["totals"]["surviving"] / block["totals"]["cost"], 6), ratio)
        self.assertNotIn("—", raw)  # terminal dashes never leak into the JSON

    # ---- value by model / tool (#39) ----------------------------------------

    def test_schema_two_adds_sources_without_changing_old_fields(self):
        block = self.build([], since="2026-11-10", until="2026-11-20")
        self.assertEqual(2, outcomes.OUTCOMES_SCHEMA)
        self.assertEqual(2, block["schema"])
        self.assertIn("sources", block)
        for key in ("range", "status", "reasons", "totals", "days", "projects",
                    "models", "no_commit_sessions", "no_repo_sessions"):
            self.assertIn(key, block)

    def test_two_models_in_one_session_split_cost_and_output_by_spend(self):
        repo = _init_repo(self.root / "proj")
        _commit(repo, {"app.py": "a = 1\nb = 2\n"},
                date_epoch=NOW.timestamp() - 8 * DAY)
        cwd = str(repo)
        first, second = "claude-sonnet-5.5", "gpt-5.6-sol"
        records = [
            _record("2026-11-12T10:00:00Z", "ses-1", cwd, model=first,
                    total=1500, parts=(1000, 500, 0, 0, 0)),
            _record("2026-11-12T11:45:00Z", "ses-1", cwd, model=second,
                    total=3000, parts=(2000, 1000, 0, 0, 0)),
        ]
        block = self.build(records, since="2026-11-10", until="2026-11-20")
        rows = {row["model"]: row for row in block["models"]}
        rates = outcomes._reference_rates()

        def priced(model, parts):
            return sum(part * rate for part, rate in zip(parts, rates[model])
                       if rate is not None) / 1_000_000

        cost_first = priced(first, (1000, 500, 0, 0, 0))
        cost_second = priced(second, (2000, 1000, 0, 0, 0))
        share = float(cost_first / (cost_first + cost_second))
        self.assertAlmostEqual(float(cost_first), rows[first]["cost"], places=2)
        self.assertAlmostEqual(float(cost_second), rows[second]["cost"], places=2)
        self.assertAlmostEqual(block["totals"]["cost"],
                               float(cost_first + cost_second), places=2)
        # Cost is exact; commits/lines follow the spend share, never the
        # "primary model takes everything" shortcut.
        self.assertAlmostEqual(share, rows[first]["commits"], places=3)
        self.assertAlmostEqual(1 - share, rows[second]["commits"], places=3)
        self.assertAlmostEqual(2 * share, rows[first]["added"], places=3)
        self.assertAlmostEqual(2 * (1 - share), rows[second]["added"], places=3)
        self.assertAlmostEqual(2 * share, rows[first]["surviving"], places=3)
        self.assertEqual(1, rows[first]["sessions"])
        self.assertEqual(1, rows[second]["sessions"])
        self.assertTrue(rows[first]["low_sample"])  # one session only
        # Tool rows use the same allocation; a session can appear in both.
        tools = {row["source"]: row for row in block["sources"]}
        self.assertEqual({"claude"}, set(tools))
        self.assertAlmostEqual(1.0, tools["claude"]["commits"], places=3)

    def test_low_sample_rows_are_marked_and_placed_outside_the_ranking(self):
        repo = _init_repo(self.root / "proj")
        cwd = str(repo)
        big = (1_000_000, 1_000_000, 0, 0, 0)
        teen = (100, 100, 0, 0, 0)
        records = []
        for index in range(3):
            day = 10 + index
            # One settled commit per session (9, 8 and 7 days old) so the
            # three-session row has real settled spend and kept lines.
            _commit(repo, {f"day{day}.py": f"line = {day}\n"},
                    date_epoch=datetime(2026, 11, day, 12,
                                        tzinfo=timezone.utc).timestamp())
            records.append(_record(f"2026-11-{day}T11:45:00Z",
                                   f"ses-adult-{index}", cwd,
                                   model="claude-sonnet-5.5", total=2_000_000,
                                   parts=big))
        records.append(_record("2026-11-12T15:00:00Z", "ses-teen", cwd,
                               model="deepseek-v4-pro", total=200, parts=teen))
        block = self.build(records, since="2026-11-10", until="2026-11-20")
        rows = {row["model"]: row for row in block["models"]}
        self.assertFalse(rows["claude-sonnet-5.5"]["low_sample"])
        self.assertTrue(rows["deepseek-v4-pro"]["low_sample"])
        labels = [row["model"] for row in block["models"]]
        self.assertLess(labels.index("claude-sonnet-5.5"),
                        labels.index("deepseek-v4-pro"))

    def test_all_pending_value_row_reports_dash_and_no_ratio(self):
        repo = _init_repo(self.root / "proj")
        _commit(repo, {"app.py": "fresh = 1\n"},
                date_epoch=NOW.timestamp() - 2 * DAY)
        records = [_record("2026-11-18T11:45:00Z", "ses-1", str(repo))]
        block = self.build(records, since="2026-11-10", until="2026-11-20")
        row = block["models"][0]
        self.assertEqual(0, row["settled_cost"])
        self.assertEqual(0, row["surviving"])
        self.assertEqual(row["pending_added"], row["added"])
        self.assertEqual(0.0, row["retained_per_dollar"])
        self.assertTrue(row["low_sample"])
        out = io.StringIO()
        with mock.patch("sys.stdout", out):
            outcomes.print_report(block, lang="zh")
        table = out.getvalue().split("按模型", 1)[1]
        self.assertIn("—", table)
        self.assertIn("样本少", out.getvalue())

    def test_deleted_opencode_worktree_recovers_its_project(self):
        repo = _init_repo(self.root / "main")
        _commit(repo, {"app.py": "base = 1\n"},
                date_epoch=NOW.timestamp() - 8 * DAY)
        missing = self.root / "worktree" / "gone"
        db = self.root / "opencode.db"
        con = sqlite3.connect(db)
        try:
            con.executescript("""
                CREATE TABLE project (id TEXT PRIMARY KEY, worktree TEXT NOT NULL);
                CREATE TABLE worktree (project_id TEXT NOT NULL, directory TEXT NOT NULL,
                                       strategy TEXT, time_created INTEGER NOT NULL);
                CREATE TABLE session_v2 (id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
                                         directory TEXT NOT NULL);
            """)
            con.execute("INSERT INTO project VALUES ('p1', ?)", (str(repo),))
            con.execute("INSERT INTO worktree VALUES ('p1', ?, 'git', 1)",
                        (str(missing),))
            con.execute("INSERT INTO session_v2 VALUES ('ses-gone', 'p1', ?)",
                        (str(missing),))
            con.commit()
        finally:
            con.close()
        records = [_record("2026-11-12T11:45:00Z", "ses-gone", str(missing))]
        with mock.patch.object(config, "OPENCODE_DB", str(db)), \
                mock.patch.object(outcomes, "_REPO_CACHE", {}), \
                mock.patch.object(outcomes, "_OPENCODE_REPO_CACHE", {}):
            block = self.build(records, since="2026-11-10", until="2026-11-20")
        self.assertEqual(0, block["reasons"].get("no_repo", 0))
        self.assertEqual(1, block["totals"]["commits"])
        self.assertEqual(os.path.realpath(str(repo)),
                         block["projects"][0]["project"])

    def test_missing_cwd_opencode_session_uses_project_mapping(self):
        repo = _init_repo(self.root / "main")
        _commit(repo, {"app.py": "base = 1\n"},
                date_epoch=NOW.timestamp() - 8 * DAY)
        db = self.root / "opencode.db"
        con = sqlite3.connect(db)
        try:
            con.executescript("""
                CREATE TABLE project (id TEXT PRIMARY KEY, worktree TEXT NOT NULL);
                CREATE TABLE session_v2 (id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
                                         directory TEXT NOT NULL);
            """)
            con.execute("INSERT INTO project VALUES ('p1', ?)", (str(repo),))
            con.execute("INSERT INTO session_v2 VALUES ('ses-gone', 'p1', ?)",
                        (str(self.root / "gone"),))
            con.commit()
        finally:
            con.close()
        record = _record("2026-11-12T11:45:00Z", "ses-gone", None)
        with mock.patch.object(config, "OPENCODE_DB", str(db)), \
                mock.patch.object(outcomes, "_REPO_CACHE", {}), \
                mock.patch.object(outcomes, "_OPENCODE_REPO_CACHE", {}):
            block = self.build([record], since="2026-11-10",
                               until="2026-11-20")
        self.assertEqual(1, block["totals"]["commits"])
        self.assertEqual(os.path.realpath(str(repo)),
                         block["projects"][0]["project"])


if __name__ == "__main__":
    unittest.main()
