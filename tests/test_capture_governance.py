import json
import os
import subprocess
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from gex_terminal.capture_governance import (
    CAPTURE_POLICY_SCHEMA,
    CapturePolicyError,
    capture_policy_identity,
    load_capture_policy,
    validate_capture_policy,
)
from gex_terminal.cli import (
    _capture_source_metadata,
    _resolve_capture_policy_for_runtime,
)
from gex_terminal.config import GexConfig


def _valid_policy():
    return {
        "schema": CAPTURE_POLICY_SCHEMA,
        "policy_id": "databento-es-certification-2026-08",
        "rights": {
            "status": "licensed",
            "basis": "Operator reviewed the applicable provider agreement.",
            "redistributable": False,
        },
        "retention": {
            "mode": "time_limited",
            "days": 30,
            "storage": "owner-only local session store",
            "owner": "named capture operator",
        },
        "redaction": {
            "status": "required",
            "profile": "normalized-no-sensitive-identifiers-v1",
            "review_before_sharing": True,
        },
        "research_use": {
            "status": "approved",
            "scope": "internal method comparison only",
        },
    }


class CapturePolicyTests(unittest.TestCase):
    def test_validates_strict_policy_and_builds_stable_identity(self):
        policy = _valid_policy()
        normalized = validate_capture_policy(policy)
        reordered = {key: policy[key] for key in reversed(tuple(policy))}

        self.assertEqual(normalized, policy)
        self.assertEqual(
            capture_policy_identity(policy),
            capture_policy_identity(reordered),
        )
        self.assertEqual(len(capture_policy_identity(policy)["sha256"]), 64)

    def test_rejects_ambiguous_or_unknown_decisions(self):
        mutations = []

        missing_rights = _valid_policy()
        del missing_rights["rights"]
        mutations.append(missing_rights)

        unknown_rights = _valid_policy()
        unknown_rights["rights"]["status"] = "unknown"
        mutations.append(unknown_rights)

        ambiguous_retention = _valid_policy()
        ambiguous_retention["retention"]["days"] = None
        mutations.append(ambiguous_retention)

        disabled_redaction_review = _valid_policy()
        disabled_redaction_review["redaction"]["review_before_sharing"] = False
        mutations.append(disabled_redaction_review)

        unknown_research_use = _valid_policy()
        unknown_research_use["research_use"]["status"] = "pending"
        mutations.append(unknown_research_use)

        extra_field = _valid_policy()
        extra_field["rights"]["approval_pending"] = True
        mutations.append(extra_field)

        for policy in mutations:
            with self.subTest(policy=policy):
                with self.assertRaises(CapturePolicyError):
                    validate_capture_policy(policy)

    def test_load_rejects_invalid_json_without_echoing_contents(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "policy.json"
            target.write_text('{"api_key":"must-not-echo",', encoding="utf-8")
            with self.assertRaisesRegex(CapturePolicyError, "not valid JSON") as context:
                load_capture_policy(target)
        self.assertNotIn("must-not-echo", str(context.exception))

    def test_load_rejects_duplicate_decision_keys(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "policy.json"
            target.write_text(
                """{
                  "schema": "gex-terminal.capture-policy.v1",
                  "policy_id": "duplicate-policy",
                  "rights": {
                    "status": "licensed",
                    "basis": "reviewed",
                    "redistributable": false
                  },
                  "retention": {
                    "mode": "time_limited",
                    "days": 30,
                    "storage": "local",
                    "owner": "operator"
                  },
                  "redaction": {
                    "status": "required",
                    "profile": "normalized-v1",
                    "review_before_sharing": true
                  },
                  "research_use": {"status": "prohibited", "scope": "none"},
                  "research_use": {"status": "approved", "scope": "internal"}
                }""",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                CapturePolicyError,
                "duplicate field: research_use",
            ):
                load_capture_policy(target)

    def test_live_capture_requires_policy_and_replay_capture_does_not(self):
        live_config = _config("live")
        replay_config = _config("replay")
        no_policy = Namespace(
            record_session=True,
            capture_path=None,
            capture_policy=None,
        )
        with self.assertRaisesRegex(SystemExit, "requires --capture-policy"):
            _resolve_capture_policy_for_runtime(no_policy, live_config)
        self.assertIsNone(_resolve_capture_policy_for_runtime(no_policy, replay_config))

    def test_valid_policy_identity_is_available_to_live_and_replay_capture(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "policy.json"
            target.write_text(json.dumps(_valid_policy()), encoding="utf-8")
            args = Namespace(
                record_session=True,
                capture_path=None,
                capture_policy=str(target),
            )
            expected = capture_policy_identity(_valid_policy())
            self.assertEqual(
                _resolve_capture_policy_for_runtime(args, _config("live")), expected
            )
            self.assertEqual(
                _resolve_capture_policy_for_runtime(args, _config("replay")), expected
            )
            self.assertEqual(
                _capture_source_metadata(_config("replay"), expected)["capture_policy"],
                expected,
            )
            self.assertNotIn(
                "capture_policy", _capture_source_metadata(_config("replay"), None)
            )

    def test_cli_rejects_live_capture_without_or_with_invalid_policy(self):
        missing = _run_cli("--mode", "live", "--record-session")
        self.assertNotEqual(missing.returncode, 0)
        self.assertIn("requires --capture-policy", missing.stderr)

        with tempfile.TemporaryDirectory() as temp_dir:
            invalid_path = Path(temp_dir) / "invalid-policy.json"
            invalid_path.write_text(
                json.dumps({"schema": CAPTURE_POLICY_SCHEMA}), encoding="utf-8"
            )
            invalid = _run_cli(
                "--mode",
                "live",
                "--record-session",
                "--capture-policy",
                str(invalid_path),
            )
        self.assertNotEqual(invalid.returncode, 0)
        self.assertIn("Capture policy rejected", invalid.stderr)
        self.assertIn("is missing", invalid.stderr)

    def test_cli_validates_policy_without_starting_a_provider(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "policy.json"
            target.write_text(json.dumps(_valid_policy()), encoding="utf-8")
            result = _run_cli("capture-policy-validate", str(target))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Capture policy valid", result.stdout)
        self.assertIn("sha256=", result.stdout)


def _config(mode: str) -> GexConfig:
    return GexConfig(
        symbol="ES",
        symbols=("ES", "NQ"),
        data_mode=mode,
        data_provider="tradovate",
        contract_multiplier=50,
        risk_free_rate=0.045,
        days_to_expiry=0.25,
        refresh_interval_seconds=1.0,
        stale_after_seconds=10.0,
        replay_path="unused.jsonl",
        replay_delay_seconds=0.0,
        tradovate_environment="demo",
    )


def _run_cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    environment.pop("GEX_LOG_LEVEL", None)
    return subprocess.run(
        [sys.executable, "-m", "gex_terminal.cli", *arguments],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


if __name__ == "__main__":
    unittest.main()
