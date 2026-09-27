import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts import refresh_previews as previews


class PreviewSafetyTests(unittest.TestCase):
    def test_environment_allowlist_drops_configuration_and_credentials(self):
        environment = previews.clean_environment({
            "PATH": "/bin", "GEX_DATA_MODE": "live", "GEX_SYMBOL": "NQ",
            "DATABENTO_API_KEY": "never-retain-me", "TRADOVATE_PASSWORD": "secret",
            "PYTHONPATH": "/untrusted", "HOME": "/private", "LANG": "ar_EG",
        })
        self.assertEqual(set(environment), {"PATH", "LANG", "TZ", "PYTHONNOUSERSITE"})
        command = previews.source_command(Path("/source"), ["doctor", "--json"])
        self.assertEqual(command[:3], [sys.executable, "-I", "-c"])
        self.assertEqual(command[-3:], ["/source", "doctor", "--json"])

    def test_existing_output_and_symlink_are_rejected_without_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            existing = root / "study-bundle"
            existing.mkdir()
            retained = existing / "frozen.txt"
            retained.write_text("preserve this study", encoding="utf-8")
            link = root / "linked-output"
            link.symlink_to(existing, target_is_directory=True)
            for path in (existing, link):
                with self.subTest(path=path), self.assertRaises(FileExistsError):
                    previews.refresh(path)
            self.assertEqual(retained.read_text(), "preserve this study")
            self.assertEqual(list(existing.iterdir()), [retained])

    def test_source_identity_excludes_cache_files_and_includes_ui_styles(self):
        identity = previews.source_identity(previews.ROOT, previews.clean_environment(os.environ))
        self.assertTrue(identity["bundled_input_sha256"])
        self.assertTrue(all(Path(name).suffix in {".json", ".jsonl", ".csv"}
                            for name in identity["bundled_input_sha256"]))
        styles = list((previews.ROOT / "gex_terminal").rglob("*.tcss"))
        for style in styles:
            self.assertIn(style.relative_to(previews.ROOT).as_posix(), identity["source_sha256"])

    def test_command_failure_retains_manifest_without_diagnostics_or_assets(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "failed"
            failure = subprocess.CompletedProcess([], 23, "secret stdout", "private stderr")
            with patch.object(previews, "source_identity", return_value={"commit": "test"}), \
                    patch.object(previews, "runtime_identity", return_value={}), \
                    patch.object(previews.subprocess, "run", return_value=failure), \
                    patch.object(previews, "write_assets") as write_assets:
                with self.assertRaisesRegex(RuntimeError, "failed with exit 23"):
                    previews.refresh(output, update_assets=True)
            write_assets.assert_not_called()
            serialized = (output / "manifest.json").read_text()
            report = json.loads(serialized)
            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["commands"][0]["exit_code"], 23)
            self.assertNotIn("secret stdout", serialized)
            self.assertNotIn("private stderr", serialized)

    def test_asset_destinations_are_validated_before_any_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "assets").mkdir()
            staged = root / "staged"
            staged.mkdir()
            target = root / "assets" / previews.ASSETS["demo.svg"]
            target.write_text("old asset")
            (staged / "demo.svg").write_text("new demo")
            (staged / "onboarding.svg").write_text("new onboarding")
            with self.assertRaisesRegex(ValueError, "existing regular file"):
                previews.write_assets(staged, root)
            self.assertEqual(target.read_text(), "old asset")

    def test_timeout_finishes_command_status_without_retaining_diagnostics(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "timeout"
            with patch.object(previews, "source_identity", return_value={"commit": "test"}), \
                    patch.object(previews, "runtime_identity", return_value={}), \
                    patch.object(previews.subprocess, "run", side_effect=subprocess.TimeoutExpired(
                        "example", 180, output="private stdout", stderr="private stderr")):
                with self.assertRaises(subprocess.TimeoutExpired):
                    previews.refresh(output)
            serialized = (output / "manifest.json").read_text()
            report = json.loads(serialized)
            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["commands"][0]["status"], "failed")
            self.assertEqual(report["commands"][0]["failure_type"], "TimeoutExpired")
            self.assertNotIn("private stdout", serialized)
            self.assertNotIn("private stderr", serialized)

    def test_real_source_previews_ignore_caller_environment_and_reproduce_metrics(self):
        with tempfile.TemporaryDirectory() as directory:
            caller = Path(directory)
            (caller / ".env").write_text(
                "GEX_SYMBOL=DO_NOT_USE_PRIVATE_SYMBOL\nGEX_DATA_MODE=live\n"
                "GEX_REPLAY_PATH=/private/provider-data\n", encoding="utf-8",
            )
            environment = dict(os.environ, GEX_SYMBOL="DO_NOT_USE_PRIVATE_SYMBOL",
                               GEX_DATA_MODE="live", GEX_CONTRACT_MULTIPLIER="invalid",
                               DATABENTO_API_KEY="PREVIEW_SECRET_MUST_NOT_APPEAR",
                               PYTHONPATH="/untrusted")
            reports = []
            for index in range(2):
                output = caller / f"preview-{index}"
                result = subprocess.run(
                    [sys.executable, "-I", str(previews.ROOT / "scripts" / "refresh_previews.py"),
                     "--output-dir", str(output), "--include-onboarding"],
                    cwd=caller, env=environment, text=True, capture_output=True, timeout=180,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                serialized = (output / "manifest.json").read_text()
                report = json.loads(serialized)
                self.assertEqual(report["status"], "passed")
                self.assertEqual(report["session"], "zero-gamma-flip")
                self.assertEqual(report["terminal_dimensions"]["demo_pack"],
                                 {"columns": 180, "rows": 54})
                self.assertEqual(report["terminal_dimensions"]["onboarding"],
                                 {"columns": 180, "rows": 64})
                self.assertEqual(report["demo_source"]["symbol"], "ES")
                self.assertTrue(report["demo_source"]["authorization"]["synthetic"])
                self.assertEqual(report["updated_repository_assets"], [])
                self.assertTrue(report["source_unchanged_during_generation"])
                self.assertNotEqual(Path(report["working_directory"]), caller)
                self.assertTrue(report["demo_receipt_content_sha256"])
                for name, identity in report["assets"].items():
                    self.assertEqual(identity["sha256"], previews.sha256(output / name))
                    self.assertNotIn("DO_NOT_USE_PRIVATE_SYMBOL", (output / name).read_text())
                self.assertNotIn("PREVIEW_SECRET_MUST_NOT_APPEAR", serialized)
                reports.append(report)
            for name in ("snapshot.json", "model-comparison.json"):
                self.assertEqual(reports[0]["demo_receipt_content_sha256"][name],
                                 reports[1]["demo_receipt_content_sha256"][name])
            self.assertEqual(reports[0]["demo_source"], reports[1]["demo_source"])
            # SVG timing/IDs are not the numerical determinism contract.
            self.assertEqual(reports[0]["assets"]["demo.svg"]["sha256"],
                             reports[1]["assets"]["demo.svg"]["sha256"])


if __name__ == "__main__":
    unittest.main()
