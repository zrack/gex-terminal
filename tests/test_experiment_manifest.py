import json
import tempfile
import unittest
from pathlib import Path

from gex_terminal.experiment_manifest import reproduce_experiment, run_experiment
from gex_terminal.package_data import provider_fixture_path


class ExperimentManifestTests(unittest.IsolatedAsyncioTestCase):
    async def test_enforces_as_of_against_price_action_observations(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            spec = json.loads(provider_fixture_path("experiment_spec_example.json").read_text())
            spec["input"] = str(provider_fixture_path("price_action_validation_example.json"))
            spec["as_of"] = "2026-08-01T00:00:00Z"
            spec_path = root / "spec.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "observations after experiment as_of"):
                await run_experiment(spec_path, root / "output")

    async def test_rejects_timezone_naive_as_of(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            spec = json.loads(provider_fixture_path("experiment_spec_example.json").read_text())
            spec["input"] = str(provider_fixture_path("price_action_validation_example.json"))
            spec["as_of"] = "2026-08-06T16:00:00"
            spec_path = root / "spec.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "include a timezone"):
                await run_experiment(spec_path, root / "output")

    async def test_run_and_reproduce_match_semantically(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            spec = json.loads(provider_fixture_path("experiment_spec_example.json").read_text())
            input_path = provider_fixture_path("price_action_validation_example.json")
            spec["input"] = str(input_path)
            spec_path = root / "spec.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            first = await run_experiment(spec_path, root / "first")
            second = await reproduce_experiment(root / "first" / "manifest.json", root / "second")
            self.assertTrue(second["reproduction"]["matched"])
            self.assertEqual(
                first["result"]["semantic_sha256"], second["result"]["semantic_sha256"]
            )
            self.assertEqual(first["result"]["predictive_validity"], "unmeasured")

    async def test_reproduction_rejects_changed_input_digest(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_path = root / "input.json"
            input_path.write_text(
                provider_fixture_path("price_action_validation_example.json").read_text(),
                encoding="utf-8",
            )
            spec = json.loads(provider_fixture_path("experiment_spec_example.json").read_text())
            spec["input"] = "input.json"
            spec_path = root / "spec.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            await run_experiment(spec_path, root / "first")
            input_path.write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "input digest changed"):
                await reproduce_experiment(root / "first" / "manifest.json", root / "second")


if __name__ == "__main__":
    unittest.main()
