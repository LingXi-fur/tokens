import hashlib
import importlib.util
import json
import os
import re
import stat
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_docs_demo.py"
SRC = ROOT / "src"

import sys
sys.path.insert(0, str(SRC))

from tokens_cli import config, dashboard_wire, report_dashboard


def _load_builder():
    spec = importlib.util.spec_from_file_location("build_docs_demo", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DocsDemoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.builder = _load_builder()

    def test_builder_is_deterministic_private_and_uses_no_readers(self):
        original_timezone = config.TZ
        with tempfile.TemporaryDirectory() as tmp:
            sandbox = Path(tmp)
            home = sandbox / "private-home"
            docs = sandbox / "docs"
            home.mkdir()
            first = docs / "first.html"
            second = docs / "nested" / "second.html"
            patches = (
                mock.patch("tokens_cli.readers.read_all"),
                mock.patch("tokens_cli.readers.load_session_summaries"),
                mock.patch("tokens_cli.readers.build_session_index"),
                mock.patch("tokens_cli.readers.session_title"),
            )
            with mock.patch.dict(
                os.environ,
                {"HOME": str(home), "USERPROFILE": str(home)},
                clear=False,
            ), patches[0] as read_all, patches[1] as summaries, \
                    patches[2] as index, patches[3] as title:
                self.builder.build_docs_demo(first, docs)
                with mock.patch.object(config, "TZ", ZoneInfo("Asia/Shanghai")):
                    # The builder must pin its own timezone, so a host in a
                    # different zone still publishes the same bytes.
                    self.builder.build_docs_demo(second, docs)
            for reader in (read_all, summaries, index, title):
                reader.assert_not_called()
            first_bytes = first.read_bytes()
            second_bytes = second.read_bytes()

        self.assertIs(config.TZ, original_timezone)
        self.assertEqual(
            hashlib.sha256(first_bytes).digest(),
            hashlib.sha256(second_bytes).digest(),
        )
        html = first_bytes.decode("utf-8")
        for marker in (
            "<html lang=en>",
            "const IS_DEMO = true",
            "Synthetic Demo",
            "Star or clone on GitHub",
            "https://github.com/LingXi-fur/tokens",
            "const LIVE = {\"enabled\": false, \"interval\": 0}",
            "/synthetic/",
            "demo-session-",
        ):
            self.assertIn(marker, html)
        for forbidden in (
            str(Path.home()),
            str(home),
            "/Users/",
            ".claude/projects",
            ".gemini/tmp",
            ".codex/sessions",
        ):
            self.assertNotIn(forbidden, html)
        self.assertIsNone(re.search(
            r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-"
            r"[89ab][0-9a-f]{3}-[0-9a-f]{12}\b",
            html,
            re.IGNORECASE,
        ))
        self.assertIsNone(re.search(
            r"\b(?:session|conversation|thread)[_-]?(?:id[_-]?)?"
            r"[0-9a-f]{16,}\b",
            html,
            re.IGNORECASE,
        ))

    def test_docs_demo_publishes_folded_other_detail(self):
        with tempfile.TemporaryDirectory() as tmp:
            docs = Path(tmp) / "docs"
            html = self.builder.build_docs_demo("demo/index.html", docs).read_text(
                encoding="utf-8"
            )

        match = re.search(r"^const WIRE = (.*);$", html, re.MULTILINE)
        self.assertIsNotNone(match)
        payload = dashboard_wire.decode_payload(json.loads(match.group(1)))
        self.assertFalse(payload["anonymized"])
        self.assertIn("other", payload["models"])
        self.assertEqual("Other", payload["pretty"]["other"])
        self.assertTrue(payload["other_models"])
        folded = {
            name for row in payload["other_models"] for name in row["models"]
        }
        self.assertTrue(folded)
        self.assertTrue(folded.isdisjoint(payload["models"]))
        days = {row["period"]: row for row in payload["day"]}
        for row in payload["other_models"]:
            with self.subTest(day=row["day"]):
                self.assertIn(row["day"], days)
                self.assertGreater(sum(row["models"].values()), 0)
                self.assertEqual(
                    sum(row["models"].values()),
                    days[row["day"]]["models"].get("other", 0),
                )

    def test_builder_confines_output_and_publishes_readable_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            sandbox = Path(tmp)
            docs = sandbox / "docs"
            target = self.builder.build_docs_demo("demo/index.html", docs)
            self.assertEqual((docs / "demo" / "index.html").resolve(), target)
            if os.name != "nt":
                self.assertEqual(0o644, stat.S_IMODE(target.stat().st_mode))
            for output in (docs, docs.parent / "escape.html", Path("../escape.html")):
                with self.subTest(output=output), self.assertRaisesRegex(
                    ValueError,
                    "inside the docs root",
                ):
                    self.builder.build_docs_demo(output, docs)

    def test_generated_page_has_no_remote_runtime_resources(self):
        with tempfile.TemporaryDirectory() as tmp:
            docs = Path(tmp)
            target = self.builder.build_docs_demo("demo/index.html", docs)
            html = target.read_text(encoding="utf-8")
        remote_resources = re.findall(
            r"<(?:script|img|link)\b[^>]*(?:src|href)=[\"']"
            r"https?://[^\"']+",
            html,
            re.IGNORECASE,
        )
        self.assertEqual([], remote_resources)
        for automatic_api in ("navigator.sendBeacon", "new WebSocket(", "EventSource("):
            self.assertNotIn(automatic_api, html)

    def test_builder_publishes_share_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            docs = Path(tmp)
            target = self.builder.build_docs_demo("demo/index.html", docs)
            html = target.read_text(encoding="utf-8")

        expected = (
            '<meta name="description"',
            '<meta property="og:type" content="website">',
            '<meta property="og:site_name" content="tokens">',
            '<meta property="og:title"',
            '<meta property="og:description"',
            f'<meta property="og:url" content="{self.builder.DEMO_URL}">',
            f'<meta property="og:image" content="{self.builder.DEMO_IMAGE_URL}">',
            '<meta property="og:image:width" content="1440">',
            '<meta property="og:image:height" content="920">',
            '<meta name="twitter:card" content="summary_large_image">',
            '<meta name="twitter:title"',
            '<meta name="twitter:description"',
            f'<meta name="twitter:image" content="{self.builder.DEMO_IMAGE_URL}">',
        )
        for marker in expected:
            self.assertIn(marker, html)
        for tag in ("<link", "<img", "<script"):
            self.assertNotIn(tag, self.builder.DEMO_META.lower())
        self.assertTrue((ROOT / "docs" / "assets" / "readme-preview.png").is_file())

    def test_local_dashboards_stay_free_of_public_metadata(self):
        wire = {"v": 1, "s": [], "d": {}}
        local_render = report_dashboard.render_dashboard(wire)
        local_build = report_dashboard.build_dashboard_html(
            [],
            generated_at=datetime(2026, 9, 24, tzinfo=timezone.utc),
            session_titles={},
        )
        for html in (local_render, local_build):
            self.assertNotIn("__HEAD_META__", html)
            self.assertNotIn("lingxi-fur.github.io", html)
            self.assertNotIn('property="og:', html)


if __name__ == "__main__":
    unittest.main()
