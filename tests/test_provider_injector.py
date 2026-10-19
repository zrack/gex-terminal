import unittest
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile

from gex_terminal.config import GexConfig
from gex_terminal.provider_injector import (
    _inject_databento,
    inject_provider_fixture,
    provider_injection_summary,
)
from gex_terminal.package_data import provider_fixture_dir
from gex_terminal.consumer import StatefulGexConsumer
from gex_terminal.engine import IntradayGexEngine
from gex_terminal.implied_volatility import black_76_option_price


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
        self.assertEqual(snapshot["feed_quality"]["data_mode"], "REPLAY")
        self.assertEqual(snapshot["feed_quality"]["connection_state"], "DISCONNECTED")
        self.assertIn("simulated local feed", snapshot["feed_quality"]["notes"])
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
        self.assertEqual(snapshot["model"]["iv_source_counts"], {"black_76_inverted": 3})
        self.assertEqual(snapshot["feed_quality"]["fallback_iv_tick_count"], 0)

    async def test_databento_injector_uses_timed_quote_exact_expiry_and_configured_rate(self):
        config = replace(_config(provider="databento"), risk_free_rate=.02)
        consumer = StatefulGexConsumer(IntradayGexEngine(config.contract_multiplier), data_mode="replay",
                                      target_underlying=config.symbol, risk_free_rate=config.risk_free_rate)
        await _inject_databento(consumer, config, FIXTURE_DIR / "databento_trade_records.json",
                               FIXTURE_DIR / "databento_definition_records.json",
                               FIXTURE_DIR / "databento_underlying_mbp1_record.json")
        prices = {"9001001": 18.5, "9001002": 16.25, "9001004": 12.75}
        expiry = datetime(2026, 6, 19, 20, tzinfo=timezone.utc)
        self.assertEqual(len(consumer.contract_state), 3)
        for row in consumer.contract_state.values():
            self.assertEqual(row["iv_source"], "black_76_inverted")
            provenance = row["iv_provenance"]
            self.assertEqual(provenance["risk_free_rate"], .02)
            self.assertEqual(provenance["underlying_price"], 5943.25)
            self.assertEqual(provenance["underlying_event_time"], "2026-06-18T14:30:00.000000000Z")
            event = datetime.fromisoformat(row["event_time"].replace("Z", "+00:00"))
            years = (expiry - event).total_seconds() / (365 * 86400)
            self.assertAlmostEqual(provenance["time_to_expiry_years"], years, places=15)
            recovered = black_76_option_price(futures_price=5943.25, strike=row["strike"],
                                              time_to_expiry_years=years, risk_free_rate=.02,
                                              volatility=row["iv"], option_type=row["option_type"])
            self.assertAlmostEqual(recovered, prices[row["contract_id"]], places=7)
        self.assertEqual(consumer.feed_quality_snapshot()["frame_count"], 4)
        self.assertEqual(consumer.feed_quality_snapshot()["subscribed_symbol_count"], 3)

    async def test_databento_date_only_expiry_retains_unpriced_volume_without_default_iv(self):
        config = _config(provider="databento")
        definitions = json.loads((FIXTURE_DIR / "databento_definition_records.json").read_text())
        for record in definitions["records"]:
            record["expiration"] = "2026-06-19"
        with tempfile.TemporaryDirectory() as directory:
            metadata = Path(directory) / "date-only-definitions.json"
            metadata.write_text(json.dumps(definitions))
            consumer = StatefulGexConsumer(IntradayGexEngine(config.contract_multiplier), data_mode="replay",
                                          target_underlying=config.symbol, risk_free_rate=config.risk_free_rate)
            await _inject_databento(consumer, config, FIXTURE_DIR / "databento_trade_records.json",
                                   metadata, FIXTURE_DIR / "databento_underlying_mbp1_record.json")
            self.assertEqual(len(consumer.contract_state), 3)
            self.assertEqual(sum(row["accumulated_volume"] for row in consumer.contract_state.values()), 97)
            self.assertTrue(all(row["iv"] is None and row["iv_source"] == "unavailable"
                                for row in consumer.contract_state.values()))
            self.assertEqual(consumer.fallback_iv_tick_count, 0)
            result = await consumer.process_latest_snapshot(.01)
            self.assertEqual(result["status"], "no_data")
            self.assertNotIn("total_net_gex", result)
            self.assertEqual(result["pricing_coverage"]["unpriced_quantity"], 97)
            with self.assertRaisesRegex(ValueError, "did not produce a computable snapshot"):
                await inject_provider_fixture(provider="databento", fixture_path=FIXTURE_DIR / "databento_trade_records.json",
                                              config=config, metadata_path=metadata,
                                              underlying_path=FIXTURE_DIR / "databento_underlying_mbp1_record.json")

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
        self.assertEqual(
            snapshot["provider_injection"]["source_kind"],
            "offline_provider_fixture",
        )
        self.assertIs(snapshot["provider_injection"]["network_used"], False)
        self.assertEqual(snapshot["provider_injection"]["mapping_status"], "computed")
        self.assertEqual(snapshot["feed_quality"]["status"], "REPLAY")
        self.assertEqual(snapshot["feed_quality"]["data_mode"], "REPLAY")
        self.assertEqual(snapshot["feed_quality"]["connection_state"], "DISCONNECTED")
        self.assertEqual(snapshot["feed_quality"]["health"], "simulated")
        self.assertIn("simulated local feed", snapshot["feed_quality"]["notes"])

        summary = provider_injection_summary(snapshot)
        self.assertIn("Source: offline provider fixture  Network used: no", summary)
        self.assertIn("Mapping: computed", summary)
        self.assertIn("Runtime: REPLAY", summary)
        self.assertIn("Connection: DISCONNECTED", summary)
        self.assertIn("Health: simulated", summary)
        self.assertNotIn("Runtime: LIVE", summary)
        self.assertNotIn("Health: healthy", summary)

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
