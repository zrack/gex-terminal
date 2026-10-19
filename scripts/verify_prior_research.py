"""Verify actual 0.5.0 research and its explicit sparse-side correction.

Creates only disposable environments/research; never edits the supplied wheel.
Dependencies are inherited from the caller's tested environment. The producer
package is installed separately without dependency or network resolution.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import sysconfig
import tempfile
import venv


PRIOR_NQ_SOURCE_SHA256 = "1935529bdf4e594c56d26fdc8f5139f78d3eefbada8bbb70d7adb138c67b73c6"
EXPECTED_REPRODUCTION_ERROR = (
    "Demo Lab reproduction decision content mismatch: replay_lab.json, snapshot.json"
)
EPHEMERAL_RUNTIME_FIELDS = frozenset({
    "elapsed_seconds", "last_message_age_seconds", "last_snapshot_age_seconds",
    "latency_ms", "p95_latency_ms", "runtime_seconds",
})
EXPECTED_PRICING_ASSUMPTIONS = {
    "models": ["black_76"],
    "model_labels": ["Black-76"],
    "exercise_style_counts": {"american": 0, "european": 0, "unknown": 10},
    "status": "exercise_style_unknown",
    "summary": "Black-76: exercise style unknown: model compatibility unqualified.",
    "limitations": [
        "European-exercise formulas; early exercise is not modeled.",
        "Exercise style is missing for some contracts; compatibility with the pricing model is unqualified.",
    ],
    "risk_free_rate": 0.045,
    "risk_free_rate_source": "configured",
    "iv_inversion_risk_free_rates": [],
    "rate_note": "Risk-free rate 4.50% is configured, not observed market data; continuously compounded, flat across maturities.",
    "day_count": "ACT/365",
    "time_note": "Exact expiry timestamps use actual seconds / 365 days; otherwise contract DTE or configured fallback is used.",
    "early_exercise_modeled": False,
    "approximation_error": "unmeasured",
}


def _without_runtime(value):
    """Use only the existing, receipt-bound canonical runtime omissions."""
    if isinstance(value, dict):
        return {key: _without_runtime(item) for key, item in value.items()
                if key not in EPHEMERAL_RUNTIME_FIELDS}
    if isinstance(value, list):
        return [_without_runtime(item) for item in value]
    return value


def _canonical_json(value):
    """Preserve JSON number/boolean/null distinctions used by receipt hashes."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def verify_known_prior_output_changes(previous: Path, current: Path) -> dict:
    """Inspect two already verified packs without relaxing either receipt.

    This is a frozen migration assertion for one known synthetic 0.5.0 input,
    not a general reproduction policy. Production reproduction stays strict.
    """
    def load(root, reference):
        return json.loads((root / reference).read_text(encoding="utf-8"))

    old_receipt = load(previous, "review-receipt.json")
    new_receipt = load(current, "review-receipt.json")
    if (old_receipt["application"]["version"] != "0.5.0"
            or new_receipt["application"]["version"] != "0.6.0"
            or old_receipt["source"]["session_name"] != "nq-research-loop"
            or old_receipt["source"]["sha256"] != PRIOR_NQ_SOURCE_SHA256
            or _canonical_json(old_receipt["source"]) != _canonical_json(new_receipt["source"])
            or _canonical_json(old_receipt["model"]) != _canonical_json(new_receipt["model"])):
        raise AssertionError("Prior sparse-side migration source/model identity changed")
    expected_canonicalization = {
        "schema": "gex-terminal.demo-lab-canonical-json.v1",
        "omitted_ephemeral_fields": sorted(EPHEMERAL_RUNTIME_FIELDS),
        "generated_at_bound": True,
    }
    if (_canonical_json(old_receipt["canonicalization"]) != _canonical_json(expected_canonicalization)
            or _canonical_json(new_receipt["canonicalization"]) != _canonical_json(expected_canonicalization)):
        raise AssertionError("Prior sparse-side migration canonicalization changed")
    if set(old_receipt["content"]) != set(new_receipt["content"]):
        raise AssertionError("Prior sparse-side migration artifact inventory changed")

    additions = []
    corrections = []

    def remove_addition(old, new, key, path, expected=None):
        if key in old or key not in new or (expected is not None and new[key] != expected):
            raise AssertionError(f"Unexpected prior migration metadata: {path}.{key}")
        additions.append(f"{path}.{key}")
        new.pop(key)

    def project_snapshot(old, new, path):
        remove_addition(old["metrics"], new["metrics"], "side_coverage", path + ".metrics", "both_sides")
        if _canonical_json(new["model"].get("pricing_assumptions")) != _canonical_json(EXPECTED_PRICING_ASSUMPTIONS):
            raise AssertionError("Prior migration pricing disclosure is incorrect")
        remove_addition(old["model"], new["model"], "pricing_assumptions", path + ".model")

    for reference in sorted(old_receipt["content"]):
        old = load(previous, reference)
        new = load(current, reference)
        projected = deepcopy(new)
        if reference == "snapshot.json":
            project_snapshot(old, projected, reference)
        elif reference == "replay_lab.json":
            if len(old["sessions"]) != 1 or len(projected["sessions"]) != 1:
                raise AssertionError("Prior migration replay session count changed")
            old_session, new_session = old["sessions"][0], projected["sessions"][0]
            project_snapshot(old_session["snapshot"], new_session["snapshot"], reference + ".sessions[0].snapshot")
            remove_addition(old_session["summary"], new_session["summary"], "side_coverage", reference + ".sessions[0].summary", "both_sides")
            if len(old_session["timeline"]) != 27 or len(new_session["timeline"]) != 27:
                raise AssertionError("Prior migration timeline length changed")
            for index, (old_point, new_point) in enumerate(zip(old_session["timeline"], new_session["timeline"])):
                path = f"{reference}.sessions[0].timeline[{index}]"
                remove_addition(old_point, new_point, "side_coverage", path,
                                "calls_only" if index == 0 else "both_sides")
                if index == 0:
                    for key, old_value in (("imbalance", 0.0), ("put_wall", 20800.0)):
                        if type(old_point.get(key)) is not float or old_point[key] != old_value or new_point.get(key, "missing") is not None:
                            raise AssertionError(f"Unexpected prior sparse-side correction: {path}.{key}")
                        corrections.append({"path": path + "." + key, "previous": old_value, "current": None})
                        # Compare every remaining field; this never alters either saved pack.
                        new_point[key] = old_value
        if _canonical_json(_without_runtime(old)) != _canonical_json(_without_runtime(projected)):
            raise AssertionError(f"Unexpected prior decision content drift: {reference}")
    if len(additions) != 32 or len(corrections) != 2:
        raise AssertionError("Prior migration expected changes were not all observed")
    return {
        "old_exact_reproduction": False,
        "reason": "known_sparse_side_corrections",
        "additive_metadata_paths": additions,
        "corrected_values": corrections,
        "all_other_decision_content_equal": True,
    }


def verify(previous: Path, reader: Path) -> dict:
    previous, reader = previous.resolve(), reader.absolute()
    with tempfile.TemporaryDirectory(prefix="gex-prior-research-") as directory:
        root = Path(directory)
        environment = {key: value for key, value in os.environ.items()
                       if not key.startswith(("GEX_", "DATABENTO_", "TRADOVATE_", "PYTHON"))}
        environment["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"

        def run(python, *arguments, expected_error=None):
            result = subprocess.run([str(python), "-I", *map(str, arguments)],
                                    cwd=root, env=environment, capture_output=True,
                                    text=True, timeout=180)
            if expected_error is not None:
                if result.returncode == 0 or result.stderr.splitlines()[-1:] != [expected_error]:
                    raise RuntimeError(f"Unexpected prior reproduction result: {result.stderr[-3000:]}")
                return result.stdout
            if result.returncode:
                raise RuntimeError(f"Prior-research check failed: {result.stderr[-3000:]}")
            return result.stdout

        venv.EnvBuilder(with_pip=True, system_site_packages=True).create(root / "producer")
        producer = root / "producer/bin/python"
        # Nested venvs inherit the base interpreter's packages, not the
        # invoking venv's dependencies. Add that tested dependency directory
        # behind the producer's own site-packages; version checks below ensure
        # the separately installed historical application wins import lookup.
        producer_library = Path(run(producer, "-c", "import sysconfig; print(sysconfig.get_path('purelib'))").strip())
        caller_libraries = sorted({sysconfig.get_path("purelib"), sysconfig.get_path("platlib")})
        (producer_library / "gex-tested-dependencies.pth").write_text("\n".join(caller_libraries) + "\n")
        run(producer, "-m", "pip", "--isolated", "install", "--no-index", "--no-deps", previous)
        old = run(producer, "-c", "import gex_terminal; print(gex_terminal.__version__)").strip()
        new = run(reader, "-c", "import gex_terminal; print(gex_terminal.__version__)").strip()
        if old != "0.5.0" or new != "0.6.0":
            raise ValueError("This gate requires a real 0.5.0 producer and 0.6.0 installed reader")
        run(producer, "-m", "gex_terminal.cli", "demo-lab", root / "pack", "--replay-session", "nq-research-loop")
        fixture = run(producer, "-c", "from gex_terminal.package_data import provider_fixture_path; print(provider_fixture_path('experiment_spec_example.json'))").strip()
        run(producer, "-m", "gex_terminal.cli", "experiment-run", fixture, root / "experiment")

        def identity():
            return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
                    for folder in (root / "pack", root / "experiment")
                    for path in folder.rglob("*") if path.is_file()}

        before = identity()
        run(reader, "-m", "gex_terminal.cli", "demo-lab", "verify", root / "pack")
        # Corrected sparse-side semantics intentionally cannot claim the old
        # phantom put wall and zero ratio were reproduced exactly.
        run(reader, "-m", "gex_terminal.cli", "demo-lab", "reproduce", root / "pack",
            root / "corrected-pack", expected_error=EXPECTED_REPRODUCTION_ERROR)
        run(reader, "-m", "gex_terminal.cli", "demo-lab", "verify", root / "corrected-pack")
        correction = verify_known_prior_output_changes(root / "pack", root / "corrected-pack")
        corrected_before = {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
                            for path in (root / "corrected-pack").rglob("*") if path.is_file()}
        run(reader, "-m", "gex_terminal.cli", "demo-lab", "reproduce", root / "corrected-pack",
            root / "reproduced-corrected-pack")
        corrected_after = {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
                           for path in (root / "corrected-pack").rglob("*") if path.is_file()}
        if corrected_after != corrected_before:
            raise AssertionError("Corrected research bytes changed during reproduction")
        run(reader, "-m", "gex_terminal.cli", "experiment-reproduce", root / "experiment/manifest.json",
            root / "reproduced-experiment")
        if identity() != before:
            raise AssertionError("Prior research bytes changed")
        return {"schema": "gex-terminal.prior-research-check.v2", "passed": True,
                "producer_version": old, "reader_version": new,
                "producer_wheel_sha256": hashlib.sha256(previous.read_bytes()).hexdigest(),
                "preserved_files": len(before), "input_sha256": before,
                "prior_demo_upgrade": correction,
                "current_pack_exact_reproduction": True,
                "current_pack_input_preserved": True,
                "checks": ["demo_receipt_verify", "prior_sparse_correction_review",
                           "current_demo_receipt_reproduce", "experiment_reproduce", "input_preservation"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--previous-wheel", type=Path, required=True)
    parser.add_argument("--reader-python", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = verify(args.previous_wheel, args.reader_python)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print("Prior 0.5.0 inputs verified unchanged; sparse-side corrections reviewed; corrected 0.6.0 pack and prior experiment reproduce exactly.")


if __name__ == "__main__":
    main()
