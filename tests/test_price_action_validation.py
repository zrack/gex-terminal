import unittest

from gex_terminal.price_action_validation import build_price_action_report


class PriceActionValidationTests(unittest.TestCase):
    def test_scores_saved_levels_and_keeps_predictive_status_unmeasured(self):
        observations = []
        for index in range(5):
            observations.append({
                "timestamp": f"2026-08-0{index + 1}T14:30:00Z",
                "spot": 6000,
                "directional_coverage": 0.8,
                "models": {
                    "raw": {"gamma_wall": 6010, "zero_gamma": 5980},
                    "directionalized": {"gamma_wall": 6005, "zero_gamma": 5990},
                },
                "future_path": [{"minutes": 5, "price": 6005}, {"minutes": 30, "price": 6012}],
            })
        report = build_price_action_report({"label": "synthetic", "observations": observations})
        self.assertEqual(report["result"]["status"], "descriptive_only")
        self.assertEqual(report["result"]["predictive_validity"], "unmeasured")
        self.assertFalse(report["result"]["promotion_allowed"])
        self.assertEqual(report["observations"][-1]["split"], "test")
        self.assertTrue(report["model_summaries"]["raw"]["touch_rate"] > 0)

    def test_missing_future_path_is_unscored(self):
        report = build_price_action_report({
            "observations": [{"timestamp":"2026-08-01T14:30:00Z", "spot":6000, "models":{}}]
        })
        self.assertEqual(report["result"]["status"], "insufficient_saved_price_action")

    def test_directional_model_is_unscored_below_coverage_gate(self):
        report = build_price_action_report({
            "minimum_directional_coverage": 0.5,
            "observations": [{
                "timestamp":"2026-08-01T14:30:00Z", "spot":6000,
                "directional_coverage":0.2,
                "models":{"raw":{"gamma_wall":6010}, "directionalized":{"gamma_wall":6005}},
                "future_path":[{"minutes":5,"price":6005}],
            }],
        })
        row = report["observations"][0]
        self.assertIn("raw", row["models"])
        self.assertNotIn("directionalized", row["models"])
        self.assertEqual(
            row["unscored_models"]["directionalized"],
            "insufficient_directional_coverage",
        )

    def test_malformed_numeric_fields_raise_contract_errors(self):
        base = {
            "timestamp": "2026-08-01T14:30:00Z",
            "spot": 6000,
            "models": {"raw": {"gamma_wall": 6010}},
            "future_path": [{"minutes": None, "price": 6005}],
        }
        with self.assertRaisesRegex(ValueError, "future_path minutes must be numeric"):
            build_price_action_report({"observations": [base]})

        invalid_coverage = dict(base)
        invalid_coverage["future_path"] = [{"minutes": 5, "price": 6005}]
        invalid_coverage["directional_coverage"] = "unknown"
        with self.assertRaisesRegex(ValueError, "directional_coverage must be numeric"):
            build_price_action_report({"observations": [invalid_coverage]})


if __name__ == "__main__":
    unittest.main()
