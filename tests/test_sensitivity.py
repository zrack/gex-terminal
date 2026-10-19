import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from gex_terminal.engine import IntradayGexEngine
from gex_terminal.sensitivity import (
    build_sensitivity_report,
    sensitivity_to_csv,
    sensitivity_to_markdown,
    write_sensitivity_report,
)


def _chain_state():
    return {
        5900.0: {"C": 1000, "P": 1800, "iv": 0.16},
        5950.0: {"C": 3200, "P": 700, "iv": 0.14},
        6000.0: {"C": 2200, "P": 400, "iv": 0.15},
    }


class SensitivityTests(unittest.TestCase):
    def test_builds_default_scenarios_with_deltas(self):
        report = build_sensitivity_report(
            spot=5943.25,
            chain_state=_chain_state(),
            days_to_expiry=0.25,
            risk_free_rate=0.045,
            contract_multiplier=50,
        )

        self.assertGreater(len(report["scenarios"]), 5)
        self.assertEqual(report["scenarios"][0]["scenario"], "base")
        self.assertEqual(report["scenarios"][0]["total_net_gex_delta"], 0.0)
        self.assertIn("zero_gamma_delta", report["scenarios"][1])

    def test_formats_csv_and_markdown(self):
        report = build_sensitivity_report(
            spot=5943.25,
            chain_state=_chain_state(),
            days_to_expiry=0.25,
            risk_free_rate=0.045,
            contract_multiplier=50,
        )

        self.assertIn("scenario,label", sensitivity_to_csv(report))
        self.assertIn("# GEX Model Sensitivity", sensitivity_to_markdown(report))

    def test_writes_report_by_extension(self):
        report = build_sensitivity_report(
            spot=5943.25,
            chain_state=_chain_state(),
            days_to_expiry=0.25,
            risk_free_rate=0.045,
            contract_multiplier=50,
        )
        with tempfile.TemporaryDirectory() as tmp:
            target = write_sensitivity_report(report, str(Path(tmp) / "sensitivity.md"))

            self.assertIn("GEX Model Sensitivity", target.read_text())

    def test_base_scenario_matches_v2_contract_aware_matrix(self):
        contract_rows = [
            {
                "provider": "oracle",
                "contract_id": "ES-5000-C",
                "strike": 5000.0,
                "option_type": "C",
                "iv": 0.15,
                "accumulated_volume": 100.0,
                "days_to_expiry": 1.0,
                "pricing_model": "black_76",
                "contract_multiplier": 50.0,
                "position_source": "open_interest",
            },
            {
                "provider": "oracle",
                "contract_id": "ES-5000-P",
                "strike": 5000.0,
                "option_type": "P",
                "iv": 0.15,
                "accumulated_volume": 35.0,
                "days_to_expiry": 1.0,
                "pricing_model": "black_76",
                "contract_multiplier": 50.0,
                "position_source": "open_interest",
            },
            {
                "provider": "oracle",
                "contract_id": "ES-5050-C",
                "strike": 5050.0,
                "option_type": "C",
                "iv": 0.18,
                "accumulated_volume": 20.0,
                "days_to_expiry": 7.0,
                "pricing_model": "black_76",
                "contract_multiplier": 50.0,
                "position_source": "trade_volume",
            },
        ]
        base_matrix = IntradayGexEngine(multiplier=50).compute_intraday_gex_matrix(
            spot_price=5000.0,
            strikes=np.array([row["strike"] for row in contract_rows]),
            days_to_expiry=np.array([row["days_to_expiry"] for row in contract_rows]),
            risk_free_rate=0.045,
            implied_vols=np.array([row["iv"] for row in contract_rows]),
            accumulated_call_vol=np.array([
                row["accumulated_volume"] if row["option_type"] == "C" else 0.0
                for row in contract_rows
            ]),
            accumulated_put_vol=np.array([
                row["accumulated_volume"] if row["option_type"] == "P" else 0.0
                for row in contract_rows
            ]),
            pricing_model=np.array([row["pricing_model"] for row in contract_rows]),
            contract_multipliers=np.array([
                row["contract_multiplier"] for row in contract_rows
            ]),
        )

        report = build_sensitivity_report(
            spot=5000.0,
            chain_state=_chain_state(),
            contract_rows=contract_rows,
            base_matrix=base_matrix,
            days_to_expiry=0.25,
            risk_free_rate=0.045,
            contract_multiplier=100,
        )
        base = report["scenarios"][0]

        self.assertAlmostEqual(base["total_net_gex"], base_matrix["total_net_gex"])
        self.assertEqual(base["gamma_wall"], base_matrix["gamma_wall_strike"])
        self.assertEqual(base["zero_gamma"], base_matrix["zero_gamma_strike"])
        self.assertEqual(base["call_wall"], base_matrix["call_wall_strike"])
        self.assertEqual(base["put_wall"], base_matrix["put_wall_strike"])
        self.assertEqual(base["total_net_gex_delta"], 0.0)

    def test_contract_expiry_timestamp_overrides_stale_dte_hint(self):
        as_of = datetime(2026, 6, 18, 14, tzinfo=timezone.utc)
        contract_rows = [{
            "provider": "oracle",
            "contract_id": "ES-20260619-C-5000",
            "strike": 5000.0,
            "option_type": "C",
            "iv": 0.15,
            "accumulated_volume": 100.0,
            "expiry_timestamp": "2026-06-19T14:00:00Z",
            "days_to_expiry": 90.0,
            "pricing_model": "black_76",
            "contract_multiplier": 50.0,
            "position_source": "trade_volume",
        }]
        expected = IntradayGexEngine(multiplier=50).compute_intraday_gex_matrix(
            spot_price=5000.0,
            strikes=np.array([5000.0]),
            days_to_expiry=np.array([1.0]),
            risk_free_rate=0.045,
            implied_vols=np.array([0.15]),
            accumulated_call_vol=np.array([100.0]),
            accumulated_put_vol=np.array([0.0]),
            pricing_model=np.array(["black_76"]),
            contract_multipliers=np.array([50.0]),
        )

        report = build_sensitivity_report(
            spot=5000.0,
            chain_state={},
            contract_rows=contract_rows,
            days_to_expiry=0.25,
            risk_free_rate=0.045,
            contract_multiplier=100.0,
            as_of=as_of,
        )

        self.assertAlmostEqual(
            report["scenarios"][0]["total_net_gex"],
            expected["total_net_gex"],
        )


if __name__ == "__main__":
    unittest.main()
