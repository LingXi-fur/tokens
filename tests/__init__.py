"""Test process guard: never write the user's real token cache.

Tests that exercise the CLI or reader cache still get a process-local temporary
directory, so a forgotten patch cannot overwrite the developer's cache.
"""
import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from tokens_cli import config  # noqa: E402

_CACHE_DIR = tempfile.mkdtemp(prefix="tokens-tests-cache-")
config.CACHE_DIR = _CACHE_DIR
config.CACHE_FILE = os.path.join(_CACHE_DIR, "records-v8.json")
atexit.register(shutil.rmtree, _CACHE_DIR, ignore_errors=True)
