"""Synthetic atb joins; no test reads a real taskboard or session store."""
from tests import _hermetic  # noqa: F401
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tokens_cli import config, outcomes, tasks

NOW = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)


def record(session, ts, total=1000, parts=(600, 400, 0, 0, 0),
           source="claude", cwd="/synthetic/repo", model="claude-sonnet-5.5"):
    return {
        "source": source, "ts": ts, "date": ts[:10], "model": model,
        "input": parts[0], "output": parts[1], "cache_read": parts[2],
        "cache_write": parts[3], "total": total, "session": session,
        "cwd": cwd,
    }


def segment(adapter, sid, start, end, *, last=None, usage=None,
            basis="worktree"):
    return {
        "adapter": adapter, "id": sid, "from": start, "to": end,
        "last_active_at": last or end, "basis": basis,
        "usage": usage if usage is not None else {
            "input": 600, "output": 400, "total": 1000},
    }


def task(tid, agent, sessions, *, merged=True, rework=0, title="Synthetic task",
         status="done"):
    return {
        "id": tid, "title": title, "agent": agent, "status": status,
        "merged": merged, "rework_count": rework, "sessions": sessions,
    }


def export(tasks_list, schema=1, repo="/synthetic/repo"):
    return {"schema": schema, "generated": NOW.isoformat(), "repo": repo,
            "target": "main", "tasks": tasks_list}


class TasksTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.cache = self.root / "cache"
        self.repo = self.root / "repo"
        (self.repo / ".taskboard").mkdir(parents=True)
        patches = (
            mock.patch.object(config, "CACHE_DIR", str(self.cache)),
            mock.patch.object(config, "TZ", timezone.utc),
            mock.patch.object(tasks, "_RUNNING", set()),
        )
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.env = mock.patch.dict(os.environ, {
            "TOKENS_ATB_REPOS": str(self.repo),
        }, clear=False)
        self.env.start()
        self.addCleanup(self.env.stop)

    def fake_command(self, payload, *, sleep=0, code=0):
        previous = os.environ.get("TOKENS_ATB_CMD")
        self.addCleanup(lambda: os.environ.__setitem__("TOKENS_ATB_CMD", previous)
                        if previous is not None
                        else os.environ.pop("TOKENS_ATB_CMD", None))
        try:
            (self.cache / "atb-tasks-v1.json").unlink()
        except OSError:
            pass
        script = self.root / "fake_atb.py"
        script.write_text(
            "import json,sys,time\n"
            f"time.sleep({sleep!r})\n"
            f"print({json.dumps(json.dumps(payload))})\n"
            f"sys.exit({code})\n",
            encoding="utf-8",
        )
        os.environ["TOKENS_ATB_CMD"] = f'{sys.executable} "{script}"'

    def build(self, records, **kwargs):
        return tasks.build_tasks(
            records=records, repos=[self.repo],
            rates_table=outcomes._reference_rates(), now=kwargs.pop("now", NOW),
            **kwargs)

    def test_adapter_mapping_and_agent_rows(self):
        self.fake_command(export([
            task("T1", "opencode", [
                segment("opencode", "ses_1", "2026-11-19T10:00:00Z",
                        "2026-11-19T10:10:00Z")]),
            task("T2", "claude-window", [
                segment("claude-code", "claude-1", "2026-11-19T11:00:00Z",
                        "2026-11-19T11:10:00Z")]),
            task("T3", "codex-window", [
                segment("codex", "codex-1", "2026-11-19T12:00:00Z",
                        "2026-11-19T12:10:00Z")]),
        ]))
        records = [
            record("ses_1", "2026-11-19T10:05:00Z", source="opencode",
                   model="deepseek-v4-pro"),
            record("claude-1", "2026-11-19T11:05:00Z"),
            dict(record("ignored", "2026-11-19T12:05:00Z", source="codex",
                        model="gpt-5.6-sol"), native_session="codex-1"),
        ]
        block, reasons = self.build(records)
        self.assertTrue(block["available"])
        self.assertEqual(0, block["evidence"]["time_window"])
        rows = {row["agent"]: row for row in block["agents"]}
        self.assertEqual({"opencode", "claude-window", "codex-window"},
                         set(rows))
        self.assertEqual([], list(reasons))
        self.assertTrue(all(task["matched_segments"] == 1
                            for task in block["tasks"]))

    def test_segments_are_half_open_and_final_segment_includes_to(self):
        self.fake_command(export([
            task("T1", "w", [
                segment("claude-code", "s", "2026-11-19T10:00:00Z",
                        "2026-11-19T10:30:00Z", last="2026-11-19T11:00:00Z",
                        usage={"input": 0, "output": 1, "total": 1})]),
            task("T2", "w", [
                segment("claude-code", "s", "2026-11-19T10:30:00Z",
                        "2026-11-19T11:00:00Z",
                        usage={"input": 30, "output": 20, "total": 50})]),
        ]))
        records = [
            record("s", "2026-11-19T10:00:00Z", total=10,
                   parts=(6, 4, 0, 0, 0)),
            record("s", "2026-11-19T10:30:00Z", total=20,
                   parts=(12, 8, 0, 0, 0)),
            record("s", "2026-11-19T11:00:00Z", total=30,
                   parts=(18, 12, 0, 0, 0)),
        ]
        block, reasons = self.build(records)
        rows = {row["id"]: row for row in block["tasks"]}
        self.assertEqual(10, rows["T1"]["tokens"])
        self.assertEqual(50, rows["T2"]["tokens"], "boundary goes to the next segment; final includes to")
        self.assertEqual(1, reasons["atb_usage_mismatch"])

    def test_missing_schema_and_failure_reasons(self):
        self.fake_command(export([], schema=2))
        block, reasons = self.build([])
        self.assertIsNone(block)
        self.assertEqual(1, reasons["atb_schema"])
        self.fake_command({}, code=3)
        block, reasons = self.build([])
        self.assertIsNone(block)
        self.assertEqual(1, reasons["atb_failed"])
        try:
            (self.cache / "atb-tasks-v1.json").unlink()
        except OSError:
            pass
        with mock.patch.object(tasks, "_command", return_value=None):
            block, reasons = self.build([])
        self.assertIsNone(block)
        self.assertEqual(1, reasons["atb_missing"])

    def test_timeout_is_a_failure(self):
        self.fake_command(export([]), sleep=2)
        with mock.patch.object(tasks, "ATB_TIMEOUT_SECONDS", 0.1):
            block, reasons = self.build([])
        self.assertIsNone(block)
        self.assertEqual(1, reasons["atb_failed"])

    def test_repo_without_taskboard_is_skipped_and_env_repo_is_called(self):
        (self.repo / ".taskboard").rmdir()
        self.fake_command(export([]))
        block, reasons = self.build([])
        self.assertIsNone(block)
        self.assertFalse(reasons)
        (self.repo / ".taskboard").mkdir()
        extra = self.root / "extra"
        (extra / ".taskboard").mkdir(parents=True)
        os.environ["TOKENS_ATB_REPOS"] = str(extra)
        block, reasons = self.build([], background=False)
        self.assertTrue(block["available"])

    def test_anonymized_titles_are_removed(self):
        self.fake_command(export([task("T1", "a", [
            segment("claude-code", "s", "2026-11-19T10:00:00Z",
                    "2026-11-19T10:10:00Z")], title="Secret title")]))
        records = [record("s", "2026-11-19T10:05:00Z")]
        plain, _ = self.build(records)
        secret, _ = self.build(records, anonymize=True)
        self.assertEqual("Secret title", plain["tasks"][0]["title"])
        self.assertNotIn("title", secret["tasks"][0])
        self.assertNotIn("Secret title", json.dumps(secret))

    def test_outcomes_integration_carries_block_schema_and_reasons(self):
        self.fake_command(export([task("T1", "a", [
            segment("claude-code", "s", "2026-11-19T10:00:00Z",
                    "2026-11-19T10:10:00Z",
                    usage={"input": 0, "output": 1, "total": 1})])]))
        records = [record("s", "2026-11-19T10:05:00Z", cwd=str(self.repo))]
        block = outcomes.build_outcomes(records, now=NOW)
        self.assertEqual(3, block["schema"])
        self.assertTrue(block["tasks"]["available"])
        self.assertEqual("T1", block["tasks"]["tasks"][0]["id"])
        self.assertGreaterEqual(block["reasons"].get("atb_usage_mismatch", 0), 1)

    def test_terminal_table_formats_agent_rows(self):
        import io
        from tokens_cli import outcomes
        block={"available": True, "agents": [{
            "agent": "opencode", "tasks": 5, "merged_tasks": 4,
            "avg_cost_merged": 8.5, "median_cost_merged": 2.1,
            "rework_rate": 0.2, "avg_tokens": 1234567.0, "avg_rework": 0.4,
            "unmatched_tasks": 1}]}
        out=io.StringIO()
        with mock.patch("sys.stdout", out):
            outcomes._print_task_table(block, outcomes._STATUS_TEXT["zh"])
        text=out.getvalue()
        self.assertIn("按 agent（来自 atb）", text)
        self.assertIn("opencode", text)
        self.assertIn("20.0%", text)
        self.assertIn("$8.50", text)

    def test_background_returns_loading_then_cached_result(self):
        self.fake_command(export([task("T1", "a", [
            segment("claude-code", "s", "2026-11-19T10:00:00Z",
                    "2026-11-19T10:10:00Z")])]), sleep=0.2)
        records = [record("s", "2026-11-19T10:05:00Z")]
        block, _ = self.build(records, background=True)
        self.assertFalse(block["available"])
        self.assertTrue(block["loading"])
        deadline = time.time() + 5
        while time.time() < deadline:
            block, _ = self.build(records, background=True)
            if block["available"]:
                break
            time.sleep(0.05)
        self.assertTrue(block["available"])
