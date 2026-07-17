import sys
import types
import unittest
from unittest.mock import patch

from gex_terminal.adapters.yfinance_adapter import YfinanceAdapter
from gex_terminal.consumer import StatefulGexConsumer
from gex_terminal.engine import IntradayGexEngine
from gex_terminal.market_data_adapter import AdapterConfigurationError


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

    async def test_rejects_futures_symbols(self):
        fake_module = types.SimpleNamespace(Ticker=FakeTicker)
        with patch.dict(sys.modules, {"yfinance": fake_module}):
            adapter = YfinanceAdapter(consumer=None, target_underlying="ES")

            with self.assertRaises(AdapterConfigurationError):
                adapter.validate()


if __name__ == "__main__":
    unittest.main()
