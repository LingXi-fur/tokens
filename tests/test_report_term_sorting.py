import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from tokens_cli import report_term


def _summary(*models):
    return {
        "total": sum(value for _, value in models),
        "calls": len(models),
        "by_model": list(models),
    }


class ReportTermModelSortingTests(unittest.TestCase):
    def test_top_columns_follow_user_token_totals_not_vendor_priority(self):
        rows = [
            (
                "2026-09-01",
                _summary(
                    ("glm-5.2", 1),
                    ("model-c", 80),
                    ("model-a", 120),
                ),
            ),
            (
                "2026-09-02",
                _summary(
                    ("model-b", 110),
                    ("model-c", 50),
                    ("deepseek-v4-pro", 2),
                ),
            ),
        ]
        self.assertEqual(
            ["model-c", "model-a", "model-b"],
            report_term._top_model_columns(rows),
        )

    def test_equal_totals_use_model_name_as_stable_tie_break(self):
        rows = [
            (
                "2026-09-01",
                _summary(
                    ("model-c", 100),
                    ("model-a", 100),
                    ("model-b", 100),
                    ("model-d", 90),
                ),
            ),
        ]
        self.assertEqual(
            ["model-a", "model-b", "model-c"],
            report_term._top_model_columns(rows),
        )

    def test_input_period_and_model_order_do_not_change_columns(self):
        forward = [
            ("2026-09-01", _summary(("model-c", 30), ("model-a", 60))),
            ("2026-09-02", _summary(("model-b", 60), ("model-c", 30))),
        ]
        reversed_input = [
            ("2026-09-02", _summary(("model-c", 30), ("model-b", 60))),
            ("2026-09-01", _summary(("model-a", 60), ("model-c", 30))),
        ]
        expected = ["model-a", "model-b", "model-c"]
        self.assertEqual(expected, report_term._top_model_columns(forward))
        self.assertEqual(expected, report_term._top_model_columns(reversed_input))


if __name__ == "__main__":
    unittest.main()
