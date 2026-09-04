import os
import subprocess
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_ENV_NAMES = (
    "GEX_CONTRACT_MULTIPLIER",
    "GEX_RISK_FREE_RATE",
    "GEX_DAYS_TO_EXPIRY",
    "GEX_REFRESH_INTERVAL_SECONDS",
    "GEX_STALE_AFTER_SECONDS",
    "GEX_REPLAY_DELAY_SECONDS",
    "GEX_REPLAY_SPEED",
    "GEX_REPLAY_MAX_GAP_SECONDS",
    "GEX_STRICT_EVENT_TIME",
)


def _run_cli(*arguments: str, env_updates: dict[str, str] | None = None):
    environment = os.environ.copy()
    for name in CONFIG_ENV_NAMES:
        environment.pop(name, None)
    environment.update(env_updates or {})
    return subprocess.run(
        [sys.executable, "-m", "gex_terminal.cli", *arguments],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


class CliConfigurationTests(unittest.TestCase):
    def test_malformed_environment_value_is_actionable_and_never_echoed(self):
        sentinel = "private-token-shaped-invalid-value"
        result = _run_cli(
            "--providers",
            env_updates={"GEX_STALE_AFTER_SECONDS": sentinel},
        )
        output = result.stdout + result.stderr

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Configuration error: GEX_STALE_AFTER_SECONDS must be numeric", output)
        self.assertNotIn(sentinel, output)
        self.assertNotIn("Traceback", output)

    def test_nonfinite_environment_value_fails_before_runtime(self):
        result = _run_cli(
            "--providers",
            env_updates={"GEX_STALE_AFTER_SECONDS": "nan"},
        )
        output = result.stdout + result.stderr

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("GEX_STALE_AFTER_SECONDS must be finite", output)
        self.assertNotIn("Traceback", output)

    def test_malformed_cli_number_is_never_echoed_by_argparse(self):
        sentinel = "private-token-shaped-invalid-value"
        result = _run_cli("--refresh", sentinel, "--providers")
        output = result.stdout + result.stderr

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("argument --refresh: must be numeric", output)
        self.assertNotIn(sentinel, output)
        self.assertNotIn("Traceback", output)

    def test_cli_overrides_use_direct_config_range_validation(self):
        cases = (
            (("--refresh", "nan"), "refresh_interval_seconds must be finite"),
            (("--multiplier", "0"), "contract_multiplier must be greater than 0"),
            (("--replay-delay", "-1"), "replay_delay_seconds must be greater than or equal to 0"),
            (("--replay-speed", "0"), "replay_speed must be greater than 0"),
            (("--replay-max-gap", "-1"), "replay_max_gap_seconds must be greater than or equal to 0"),
        )

        for arguments, expected in cases:
            with self.subTest(arguments=arguments):
                result = _run_cli(*arguments, "--providers")
                output = result.stdout + result.stderr
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(f"Configuration error: {expected}", output)
                self.assertNotIn("Traceback", output)


if __name__ == "__main__":
    unittest.main()
