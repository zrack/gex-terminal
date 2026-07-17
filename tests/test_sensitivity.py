import tempfile
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
