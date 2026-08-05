import sys
import types
import unittest
import json
from pathlib import Path
from unittest.mock import patch

from gex_terminal.adapters.yfinance_adapter import YfinanceAdapter
from gex_terminal.consumer import StatefulGexConsumer
from gex_terminal.engine import IntradayGexEngine
from gex_terminal.market_data_adapter import AdapterConfigurationError
from gex_terminal.package_data import provider_fixture_path


class FakeTable:
    def __init__(self, rows):
        self.rows = rows

    def to_dict(self, orient):
        self.assert_orient = orient
        return self.rows


class FakeTicker:
    options = ("2026-07-17",)
    fast_info = {"last_price": 512.34}

    def __init__(self, symbol):
        self.symbol = symbol

    def option_chain(self, expiry):
        return types.SimpleNamespace(
            calls=FakeTable([
                {"strike": 510.0, "volume": 120, "impliedVolatility": 0.18},
                {"strike": 515.0, "volume": 80, "impliedVolatility": 0.17},
            ]),
            puts=FakeTable([
                {"strike": 510.0, "openInterest": 95, "impliedVolatility": 0.19},
                {"strike": 505.0, "volume": 60, "impliedVolatility": 0.21},
            ]),
        )

    def history(self, period):
        raise AssertionError("fast_info should provide the quote")


class YfinanceAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_streams_delayed_option_snapshot_into_consumer(self):
        fake_module = types.SimpleNamespace(Ticker=FakeTicker)
        with patch.dict(sys.modules, {"yfinance": fake_module}):
            consumer = StatefulGexConsumer(
                IntradayGexEngine(),
                target_underlying="SPY",
                data_mode="live",
            )
            adapter = YfinanceAdapter(consumer, target_underlying="SPY")

            await adapter.stream_market_data()

        self.assertEqual(consumer.current_spot, 512.34)
        self.assertEqual(consumer.chain_state[510.0]["C"], 120)
        self.assertEqual(consumer.chain_state[510.0]["P"], 95)
        self.assertEqual(consumer.chain_state[505.0]["P"], 60)
        self.assertEqual(len(consumer.contract_state), 4)

    async def test_rejects_futures_symbols(self):
        fake_module = types.SimpleNamespace(Ticker=FakeTicker)
        with patch.dict(sys.modules, {"yfinance": fake_module}):
            adapter = YfinanceAdapter(consumer=None, target_underlying="ES")

            with self.assertRaises(AdapterConfigurationError):
                adapter.validate()

    async def test_normalizes_sanitized_option_chain_fixture(self):
        fixture_path = provider_fixture_path("yfinance_option_chain_records.json")
        payload = json.loads(fixture_path.read_text(encoding="utf-8"))
        adapter = YfinanceAdapter(consumer=None, target_underlying=payload["symbol"])

        calls = adapter._normalized_option_rows(payload["calls"], "C", payload["expiry"])
        puts = adapter._normalized_option_rows(payload["puts"], "P", payload["expiry"])

        self.assertEqual(calls[0]["strike"], 510.0)
        self.assertEqual(calls[0]["volume"], 120)
        self.assertEqual(calls[0]["schema_version"], 2)
        self.assertEqual(calls[0]["volume_semantics"], "cumulative")
        self.assertEqual(calls[0]["position_source"], "trade_volume")
        self.assertEqual(calls[0]["iv_source"], "provider")
        self.assertEqual(puts[0]["volume"], 95)
        self.assertEqual(puts[0]["position_source"], "open_interest")
        self.assertEqual(puts[0]["expiry"], "2026-07-17")

    async def test_missing_iv_is_labeled_and_degrades_consumer_quality(self):
        consumer = StatefulGexConsumer(
            IntradayGexEngine(),
            target_underlying="SPY",
            data_mode="live",
        )
        consumer.mark_connected()
        adapter = YfinanceAdapter(consumer=consumer, target_underlying="SPY")
        rows = adapter._normalized_option_rows(
            [{"strike": 510.0, "volume": 10}],
            "C",
            "2026-07-17",
            observed_at="2026-07-16T20:00:00Z",
        )

        await consumer.update_market_state(json.dumps(rows[0]))
        quality = consumer.feed_quality_snapshot()

        self.assertEqual(rows[0]["iv_source"], "configured_default")
        self.assertEqual(quality["fallback_iv_tick_count"], 1)
        self.assertEqual(quality["health"], "degraded")
        self.assertTrue(any("fallback IV" in note for note in quality["notes"]))


if __name__ == "__main__":
    unittest.main()
