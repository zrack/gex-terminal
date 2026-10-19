import unittest

from gex_terminal.adapters.registry import adapter_info
from gex_terminal.config import GexConfig
from gex_terminal.provider_readiness import (
    PROVIDER_READINESS_STATES,
    runtime_provider_readiness,
)


def _config(**overrides):
    values = dict(
        symbol="ES", symbols=("ES",), data_mode="demo", data_provider="tradovate",
        contract_multiplier=50, risk_free_rate=0.045, days_to_expiry=0.25,
        refresh_interval_seconds=1, stale_after_seconds=10, replay_path="",
        replay_delay_seconds=0, tradovate_environment="demo",
    )
    values.update(overrides)
    return GexConfig(**values)


class ProviderReadinessTests(unittest.TestCase):
    def test_all_registry_statuses_use_canonical_vocabulary(self):
        for provider in ("databento", "ibkr", "replay", "tradovate", "yfinance"):
            self.assertIn(adapter_info(provider).status, PROVIDER_READINESS_STATES)

    def test_runtime_connection_mode_does_not_promote_provider(self):
        self.assertEqual(runtime_provider_readiness(_config()), "offline-certified")
        self.assertEqual(
            runtime_provider_readiness(_config(data_mode="live", data_provider="databento")),
            "live-uncertified",
        )


if __name__ == "__main__":
    unittest.main()
