import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tokens_cli import dashboard_payload


class DashboardModelColorTests(unittest.TestCase):
    def record(self, model, day, total, hour=0, suffix=None):
        suffix = suffix or model
        return {
            "source": "claude",
            "ts": f"{day}T{hour:02d}:00:00Z",
            "date": day,
            "model": model,
            "input": total,
            "output": 0,
            "cache_read": 0,
            "cache_write": 0,
            "total": total,
            "session": f"session-{suffix}",
            "cwd": f"/synthetic/project-{suffix}",
        }

    def payload(self, records, **kwargs):
        return dashboard_payload.build_payload(
            records,
            anonymize=True,
            **kwargs,
        )

    def test_palettes_are_independent_and_identity_stable_across_input_order(self):
        records = [
            self.record("model-a", "2026-07-01", 10),
            self.record("model-b", "2026-07-02", 20),
            self.record("model-c", "2026-07-03", 30),
        ]
        forward = self.payload(records)
        reverse = self.payload(list(reversed(records)))

        self.assertEqual(forward["colors"], reverse["colors"])
        self.assertEqual(set(forward["models"]), set(forward["colors"]["light"]))
        self.assertEqual(set(forward["models"]), set(forward["colors"]["dark"]))
        self.assertNotEqual(forward["colors"]["light"], forward["colors"]["dark"])
        for model in forward["models"]:
            self.assertNotEqual(
                forward["colors"]["light"][model],
                forward["colors"]["dark"][model],
            )

    def test_range_and_token_ranking_do_not_reassign_surviving_models(self):
        records = [
            self.record("model-a", "2026-07-01", 900, 1, "a-old"),
            self.record("model-b", "2026-07-01", 100, 2, "b-old"),
            self.record("model-a", "2026-07-02", 10, 1, "a-new"),
            self.record("model-b", "2026-07-02", 800, 2, "b-new"),
        ]
        first = self.payload(records, since="2026-07-01", until="2026-07-01")
        second = self.payload(records, since="2026-07-02", until="2026-07-02")

        self.assertEqual(["model-a", "model-b"], first["models"])
        self.assertEqual(["model-b", "model-a"], second["models"])
        for theme in ("light", "dark"):
            self.assertEqual(
                first["colors"][theme]["model-a"],
                second["colors"][theme]["model-a"],
            )
            self.assertEqual(
                first["colors"][theme]["model-b"],
                second["colors"][theme]["model-b"],
            )

    def test_appending_newer_model_does_not_change_existing_identity_colors(self):
        records = [
            self.record("model-a", "2026-07-01", 10),
            self.record("model-b", "2026-07-02", 20),
        ]
        before = self.payload(records)
        after = self.payload(records + [
            self.record("model-c", "2026-07-03", 999),
        ])

        self.assertEqual("model-c", after["models"][0])
        for theme in ("light", "dark"):
            for model in ("model-a", "model-b"):
                self.assertEqual(
                    before["colors"][theme][model],
                    after["colors"][theme][model],
                )

    def test_eighth_and_later_models_fold_into_other_before_all_aggregation(self):
        records = [
            self.record(f"model-{index}", f"2026-07-{index + 1:02d}", index + 1)
            for index in range(9)
        ]
        payload = self.payload(records)

        retained = {f"model-{index}" for index in range(7)}
        overflow = {"model-7", "model-8"}
        self.assertEqual(retained | {dashboard_payload.OTHER_MODEL}, set(payload["models"]))
        self.assertEqual(8, len(payload["models"]))
        self.assertEqual("Other", payload["pretty"][dashboard_payload.OTHER_MODEL])
        self.assertEqual(17, next(
            row["models"][dashboard_payload.OTHER_MODEL]
            for row in payload["month"]
        ))

        encoded = json.dumps(payload, sort_keys=True)
        for model in overflow:
            self.assertNotIn(f'"{model}"', encoded)

        for theme, palette in (
            ("light", dashboard_payload.LIGHT_PALETTE),
            ("dark", dashboard_payload.DARK_PALETTE),
        ):
            self.assertEqual(
                palette[dashboard_payload.MODEL_IDENTITY_CAPACITY],
                payload["colors"][theme][dashboard_payload.OTHER_MODEL],
            )
            self.assertEqual(len(payload["models"]), len(set(payload["colors"][theme].values())))

    def test_model_order_uses_current_range_totals_with_stable_name_tie_break(self):
        records = [
            self.record("model-c", "2026-07-01", 20),
            self.record("model-b", "2026-07-02", 20),
            self.record("model-a", "2026-07-03", 50),
        ]
        payload = self.payload(records)
        self.assertEqual(["model-a", "model-b", "model-c"], payload["models"])

    def test_registry_uses_earliest_valid_timestamp_then_name(self):
        records = [
            self.record("model-b", "2026-07-01", 1, 2),
            self.record("model-a", "2026-07-01", 1, 2),
            self.record("model-c", "2026-07-01", 1, 1),
        ]
        payload = self.payload(list(reversed(records)))
        light = payload["colors"]["light"]
        self.assertEqual(dashboard_payload.LIGHT_PALETTE[0], light["model-c"])
        self.assertEqual(dashboard_payload.LIGHT_PALETTE[1], light["model-a"])
        self.assertEqual(dashboard_payload.LIGHT_PALETTE[2], light["model-b"])


if __name__ == "__main__":
    unittest.main()
