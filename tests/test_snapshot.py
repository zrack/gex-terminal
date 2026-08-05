import json
import tempfile
import unittest
from pathlib import Path

from gex_terminal.snapshot import build_snapshot, write_snapshot


def _data():
    return {
        "strikes": [5900.0, 5950.0, 6000.0],
        "gammas": [0.003, 0.018, 0.001],
        "call_gex": [200_000_000.0, 4_000_000_000.0, 120_000_000.0],
        "put_gex": [-450_000_000.0, -1_000_000_000.0, -20_000_000.0],
        "net_gex": [-250_000_000.0, 3_000_000_000.0, 100_000_000.0],
        "total_net_gex": 2_850_000_000.0,
        "gamma_wall_strike": 5950.0,
        "call_wall_strike": 5950.0,
        "put_wall_strike": 5900.0,
        "zero_gamma_strike": 5914.0,
        "concentration_ratio": 0.65,
        "concentration_band_low": 5950.0,
        "concentration_band_high": 6000.0,
        "schema_version": 2,
        "model_version": "gex-terminal.gex-model.v2",
        "normalized_schema_versions": [2],
        "calculation_mode": "contract_v2",
        "pricing_models": ["black_76"],
        "gamma_aggregation": "quantity_weighted_mean",
        "zero_gamma_semantics": "strike_profile_exposure_crossing",
        "contract_count": 6,
        "selected_contract_count": 6,
        "position_sources": ["open_interest", "trade_volume"],
        "expiry_filter": "0dte",
        "units": "USD gamma exposure per 1% underlying move",
        "day_count_convention": "ACT/365",
    }


class SnapshotTests(unittest.TestCase):
    def _snapshot(self):
        return build_snapshot(
            symbol="ES",
            spot=5943.25,
            session_open=5904.50,
            days_to_expiry=0.25,
            contract_multiplier=50,
            risk_free_rate=0.045,
            data=_data(),
            chain_state={
                5900.0: {"C": 4781, "P": 7406},
                5950.0: {"C": 13480, "P": 3044},
                6000.0: {"C": 10872, "P": 1624},
            },
            expiry_breakdown={"0.25DTE": 2_850_000_000.0},
        )

    def test_snapshot_has_expected_top_level_keys(self):
        snap = self._snapshot()
        for key in (
            "timestamp",
            "symbol",
            "spot",
            "metrics",
            "model",
            "expiry_breakdown",
            "strikes",
        ):
            self.assertIn(key, snap)

    def test_snapshot_carries_complete_model_provenance(self):
        model = self._snapshot()["model"]

        self.assertEqual(model["schema_version"], 2)
        self.assertEqual(model["model_version"], "gex-terminal.gex-model.v2")
        self.assertEqual(model["normalized_schema_versions"], [2])
        self.assertEqual(model["calculation_mode"], "contract_v2")
        self.assertEqual(model["pricing_models"], ["black_76"])
        self.assertEqual(model["position_sources"], ["open_interest", "trade_volume"])
        self.assertEqual(model["contract_count"], 6)
        self.assertEqual(model["expiry_filter"], "0dte")
        self.assertEqual(
            model["units"], "USD gamma exposure per 1% underlying move"
        )
        self.assertEqual(model["day_count_convention"], "ACT/365")
        self.assertEqual(model["gamma_aggregation"], "quantity_weighted_mean")
        self.assertEqual(
            model["zero_gamma_semantics"], "strike_profile_exposure_crossing"
        )

    def test_metrics_carry_walls_and_concentration(self):
        metrics = self._snapshot()["metrics"]
        self.assertEqual(metrics["call_wall"], 5950.0)
        self.assertEqual(metrics["put_wall"], 5900.0)
        self.assertEqual(metrics["concentration_band"], [5950.0, 6000.0])
        self.assertAlmostEqual(metrics["imbalance"], 4_320_000_000.0 / 1_470_000_000.0, places=4)

    def test_strike_rows_merge_volume_from_chain_state(self):
        snap = self._snapshot()
        first = next(row for row in snap["strikes"] if row["strike"] == 5950.0)
        self.assertEqual(first["call_volume"], 13480)
        self.assertEqual(first["put_volume"], 3044)

    def test_session_change_uses_open(self):
        snap = self._snapshot()
        self.assertAlmostEqual(snap["session_change"], 38.75, places=2)

    def test_write_snapshot_round_trips_json(self):
        snap = self._snapshot()
        with tempfile.TemporaryDirectory() as tmp:
            target = write_snapshot(snap, str(Path(tmp) / "out.json"))
            loaded = json.loads(target.read_text())
        self.assertEqual(loaded["symbol"], "ES")
        self.assertEqual(len(loaded["strikes"]), 3)


if __name__ == "__main__":
    unittest.main()
