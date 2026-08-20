import unittest

from gex_terminal.config import GexConfig
from gex_terminal.model_properties import build_model_property_report
from gex_terminal.performance_lab import build_performance_report
from gex_terminal.provider_fault_lab import build_provider_fault_report


def _config():
    return GexConfig(
        symbol="ES", symbols=("ES",), data_mode="replay", data_provider="replay",
        contract_multiplier=50, risk_free_rate=0.045, days_to_expiry=0.25,
        refresh_interval_seconds=1, stale_after_seconds=10, replay_path="",
        replay_delay_seconds=0, tradovate_environment="demo",
    )


class OfflineCertificationExtensionTests(unittest.IsolatedAsyncioTestCase):
    async def test_property_and_fault_certifications_pass_without_market_claims(self):
        properties = await build_model_property_report()
        faults = await build_provider_fault_report(_config())
        self.assertTrue(properties["result"]["passed"])
        self.assertTrue(faults["result"]["passed"])
        self.assertFalse(faults["result"]["live_transport_certified"])
        self.assertEqual(properties["result"]["predictive_validity"], "unmeasured")

    async def test_generated_performance_budget_is_explicit(self):
        report = await build_performance_report(
            _config(),
            contracts=40,
            minimum_ingest_records_per_second=1,
            maximum_snapshot_milliseconds=5000,
            maximum_peak_megabytes=512,
        )
        self.assertTrue(report["result"]["passed"])
        self.assertFalse(report["result"]["live_capacity_certified"])
        self.assertEqual(report["workload"]["option_contracts"], 40)


if __name__ == "__main__":
    unittest.main()
