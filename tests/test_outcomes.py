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
        self.assertEqual(cwd, project["project"])
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
        _commit(repo, {"app.py": "base = 1\n"}, date_epoch=NOW.timestamp() - 15 * DAY)
        worktree = self.root / "wt"
        _git(repo, "worktree", "add", "-q", str(worktree))
        _git(worktree, "config", "user.email", EMAIL)
        _git(worktree, "config", "user.name", NAME)
        _commit(worktree, {"app.py": "base = 1\nextra = 2\n"},
                date_epoch=NOW.timestamp() - 8 * DAY)
        records = [_record("2026-11-12T11:45:00Z", "ses-1", str(worktree))]
        block = self.build(records, since="2026-11-10", until="2026-11-20")
        self.assertEqual(1, block["totals"]["commits"])
        self.assertEqual(1, block["totals"]["added"])

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

    def test_no_sessions_returns_empty_clean_block(self):
        block = self.build([], since="2026-11-10", until="2026-11-20")
        self.assertEqual("ok", block["status"])
        self.assertEqual({}, block["reasons"])
        self.assertEqual(0, block["totals"]["sessions"])


if __name__ == "__main__":
    unittest.main()
