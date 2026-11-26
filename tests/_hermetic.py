"""Process-wide cache isolation for the test suite.

Imported from ``tests/__init__.py`` and from every ``tests/test_*.py`` module,
so it runs both under package imports and under
``python -m unittest discover -s tests`` where modules are imported as
``test_*``. Repeated imports are harmless.
"""
import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from tokens_cli import config  # noqa: E402


def install():
    # Dates in fixtures are UTC-based.  Pin the process zone so the suite does
    # not depend on whether the host exposes a named local zone (Windows and
    # some macOS runners do not), which also keeps disk/memo reuse enabled.
    config.TZ = ZoneInfo("UTC")
    if getattr(config, "_TOKENS_TEST_CACHE_DIR", None):
        return
    cache_dir = tempfile.mkdtemp(prefix="tokens-tests-cache-")
    cache_name = os.path.basename(config.CACHE_FILE) or "records-v8.json"
    config.CACHE_DIR = cache_dir
    config.CACHE_FILE = os.path.join(cache_dir, cache_name)
    config._TOKENS_TEST_CACHE_DIR = cache_dir
    atexit.register(shutil.rmtree, cache_dir, ignore_errors=True)


install()
