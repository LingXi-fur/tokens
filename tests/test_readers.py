import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]

SRC = ROOT / "src"

import sys
sys.path.insert(0, str(SRC))

import tokens_cli
from tokens_cli import readers


class ReadersTests(unittest.TestCase):
    def test_session_title_uses_supplied_index_without_glob(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "session-a.jsonl"
            path.write_text(
                json.dumps({
                    "type": "user",
                    "message": {"content": "请优化这个性能热点\n第二行"},
                }) + "\n",
                encoding="utf-8",
            )
            with mock.patch("tokens_cli.readers.glob.glob") as glob_fn:
                title = tokens_cli.readers.session_title(
                    "session-a",
                    session_index={"session-a": str(path)},
                )
            glob_fn.assert_not_called()
            self.assertEqual("请优化这个性能热点", title)

    def test_build_session_index_maps_jsonl_stems_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "a" / "session-a.jsonl"
            second = root / "b" / "session-b.jsonl"
            first.parent.mkdir()
            second.parent.mkdir()
            first.write_text("", encoding="utf-8")
            second.write_text("", encoding="utf-8")
            with mock.patch.object(tokens_cli.readers.config, "CLAUDE_PROJECTS", tmp):
                index = tokens_cli.readers.build_session_index()
            self.assertEqual(str(first), index["session-a"])
            self.assertEqual(str(second), index["session-b"])

    def test_safe_to_parse_rejects_symlink_and_oversized_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "target.jsonl"
            target.write_text("{}\n", encoding="utf-8")
            link = root / "link.jsonl"
            link.symlink_to(target)
            self.assertFalse(tokens_cli.readers._safe_to_parse(str(link), os.stat(link)))
            fake = mock.Mock(st_mode=stat.S_IFREG, st_size=tokens_cli.readers.MAX_FILE_BYTES + 1)
            self.assertFalse(tokens_cli.readers._safe_to_parse(str(target), fake))

    def test_cache_writer_uses_private_compact_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache_file = Path(tmp) / "records-v3.json"
            with mock.patch.object(readers.config, "CACHE_DIR", tmp), \
                    mock.patch.object(readers.config, "CACHE_FILE", str(cache_file)):
                readers._save_cache({"claude::x": {"key": "1|2", "records": []}})
            text = cache_file.read_text(encoding="utf-8")
            self.assertNotIn(": ", text)
            self.assertNotIn(", ", text)
            self.assertEqual(readers.CACHE_VERSION, json.loads(text)["_v"])
            if os.name != "nt":
                self.assertEqual(0o600, stat.S_IMODE(cache_file.stat().st_mode))


if __name__ == "__main__":
    unittest.main()
