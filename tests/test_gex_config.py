import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from gex_terminal.config import (
    ConfigValidationError,
    GexConfig,
    _load_working_directory_dotenv,
)


def _config(**updates) -> GexConfig:
    values = {
        "symbol": "ES",
        "symbols": ("ES",),
        "data_mode": "replay",
        "data_provider": "replay",
        "contract_multiplier": 50,
        "risk_free_rate": 0.045,
        "days_to_expiry": 0.25,
        "refresh_interval_seconds": 1.0,
        "stale_after_seconds": 10.0,
        "replay_path": "",
        "replay_delay_seconds": 0.0,
        "tradovate_environment": "demo",
    }
    values.update(updates)
    return GexConfig(**values)


class GexConfigTests(unittest.TestCase):
    def test_defaults_to_demo_mode(self):
        with patch.dict(os.environ, {}, clear=True):
            config = GexConfig.from_env()

        self.assertEqual(config.data_mode, "demo")
        self.assertEqual(config.data_provider, "tradovate")
        self.assertEqual(Path(config.replay_path).name, "demo_replay.jsonl")
        self.assertTrue(Path(config.replay_path).is_file())
        self.assertEqual(config.expiry_filter, "all")

    def test_reads_expiry_filter_from_environment(self):
        with patch.dict(os.environ, {"GEX_EXPIRY_FILTER": "0dte"}, clear=True):
            config = GexConfig.from_env()

        self.assertEqual(config.expiry_filter, "0dte")

    def test_loads_dotenv_from_callers_working_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            dotenv_path = Path(temp_dir) / ".env"
            dotenv_path.write_text(
                "GEX_SYMBOL=NQ\nGEX_DATA_MODE=replay\n",
                encoding="utf-8",
            )
            original_cwd = Path.cwd()
            try:
                os.chdir(temp_dir)
                with patch.dict(os.environ, {}, clear=True):
                    self.assertTrue(_load_working_directory_dotenv())
                    config = GexConfig.from_env()
            finally:
                os.chdir(original_cwd)

        self.assertEqual(config.symbol, "NQ")
        self.assertEqual(config.data_mode, "replay")

    def test_direct_construction_rejects_nonfinite_and_out_of_domain_values(self):
        cases = (
            ("contract_multiplier", 0),
            ("contract_multiplier", -1),
            ("contract_multiplier", 50.5),
            ("contract_multiplier", True),
            ("risk_free_rate", float("nan")),
            ("risk_free_rate", float("inf")),
            ("days_to_expiry", 0.0),
            ("days_to_expiry", -1.0),
            ("days_to_expiry", float("nan")),
            ("refresh_interval_seconds", 0.0),
            ("refresh_interval_seconds", float("inf")),
            ("stale_after_seconds", 0.0),
            ("stale_after_seconds", float("nan")),
            ("replay_delay_seconds", -0.01),
            ("replay_delay_seconds", float("inf")),
            ("replay_speed", 0.0),
            ("replay_speed", float("nan")),
            ("replay_max_gap_seconds", -0.01),
            ("replay_max_gap_seconds", float("inf")),
            ("strict_event_time", "false"),
        )

        for field, value in cases:
            with self.subTest(field=field, value=value):
                with self.assertRaisesRegex(ConfigValidationError, field):
                    _config(**{field: value})

    def test_replace_uses_the_same_validation_boundary(self):
        config = _config()

        with self.assertRaisesRegex(
            ConfigValidationError,
            "refresh_interval_seconds must be finite",
        ):
            replace(config, refresh_interval_seconds=float("nan"))

    def test_zero_replay_timing_and_negative_finite_rate_are_valid_boundaries(self):
        config = _config(
            risk_free_rate=-0.01,
            replay_delay_seconds=0,
            replay_max_gap_seconds=0,
        )

        self.assertEqual(config.risk_free_rate, -0.01)
        self.assertEqual(config.replay_delay_seconds, 0.0)
        self.assertEqual(config.replay_max_gap_seconds, 0.0)
        self.assertEqual(config.replay_path, "")

    def test_environment_numeric_and_boolean_errors_fail_closed_without_raw_values(self):
        sentinel = "private-token-shaped-invalid-value"
        cases = (
            ("GEX_CONTRACT_MULTIPLIER", sentinel),
            ("GEX_RISK_FREE_RATE", sentinel),
            ("GEX_DAYS_TO_EXPIRY", "nan"),
            ("GEX_REFRESH_INTERVAL_SECONDS", "inf"),
            ("GEX_STALE_AFTER_SECONDS", sentinel),
            ("GEX_REPLAY_DELAY_SECONDS", sentinel),
            ("GEX_REPLAY_SPEED", "-inf"),
            ("GEX_REPLAY_MAX_GAP_SECONDS", sentinel),
            ("GEX_STRICT_EVENT_TIME", sentinel),
        )

        for name, value in cases:
            with self.subTest(name=name):
                with patch.dict(os.environ, {name: value}, clear=True):
                    with self.assertRaises(ConfigValidationError) as caught:
                        GexConfig.from_env()
                self.assertIn(name, str(caught.exception))
                self.assertNotIn(sentinel, str(caught.exception))

    def test_blank_required_numeric_is_malformed_but_blank_optional_is_none(self):
        with patch.dict(
            os.environ,
            {"GEX_REFRESH_INTERVAL_SECONDS": ""},
            clear=True,
        ):
            with self.assertRaisesRegex(
                ConfigValidationError,
                "GEX_REFRESH_INTERVAL_SECONDS must be numeric",
            ):
                GexConfig.from_env()

        with patch.dict(
            os.environ,
            {"GEX_REPLAY_MAX_GAP_SECONDS": "  "},
            clear=True,
        ):
            config = GexConfig.from_env()

        self.assertIsNone(config.replay_max_gap_seconds)


if __name__ == "__main__":
    unittest.main()
