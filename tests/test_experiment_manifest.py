import copy
import hashlib
import io
import json
import tempfile
import unittest
from argparse import Namespace
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from gex_terminal.cli import experiment_reproduce_command
from gex_terminal.experiment_manifest import (
    EXPERIMENT_CANONICALIZATION,
    EXPERIMENT_EVIDENCE_CEILING,
    EXPERIMENT_EVIDENCE_POLICY,
    EXPERIMENT_IDENTITY_SCHEMA,
    EXPERIMENT_MANIFEST_SCHEMA_V1,
    EXPERIMENT_MANIFEST_SCHEMA_V2,
    EXPERIMENT_RUNTIME_CONTRACT,
    canonical_sha256,
    reproduce_experiment,
    run_experiment,
    semantic_sha256,
)
from gex_terminal.package_data import provider_fixture_path
from gex_terminal.price_action_validation import load_price_action_report


class ExperimentManifestTests(unittest.IsolatedAsyncioTestCase):
    async def _run_example(self, root: Path) -> tuple[dict, Path]:
        spec = json.loads(provider_fixture_path("experiment_spec_example.json").read_text())
        spec["input"] = str(provider_fixture_path("price_action_validation_example.json"))
        spec_path = root / "spec.json"
        spec_path.write_text(json.dumps(spec), encoding="utf-8")
        manifest = await run_experiment(spec_path, root / "first")
        return manifest, root / "first" / "manifest.json"

    @staticmethod
    def _write_manifest(root: Path, name: str, manifest: dict) -> Path:
        target = root / name
        target.write_text(json.dumps(manifest), encoding="utf-8")
        return target

    @staticmethod
    def _legacy_v1_manifest(v2: dict, *, version: str = "0.4.0") -> dict:
        return {
            "schema": EXPERIMENT_MANIFEST_SCHEMA_V1,
            "experiment_id": v2["experiment_id"],
            "generated_at": v2["generated_at"],
            "workflow": v2["workflow"],
            "implementation": {
                "package": "gex-terminal",
                "version": version,
                "python": v2["implementation"]["python"],
            },
            "spec_reference": v2["spec_reference"],
            "source_root": v2["source_root"],
            "experiment_spec": copy.deepcopy(v2["experiment_spec"]),
            "profile_sha256": semantic_sha256(v2["experiment_spec"]["model_profile"]),
            "input": copy.deepcopy(v2["input"]),
            "result": copy.deepcopy(v2["result"]),
            "reproduction": {
                "expected_semantic_sha256": None,
                "matched": True,
            },
            "evidence_ceiling": EXPERIMENT_EVIDENCE_CEILING,
        }

    @staticmethod
    def _refresh_experiment_sha256(manifest: dict) -> None:
        identity = manifest["identity"]
        identity["experiment_sha256"] = canonical_sha256({
            "schema": EXPERIMENT_IDENTITY_SCHEMA,
            "canonicalization": EXPERIMENT_CANONICALIZATION,
            "manifest_schema": EXPERIMENT_MANIFEST_SCHEMA_V2,
            "profile_sha256": identity["profile_sha256"],
            "experiment_spec_sha256": identity["experiment_spec_sha256"],
            "input": {
                "sha256": manifest["input"]["sha256"],
                "bytes": manifest["input"]["bytes"],
            },
            "implementation": manifest["implementation"],
            "result": {
                "semantic_sha256": manifest["result"]["semantic_sha256"],
                "predictive_validity": "unmeasured",
            },
            "evidence_policy": EXPERIMENT_EVIDENCE_POLICY,
        })

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
            first, manifest_path = await self._run_example(root)
            second = await reproduce_experiment(root / "first" / "manifest.json", root / "second")
            self.assertEqual(first["schema"], EXPERIMENT_MANIFEST_SCHEMA_V2)
            self.assertEqual(first["identity"]["schema"], EXPERIMENT_IDENTITY_SCHEMA)
            self.assertEqual(
                first["identity"]["canonicalization"], EXPERIMENT_CANONICALIZATION
            )
            self.assertEqual(
                first["implementation"]["runtime_contract"],
                EXPERIMENT_RUNTIME_CONTRACT,
            )
            self.assertTrue(second["reproduction"]["matched"])
            self.assertEqual(second["reproduction"]["identity_validation"], "complete")
            self.assertEqual(
                second["reproduction"]["source_manifest_schema"],
                EXPERIMENT_MANIFEST_SCHEMA_V2,
            )
            self.assertEqual(
                second["reproduction"]["source_manifest_sha256"],
                hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            )
            self.assertEqual(
                first["result"]["semantic_sha256"], second["result"]["semantic_sha256"]
            )
            self.assertEqual(
                first["identity"]["experiment_sha256"],
                second["identity"]["experiment_sha256"],
            )
            self.assertEqual(first["result"]["predictive_validity"], "unmeasured")

    async def test_v2_rejects_profile_and_complete_spec_relabeling_before_execution(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first, _ = await self._run_example(root)
            cases = (
                (
                    "profile",
                    lambda manifest: manifest["experiment_spec"]["model_profile"].__setitem__(
                        "profile_id", "relabeled-profile"
                    ),
                    "profile identity",
                ),
                (
                    "split",
                    lambda manifest: manifest["experiment_spec"].__setitem__("split", "train"),
                    "spec identity",
                ),
                (
                    "outcome",
                    lambda manifest: manifest["experiment_spec"].__setitem__(
                        "outcome_definition", "relabeled outcome"
                    ),
                    "spec identity",
                ),
                (
                    "costs",
                    lambda manifest: manifest["experiment_spec"].__setitem__(
                        "cost_assumptions", {"fees": "zero"}
                    ),
                    "spec identity",
                ),
                (
                    "as-of",
                    lambda manifest: manifest["experiment_spec"].__setitem__(
                        "as_of", "2026-08-07T16:00:00Z"
                    ),
                    "spec identity",
                ),
                (
                    "predictive-validity",
                    lambda manifest: manifest["experiment_spec"].__setitem__(
                        "predictive_validity", "validated"
                    ),
                    "predictive_validity must be unmeasured",
                ),
            )
            for name, mutate, message in cases:
                with self.subTest(name=name):
                    manifest = copy.deepcopy(first)
                    mutate(manifest)
                    manifest_path = self._write_manifest(root, f"{name}.json", manifest)
                    output = root / f"{name}-output"
                    with patch(
                        "gex_terminal.experiment_manifest.load_price_action_report"
                    ) as workflow:
                        with self.assertRaisesRegex(ValueError, message):
                            await reproduce_experiment(manifest_path, output)
                    workflow.assert_not_called()
                    self.assertFalse(output.exists())

    async def test_v2_rejects_unknown_contract_fields_before_execution(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first, _ = await self._run_example(root)
            cases = (
                (
                    "manifest",
                    lambda manifest: manifest.__setitem__("extension", "ignored"),
                    "experiment manifest contains unsupported fields",
                ),
                (
                    "spec",
                    lambda manifest: manifest["experiment_spec"].__setitem__(
                        "extension", "ignored"
                    ),
                    "experiment spec contains unsupported fields",
                ),
                (
                    "profile",
                    lambda manifest: manifest["experiment_spec"][
                        "model_profile"
                    ].__setitem__("extension", "ignored"),
                    "experiment model_profile contains unsupported fields",
                ),
                (
                    "implementation",
                    lambda manifest: manifest["implementation"].__setitem__(
                        "extension", "ignored"
                    ),
                    "experiment implementation contains unsupported fields",
                ),
                (
                    "identity",
                    lambda manifest: manifest["identity"].__setitem__(
                        "extension", "ignored"
                    ),
                    "experiment identity contains unsupported fields",
                ),
            )
            for name, mutate, message in cases:
                with self.subTest(name=name):
                    manifest = copy.deepcopy(first)
                    mutate(manifest)
                    manifest_path = self._write_manifest(
                        root, f"unknown-{name}.json", manifest
                    )
                    output = root / f"unknown-{name}-output"
                    with patch(
                        "gex_terminal.experiment_manifest.load_price_action_report"
                    ) as workflow:
                        with self.assertRaisesRegex(ValueError, message):
                            await reproduce_experiment(manifest_path, output)
                    workflow.assert_not_called()
                    self.assertFalse(output.exists())

    async def test_reproduction_refuses_nonempty_output_without_overwrite(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, manifest_path = await self._run_example(root)
            report_path = root / "first" / "report.json"
            original_manifest = manifest_path.read_bytes()
            original_report = report_path.read_bytes()

            with patch(
                "gex_terminal.experiment_manifest.load_price_action_report"
            ) as workflow:
                with self.assertRaisesRegex(ValueError, "output directory must be empty"):
                    await reproduce_experiment(manifest_path, root / "first")

            workflow.assert_not_called()
            self.assertEqual(manifest_path.read_bytes(), original_manifest)
            self.assertEqual(report_path.read_bytes(), original_report)

    async def test_v2_rejects_mirror_identity_and_implementation_changes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first, _ = await self._run_example(root)
            cases = (
                (
                    "experiment-id",
                    lambda manifest: manifest.__setitem__("experiment_id", "other"),
                    "experiment_id does not match",
                ),
                (
                    "input-reference",
                    lambda manifest: manifest["input"].__setitem__("reference", "other.json"),
                    "input reference does not match",
                ),
                (
                    "workflow",
                    lambda manifest: manifest.__setitem__("workflow", "databento_replay"),
                    "workflow does not match",
                ),
                (
                    "identity",
                    lambda manifest: manifest["identity"].__setitem__(
                        "experiment_sha256", "0" * 64
                    ),
                    "identity does not match",
                ),
                (
                    "producer",
                    lambda manifest: manifest["implementation"].__setitem__(
                        "version", "9.9.9"
                    ),
                    "unsupported experiment producer version",
                ),
                (
                    "runtime",
                    lambda manifest: manifest["implementation"].__setitem__(
                        "runtime_contract", "gex-terminal.experiment-runtime.v999"
                    ),
                    "unsupported experiment runtime contract",
                ),
            )
            for name, mutate, message in cases:
                with self.subTest(name=name):
                    manifest = copy.deepcopy(first)
                    mutate(manifest)
                    manifest_path = self._write_manifest(root, f"{name}.json", manifest)
                    output = root / f"{name}-output"
                    with self.assertRaisesRegex(ValueError, message):
                        await reproduce_experiment(manifest_path, output)
                    self.assertFalse(output.exists())

    async def test_v2_rejects_result_drift_without_writing_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _, manifest_path = await self._run_example(root)
            changed_report = load_price_action_report(
                provider_fixture_path("price_action_validation_example.json")
            )
            changed_report["dataset"]["label"] = "changed-after-recording"
            output = root / "drift-output"
            with patch(
                "gex_terminal.experiment_manifest.load_price_action_report",
                return_value=changed_report,
            ):
                with self.assertRaisesRegex(ValueError, "semantic result"):
                    await reproduce_experiment(manifest_path, output)
            self.assertFalse(output.exists())

    async def test_v2_rejects_source_byte_count_drift_after_identity_validation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first, _ = await self._run_example(root)
            changed = copy.deepcopy(first)
            changed["input"]["bytes"] += 1
            self._refresh_experiment_sha256(changed)
            manifest_path = self._write_manifest(root, "wrong-size.json", changed)
            output = root / "wrong-size-output"
            with patch(
                "gex_terminal.experiment_manifest.load_price_action_report"
            ) as workflow:
                with self.assertRaisesRegex(ValueError, "input byte count changed"):
                    await reproduce_experiment(manifest_path, output)
            workflow.assert_not_called()
            self.assertFalse(output.exists())

    async def test_v1_known_producers_reproduce_with_partial_identity_lineage(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first, _ = await self._run_example(root)
            for version in ("0.3.0", "0.4.0"):
                with self.subTest(version=version):
                    legacy = self._legacy_v1_manifest(first, version=version)
                    manifest_path = self._write_manifest(
                        root, f"legacy-{version}.json", legacy
                    )
                    source_sha256 = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
                    reproduced = await reproduce_experiment(
                        manifest_path, root / f"legacy-{version}-output"
                    )
                    self.assertEqual(reproduced["schema"], EXPERIMENT_MANIFEST_SCHEMA_V2)
                    self.assertTrue(reproduced["reproduction"]["matched"])
                    self.assertEqual(
                        reproduced["reproduction"]["identity_validation"],
                        "legacy_partial",
                    )
                    self.assertEqual(
                        reproduced["reproduction"]["source_manifest_sha256"],
                        source_sha256,
                    )
                    self.assertEqual(
                        reproduced["reproduction"]["implementation_compatibility"][
                            "recorded_version"
                        ],
                        version,
                    )

    async def test_cli_exposes_legacy_partial_identity_status(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first, _ = await self._run_example(root)
            legacy = self._legacy_v1_manifest(first)
            manifest_path = self._write_manifest(root, "legacy-cli.json", legacy)
            output = io.StringIO()
            with redirect_stdout(output):
                await experiment_reproduce_command(Namespace(
                    command_path=str(manifest_path),
                    command_args=[str(root / "legacy-cli-output")],
                ))
            self.assertIn("matched=True", output.getvalue())
            self.assertIn("identity_validation=legacy_partial", output.getvalue())

    async def test_v1_rejects_stale_profile_hash_and_unknown_producer(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first, _ = await self._run_example(root)

            stale = self._legacy_v1_manifest(first)
            stale["experiment_spec"]["model_profile"]["profile_id"] = "relabeled"
            stale_path = self._write_manifest(root, "legacy-stale.json", stale)
            with self.assertRaisesRegex(ValueError, "profile identity"):
                await reproduce_experiment(stale_path, root / "stale-output")

            unknown = self._legacy_v1_manifest(first, version="0.2.0")
            unknown_path = self._write_manifest(root, "legacy-unknown.json", unknown)
            with self.assertRaisesRegex(ValueError, "unsupported experiment producer version"):
                await reproduce_experiment(unknown_path, root / "unknown-output")

    async def test_rejects_unknown_schema_malformed_digest_and_nonfinite_json(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first, _ = await self._run_example(root)

            unknown = copy.deepcopy(first)
            unknown["schema"] = "gex-terminal.experiment-manifest.v999"
            unknown_path = self._write_manifest(root, "unknown-schema.json", unknown)
            with self.assertRaisesRegex(ValueError, "unsupported experiment manifest schema"):
                await reproduce_experiment(unknown_path, root / "unknown-schema-output")

            malformed = copy.deepcopy(first)
            malformed["identity"]["profile_sha256"] = "not-a-digest"
            malformed_path = self._write_manifest(root, "malformed-hash.json", malformed)
            with self.assertRaisesRegex(ValueError, "lowercase SHA-256"):
                await reproduce_experiment(malformed_path, root / "malformed-output")

            spec = json.loads(provider_fixture_path("experiment_spec_example.json").read_text())
            spec["input"] = str(provider_fixture_path("price_action_validation_example.json"))
            spec["cost_assumptions"] = {"fees": float("nan")}
            nonfinite_path = root / "nonfinite-spec.json"
            nonfinite_path.write_text(json.dumps(spec), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "non-finite JSON value"):
                await run_experiment(nonfinite_path, root / "nonfinite-output")

            duplicate_path = root / "duplicate-manifest.json"
            duplicate_path.write_text(
                '{"schema":"gex-terminal.experiment-manifest.v2",'
                '"schema":"gex-terminal.experiment-manifest.v2"}',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
                await reproduce_experiment(duplicate_path, root / "duplicate-output")

    def test_canonical_identity_hashes_every_field(self):
        first = {"generated_at": "one", "value": 1}
        second = {"generated_at": "two", "value": 1}
        self.assertNotEqual(canonical_sha256(first), canonical_sha256(second))
        self.assertEqual(semantic_sha256(first), semantic_sha256(second))
        self.assertEqual(EXPERIMENT_EVIDENCE_POLICY, "gex-terminal.offline-evidence-ceiling.v1")

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
