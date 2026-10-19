import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.collect_ci_evidence import ARTIFACTS, CHECK_IDS, collect


class CiEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.inputs = self.root / "synthetic"
        self.inputs.mkdir()
        self.output = self.root / "retained"

    def write(self, name, data=b'{"synthetic": true}\n'):
        path = self.inputs / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def collect(self, outcomes=None):
        return collect(self.inputs, self.output, self.root, outcomes or {})

    def test_complete_allowlist_has_byte_hashes_and_excludes_unlisted_private_data(self):
        for name in ARTIFACTS:
            self.write(name)
        self.write(".env", b"API_TOKEN=private-token\n")
        self.write("gex-wheel-nq/private.json", b"private research")
        self.write("gex-wheel-wind-tunnel/discovered-break.json", b"unlisted complete receipt")
        self.write("debug.log", b"private debug output")
        with patch.dict(os.environ, {"GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "2",
                                     "GITHUB_SHA": "abc123", "PRIVATE_TOKEN": "never serialize"}):
            result = self.collect({name: "success" for name in CHECK_IDS})
        saved = json.loads((self.output / "manifest.json").read_text())
        self.assertEqual(saved, result)
        self.assertTrue(saved["summary"]["collection_complete"])
        self.assertEqual(saved["run"]["id"], "123")
        self.assertEqual(saved["run"]["attempt"], "2")
        self.assertIn("python", saved["runtime"])
        self.assertEqual({p.relative_to(self.output).as_posix() for p in self.output.rglob("*") if p.is_file()},
                         {*ARTIFACTS, "manifest.json"})
        for entry in saved["artifacts"]:
            retained = (self.output / entry["path"]).read_bytes()
            self.assertEqual(entry["sha256"], hashlib.sha256(retained).hexdigest())
            self.assertEqual(entry["bytes"], len(retained))
        text = (self.output / "manifest.json").read_text()
        self.assertNotIn("PRIVATE_TOKEN", text)
        self.assertNotIn("never serialize", text)
        self.assertNotIn(str(self.root), text)

    def test_partial_failure_retains_available_output_and_explicit_absence(self):
        self.write("gex-wheel-snapshot.json")
        result = self.collect({"tests": "success", "wheel": "failure", "lifecycle": "skipped"})
        self.assertFalse(result["summary"]["collection_complete"])
        self.assertEqual(result["summary"]["failed_checks"], ["wheel"])
        self.assertIn("lifecycle", result["summary"]["skipped_checks"])
        entries = {item["path"]: item for item in result["artifacts"]}
        self.assertEqual(entries["gex-wheel-snapshot.json"]["status"], "retained")
        self.assertEqual(entries["gex-wheel-faults.json"]["status"], "missing")
        self.assertEqual(entries["gex-wheel-faults.json"]["producer_outcome"], "failure")
        self.assertEqual(entries["gex-lifecycle.json"]["producer_outcome"], "skipped")

    def test_symlinked_file_and_directory_never_copy_external_bytes(self):
        private = self.root / "private"
        private.mkdir()
        (private / "manifest.json").write_text("PRIVATE")
        (self.inputs / "gex-wheel-doctor.json").symlink_to(private / "manifest.json")
        (self.inputs / "gex-wheel-demo").symlink_to(private, target_is_directory=True)
        result = self.collect()
        entries = {item["path"]: item for item in result["artifacts"]}
        self.assertEqual(entries["gex-wheel-doctor.json"]["status"], "rejected_symlink")
        self.assertEqual(entries["gex-wheel-demo/manifest.json"]["status"], "rejected_symlink")
        self.assertEqual(result["summary"]["retained_files"], 0)
        self.assertNotIn("PRIVATE", (self.output / "manifest.json").read_text())

    def test_file_and_aggregate_budgets_are_enforced_without_partial_file_copies(self):
        self.write("previews/demo.svg", b"x" * 17)
        self.write("previews/onboarding.svg", b"a" * 8)
        self.write("previews/manifest.json", b"b" * 8)
        self.write("gex-model-evidence.json", b"c" * 8)
        with patch("scripts.collect_ci_evidence.MAX_FILE_BYTES", 16), patch(
            "scripts.collect_ci_evidence.MAX_TOTAL_BYTES", 16
        ):
            result = self.collect()
        entries = {item["path"]: item for item in result["artifacts"]}
        self.assertEqual(entries["previews/demo.svg"]["status"], "rejected_file_limit")
        self.assertEqual(entries["gex-model-evidence.json"]["status"], "rejected_total_limit")
        self.assertEqual(result["summary"]["retained_bytes"], 16)
        self.assertFalse((self.output / "previews/demo.svg").exists())
        self.assertFalse((self.output / "gex-model-evidence.json").exists())

    def test_directory_and_empty_file_are_explicit_rejections(self):
        (self.inputs / "gex-wheel-doctor.json").mkdir()
        self.write("gex-wheel-snapshot.json", b"")
        result = self.collect()
        entries = {item["path"]: item for item in result["artifacts"]}
        self.assertEqual(entries["gex-wheel-doctor.json"]["status"], "rejected_nonregular")
        self.assertEqual(entries["gex-wheel-snapshot.json"]["status"], "rejected_empty")

    def test_existing_staging_directory_is_not_reused(self):
        self.output.mkdir()
        private = self.output / "private.txt"
        private.write_text("do not archive")
        with self.assertRaises(FileExistsError):
            self.collect()
        self.assertEqual(private.read_text(), "do not archive")

    def test_unrecognized_outcomes_cannot_become_an_environment_dump(self):
        for outcomes in ({"PRIVATE_TOKEN": "secret"}, {"wheel": "unexpected secret"}, []):
            with self.subTest(outcomes=outcomes), self.assertRaises(ValueError):
                collect(self.inputs, self.output, self.root, outcomes)
        self.assertFalse(self.output.exists())

    def test_cli_partial_collection_writes_manifest_but_fails_the_gate(self):
        script = Path(__file__).resolve().parents[1] / "scripts/collect_ci_evidence.py"
        marker = self.root / "github-output"
        completed = subprocess.run(
            [sys.executable, str(script), "--input-root", str(self.inputs),
             "--output-dir", str(self.output), "--source-root", str(self.root),
             "--github-output", str(marker)],
            text=True, capture_output=True, timeout=20,
        )
        self.assertEqual(completed.returncode, 1, completed.stderr)
        self.assertTrue((self.output / "manifest.json").is_file())
        self.assertEqual(json.loads(completed.stdout)["retained_files"], 0)
        self.assertEqual(marker.read_text(), "staged=true\n")

    def test_cli_refuses_to_authorize_upload_of_existing_staging(self):
        script = Path(__file__).resolve().parents[1] / "scripts/collect_ci_evidence.py"
        marker = self.root / "github-output"
        self.output.mkdir()
        (self.output / "private.txt").write_text("private")
        completed = subprocess.run(
            [sys.executable, str(script), "--input-root", str(self.inputs),
             "--output-dir", str(self.output), "--github-output", str(marker)],
            text=True, capture_output=True, timeout=20,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertFalse(marker.exists())

    def test_input_symlink_and_staging_inside_inputs_are_rejected(self):
        alias = self.root / "alias"
        alias.symlink_to(self.inputs, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink"):
            collect(alias, self.output, self.root, {})
        with self.assertRaisesRegex(ValueError, "outside"):
            collect(self.inputs, self.inputs / "retained", self.root, {})


if __name__ == "__main__":
    unittest.main()
