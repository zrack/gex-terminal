import json
import os
import subprocess
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_ENV_NAMES = (
    "GEX_CONTRACT_MULTIPLIER",
    "GEX_DATA_MODE",
    "GEX_DATA_PROVIDER",
    "GEX_DAYS_TO_EXPIRY",
    "GEX_REFRESH_INTERVAL_SECONDS",
    "GEX_REPLAY_DELAY_SECONDS",
    "GEX_REPLAY_MAX_GAP_SECONDS",
    "GEX_REPLAY_PATH",
    "GEX_REPLAY_SPEED",
    "GEX_RISK_FREE_RATE",
    "GEX_STALE_AFTER_SECONDS",
    "GEX_STRICT_EVENT_TIME",
    "GEX_SYMBOL",
    "GEX_SYMBOLS",
    "GEX_LOG_LEVEL",
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


class DoctorCliTests(unittest.TestCase):
    def test_public_json_and_text_commands_return_report_exit(self):
        json_result = _run_cli("doctor", "--json")
        text_result = _run_cli("doctor")
        report = json.loads(json_result.stdout)

        self.assertEqual(json_result.returncode, report["summary"]["exit_code"])
        self.assertEqual(json_result.returncode, 0)
        self.assertEqual(report["schema"], "gex-terminal.doctor.v1")
        self.assertFalse(report["execution"]["network_used"])
        self.assertEqual(text_result.returncode, 0)
        self.assertIn("gex-terminal doctor", text_result.stdout)
        self.assertIn("[UNVERIFIED] provider.live_access", text_result.stdout)
        self.assertNotIn("Traceback", json_result.stderr + text_result.stderr)

    def test_invalid_environment_becomes_json_diagnostic_without_raw_value(self):
        sentinel = "private-token-shaped-invalid-value"
        result = _run_cli(
            "doctor",
            "--json",
            env_updates={"GEX_STALE_AFTER_SECONDS": sentinel},
        )
        report = json.loads(result.stdout)
        rendered = result.stdout + result.stderr

        self.assertEqual(result.returncode, 2)
        self.assertEqual(report["summary"]["exit_code"], 2)
        self.assertIn("GEX_STALE_AFTER_SECONDS must be numeric", rendered)
        self.assertNotIn(sentinel, rendered)
        self.assertNotIn("Traceback", rendered)

    def test_scaffold_selected_provider_is_nonzero_without_live_attempt(self):
        result = _run_cli(
            "doctor",
            "--mode",
            "live",
            "--provider",
            "ibkr",
            "--json",
        )
        report = json.loads(result.stdout)
        selection = next(
            check for check in report["checks"] if check["id"] == "provider.selection"
        )

        self.assertEqual(result.returncode, 2)
        self.assertEqual(selection["status"], "fail")
        self.assertIn("scaffold", selection["summary"])
        self.assertEqual(
            next(
                check
                for check in report["checks"]
                if check["id"] == "provider.live_access"
            )["status"],
            "unverified",
        )

    def test_invalid_log_level_is_reported_without_echoing_raw_value(self):
        sentinel = "private-log-level-secret"
        result = _run_cli(
            "doctor",
            "--json",
            env_updates={"GEX_LOG_LEVEL": sentinel},
        )
        report = json.loads(result.stdout)
        rendered = result.stdout + result.stderr

        self.assertEqual(result.returncode, 2)
        self.assertEqual(report["summary"]["exit_code"], 2)
        self.assertEqual(
            next(
                check
                for check in report["checks"]
                if check["id"] == "configuration.logging"
            )["status"],
            "fail",
        )
        self.assertNotIn(sentinel, rendered)
        self.assertNotIn("Traceback", rendered)

    def test_invalid_choice_is_rejected_without_echoing_raw_value(self):
        sentinel = "private-provider-choice-secret"
        result = _run_cli("doctor", "--provider", sentinel, "--json")
        rendered = result.stdout + result.stderr

        self.assertEqual(result.returncode, 2)
        self.assertIn("invalid choice", rendered)
        self.assertNotIn(sentinel, rendered)
        self.assertNotIn("Traceback", rendered)

    def test_unexpected_doctor_argument_is_rejected_without_echoing_it(self):
        sentinel = "/Users/private-person/unexpected-secret"
        public_result = _run_cli("doctor", sentinel, "--json")
        environment = os.environ.copy()
        direct_result = subprocess.run(
            [sys.executable, "-m", "gex_terminal.doctor", sentinel],
            cwd=PROJECT_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

        for result in (public_result, direct_result):
            rendered = result.stdout + result.stderr
            self.assertEqual(result.returncode, 2)
            self.assertNotIn(sentinel, rendered)
            self.assertNotIn("Traceback", rendered)

    def test_unreadable_replay_and_sensitive_environment_never_leak(self):
        private_path = "/Users/private-person/private-replay.jsonl"
        credential = "credential-secret-value"
        account = "private-account-identifier"
        result = _run_cli(
            "doctor",
            "--mode",
            "replay",
            "--replay",
            private_path,
            "--json",
            env_updates={
                "DATABENTO_API_KEY": credential,
                "PRIVATE_ACCOUNT_ID": account,
            },
        )
        report = json.loads(result.stdout)
        rendered = result.stdout + result.stderr

        self.assertEqual(result.returncode, 2)
        self.assertEqual(report["summary"]["exit_code"], 2)
        self.assertNotIn(private_path, rendered)
        self.assertNotIn(credential, rendered)
        self.assertNotIn(account, rendered)
        self.assertNotIn("/Users/", rendered)

    def test_minimal_module_entrypoint_emits_versioned_json(self):
        environment = os.environ.copy()
        for name in CONFIG_ENV_NAMES:
            environment.pop(name, None)
        result = subprocess.run(
            [sys.executable, "-m", "gex_terminal.doctor", "--json"],
            cwd=PROJECT_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        report = json.loads(result.stdout)

        self.assertEqual(result.returncode, report["summary"]["exit_code"])
        self.assertEqual(report["schema"], "gex-terminal.doctor.v1")
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
