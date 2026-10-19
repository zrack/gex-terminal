import argparse
import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gex_terminal import __version__
from gex_terminal.cli import (
    parse_args,
    research_backup_command,
    research_backup_verify_command,
    research_restore_command,
    research_retention_apply_command,
    research_retention_plan_command,
    support_bundle_command,
)
from gex_terminal.config import GexConfig
from gex_terminal.research_journal import ENTRY_SCHEMA


def _config() -> GexConfig:
    return GexConfig(
        symbol="PRIVATE-SYMBOL",
        symbols=("PRIVATE-SYMBOL",),
        data_mode="demo",
        data_provider="tradovate",
        contract_multiplier=50,
        risk_free_rate=0.045,
        days_to_expiry=0.25,
        refresh_interval_seconds=1.0,
        stale_after_seconds=10.0,
        replay_path="/private/operator/replay.jsonl",
        replay_delay_seconds=0.0,
        tradovate_environment="demo",
    )


def _doctor_report() -> dict:
    return {
        "schema": "gex-terminal.doctor.v1",
        "generated_at": "2026-09-04T12:00:00Z",
        "application": {"name": "gex-terminal", "version": __version__},
        "execution": {
            "network_used": False,
            "live_adapter_constructed": False,
            "optional_sdk_imported": False,
            "persistent_state_created": False,
            "sensitive_values_included": False,
        },
        "checks": [
            {
                "id": "configuration.shape",
                "category": "configuration",
                "status": "pass",
                "summary": "Configuration shape is valid; values are omitted.",
                "details": {"values_disclosed": False},
            }
        ],
        "summary": {
            "status": "pass",
            "exit_code": 0,
            "counts": {"pass": 1, "warning": 0, "fail": 0, "unverified": 0},
        },
        "evidence_ceiling": "offline diagnostics only",
    }


class LocalSupportCliTests(unittest.TestCase):
    @staticmethod
    def _journal(root: Path, name: str) -> Path:
        target = root / name
        entries = target / "entries"
        entries.mkdir(parents=True)
        entry = {
            "schema": ENTRY_SCHEMA,
            "id": f"{name}-entry",
            "generated_at": "2026-09-04T12:00:00Z",
            "summary": {"label": "synthetic CLI lifecycle test"},
        }
        (entries / "entry.json").write_text(json.dumps(entry), encoding="utf-8")
        return target

    def test_parser_routes_all_local_support_commands(self):
        cases = (
            (["support-bundle", "support.json", "artifact"], "support-bundle"),
            (["research-backup", "artifact", "backup"], "research-backup"),
            (["research-backup-verify", "backup"], "research-backup-verify"),
            (["research-restore", "backup", "restored"], "research-restore"),
            (
                [
                    "research-retention-plan",
                    "plan.json",
                    "2026-01-01T00:00:00Z",
                    "artifact",
                    "--retention-backup",
                    "backup",
                ],
                "research-retention-plan",
            ),
            (
                [
                    "research-retention-apply",
                    "plan.json",
                    "--confirm-plan-sha256",
                    "0" * 64,
                ],
                "research-retention-apply",
            ),
        )
        for arguments, expected in cases:
            with self.subTest(command=expected), patch(
                "sys.argv", ["gex-terminal", *arguments]
            ):
                self.assertEqual(parse_args().command, expected)

    def test_support_command_writes_reviewable_redacted_json(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            journal = self._journal(root, "journal")
            output = root / "support.json"
            args = argparse.Namespace(
                command_path=str(output), command_args=[str(journal)]
            )
            stdout = io.StringIO()
            with patch(
                "gex_terminal.local_support._build_doctor_report",
                return_value=_doctor_report(),
            ), contextlib.redirect_stdout(stdout):
                support_bundle_command(_config(), args)

            bundle = json.loads(output.read_text())
            encoded = json.dumps(bundle)
            self.assertIn("Saved redacted support bundle", stdout.getvalue())
            self.assertEqual(bundle["artifacts"][0]["kind"], "research_journal")
            self.assertNotIn(str(root), encoded)
            self.assertNotIn("PRIVATE-SYMBOL", encoded)

    def test_private_cli_round_trip_and_separate_retention_confirmation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = self._journal(root, "source")
            backup = root / "backup"
            restored = root / "restored"
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                research_backup_command(
                    argparse.Namespace(
                        command_path=str(source), command_args=[str(backup)]
                    )
                )
                research_backup_verify_command(
                    argparse.Namespace(command_path=str(backup))
                )
                research_restore_command(
                    argparse.Namespace(
                        command_path=str(backup), command_args=[str(restored)]
                    )
                )
            self.assertTrue(restored.is_dir())
            self.assertIn("restored and verified", output.getvalue())

            old = 1_600_000_000_000_000_000
            for path in restored.rglob("*"):
                if path.is_file():
                    os.utime(path, ns=(old, old))
            plan_path = root / "plan.json"
            research_retention_plan_command(
                argparse.Namespace(
                    command_path=str(plan_path),
                    command_args=["2026-01-01T00:00:00Z", str(restored)],
                    retention_backups=[str(backup)],
                )
            )
            plan = json.loads(plan_path.read_text())
            research_retention_apply_command(
                argparse.Namespace(
                    command_path=str(plan_path),
                    confirm_plan_sha256=plan["plan_sha256"],
                )
            )
            self.assertFalse(restored.exists())


if __name__ == "__main__":
    unittest.main()
