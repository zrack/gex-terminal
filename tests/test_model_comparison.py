import tempfile
import unittest
from pathlib import Path

from gex_terminal.model_comparison import (
    build_model_comparison_report,
    model_comparison_to_csv,
    model_comparison_to_markdown,
    write_model_comparison_report,
)


def _snapshot(status="available"):
    directional = {
        "model": "aggressor_directionalized_volume",
        "status": status,
        "strikes": [5900.0, 5950.0, 6000.0],
        "net_gex": [-80.0, -120.0, 20.0],
        "buy_aggressor_volume": [10.0, 0.0, 1.0],
        "sell_aggressor_volume": [0.0, 15.0, 3.0],
        "unknown_aggressor_volume": [0.0, 5.0, 1.0],
        "total_net_gex": -180.0,
        "gamma_wall_strike": 5950.0,
        "zero_gamma_strike": 5920.0,
        "known_direction_volume": 29.0,
        "unknown_direction_volume": 6.0,
        "directional_coverage": 29.0 / 35.0,
        "direction_sources": ["provider"],
        "directional_assumption": "test assumption",
        "participant_classification": "unobserved",
        "opening_closing_classification": "unobserved",
        "predictive_validity": "unmeasured",
    }
    return {
        "timestamp": "2026-08-06T16:00:00Z",
        "symbol": "ES",
        "spot": 5950.0,
        "metrics": {
            "total_net_gex": 130.0,
            "gamma_wall": 5900.0,
            "zero_gamma": 5940.0,
        },
        "model": {"position_sources": ["trade_volume"]},
        "strikes": [
            {"strike": 5900.0, "net_gex": 100.0},
            {"strike": 5950.0, "net_gex": -50.0},
            {"strike": 6000.0, "net_gex": 80.0},
        ],
        "directionalized": directional,
    }


class ModelComparisonTests(unittest.TestCase):
    def test_builds_disagreement_metrics_without_predictive_claim(self):
        report = build_model_comparison_report(_snapshot())

        self.assertEqual(report["result"]["status"], "available")
        self.assertEqual(report["result"]["predictive_validity"], "unmeasured")
        self.assertTrue(report["default_model"]["unchanged_default"])
        self.assertFalse(report["metrics"]["regime_sign_agreement"])
        self.assertEqual(report["metrics"]["gamma_wall_distance"], 50.0)
        self.assertEqual(report["metrics"]["zero_gamma_distance"], 20.0)
        self.assertEqual(report["metrics"]["strike_sign_agreement"], 2 / 3)
        self.assertEqual(len(report["strikes"]), 3)

    def test_insufficient_coverage_remains_unscored(self):
        snapshot = _snapshot(status="insufficient_directional_coverage")
        snapshot["directionalized"].update({
            "known_direction_volume": 0.0,
            "unknown_direction_volume": 35.0,
            "directional_coverage": 0.0,
        })

        report = build_model_comparison_report(snapshot)

        self.assertEqual(report["result"]["status"], "insufficient_directional_coverage")
        self.assertNotIn("raw_total_net_gex", report["metrics"])
        self.assertIn("intentionally unscored", model_comparison_to_markdown(report))

    def test_available_model_without_common_strikes_remains_unscored(self):
        snapshot = _snapshot()
        snapshot["directionalized"]["strikes"] = [6050.0]
        snapshot["directionalized"]["net_gex"] = [10.0]

        report = build_model_comparison_report(snapshot)

        self.assertEqual(report["result"]["status"], "no_comparable_strikes")
        self.assertNotIn("raw_total_net_gex", report["metrics"])

    def test_writes_all_supported_report_formats(self):
        report = build_model_comparison_report(_snapshot())
        self.assertIn("record_type,name,value", model_comparison_to_csv(report))
        self.assertIn("# GEX Model Comparison", model_comparison_to_markdown(report))
        with tempfile.TemporaryDirectory() as tmp:
            for suffix in ("json", "csv", "md"):
                target = write_model_comparison_report(
                    report, str(Path(tmp) / f"comparison.{suffix}")
                )
                self.assertTrue(target.exists())


if __name__ == "__main__":
    unittest.main()
