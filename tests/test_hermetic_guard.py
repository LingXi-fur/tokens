"""Meta-test: every test module must install the process cache guard."""
from tests import _hermetic  # noqa: F401
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class HermeticGuardTests(unittest.TestCase):
    def test_every_test_module_imports_the_cache_guard(self):
        missing = []
        for path in sorted((ROOT / "tests").glob("test_*.py")):
            text = path.read_text(encoding="utf-8")
            if "from tests import _hermetic" not in text:
                missing.append(path.name)
        self.assertEqual([], missing, "test modules missing _hermetic import")


if __name__ == "__main__":
    unittest.main()
