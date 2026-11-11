import io
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from tokens_cli import aggregate, readers, report_term


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

    def test_opencode_records_render_without_source_specific_labels(self):
        # OpenCode totals include reasoning in output while billing keeps it
        # separate; the terminal report only consumes normalized records.
        billing = readers._opencode_billing({
            "input": 10, "output": 15, "reasoning": 5,
            "cache_read": 3, "cache_write": 2,
        })
        record = {
            "source": "opencode", "date": "2026-11-10",
            "model": "deepseek-v4.1-flash",
            "input": 10, "output": 20, "cache_read": 3, "cache_write": 2,
            "total": 35, "session": "synthetic-session",
            "cwd": "/synthetic/private-project", "billing": billing,
        }
        rows = [("2026-11-10", aggregate.summarize([record]))]
        stdout = io.StringIO()
        with mock.patch("sys.stdout", stdout):
            report_term.print_report("day", rows, "2026-11-10", "Today", lang="en")
        text = stdout.getvalue()
        self.assertIn("deepseek-v4.1-flash", text)
        self.assertIn("Total tokens", text)
        self.assertIn("1 calls", text)
        self.assertNotIn("/synthetic/private-project", text)
        self.assertNotIn("synthetic-session", text)


if __name__ == "__main__":
    unittest.main()
