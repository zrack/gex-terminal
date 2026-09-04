import json
import tempfile
import unittest
from pathlib import Path

from gex_terminal.config import GexConfig
from gex_terminal.experiment_manifest import run_experiment
from gex_terminal.local_support import (
    SUPPORT_BUNDLE_SCHEMA,
    build_support_bundle,
    inspect_research_artifact,
    write_support_bundle,
)
from gex_terminal.package_data import provider_fixture_path


def _config(*, symbol: str = "PRIVATE-SYMBOL") -> GexConfig:
    return GexConfig(
        symbol=symbol,
        symbols=(symbol,),
        data_mode="replay",
        data_provider="replay",
        contract_multiplier=77,
        risk_free_rate=0.123456,
        days_to_expiry=9.876,
        refresh_interval_seconds=3.21,
        stale_after_seconds=45.67,
        replay_path="/private/local/research/source.jsonl",
        replay_delay_seconds=0.0,
        tradovate_environment="demo",
    )


def _doctor_report(secret: str, local_path: str) -> dict:
    return {
        "schema": "gex-terminal.doctor.v1",
        "generated_at": "2026-09-04T12:00:00Z",
        "application": {"name": "gex-terminal", "version": "0.4.0"},
        "execution": {
            "network_used": False,
            "live_adapter_constructed": False,
            "optional_sdk_imported": False,
            "persistent_state_created": False,
            "sensitive_values_included": False,
        },
        "checks": [
            {
                "id": "base-installation",
                "category": "runtime",
                "status": "pass",
                "summary": f"safe check; injected value={secret}",
                "action": f"inspect {local_path}",
                "details": {
                    "provider": "replay",
                    "readiness": "offline-certified",
                    "account_id": "account-should-not-appear",
                    "path": local_path,
                    "unix_location": "/etc/private-support.conf",
                    "windows_location": r"C:\\Users\\private\\support.ini",
                },
            }
        ],
        "summary": {
            "status": "pass",
            "exit_code": 0,
            "counts": {"pass": 1, "warning": 0, "fail": 0, "unverified": 0},
        },
        "evidence_ceiling": "offline diagnostics only",
    }


class LocalSupportTests(unittest.IsolatedAsyncioTestCase):
    async def _experiment(self, root: Path, experiment_id: str) -> Path:
        spec = json.loads(
            provider_fixture_path("experiment_spec_example.json").read_text()
        )
        spec["experiment_id"] = experiment_id
        spec["input"] = str(
            provider_fixture_path("price_action_validation_example.json")
        )
        spec_path = root / "spec.json"
        spec_path.write_text(json.dumps(spec), encoding="utf-8")
        target = root / "experiment"
        await run_experiment(spec_path, target)
        return target

    async def test_support_bundle_contains_only_redacted_bounded_shapes_and_identities(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            secret = "support-super-secret-value"
            account = "account-should-not-appear"
            artifact = await self._experiment(root, account)
            report = _doctor_report(secret, str(root / "private" / "doctor.log"))

            bundle = build_support_bundle(
                _config(),
                artifact_dirs=[artifact],
                doctor_report=report,
                environ={"DATABENTO_API_KEY": secret},
                generated_at="2026-09-04T12:01:00Z",
            )
            encoded = json.dumps(bundle, sort_keys=True)

            self.assertEqual(bundle["schema"], SUPPORT_BUNDLE_SCHEMA)
            self.assertFalse(bundle["privacy"]["raw_paths_included"])
            self.assertFalse(bundle["privacy"]["configuration_values_included"])
            self.assertFalse(bundle["privacy"]["log_files_included"])
            self.assertEqual(bundle["artifacts"][0]["kind"], "experiment")
            self.assertEqual(len(bundle["artifacts"][0]["id_fingerprint"]), 64)
            self.assertEqual(bundle["doctor"]["summary"]["exit_code"], 0)
            self.assertIn("[redacted]", encoded)
            self.assertIn("[redacted-local-path]", encoded)
            for forbidden in (
                secret,
                account,
                str(root),
                _config().symbol,
                _config().replay_path,
                "/etc/private-support.conf",
                r"C:\\Users\\private\\support.ini",
                "0.123456",
                "9.876",
            ):
                self.assertNotIn(forbidden, encoded)

            output = root / "support.json"
            self.assertEqual(write_support_bundle(bundle, output), output)
            with self.assertRaisesRegex(ValueError, "already exists"):
                write_support_bundle(bundle, output)

    async def test_support_bundle_rejects_unbounded_or_unknown_doctor_contract(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            artifact = await self._experiment(root, "bounded-doctor")
            report = _doctor_report("safe", "/tmp/safe")
            report["checks"] = report["checks"] * 65
            with self.assertRaisesRegex(ValueError, "at most 64"):
                build_support_bundle(
                    _config(),
                    artifact_dirs=[artifact],
                    doctor_report=report,
                    environ={},
                )

            report = _doctor_report("safe", "/tmp/safe")
            report["schema"] = "gex-terminal.doctor.v999"
            with self.assertRaisesRegex(ValueError, "doctor report schema"):
                build_support_bundle(
                    _config(),
                    artifact_dirs=[artifact],
                    doctor_report=report,
                    environ={},
                )

            report = _doctor_report("safe", "/tmp/safe")
            report["execution"]["network_used"] = True
            with self.assertRaisesRegex(ValueError, "offline privacy-safe"):
                build_support_bundle(
                    _config(),
                    artifact_dirs=[artifact],
                    doctor_report=report,
                    environ={},
                )

            report = _doctor_report("safe", "/tmp/safe")
            report["summary"]["counts"]["pass"] = 2
            with self.assertRaisesRegex(ValueError, "counts do not match"):
                build_support_bundle(
                    _config(),
                    artifact_dirs=[artifact],
                    doctor_report=report,
                    environ={},
                )

    async def test_artifact_inventory_rejects_report_drift_and_symlinks(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            artifact = await self._experiment(root, "drift-check")
            inventory = inspect_research_artifact(artifact)
            self.assertEqual(inventory["kind"], "experiment")

            report_path = artifact / "report.json"
            report_path.write_text('{"changed":true}\n', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "semantic result digest"):
                inspect_research_artifact(artifact)

            link_root = root / "linked"
            link_root.mkdir()
            (link_root / "manifest.json").symlink_to(artifact / "manifest.json")
            with self.assertRaisesRegex(ValueError, "symlinks"):
                inspect_research_artifact(link_root)


if __name__ == "__main__":
    unittest.main()
