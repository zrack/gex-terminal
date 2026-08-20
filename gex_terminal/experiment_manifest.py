"""Run and reproduce versioned offline research experiments."""

from __future__ import annotations

import hashlib
import json
import platform
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from gex_terminal import __version__
from gex_terminal.databento_offline import replay_databento_file
from gex_terminal.model_profiles import (
    config_from_model_profile,
    validate_model_profile,
)
from gex_terminal.position_model_comparison import load_position_model_comparison
from gex_terminal.price_action_validation import load_price_action_report


EXPERIMENT_SPEC_SCHEMA = "gex-terminal.experiment-spec.v1"
EXPERIMENT_MANIFEST_SCHEMA = "gex-terminal.experiment-manifest.v1"
EXPERIMENT_WORKFLOWS = {
    "databento_replay",
    "position_model_compare",
    "price_action_evaluate",
}


async def run_experiment(
    spec_path: str | Path, output_dir: str | Path
) -> dict[str, Any]:
    source = Path(spec_path).resolve()
    spec = _load_spec(source)
    return await _execute_experiment(
        spec,
        source_root=source.parent,
        spec_reference=str(source),
        output_dir=output_dir,
        expected=None,
    )


async def reproduce_experiment(
    manifest_path: str | Path, output_dir: str | Path
) -> dict[str, Any]:
    manifest_source = Path(manifest_path).resolve()
    manifest = json.loads(manifest_source.read_text(encoding="utf-8"))
    if not isinstance(manifest, Mapping) or manifest.get("schema") != EXPERIMENT_MANIFEST_SCHEMA:
        raise ValueError("experiment manifest schema is unsupported")
    spec = manifest.get("experiment_spec")
    if not isinstance(spec, Mapping):
        raise ValueError("experiment manifest is missing experiment_spec")
    source_root = Path(str(manifest.get("source_root") or ""))
    if not source_root.is_absolute():
        source_root = (manifest_source.parent / source_root).resolve()
    result = await _execute_experiment(
        dict(spec),
        source_root=source_root,
        spec_reference=str(manifest.get("spec_reference") or manifest_source),
        output_dir=output_dir,
        expected=manifest,
    )
    if not result["reproduction"]["matched"]:
        raise ValueError("experiment reproduction did not match the recorded semantic result")
    return result


async def _execute_experiment(
    spec: Mapping[str, Any],
    *,
    source_root: Path,
    spec_reference: str,
    output_dir: str | Path,
    expected: Mapping[str, Any] | None,
) -> dict[str, Any]:
    normalized = _validate_spec(spec)
    input_path = _resolve_reference(source_root, normalized["input"])
    input_digest = _file_digest(input_path)
    if expected is not None and input_digest != expected.get("input", {}).get("sha256"):
        raise ValueError("experiment input digest changed since the recorded run")
    profile = normalized["model_profile"]
    config = config_from_model_profile(profile)
    workflow = normalized["workflow"]
    if workflow == "databento_replay":
        report = await replay_databento_file(
            input_path,
            config=config,
            maximum_underlying_age_seconds=profile["maximum_underlying_age_seconds"],
        )
    elif workflow == "position_model_compare":
        report = await load_position_model_comparison(input_path, config=config)
    else:
        report = load_price_action_report(input_path)
    _enforce_as_of(workflow, normalized["as_of"], report)
    semantic_digest = semantic_sha256(report)
    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    report_path = target / "report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    expected_digest = (
        expected.get("result", {}).get("semantic_sha256") if expected is not None else None
    )
    manifest = {
        "schema": EXPERIMENT_MANIFEST_SCHEMA,
        "experiment_id": normalized["experiment_id"],
        "generated_at": generated_at,
        "workflow": workflow,
        "implementation": {
            "package": "gex-terminal",
            "version": __version__,
            "python": platform.python_version(),
        },
        "spec_reference": spec_reference,
        "source_root": str(source_root),
        "experiment_spec": normalized,
        "profile_sha256": semantic_sha256(profile),
        "input": {
            "reference": normalized["input"],
            "sha256": input_digest,
            "bytes": input_path.stat().st_size,
        },
        "result": {
            "path": "report.json",
            "semantic_sha256": semantic_digest,
            "predictive_validity": "unmeasured",
        },
        "reproduction": {
            "expected_semantic_sha256": expected_digest,
            "matched": expected_digest is None or expected_digest == semantic_digest,
        },
        "evidence_ceiling": (
            "reproducible offline software result only; no live-provider, dealer-inventory, "
            "predictive, execution, or profitability claim"
        ),
    }
    manifest_path = target / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def semantic_sha256(value: Any) -> str:
    """Hash decision-relevant JSON while excluding volatile generation times."""
    normalized = _without_volatile_fields(value)
    encoded = json.dumps(
        normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _without_volatile_fields(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _without_volatile_fields(item)
            for key, item in value.items()
            if key not in {"generated_at"}
        }
    if isinstance(value, list):
        return [_without_volatile_fields(item) for item in value]
    return value


def _load_spec(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("experiment spec must be a JSON object")
    return _validate_spec(payload)


def _validate_spec(spec: Mapping[str, Any]) -> dict[str, Any]:
    if spec.get("schema") != EXPERIMENT_SPEC_SCHEMA:
        raise ValueError(f"experiment spec schema must be {EXPERIMENT_SPEC_SCHEMA}")
    experiment_id = str(spec.get("experiment_id") or "").strip()
    if not experiment_id:
        raise ValueError("experiment spec requires experiment_id")
    workflow = str(spec.get("workflow") or "").strip()
    if workflow not in EXPERIMENT_WORKFLOWS:
        raise ValueError(f"unsupported experiment workflow: {workflow}")
    input_reference = str(spec.get("input") or "").strip()
    if not input_reference:
        raise ValueError("experiment spec requires input")
    raw_profile = spec.get("model_profile")
    if not isinstance(raw_profile, Mapping):
        raise ValueError("experiment spec requires an inline model_profile")
    profile = validate_model_profile(raw_profile)
    split = str(spec.get("split") or "unspecified").strip().lower()
    if split not in {"train", "calibration", "test", "unspecified"}:
        raise ValueError("experiment split must be train, calibration, test, or unspecified")
    costs = spec.get("cost_assumptions", {})
    if not isinstance(costs, Mapping):
        raise ValueError("cost_assumptions must be an object")
    outcome = spec.get("outcome_definition")
    if outcome is not None and not isinstance(outcome, (str, Mapping)):
        raise ValueError("outcome_definition must be a string, object, or null")
    as_of = _timezone_aware_timestamp(spec.get("as_of"), "experiment as_of")
    if as_of is None:
        raise ValueError("experiment spec requires as_of")
    return {
        "schema": EXPERIMENT_SPEC_SCHEMA,
        "experiment_id": experiment_id,
        "workflow": workflow,
        "input": input_reference,
        "model_profile": profile,
        "as_of": as_of,
        "split": split,
        "outcome_definition": outcome,
        "cost_assumptions": dict(costs),
        "predictive_validity": "unmeasured",
    }


def _timezone_aware_timestamp(value: Any, label: str) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        raise ValueError(f"{label} must not be empty")
    candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ValueError(f"{label} must be ISO 8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label} must include a timezone")
    return text


def _enforce_as_of(workflow: str, as_of: str, report: Mapping[str, Any]) -> None:
    cutoff = _parse_timestamp(as_of, "experiment as_of")
    if workflow == "position_model_compare":
        report_as_of = _parse_timestamp(report.get("as_of"), "position report as_of")
        if report_as_of != cutoff:
            raise ValueError("experiment as_of must match the position-comparison input cutoff")
        return
    if workflow == "databento_replay":
        model = report.get("snapshot", {}).get("model", {})
        report_as_of = _parse_timestamp(model.get("as_of"), "Databento snapshot as_of")
        if report_as_of > cutoff:
            raise ValueError("Databento experiment includes records after experiment as_of")
        return
    for observation in report.get("observations", []):
        timestamp = _parse_timestamp(
            observation.get("timestamp") if isinstance(observation, Mapping) else None,
            "price-action observation timestamp",
        )
        if timestamp > cutoff:
            raise ValueError("price-action experiment includes observations after experiment as_of")


def _parse_timestamp(value: Any, label: str) -> datetime:
    text = _timezone_aware_timestamp(value, label)
    if text is None:
        raise ValueError(f"{label} is required")
    candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
    return datetime.fromisoformat(candidate).astimezone(timezone.utc)


def _resolve_reference(root: Path, reference: str) -> Path:
    path = Path(reference)
    return path if path.is_absolute() else (root / path).resolve()


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
