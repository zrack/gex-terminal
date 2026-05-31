import os
import unittest
from unittest.mock import patch

from gex_terminal.adapters.databento import DatabentoAdapter
from gex_terminal.adapters.ibkr import IbkrAdapter
from gex_terminal.adapters.registry import (
    available_provider_names,
    build_market_data_adapter,
    effective_provider,
)
from gex_terminal.adapters.replay import ReplayAdapter
from gex_terminal.config import GexConfig
from gex_terminal.engine import IntradayGexEngine
from gex_terminal.consumer import StatefulGexConsumer
from gex_terminal.market_data_adapter import AdapterConfigurationError


def _config(**overrides) -> GexConfig:
    values = {
        "symbol": "ES",
        "symbols": ("ES", "NQ", "SPX", "QQQ"),
        "data_mode": "live",
        "data_provider": "tradovate",
        "contract_multiplier": 50,
        "risk_free_rate": 0.045,
        "days_to_expiry": 0.01,
        "refresh_interval_seconds": 1.0,
        "stale_after_seconds": 10.0,
        "replay_path": "sample_data/demo_replay.jsonl",
        "replay_delay_seconds": 0.0,
        "tradovate_environment": "demo",
    }
    values.update(overrides)
    return GexConfig(**values)


class AdapterRegistryTests(unittest.TestCase):
    def test_lists_known_providers(self):
        self.assertEqual(
            available_provider_names(),
            ("databento", "ibkr", "replay", "tradovate", "yfinance"),
        )

    def test_replay_mode_forces_replay_provider(self):
        config = _config(data_mode="replay", data_provider="tradovate")

        self.assertEqual(effective_provider(config), "replay")

    def test_builds_replay_adapter(self):
        consumer = StatefulGexConsumer(IntradayGexEngine(), data_mode="replay")
        adapter = build_market_data_adapter(consumer, _config(data_mode="replay"))

        self.assertIsInstance(adapter, ReplayAdapter)

    def test_builds_databento_adapter(self):
        consumer = StatefulGexConsumer(IntradayGexEngine())
        adapter = build_market_data_adapter(
            consumer, _config(data_provider="databento"), validate=False
        )

        self.assertIsInstance(adapter, DatabentoAdapter)

    def test_builds_ibkr_adapter(self):
        consumer = StatefulGexConsumer(IntradayGexEngine())
        adapter = build_market_data_adapter(
            consumer, _config(data_provider="ibkr"), validate=False
        )

        self.assertIsInstance(adapter, IbkrAdapter)

    def test_provider_factory_validates_selected_provider(self):
        consumer = StatefulGexConsumer(IntradayGexEngine())
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(AdapterConfigurationError):
                build_market_data_adapter(
                    consumer, _config(data_provider="databento")
                )

    def test_databento_validation_reports_missing_key(self):
        with patch.dict(os.environ, {}, clear=True):
            adapter = DatabentoAdapter(consumer=None)

            with self.assertRaises(AdapterConfigurationError):
                adapter.validate()


if __name__ == "__main__":
    unittest.main()
