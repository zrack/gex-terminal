import unittest

from gex_terminal.config import GexConfig
from gex_terminal.model_profiles import (
    config_from_model_profile,
    default_model_profile,
    validate_model_profile,
)


def _config():
    return GexConfig(
        symbol="ES", symbols=("ES", "NQ"), data_mode="replay", data_provider="replay",
        contract_multiplier=50, risk_free_rate=0.045, days_to_expiry=0.25,
        refresh_interval_seconds=1, stale_after_seconds=10, replay_path="",
        replay_delay_seconds=0, tradovate_environment="demo",
    )


class ModelProfileTests(unittest.TestCase):
    def test_profile_rejects_fractional_multiplier(self):
        profile = default_model_profile(_config())
        profile["contract_multiplier"] = 12.5
        with self.assertRaisesRegex(ValueError, "must be an integer"):
            validate_model_profile(profile)

    def test_default_profile_round_trips_into_config(self):
        profile = validate_model_profile(default_model_profile(_config()))
        rebuilt = config_from_model_profile(profile)
        self.assertEqual(rebuilt.symbol, "ES")
        self.assertEqual(rebuilt.contract_multiplier, 50)
        self.assertEqual(profile["predictive_validity"], "unmeasured")

    def test_profile_rejects_model_ladder_reordering(self):
        profile = default_model_profile(_config())
        profile["position_models"] = list(reversed(profile["position_models"]))
        with self.assertRaisesRegex(ValueError, "position_models"):
            validate_model_profile(profile)

    def test_profile_rejects_predictive_promotion(self):
        profile = default_model_profile(_config())
        profile["predictive_validity"] = "validated"
        with self.assertRaisesRegex(ValueError, "predictive_validity=unmeasured"):
            validate_model_profile(profile)


if __name__ == "__main__":
    unittest.main()
