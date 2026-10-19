import csv
import io
import tempfile
import unittest
from pathlib import Path

from gex_terminal.config import GexConfig
from gex_terminal.position_model_comparison import (
    build_position_model_comparison,
    position_model_comparison_to_csv,
    position_model_comparison_to_markdown,
    write_position_model_comparison,
)


def _config():
    return GexConfig(
        symbol="ES", symbols=("ES",), data_mode="replay", data_provider="replay",
        contract_multiplier=50, risk_free_rate=0.045, days_to_expiry=10,
        refresh_interval_seconds=1, stale_after_seconds=10, replay_path="",
        replay_delay_seconds=0, tradovate_environment="demo",
    )


def _option(contract_id, position_source, volume, side="unknown", event_time="2026-08-06T15:59:00Z"):
    return {
        "schema_version":2, "type":"options_volume_tick", "provider":"test",
        "contract_id":contract_id, "symbol":"ES", "strike":6000,
        "option_type":"C" if contract_id.endswith("c") else "P", "volume":volume,
        "volume_semantics":"cumulative" if position_source == "open_interest" else "incremental",
        "position_source":position_source, "iv":0.2, "iv_source":"provider",
        "instrument_class":"futures_option", "pricing_model":"black_76",
        "expiry":"2026-08-20", "expiry_timestamp":"2026-08-20T20:00:00Z",
        "event_time":event_time, "aggressor_side":side,
        "direction_source":"provider" if side != "unknown" else "unknown",
    }


class PositionModelComparisonTests(unittest.IsolatedAsyncioTestCase):
    async def test_compares_sources_without_summing_and_rejects_future_vintage(self):
        messages = [
            {"schema_version":2, "type":"underlying_tick", "provider":"test",
             "symbol":"ES", "price":6000, "event_time":"2026-08-06T15:58:00Z"},
            _option("oic", "open_interest", 1000),
            _option("oip", "open_interest", 900),
            _option("volc", "trade_volume", 10, "buy"),
            _option("volp", "trade_volume", 8, "sell"),
            _option("futurec", "open_interest", 9999, event_time="2026-08-06T16:01:00Z"),
        ]
        report = await build_position_model_comparison(
            {"as_of":"2026-08-06T16:00:00Z", "messages":messages}, config=_config()
        )
        self.assertEqual(report["result"]["status"], "available")
        self.assertTrue(report["result"]["models_may_not_be_summed"])
        self.assertEqual(report["vintage_control"]["future_messages_rejected"], 1)
        self.assertEqual(report["result"]["predictive_validity"], "unmeasured")
        self.assertEqual(report["models"]["open_interest"]["position_sources"], ["open_interest"])

        markdown = position_model_comparison_to_markdown(report)
        csv_rows = list(csv.DictReader(io.StringIO(position_model_comparison_to_csv(report))))
        self.assertIn("Models may be summed: `false`", markdown)
        self.assertIn("Differences, Not Combined Exposure", markdown)
        self.assertIn("Evidence ceiling:", markdown)
        self.assertEqual(
            {row["name"] for row in csv_rows if row["record_type"] == "model"},
            {"open_interest", "raw_trade_volume", "directionalized_trade_volume"},
        )
        self.assertIn("models_may_not_be_summed", {
            row["name"] for row in csv_rows if row["record_type"] == "limitation"
        })

        with tempfile.TemporaryDirectory() as tmp:
            for suffix in ("json", "csv", "md"):
                target = write_position_model_comparison(
                    report,
                    Path(tmp) / f"position-comparison.{suffix}",
                )
                self.assertTrue(target.exists())


if __name__ == "__main__":
    unittest.main()
