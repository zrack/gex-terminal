"""Regression checks for the frozen 0.5.0 research migration review."""

from copy import deepcopy
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from gex_terminal.config import GexConfig
from gex_terminal.demo_lab import build_demo_lab, reproduce_demo_lab, verify_demo_lab
from gex_terminal.demo_lab_receipt import file_sha256, stable_json_sha256
from scripts.verify_prior_research import (
    EPHEMERAL_RUNTIME_FIELDS,
    EXPECTED_CURRENT_PROVIDER_SCORECARD,
    EXPECTED_PRIOR_PROVIDER_SCORECARD,
    PRIOR_NQ_PROFILE_SHA256,
    EXPECTED_PRICING_ASSUMPTIONS,
    PRIOR_NQ_SOURCE_SHA256,
    verify_known_prior_output_changes,
)


def _write(root, reference, payload):
    path = root / reference
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _comparison_fixture(root):
    """Minimal already-verified-artifact shapes for the independent diff gate."""
    previous, current = root / "previous", root / "current"
    snapshot = {"metrics": {"total_net_gex": 10.0}, "model": {"version": "v2"}}
    timeline = [
        {"total_net_gex": 10.0, "imbalance": 0.0 if index == 0 else 1.0,
         "put_wall": 20800.0, "regime": "positive_gex_proxy"}
        for index in range(27)
    ]
    replay = {"sessions": [{"snapshot": deepcopy(snapshot), "summary": {"symbol": "NQ"},
                            "timeline": timeline}], "alerts": []}
    artifacts = {"snapshot.json": snapshot, "replay_lab.json": replay,
                 "manifest.json": {"symbol": "NQ", "provider_fixture_lab": deepcopy(EXPECTED_PRIOR_PROVIDER_SCORECARD)},
                 "model-comparison.json": {"total": 10.0},
                 "position-model-comparison.json": {"total": 10.0}}
    receipt = {
        "application": {"version": "0.5.0"},
        "source": {"session_name": "nq-research-loop", "sha256": PRIOR_NQ_SOURCE_SHA256},
        "model": {"profile_sha256": PRIOR_NQ_PROFILE_SHA256},
        "canonicalization": {"schema": "gex-terminal.demo-lab-canonical-json.v1",
                             "omitted_ephemeral_fields": sorted(EPHEMERAL_RUNTIME_FIELDS),
                             "generated_at_bound": True},
        "content": {name: "bound-by-verifier" for name in artifacts},
    }
    for name, payload in artifacts.items():
        _write(previous, name, payload)
    _write(previous, "review-receipt.json", receipt)
    updated = deepcopy(artifacts)
    updated["manifest.json"]["provider_fixture_lab"] = deepcopy(EXPECTED_CURRENT_PROVIDER_SCORECARD)
    for snap in (updated["snapshot.json"], updated["replay_lab.json"]["sessions"][0]["snapshot"]):
        snap["metrics"]["side_coverage"] = "both_sides"
        snap["model"]["pricing_assumptions"] = deepcopy(EXPECTED_PRICING_ASSUMPTIONS)
    session = updated["replay_lab.json"]["sessions"][0]
    session["summary"]["side_coverage"] = "both_sides"
    for index, point in enumerate(session["timeline"]):
        point["side_coverage"] = "calls_only" if index == 0 else "both_sides"
    session["timeline"][0]["imbalance"] = None
    session["timeline"][0]["put_wall"] = None
    for name, payload in updated.items():
        _write(current, name, payload)
    receipt["application"]["version"] = "0.6.0"
    _write(current, "review-receipt.json", receipt)
    return previous, current


class PriorResearchDiffTests(unittest.TestCase):
    def test_known_corrections_are_reviewed_without_claiming_exact_reproduction(self):
        with tempfile.TemporaryDirectory() as directory:
            previous, current = _comparison_fixture(Path(directory))
            before = {str(path): path.read_bytes() for root in (previous, current)
                      for path in root.rglob("*") if path.is_file()}
            result = verify_known_prior_output_changes(previous, current)
            self.assertFalse(result["old_exact_reproduction"])
            self.assertTrue(result["all_other_decision_content_equal"])
            self.assertEqual(len(result["additive_metadata_paths"]), 32)
            self.assertEqual(len(result["corrected_values"]), 2)
            self.assertEqual(result["synthetic_fixture_scorecard_corrections"], [
                {"path": "manifest.json.provider_fixture_lab.degraded", "previous": 2, "current": 1},
                {"path": "manifest.json.provider_fixture_lab.simulated", "previous": 3, "current": 4},
            ])
            self.assertEqual(before, {str(path): path.read_bytes() for root in (previous, current)
                                      for path in root.rglob("*") if path.is_file()})

    def test_unexpected_numeric_alert_and_unknown_field_drift_fail(self):
        mutations = (
            ("snapshot.json", lambda value: value["metrics"].update(total_net_gex=11.0)),
            ("replay_lab.json", lambda value: value["alerts"].append("changed alert")),
            ("replay_lab.json", lambda value: value["sessions"][0]["timeline"][1].update(imbalance=None)),
            ("snapshot.json", lambda value: value.update(unrecognized_metadata="must stay bound")),
            ("model-comparison.json", lambda value: value.update(total=11.0)),
            ("model-comparison.json", lambda value: value.update(total=10)),
            ("manifest.json", lambda value: value.update(symbol="ES")),
        )
        for reference, mutate in mutations:
            with self.subTest(reference=reference), tempfile.TemporaryDirectory() as directory:
                previous, current = _comparison_fixture(Path(directory))
                payload = json.loads((current / reference).read_text())
                mutate(payload)
                _write(current, reference, payload)
                with self.assertRaisesRegex(AssertionError, "decision content drift"):
                    verify_known_prior_output_changes(previous, current)

    def test_fixture_scorecard_correction_requires_exact_counters_and_json_types(self):
        for target, mutate in (
            ("previous", lambda score: score.update(degraded=1, simulated=4)),
            ("current", lambda score: score.update(degraded=2, simulated=3)),
            ("current", lambda score: score.update(simulated=4.0)),
            ("current", lambda score: score.update(degraded=True)),
            ("current", lambda score: score.update(passed=4, failed=1)),
            ("current", lambda score: score.update(normalized_messages=27)),
            ("current", lambda score: score.update(unrecognized="must remain bound")),
        ):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as directory:
                previous, current = _comparison_fixture(Path(directory))
                root = previous if target == "previous" else current
                payload = json.loads((root / "manifest.json").read_text())
                mutate(payload["provider_fixture_lab"])
                _write(root, "manifest.json", payload)
                with self.assertRaisesRegex(AssertionError, "synthetic fixture scorecard"):
                    verify_known_prior_output_changes(previous, current)

    def test_pricing_and_side_disclosures_must_have_exact_expected_values(self):
        mutations = (
            lambda value: value["model"]["pricing_assumptions"].update(risk_free_rate=0.055),
            lambda value: value["model"]["pricing_assumptions"].update(early_exercise_modeled=True),
            lambda value: value["model"]["pricing_assumptions"]["exercise_style_counts"].update(unknown=9),
            lambda value: value["model"]["pricing_assumptions"]["exercise_style_counts"].update(unknown=10.0),
            lambda value: value["model"]["pricing_assumptions"].update(early_exercise_modeled=0),
            lambda value: value["model"]["pricing_assumptions"].update(unrecognized="extra"),
            lambda value: value["metrics"].update(side_coverage="puts_only"),
        )
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index), tempfile.TemporaryDirectory() as directory:
                previous, current = _comparison_fixture(Path(directory))
                payload = json.loads((current / "snapshot.json").read_text())
                mutate(payload)
                _write(current, "snapshot.json", payload)
                with self.assertRaises(AssertionError):
                    verify_known_prior_output_changes(previous, current)

    def test_exception_is_bound_to_exact_prior_source_model_and_sparse_values(self):
        for target, reference, mutate in (
            ("previous", "review-receipt.json", lambda value: value["source"].update(sha256="different")),
            ("current", "review-receipt.json", lambda value: value["model"].update(profile_sha256="different")),
            ("previous", "replay_lab.json", lambda value: value["sessions"][0]["timeline"][0].update(put_wall=20900.0)),
            ("current", "replay_lab.json", lambda value: value["sessions"][0]["timeline"][0].update(imbalance=0.0)),
        ):
            with self.subTest(target=target, reference=reference), tempfile.TemporaryDirectory() as directory:
                previous, current = _comparison_fixture(Path(directory))
                root = previous if target == "previous" else current
                payload = json.loads((root / reference).read_text())
                mutate(payload)
                _write(root, reference, payload)
                with self.assertRaises(AssertionError):
                    verify_known_prior_output_changes(previous, current)

    def test_matching_but_different_model_profiles_cannot_use_migration_exception(self):
        with tempfile.TemporaryDirectory() as directory:
            previous, current = _comparison_fixture(Path(directory))
            for root in (previous, current):
                receipt = json.loads((root / "review-receipt.json").read_text())
                receipt["model"]["profile_sha256"] = "different-but-equal-model-profile"
                _write(root, "review-receipt.json", receipt)
            with self.assertRaisesRegex(AssertionError, "source/model identity changed"):
                verify_known_prior_output_changes(previous, current)


def _config():
    return GexConfig(symbol="NQ", symbols=("NQ",), data_mode="demo", data_provider="replay",
                     contract_multiplier=20, risk_free_rate=0.045, days_to_expiry=0.01,
                     refresh_interval_seconds=1.0, stale_after_seconds=10.0,
                     replay_path="unused", replay_delay_seconds=0.0, tradovate_environment="demo")


def _rebind(root, version=None):
    path = root / "review-receipt.json"
    receipt = json.loads(path.read_text())
    if version is not None:
        receipt["application"]["version"] = version
    for entry in receipt["artifacts"]:
        artifact = root / entry["path"]
        entry.update(bytes=artifact.stat().st_size, sha256=file_sha256(artifact))
    receipt["pack"]["content_sha256"] = stable_json_sha256(receipt["artifacts"])
    for reference in receipt["content"]:
        receipt["content"][reference] = stable_json_sha256(json.loads((root / reference).read_text()))
    receipt.pop("receipt_sha256", None)
    receipt["receipt_sha256"] = stable_json_sha256(receipt)
    _write(root, "review-receipt.json", receipt)


class PriorResearchReceiptTests(unittest.IsolatedAsyncioTestCase):
    async def test_old_and_current_receipts_keep_new_metadata_integrity_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = base / "source"
            await build_demo_lab(_config(), source, replay_session_name="nq-research-loop",
                                 screenshot_width=140, screenshot_height=42)
            for version in ("0.5.0", "0.6.0"):
                for field in ("pricing", "coverage"):
                    with self.subTest(version=version, field=field):
                        pack = base / (version + field)
                        shutil.copytree(source, pack)
                        _rebind(pack, version)
                        verify_demo_lab(pack)
                        snapshot = json.loads((pack / "snapshot.json").read_text())
                        if field == "pricing":
                            snapshot["model"]["pricing_assumptions"]["risk_free_rate"] = 0.055
                        else:
                            snapshot["metrics"]["side_coverage"] = "calls_only"
                        _write(pack, "snapshot.json", snapshot)
                        with self.assertRaisesRegex(ValueError, "artifact (size|content) changed"):
                            verify_demo_lab(pack)
                        with self.assertRaisesRegex(ValueError, "artifact (size|content) changed"):
                            await reproduce_demo_lab(pack, base / (version + field + "-reproduced"))

    async def test_self_consistent_current_metadata_drift_still_refuses_reproduction(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = base / "source"
            await build_demo_lab(_config(), source, replay_session_name="nq-research-loop",
                                 screenshot_width=140, screenshot_height=42)
            snapshot = json.loads((source / "snapshot.json").read_text())
            snapshot["model"]["pricing_assumptions"]["risk_free_rate"] = 0.055
            _write(source, "snapshot.json", snapshot)
            _rebind(source)
            verify_demo_lab(source)
            with self.assertRaisesRegex(ValueError, "decision content mismatch: snapshot.json"):
                await reproduce_demo_lab(source, base / "reproduced", screenshot_width=140,
                                         screenshot_height=42)


if __name__ == "__main__":
    unittest.main()
