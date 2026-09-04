import unittest
from dataclasses import replace
from pathlib import Path

from gex_terminal.config import GexConfig
from gex_terminal.provider_injector import (
    inject_provider_fixture,
    provider_injection_summary,
)
from gex_terminal.package_data import provider_fixture_dir


FIXTURE_DIR = provider_fixture_dir()


def _config(symbol: str = "ES", provider: str = "tradovate") -> GexConfig:
    return replace(
        GexConfig.from_env(),
        symbol=symbol,
        symbols=(symbol,),
        data_mode="live",
        data_provider=provider,
        replay_delay_seconds=0.0,
        days_to_expiry=0.01,
    )


class ProviderInjectorTests(unittest.IsolatedAsyncioTestCase):
    async def test_tradovate_raw_fixture_drives_snapshot_without_credentials(self):
        snapshot = await inject_provider_fixture(
            provider="tradovate",
            fixture_path=FIXTURE_DIR / "tradovate_live_sample.jsonl",
            config=_config(),
        )

        self.assertEqual(snapshot["symbol"], "ES")
        self.assertEqual(snapshot["spot"], 5943.25)
        self.assertEqual(snapshot["provider_injection"]["fixture_format"], "tradovate")
        self.assertEqual(snapshot["feed_quality"]["frame_count"], 3)
        self.assertEqual(snapshot["feed_quality"]["parse_error_count"], 1)
        self.assertEqual(snapshot["feed_quality"]["dropped_count"], 1)
        self.assertIn("gamma_wall", snapshot["metrics"])
        self.assertIn("Zero gamma", provider_injection_summary(snapshot))

    async def test_databento_fixture_joins_underlying_definitions_and_trades(self):
        snapshot = await inject_provider_fixture(
            provider="databento",
            fixture_path=FIXTURE_DIR / "databento_trade_records.json",
            config=_config(provider="databento"),
            metadata_path=FIXTURE_DIR / "databento_definition_records.json",
            underlying_path=FIXTURE_DIR / "databento_underlying_mbp1_record.json",
        )

        volumes = {row["strike"]: row for row in snapshot["strikes"]}
        self.assertEqual(snapshot["spot"], 5943.25)
        self.assertEqual(volumes[5950.0]["call_volume"], 42)
        self.assertEqual(volumes[5900.0]["put_volume"], 31)
        self.assertEqual(volumes[6000.0]["call_volume"], 24)
        self.assertEqual(snapshot["feed_quality"]["subscribed_symbol_count"], 3)
        self.assertEqual(snapshot["feed_quality"]["frame_count"], 4)
        directional = snapshot["directionalized"]
        self.assertEqual(directional["status"], "available")
        self.assertEqual(directional["known_direction_volume"], 73.0)
        self.assertEqual(directional["unknown_direction_volume"], 24.0)
        self.assertAlmostEqual(directional["directional_coverage"], 73 / 97)
        self.assertEqual(directional["direction_sources"], ["provider"])

    async def test_yfinance_fixture_injection_supports_equity_etf_samples(self):
        snapshot = await inject_provider_fixture(
            provider="yfinance",
            fixture_path=FIXTURE_DIR / "yfinance_option_chain_records.json",
            config=_config(symbol="SPY", provider="yfinance"),
        )

        strikes = [row["strike"] for row in snapshot["strikes"]]
        self.assertEqual(snapshot["symbol"], "SPY")
        self.assertEqual(snapshot["spot"], 512.34)
        self.assertEqual(strikes, [505.0, 510.0, 515.0])
        self.assertEqual(snapshot["contract_multiplier"], 50)
        self.assertEqual(snapshot["contract_multiplier_semantics"], "configured_fallback")
        self.assertEqual(snapshot["effective_contract_multiplier"], 100.0)
        provenance = snapshot["model"]["multiplier_provenance"]
        self.assertEqual(provenance["effective_multipliers"], [100.0])
        self.assertEqual(provenance["fallback_row_count"], 0)
        self.assertTrue(all(row["source"] == "contract" for row in provenance["rows"]))
        self.assertEqual(snapshot["feed_quality"]["subscription_status"], "subscribed")

    async def test_cboe_option_quotes_csv_fixture_injection(self):
        snapshot = await inject_provider_fixture(
            provider="cboe",
            fixture_path=FIXTURE_DIR / "cboe_option_quotes_sample.csv",
            config=_config(symbol="SPY"),
            fixture_format="cboe-option-quotes",
        )

        volumes = {row["strike"]: row for row in snapshot["strikes"]}
        self.assertEqual(snapshot["provider_injection"]["fixture_format"], "cboe-option-quotes")
        self.assertAlmostEqual(snapshot["spot"], 512.34)
        self.assertEqual(volumes[510.0]["call_volume"], 120)
        self.assertEqual(volumes[510.0]["put_volume"], 95)
        self.assertEqual(snapshot["feed_quality"]["frame_count"], 4)


if __name__ == "__main__":
    unittest.main()
