import json
import random
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tokens_cli import dashboard_payload


class DashboardModelColorTests(unittest.TestCase):
    def record(self, model, day, total, hour=0, suffix=None, source="claude"):
        suffix = suffix or model
        return {
            "source": source,
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

    def test_ninth_and_later_models_fold_into_other_before_all_aggregation(self):
        records = [
            self.record(f"model-{index}", f"2026-07-{index + 1:02d}", index + 1)
            for index in range(10)
        ]
        payload = self.payload(records)

        # All-time usage decides the registry: the eight heaviest identities
        # stay first-class and only the two lightest fold into Other.
        retained = {f"model-{index}" for index in range(2, 10)}
        overflow = {"model-0", "model-1"}
        self.assertEqual(retained | {dashboard_payload.OTHER_MODEL}, set(payload["models"]))
        self.assertEqual(9, len(payload["models"]))
        self.assertEqual("Other", payload["pretty"][dashboard_payload.OTHER_MODEL])
        self.assertEqual(3, next(
            row["models"][dashboard_payload.OTHER_MODEL]
            for row in payload["month"]
        ))
        self.assertEqual("model-9", payload["range"]["latest_backend"])
        self.assertFalse(payload["range"]["latest_backend_folded"])

        encoded = json.dumps(payload, sort_keys=True)
        for model in overflow:
            self.assertNotIn(f'"{model}"', encoded)

        for theme, palette, other_color in (
            ("light", dashboard_payload.LIGHT_PALETTE, dashboard_payload.LIGHT_OTHER_COLOR),
            ("dark", dashboard_payload.DARK_PALETTE, dashboard_payload.DARK_OTHER_COLOR),
        ):
            self.assertEqual(
                other_color,
                payload["colors"][theme][dashboard_payload.OTHER_MODEL],
            )
            self.assertNotIn(other_color, palette)
            self.assertEqual(len(payload["models"]), len(set(payload["colors"][theme].values())))

    def test_recent_backend_keeps_one_seat_when_registry_overflows(self):
        records = [
            self.record(f"model-{index}", f"2026-07-{index + 1:02d}", 100 - index * 10)
            for index in range(8)
        ] + [
            self.record("gpt-5.6-sol", "2026-07-09", 5),
            self.record("gpt-6-sol", "2026-07-10", 3),
        ]
        payload = self.payload(records)
        reversed_payload = self.payload(list(reversed(records)))

        # The lightest-but-latest backend is rescued: it claims a seat and the
        # weakest survivor (model-7 = 30) folds into Other.
        self.assertIn("gpt-6-sol", payload["models"])
        self.assertNotIn("gpt-5.6-sol", payload["models"])
        self.assertNotIn("model-7", payload["models"])
        self.assertEqual(35, next(
            row["models"][dashboard_payload.OTHER_MODEL] for row in payload["month"]
        ))
        self.assertEqual(payload["colors"], reversed_payload["colors"])
        self.assertEqual("gpt-6-sol", payload["range"]["latest_backend"])
        self.assertFalse(payload["range"]["latest_backend_folded"])
        for theme in ("light", "dark"):
            self.assertEqual(
                getattr(dashboard_payload, theme.upper() + "_PALETTE")[7],
                payload["colors"][theme]["gpt-6-sol"],
            )

    def test_recent_backend_uses_report_day_even_when_timestamp_missing(self):
        records = [
            self.record(f"model-{index}", f"2026-07-{index + 1:02d}", 100 - index * 10)
            for index in range(8)
        ]
        previous = self.record("model-older", "2026-07-09", 20)
        recent = self.record("gpt-6-sol", "2026-07-10", 7)
        recent["ts"] = "invalid"
        payload = self.payload(records + [previous, recent])

        # Day ordering alone lets the untimed newest backend rescue a seat.
        self.assertIn("gpt-6-sol", payload["models"])
        self.assertNotIn("model-older", payload["models"])
        self.assertNotIn("model-7", payload["models"])
        self.assertEqual("gpt-6-sol", payload["range"]["latest_backend"])
        self.assertFalse(payload["range"]["latest_backend_folded"])

    def test_recent_backend_uses_timestamp_within_same_report_day(self):
        early = self.record("model-early", "2026-07-02", 1, 1)
        late = self.record("model-late", "2026-07-02", 1, 22)
        payload = self.payload([late, early])
        self.assertEqual("model-late", payload["range"]["latest_backend"])

    def test_glm_variants_keep_separate_seats_under_overflow(self):
        records = [self.record(f"major-{i}", "2026-10-14", 1000 - i) for i in range(8)] + [
            self.record("glm-5.3", "2026-10-15", 11),
            self.record("glm-5.3-flash", "2026-10-15", 13),
            self.record("glm-5.3", "2026-10-16", 17),
            self.record("glm-5.3-flash", "2026-10-16", 19),
            self.record("latest-backend", "2026-10-17", 1),
        ]
        payload = self.payload(records)
        self.assertEqual(9, len(payload["models"]))
        for name in ("glm-5.3", "glm-5.3-flash", "latest-backend"):
            self.assertIn(name, payload["models"])
        yesterday = next(row for row in payload["day"] if row["period"] == "2026-10-16")
        self.assertEqual({"glm-5.3": 17, "glm-5.3-flash": 19}, yesterday["models"])
        self.assertEqual(36, yesterday["total"])
        self.assertEqual(sum(r["total"] for r in records), sum(row["total"] for row in payload["day"]))
        reverse = self.payload(list(reversed(records)))
        self.assertEqual(payload["colors"], reverse["colors"])
        self.assertEqual(payload["day"], reverse["day"])
        for theme in ("light", "dark"):
            self.assertEqual(9, len(set(payload["colors"][theme].values())))

    def test_glm_seats_only_use_exact_recorded_names(self):
        payload = self.payload([self.record("glm-5.3-preview", "2026-10-16", 5)])
        self.assertEqual(["glm-5.3-preview"], payload["models"])
        self.assertNotIn("glm-5.3", payload["models"])
        self.assertNotIn("glm-5.3-flash", payload["models"])

    def test_historical_and_current_sol_stay_distinct_without_overflow(self):
        payload = self.payload([
            self.record("gpt-5.6-sol", "2026-07-01", 15),
            self.record("gpt-6-sol", "2026-07-02", 25),
        ])
        self.assertEqual({"gpt-5.6-sol", "gpt-6-sol"}, set(payload["models"]))
        self.assertEqual(15, payload["month"][0]["models"]["gpt-5.6-sol"])
        self.assertEqual(25, payload["month"][0]["models"]["gpt-6-sol"])

    def test_overflow_names_keep_daily_totals_only_in_non_anonymized_reports(self):
        records = [
            self.record(f"model-{index}", "2026-07-01", (index + 1) * 100, index)
            for index in range(8)
        ] + [
            self.record("model-7", "2026-07-03", 1),
            self.record("other", "2026-07-01", 3),
            self.record("unknown", "2026-07-01", 4, 21),
            self.record("overflow-name", "2026-07-01", 11, 20),
            self.record("overflow-name", "2026-07-02", 13),
            self.record("overflow-later", "2026-07-02", 17),
        ]
        forward = dashboard_payload.build_payload(records)
        reverse = dashboard_payload.build_payload(list(reversed(records)))
        self.assertEqual(forward["other_models"], reverse["other_models"])
        self.assertEqual(9, len(forward["models"]))
        self.assertNotIn("overflow-name", forward["models"])
        self.assertEqual([
            {"day": "2026-07-01", "models": {"overflow-name": 11, "unknown": 4}},
            {"day": "2026-07-02", "models": {"overflow-later": 17, "overflow-name": 13}},
        ], forward["other_models"])
        for row in forward["other_models"]:
            self.assertLessEqual(sum(row["models"].values()),
                                 next(day["models"].get("other", 0) for day in forward["day"]
                                      if day["period"] == row["day"]))
        limited = dashboard_payload.build_payload(records, since="2026-07-02")
        self.assertEqual([{"day": "2026-07-02", "models": {
            "overflow-later": 17, "overflow-name": 13,
        }}], limited["other_models"])
        self.assertEqual([], self.payload(records)["other_models"])
        self.assertNotIn('"overflow-name"', json.dumps(self.payload(records)))

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

    def test_eleven_models_keep_both_sol_variants_with_total_conservation(self):
        records = [
            self.record("gpt-6-sol", "2026-07-01", 900, 1, "gpt6"),
            self.record("gpt-6.1-sol", "2026-07-02", 800, 2, "gpt61"),
        ] + [
            self.record(
                f"model-{index}", f"2026-07-{index + 2:02d}", 10 + index, index, f"m{index}"
            )
            for index in range(9)
        ]
        payload = self.payload(records)

        # Eight retained identities plus the Other bucket.
        self.assertEqual(9, len(payload["models"]))
        # Both Sol generations survive on their own; neither is folded away.
        self.assertIn("gpt-6-sol", payload["models"])
        self.assertIn("gpt-6.1-sol", payload["models"])
        light = payload["colors"]["light"]
        self.assertEqual(9, len(set(light.values())))
        self.assertNotEqual(light["gpt-6-sol"], light["gpt-6.1-sol"])
        self.assertNotEqual(light["gpt-6.1-sol"], light[dashboard_payload.OTHER_MODEL])
        self.assertEqual(
            dashboard_payload.LIGHT_OTHER_COLOR,
            light[dashboard_payload.OTHER_MODEL],
        )
        # The three lightest identities fold into Other without losing a token.
        self.assertEqual(33, next(
            row["models"][dashboard_payload.OTHER_MODEL] for row in payload["month"]
        ))
        for row in payload["month"]:
            self.assertEqual(row["total"], sum(row["models"].values()))
        self.assertEqual(
            sum(record["total"] for record in records),
            sum(row["total"] for row in payload["month"]),
        )

    def test_overflow_names_are_gated_by_anonymization(self):
        records = [
            self.record(f"model-{index}", "2026-07-01", 10 + index, index)
            for index in range(10)
        ]
        public = dashboard_payload.build_payload(records)
        anonymized = self.payload(records)

        # Only the two lightest identities overflow (10 + 11 tokens).
        self.assertEqual(
            [{"day": "2026-07-01", "models": {"model-0": 10, "model-1": 11}}],
            public["other_models"],
        )
        self.assertEqual([], anonymized["other_models"])
        self.assertEqual(public["models"], anonymized["models"])
        self.assertNotIn("model-0", json.dumps(anonymized))
        self.assertNotIn("model-1", json.dumps(anonymized))

    def test_registry_survives_input_permutation_and_range_narrowing(self):
        records = [
            self.record("gpt-6-sol", "2026-07-01", 900, 1, "gpt6"),
            self.record("gpt-6.1-sol", "2026-07-02", 800, 2, "gpt61"),
        ] + [
            self.record(
                f"model-{index}", f"2026-07-{index + 2:02d}", 10 + index, index, f"m{index}"
            )
            for index in range(9)
        ]
        baseline = self.payload(records, since="2026-07-01", until="2026-07-31")
        shuffled = list(records)
        random.Random(7).shuffle(shuffled)
        permuted = self.payload(shuffled, since="2026-07-01", until="2026-07-31")
        self.assertEqual(baseline["colors"], permuted["colors"])
        self.assertEqual(baseline["models"], permuted["models"])

        # A narrower window must not reshuffle identities that survive it.
        narrowed = self.payload(records, since="2026-07-05", until="2026-07-31")
        self.assertLess(len(narrowed["models"]), len(baseline["models"]))
        for model in narrowed["models"]:
            self.assertEqual(
                baseline["colors"]["light"][model],
                narrowed["colors"]["light"][model],
            )

    def test_each_active_source_keeps_its_top_model_even_when_small(self):
        records = [
            # Heavy sources with multiple models competing for global top-7.
            self.record("claude-opus-4-1", "2026-07-01", 500_000, 1, source="claude"),
            self.record("claude-sonnet-4-5", "2026-07-01", 400_000, 2, source="claude"),
            self.record("claude-haiku-4-5", "2026-07-01", 300_000, 3, source="claude"),
            self.record("gpt-5-codex", "2026-07-02", 450_000, 1, source="codex"),
            self.record("gpt-5-mini", "2026-07-02", 250_000, 2, source="codex"),
            self.record("kimi-k2.6", "2026-07-03", 200_000, 1, source="opencode"),
            self.record("deepseek-v4.1", "2026-07-03", 180_000, 2, source="opencode"),
            # Small (~1%) sources whose top models would otherwise be folded into Other.
            self.record("gemini-2.5-pro", "2026-07-04", 20_000, 1, source="gemini"),
            self.record("gemini-2.5-flash", "2026-07-04", 5_000, 2, source="gemini"),
            self.record("gemini-4-hydrogen", "2026-07-05", 15_000, 1, source="antigravity"),
            self.record("gemini-4-argon", "2026-07-05", 4_000, 2, source="antigravity"),
        ]
        payload = dashboard_payload.build_payload(records)
        self.assertEqual(9, len(payload["models"]))
        for guaranteed in (
            "claude-opus-4-1",
            "gpt-5-codex",
            "kimi-k2.6",
            "gemini-2.5-pro",
            "gemini-4-hydrogen",
        ):
            self.assertIn(guaranteed, payload["models"])
            self.assertNotEqual(
                payload["colors"]["light"][guaranteed],
                payload["colors"]["light"][dashboard_payload.OTHER_MODEL],
            )
        # Filtering to a narrowed range keeps identical colors for surviving models.
        narrowed = dashboard_payload.build_payload(records, since="2026-07-03")
        for model in narrowed["models"]:
            self.assertEqual(
                payload["colors"]["dark"][model],
                narrowed["colors"]["dark"][model],
            )

    def test_more_than_capacity_sources_prioritizes_higher_total_sources(self):
        records = [
            self.record(f"model-src-{idx}", f"2026-07-{idx + 1:02d}", (idx + 1) * 100, source=f"src-{idx}")
            for idx in range(10)
        ]
        payload = self.payload(records)
        self.assertEqual(9, len(payload["models"]))
        for idx in range(2, 10):
            self.assertIn(f"model-src-{idx}", payload["models"])
        self.assertIn(dashboard_payload.OTHER_MODEL, payload["models"])
        self.assertNotIn("model-src-0", payload["models"])
        self.assertNotIn("model-src-1", payload["models"])


if __name__ == "__main__":
    unittest.main()
