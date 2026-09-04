import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from gex_terminal import __version__
from gex_terminal.config import GexConfig
from gex_terminal.demo_lab import (
    DEMO_LAB_SCHEMA,
    build_demo_lab,
    compute_replay_snapshot,
    reproduce_demo_lab,
    verify_demo_lab,
)
from gex_terminal.demo_lab_receipt import (
    REVIEW_RECEIPT_SCHEMA,
    RUNTIME_SCHEMA,
    SUPPORTED_DEMO_LAB_PRODUCERS,
    SUPPORTED_DEMO_LAB_READERS,
    file_sha256,
    stable_json_sha256,
)
from gex_terminal.replay_catalog import replay_session_for_name


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _config():
    return GexConfig(
        symbol="ES",
        symbols=("ES", "NQ", "SPX", "QQQ"),
        data_mode="demo",
        data_provider="tradovate",
        contract_multiplier=50,
        risk_free_rate=0.045,
        days_to_expiry=0.01,
        refresh_interval_seconds=1.0,
        stale_after_seconds=10.0,
        replay_path="sample_data/demo_replay.jsonl",
        replay_delay_seconds=0.0,
        tradovate_environment="demo",
    )


def _write_signed_receipt(path: Path, receipt: dict) -> None:
    receipt.pop("receipt_sha256", None)
    receipt["receipt_sha256"] = stable_json_sha256(receipt)
    path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _run_cli(*arguments: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    for key in tuple(environment):
        if key.startswith("GEX_"):
            environment.pop(key)
    existing_pythonpath = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(PROJECT_ROOT), existing_pythonpath) if part
    )
    return subprocess.run(
        [sys.executable, "-m", "gex_terminal.cli", *arguments],
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


class DemoLabTests(unittest.IsolatedAsyncioTestCase):
    async def test_compute_replay_snapshot_keeps_replay_status_without_credentials(self):
        snapshot, consumer, _ = await compute_replay_snapshot(_config())

        self.assertEqual(snapshot["symbol"], "ES")
        self.assertGreater(snapshot["spot"], 0)
        self.assertEqual(consumer.runtime_status, "REPLAY")

    async def test_build_demo_lab_writes_shareable_artifact_pack(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "demo_lab"
            manifest = await build_demo_lab(
                replace(_config(), symbol="NQ", contract_multiplier=20),
                output_dir,
                replay_session_name="zero-gamma-flip",
                screenshot_width=140,
                screenshot_height=42,
            )

            self.assertEqual(manifest["schema"], DEMO_LAB_SCHEMA)
            self.assertEqual(manifest["replay_session"]["name"], "zero-gamma-flip")
            self.assertEqual(manifest["summary"]["symbol"], "ES")
            self.assertEqual(manifest["inputs"]["contract_multiplier"], 50)
            self.assertEqual(manifest["output_dir"], ".")
            self.assertEqual(len(manifest["artifacts"]), 20)
            self.assertEqual(manifest["provider_fixture_lab"]["failed"], 0)

            color_svg = output_dir / "gex-terminal-color.svg"
            terminal_svg = output_dir / "terminal-screenshot.svg"
            manifest_path = output_dir / "manifest.json"
            readme_path = output_dir / "README.md"

            self.assertTrue(color_svg.exists())
            self.assertTrue(terminal_svg.exists())
            self.assertTrue(manifest_path.exists())
            self.assertTrue(readme_path.exists())
            self.assertIn("#38bdf8", color_svg.read_text())
            terminal_svg_text = terminal_svg.read_text()
            self.assertIn("#38bdf8", terminal_svg_text)
            self.assertIn("#4ade80", terminal_svg_text)
            readme = readme_path.read_text()
            self.assertIn("gex-terminal Demo Lab", readme)
            self.assertIn("manifest.json", readme)
            self.assertEqual(json.loads(manifest_path.read_text())["schema"], DEMO_LAB_SCHEMA)

    async def test_nq_portable_loop_separates_models_and_verifies_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "nq-pack"
            manifest = await build_demo_lab(
                _config(),
                output_dir,
                replay_session_name="nq-research-loop",
                screenshot_width=140,
                screenshot_height=42,
            )
            verification = verify_demo_lab(output_dir)
            receipt = verification["receipt"]
            comparison = json.loads(
                (output_dir / "position-model-comparison.json").read_text(encoding="utf-8")
            )

            self.assertEqual(manifest["summary"]["symbol"], "NQ")
            self.assertEqual(manifest["inputs"]["contract_multiplier"], 20)
            self.assertEqual(manifest["source"]["normalized_schema_versions"], [2])
            self.assertEqual(
                manifest["source"]["position_sources"],
                ["open_interest", "trade_volume"],
            )
            self.assertEqual(verification["artifact_count"], 20)
            self.assertEqual(verification["bound_artifact_count"], 19)
            self.assertEqual(receipt["schema"], REVIEW_RECEIPT_SCHEMA)
            self.assertIn("0.4.0", SUPPORTED_DEMO_LAB_PRODUCERS[REVIEW_RECEIPT_SCHEMA])
            self.assertIn(__version__, SUPPORTED_DEMO_LAB_PRODUCERS[REVIEW_RECEIPT_SCHEMA])
            self.assertIn(__version__, SUPPORTED_DEMO_LAB_READERS[RUNTIME_SCHEMA])
            self.assertEqual(receipt["source"]["symbol"], "NQ")
            self.assertEqual(receipt["source"]["contract_multiplier"], 20)
            self.assertEqual(receipt["source"]["authorization"]["live_data"], False)
            self.assertEqual(receipt["source"]["authorization"]["credentials"], False)
            self.assertEqual(
                set(comparison["models"]),
                {"open_interest", "raw_trade_volume", "directionalized_trade_volume"},
            )
            self.assertTrue(comparison["result"]["models_may_not_be_summed"])
            self.assertEqual(comparison["result"]["predictive_validity"], "unmeasured")
            self.assertEqual(
                (output_dir / "inputs" / "replay.jsonl").read_bytes(),
                Path(replay_session_for_name("nq-research-loop").path).read_bytes(),
            )

            readme = (output_dir / "README.md").read_text(encoding="utf-8")
            section_offsets = [
                readme.index(f"## {name}")
                for name in ("Today", "Explain", "Compare", "Replay", "Review")
            ]
            self.assertEqual(section_offsets, sorted(section_offsets))
            self.assertIn("Position models may not be summed", readme)
            self.assertIn("Python helpers are experimental", readme)
            for path in output_dir.rglob("*"):
                if path.is_file():
                    self.assertNotIn(str(output_dir.resolve()), path.read_text(encoding="utf-8"))

    async def test_copied_pack_reproduces_through_public_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            original = base / "original"
            copied = base / "detached" / "copied-pack"
            reproduced = base / "reproduced"
            await build_demo_lab(
                _config(),
                original,
                replay_session_name="nq-research-loop",
                screenshot_width=140,
                screenshot_height=42,
            )
            shutil.copytree(original, copied)

            verify_result = _run_cli("demo-lab", "verify", str(copied), cwd=base)
            self.assertEqual(verify_result.returncode, 0, verify_result.stderr)
            reproduce_result = _run_cli(
                "demo-lab",
                "reproduce",
                str(copied),
                str(reproduced),
                "--screenshot-width",
                "140",
                "--screenshot-height",
                "42",
                cwd=base,
            )
            self.assertEqual(reproduce_result.returncode, 0, reproduce_result.stderr)

            original_receipt = verify_demo_lab(copied)["receipt"]
            reproduced_receipt = verify_demo_lab(reproduced)["receipt"]
            self.assertEqual(
                original_receipt["source"]["sha256"],
                reproduced_receipt["source"]["sha256"],
            )
            self.assertEqual(
                original_receipt["model"]["profile_sha256"],
                reproduced_receipt["model"]["profile_sha256"],
            )
            self.assertEqual(original_receipt["content"], reproduced_receipt["content"])

    async def test_verifier_fails_closed_on_tampering_and_incompatible_contracts(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = base / "source"
            await build_demo_lab(
                _config(),
                source,
                replay_session_name="nq-research-loop",
                screenshot_width=140,
                screenshot_height=42,
            )

            artifact_pack = base / "artifact"
            shutil.copytree(source, artifact_pack)
            (artifact_pack / "snapshot.json").write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "artifact (size|content) changed"):
                verify_demo_lab(artifact_pack)

            extra_pack = base / "extra"
            shutil.copytree(source, extra_pack)
            (extra_pack / "undeclared.txt").write_text("not declared\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "artifacts do not match"):
                verify_demo_lab(extra_pack)

            missing_pack = base / "missing"
            shutil.copytree(source, missing_pack)
            (missing_pack / "tradingview-overlay.csv").unlink()
            with self.assertRaisesRegex(ValueError, "artifacts do not match"):
                verify_demo_lab(missing_pack)

            schema_pack = base / "receipt-schema"
            shutil.copytree(source, schema_pack)
            receipt_path = schema_pack / "review-receipt.json"
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            receipt["schema"] = "gex-terminal.demo-lab-review-receipt.v999"
            _write_signed_receipt(receipt_path, receipt)
            with self.assertRaisesRegex(ValueError, "receipt schema is unsupported"):
                verify_demo_lab(schema_pack)

            runtime_pack = base / "runtime"
            shutil.copytree(source, runtime_pack)
            receipt_path = runtime_pack / "review-receipt.json"
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            receipt["runtime"]["python_major_minor"] = "0.0"
            _write_signed_receipt(receipt_path, receipt)
            with self.assertRaisesRegex(ValueError, "runtime contract is incompatible"):
                verify_demo_lab(runtime_pack)

            producer_pack = base / "producer"
            shutil.copytree(source, producer_pack)
            receipt_path = producer_pack / "review-receipt.json"
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            receipt["application"]["version"] = "999.0.0"
            _write_signed_receipt(receipt_path, receipt)
            with self.assertRaisesRegex(ValueError, "producer version is unsupported"):
                verify_demo_lab(producer_pack)

            model_pack = base / "model"
            shutil.copytree(source, model_pack)
            receipt_path = model_pack / "review-receipt.json"
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            receipt["model"]["profile"]["symbol"] = "ES"
            receipt["model"]["profile_sha256"] = stable_json_sha256(
                receipt["model"]["profile"]
            )
            _write_signed_receipt(receipt_path, receipt)
            with self.assertRaisesRegex(ValueError, "model identity conflicts"):
                verify_demo_lab(model_pack)

            identity_pack = base / "identity"
            shutil.copytree(source, identity_pack)
            receipt_path = identity_pack / "review-receipt.json"
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            receipt["source"]["contract_multiplier"] = 50
            _write_signed_receipt(receipt_path, receipt)
            with self.assertRaisesRegex(ValueError, "source identity conflicts"):
                verify_demo_lab(identity_pack)

            source_pack = base / "source-schema"
            shutil.copytree(source, source_pack)
            copied_input = source_pack / "inputs" / "replay.jsonl"
            lines = copied_input.read_text(encoding="utf-8").splitlines()
            first = json.loads(lines[0])
            first["schema_version"] = 999
            lines[0] = json.dumps(first, separators=(",", ":"))
            copied_input.write_text("\n".join(lines) + "\n", encoding="utf-8")
            receipt_path = source_pack / "review-receipt.json"
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            receipt["source"]["bytes"] = copied_input.stat().st_size
            receipt["source"]["sha256"] = file_sha256(copied_input)
            input_artifact = next(
                row for row in receipt["artifacts"] if row["path"] == "inputs/replay.jsonl"
            )
            input_artifact["bytes"] = copied_input.stat().st_size
            input_artifact["sha256"] = file_sha256(copied_input)
            receipt["pack"]["content_sha256"] = stable_json_sha256(receipt["artifacts"])
            _write_signed_receipt(receipt_path, receipt)
            with self.assertRaisesRegex(ValueError, "schema|unsupported"):
                verify_demo_lab(source_pack)


if __name__ == "__main__":
    unittest.main()
