"""Run and reproduce versioned offline research experiments."""

from __future__ import annotations

import hashlib
import hmac
import json
import platform
import re
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
EXPERIMENT_MANIFEST_SCHEMA_V1 = "gex-terminal.experiment-manifest.v1"
EXPERIMENT_MANIFEST_SCHEMA_V2 = "gex-terminal.experiment-manifest.v2"
EXPERIMENT_MANIFEST_SCHEMA = EXPERIMENT_MANIFEST_SCHEMA_V2
EXPERIMENT_IDENTITY_SCHEMA = "gex-terminal.experiment-identity.v1"
EXPERIMENT_CANONICALIZATION = "gex-terminal.canonical-json.v1"
EXPERIMENT_RUNTIME_CONTRACT = "gex-terminal.experiment-runtime.v1"
EXPERIMENT_EVIDENCE_POLICY = "gex-terminal.offline-evidence-ceiling.v1"
EXPERIMENT_EVIDENCE_CEILING = (
    "reproducible offline software result only; no live-provider, dealer-inventory, "
    "predictive, execution, or profitability claim"
)
EXPERIMENT_WORKFLOWS = {
    "databento_replay",
    "position_model_compare",
    "price_action_evaluate",
}

# Compatibility is explicit rather than inferred from package-version ordering.
# A future release must deliberately extend these declarations or introduce a
# new runtime contract.
SUPPORTED_EXPERIMENT_PRODUCERS = {
    EXPERIMENT_MANIFEST_SCHEMA_V1: frozenset({"0.3.0", "0.4.0"}),
    EXPERIMENT_MANIFEST_SCHEMA_V2: frozenset({"0.4.0"}),
}
SUPPORTED_EXPERIMENT_READERS = {
    EXPERIMENT_RUNTIME_CONTRACT: frozenset({"0.4.0"}),
}

_PACKAGE_NAME = "gex-terminal"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_EXPERIMENT_SPEC_FIELDS = frozenset(
    {
        "schema",
        "experiment_id",
        "workflow",
        "input",
        "model_profile",
        "as_of",
        "split",
        "outcome_definition",
        "cost_assumptions",
        "predictive_validity",
    }
)
_MODEL_PROFILE_FIELDS = frozenset(
    {
        "schema",
        "profile_id",
        "model_version",
        "symbol",
        "contract_multiplier",
        "risk_free_rate",
        "days_to_expiry",
        "expiry_filter",
        "pricing",
        "position_models",
        "minimum_directional_coverage",
        "maximum_underlying_age_seconds",
        "predictive_validity",
    }
)
_MANIFEST_FIELDS = {
    EXPERIMENT_MANIFEST_SCHEMA_V1: frozenset(
        {
            "schema",
            "experiment_id",
            "generated_at",
            "workflow",
            "implementation",
            "spec_reference",
            "source_root",
            "experiment_spec",
            "profile_sha256",
            "input",
            "result",
            "reproduction",
            "evidence_ceiling",
        }
    ),
    EXPERIMENT_MANIFEST_SCHEMA_V2: frozenset(
        {
            "schema",
            "experiment_id",
            "generated_at",
            "workflow",
            "implementation",
            "spec_reference",
            "source_root",
            "experiment_spec",
            "identity",
            "input",
            "result",
            "reproduction",
            "evidence_policy",
            "evidence_ceiling",
        }
    ),
}
_IMPLEMENTATION_FIELDS = {
    EXPERIMENT_MANIFEST_SCHEMA_V1: frozenset({"package", "version", "python"}),
    EXPERIMENT_MANIFEST_SCHEMA_V2: frozenset(
        {
            "package",
            "version",
            "python",
            "runtime_contract",
        }
    ),
}
_IDENTITY_FIELDS = frozenset(
    {
        "schema",
        "canonicalization",
        "profile_sha256",
        "experiment_spec_sha256",
        "experiment_sha256",
    }
)
_INPUT_FIELDS = frozenset({"reference", "sha256", "bytes"})
_RESULT_FIELDS = frozenset({"path", "semantic_sha256", "predictive_validity"})
_REPRODUCTION_FIELDS = {
    EXPERIMENT_MANIFEST_SCHEMA_V1: frozenset(
        {
            "expected_semantic_sha256",
            "matched",
        }
    ),
    EXPERIMENT_MANIFEST_SCHEMA_V2: frozenset(
        {
            "expected_semantic_sha256",
            "matched",
            "identity_validation",
            "source_manifest_schema",
            "source_manifest_sha256",
            "implementation_compatibility",
        }
    ),
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
    manifest_bytes = manifest_source.read_bytes()
    try:
        manifest_text = manifest_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("experiment manifest must be UTF-8 JSON") from exc
    manifest = _parse_json_object(manifest_text, "experiment manifest")
    expected = _validate_recorded_manifest(
        manifest, hashlib.sha256(manifest_bytes).hexdigest()
    )
    source_root = Path(expected["source_root"])
    if not source_root.is_absolute():
        source_root = (manifest_source.parent / source_root).resolve()
    return await _execute_experiment(
        expected["experiment_spec"],
        source_root=source_root,
        spec_reference=expected["spec_reference"],
        output_dir=output_dir,
        expected=expected,
    )


async def _execute_experiment(
    spec: Mapping[str, Any],
    *,
    source_root: Path,
    spec_reference: str,
    output_dir: str | Path,
    expected: Mapping[str, Any] | None,
) -> dict[str, Any]:
    target = _validate_output_target(output_dir)
    normalized = _validate_spec(spec)
    profile = normalized["model_profile"]
    implementation = _current_implementation()
    profile_digest = canonical_sha256(profile)
    spec_digest = canonical_sha256(normalized)

    input_path = _resolve_reference(source_root, normalized["input"])
    input_digest = _file_digest(input_path)
    input_bytes = input_path.stat().st_size
    if expected is not None:
        if not hmac.compare_digest(input_digest, expected["input_sha256"]):
            raise ValueError("experiment input digest changed since the recorded run")
        if input_bytes != expected["input_bytes"]:
            raise ValueError("experiment input byte count changed since the recorded run")

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
    if _file_digest(input_path) != input_digest or input_path.stat().st_size != input_bytes:
        raise ValueError("experiment input changed while the workflow was executing")
    semantic_digest = semantic_sha256(report)
    expected_digest = expected["result_sha256"] if expected is not None else None
    if expected_digest is not None and not hmac.compare_digest(
        semantic_digest, expected_digest
    ):
        raise ValueError("experiment reproduction did not match the recorded semantic result")

    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    identity = {
        "schema": EXPERIMENT_IDENTITY_SCHEMA,
        "canonicalization": EXPERIMENT_CANONICALIZATION,
        "profile_sha256": profile_digest,
        "experiment_spec_sha256": spec_digest,
    }
    identity["experiment_sha256"] = canonical_sha256(
        _experiment_identity_payload(
            profile_sha256=profile_digest,
            experiment_spec_sha256=spec_digest,
            input_sha256=input_digest,
            input_bytes=input_bytes,
            implementation=implementation,
            result_sha256=semantic_digest,
        )
    )
    reproduction = {
        "expected_semantic_sha256": expected_digest,
        "matched": expected_digest is None or expected_digest == semantic_digest,
        "identity_validation": (
            expected["identity_validation"] if expected is not None else "complete"
        ),
        "source_manifest_schema": (
            expected["manifest_schema"] if expected is not None else None
        ),
        "source_manifest_sha256": (
            expected["source_manifest_sha256"] if expected is not None else None
        ),
        "implementation_compatibility": (
            expected["implementation_compatibility"] if expected is not None else None
        ),
    }
    manifest = {
        "schema": EXPERIMENT_MANIFEST_SCHEMA,
        "experiment_id": normalized["experiment_id"],
        "generated_at": generated_at,
        "workflow": workflow,
        "implementation": implementation,
        "spec_reference": spec_reference,
        "source_root": str(source_root),
        "experiment_spec": normalized,
        "identity": identity,
        "input": {
            "reference": normalized["input"],
            "sha256": input_digest,
            "bytes": input_bytes,
        },
        "result": {
            "path": "report.json",
            "semantic_sha256": semantic_digest,
            "predictive_validity": "unmeasured",
        },
        "reproduction": reproduction,
        "evidence_policy": EXPERIMENT_EVIDENCE_POLICY,
        "evidence_ceiling": EXPERIMENT_EVIDENCE_CEILING,
    }

    _validate_output_target(target)
    target.mkdir(parents=True, exist_ok=True)
    report_path = target / "report.json"
    _write_new_json(report_path, report)
    manifest_path = target / "manifest.json"
    _write_new_json(manifest_path, manifest)
    return manifest


def canonical_sha256(value: Any) -> str:
    """Hash every field of a canonical JSON-compatible identity value."""
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


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
    return _validate_spec(_load_json_object(path, "experiment spec"))


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    return _parse_json_object(path.read_text(encoding="utf-8"), label)


def _parse_json_object(text: str, label: str) -> dict[str, Any]:
    payload = json.loads(
        text,
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_nonfinite_constant,
    )
    if not isinstance(payload, Mapping):
        raise ValueError(f"{label} must be a JSON object")
    return dict(payload)


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key is unsupported: {key}")
        result[key] = value
    return result


def _reject_nonfinite_constant(value: str) -> Any:
    raise ValueError(f"non-finite JSON value is unsupported: {value}")


def _validate_recorded_manifest(
    manifest: Mapping[str, Any], source_manifest_sha256: str
) -> dict[str, Any]:
    schema = manifest.get("schema")
    if not isinstance(schema, str) or schema not in {
        EXPERIMENT_MANIFEST_SCHEMA_V1,
        EXPERIMENT_MANIFEST_SCHEMA_V2,
    }:
        raise ValueError(f"unsupported experiment manifest schema: {schema}")
    _reject_unknown_fields(manifest, _MANIFEST_FIELDS[schema], "experiment manifest")

    common = _validate_manifest_common(manifest, str(schema))
    profile = common["experiment_spec"]["model_profile"]
    if schema == EXPERIMENT_MANIFEST_SCHEMA_V1:
        recorded_profile_sha256 = _required_sha256(
            manifest.get("profile_sha256"), "experiment profile_sha256"
        )
        expected_profile_sha256 = semantic_sha256(profile)
        if not hmac.compare_digest(
            recorded_profile_sha256, expected_profile_sha256
        ):
            raise ValueError(
                "experiment profile identity does not match the embedded model_profile"
            )
        identity_validation = "legacy_partial"
    else:
        _validate_v2_identity(manifest, common)
        identity_validation = "complete"

    return {
        **common,
        "manifest_schema": schema,
        "identity_validation": identity_validation,
        "source_manifest_sha256": source_manifest_sha256,
    }


def _validate_manifest_common(
    manifest: Mapping[str, Any], schema: str
) -> dict[str, Any]:
    raw_spec = _required_mapping(
        manifest.get("experiment_spec"), "experiment manifest experiment_spec"
    )
    spec = _validate_spec(raw_spec)
    if manifest.get("experiment_id") != spec["experiment_id"]:
        raise ValueError("experiment manifest experiment_id does not match experiment_spec")
    if manifest.get("workflow") != spec["workflow"]:
        raise ValueError("experiment manifest workflow does not match experiment_spec")

    input_record = _required_mapping(manifest.get("input"), "experiment manifest input")
    _reject_unknown_fields(input_record, _INPUT_FIELDS, "experiment input")
    input_reference = _required_text(
        input_record.get("reference"), "experiment input reference"
    )
    if input_reference != spec["input"]:
        raise ValueError("experiment input reference does not match experiment_spec")
    input_sha256 = _required_sha256(
        input_record.get("sha256"), "experiment input sha256"
    )
    input_bytes = _nonnegative_integer(
        input_record.get("bytes"), "experiment input bytes"
    )

    result = _required_mapping(manifest.get("result"), "experiment manifest result")
    _reject_unknown_fields(result, _RESULT_FIELDS, "experiment result")
    _required_text(result.get("path"), "experiment result path")
    result_sha256 = _required_sha256(
        result.get("semantic_sha256"), "experiment result semantic_sha256"
    )
    if result.get("predictive_validity") != "unmeasured":
        raise ValueError("experiment result predictive_validity must be unmeasured")

    implementation, compatibility = _validate_implementation(
        manifest.get("implementation"), schema
    )
    source_root = _required_text(manifest.get("source_root"), "experiment source_root")
    spec_reference = _required_text(
        manifest.get("spec_reference"), "experiment spec_reference"
    )
    if manifest.get("evidence_ceiling") != EXPERIMENT_EVIDENCE_CEILING:
        raise ValueError("experiment evidence ceiling is unsupported")
    reproduction = _required_mapping(
        manifest.get("reproduction"), "experiment manifest reproduction"
    )
    _reject_unknown_fields(
        reproduction,
        _REPRODUCTION_FIELDS[schema],
        "experiment reproduction",
    )

    return {
        "experiment_spec": spec,
        "source_root": source_root,
        "spec_reference": spec_reference,
        "input_sha256": input_sha256,
        "input_bytes": input_bytes,
        "result_sha256": result_sha256,
        "implementation": implementation,
        "implementation_compatibility": compatibility,
    }


def _validate_v2_identity(
    manifest: Mapping[str, Any], common: Mapping[str, Any]
) -> None:
    if manifest.get("evidence_policy") != EXPERIMENT_EVIDENCE_POLICY:
        raise ValueError("experiment evidence policy is unsupported")
    identity = _required_mapping(manifest.get("identity"), "experiment identity")
    _reject_unknown_fields(identity, _IDENTITY_FIELDS, "experiment identity")
    if identity.get("schema") != EXPERIMENT_IDENTITY_SCHEMA:
        raise ValueError(f"unsupported experiment identity schema: {identity.get('schema')}")
    if identity.get("canonicalization") != EXPERIMENT_CANONICALIZATION:
        raise ValueError(
            "unsupported experiment identity canonicalization: "
            f"{identity.get('canonicalization')}"
        )

    profile_sha256 = _required_sha256(
        identity.get("profile_sha256"), "experiment identity profile_sha256"
    )
    expected_profile_sha256 = canonical_sha256(
        common["experiment_spec"]["model_profile"]
    )
    if not hmac.compare_digest(profile_sha256, expected_profile_sha256):
        raise ValueError(
            "experiment profile identity does not match the embedded model_profile"
        )

    spec_sha256 = _required_sha256(
        identity.get("experiment_spec_sha256"),
        "experiment identity experiment_spec_sha256",
    )
    expected_spec_sha256 = canonical_sha256(common["experiment_spec"])
    if not hmac.compare_digest(spec_sha256, expected_spec_sha256):
        raise ValueError(
            "experiment spec identity does not match the embedded experiment_spec"
        )

    experiment_sha256 = _required_sha256(
        identity.get("experiment_sha256"), "experiment identity experiment_sha256"
    )
    expected_experiment_sha256 = canonical_sha256(
        _experiment_identity_payload(
            profile_sha256=profile_sha256,
            experiment_spec_sha256=spec_sha256,
            input_sha256=common["input_sha256"],
            input_bytes=common["input_bytes"],
            implementation=common["implementation"],
            result_sha256=common["result_sha256"],
        )
    )
    if not hmac.compare_digest(experiment_sha256, expected_experiment_sha256):
        raise ValueError("experiment identity does not match the recorded fields")


def _experiment_identity_payload(
    *,
    profile_sha256: str,
    experiment_spec_sha256: str,
    input_sha256: str,
    input_bytes: int,
    implementation: Mapping[str, Any],
    result_sha256: str,
) -> dict[str, Any]:
    return {
        "schema": EXPERIMENT_IDENTITY_SCHEMA,
        "canonicalization": EXPERIMENT_CANONICALIZATION,
        "manifest_schema": EXPERIMENT_MANIFEST_SCHEMA_V2,
        "profile_sha256": profile_sha256,
        "experiment_spec_sha256": experiment_spec_sha256,
        "input": {"sha256": input_sha256, "bytes": input_bytes},
        "implementation": dict(implementation),
        "result": {
            "semantic_sha256": result_sha256,
            "predictive_validity": "unmeasured",
        },
        "evidence_policy": EXPERIMENT_EVIDENCE_POLICY,
    }


def _current_implementation() -> dict[str, str]:
    implementation = {
        "package": _PACKAGE_NAME,
        "version": __version__,
        "python": platform.python_version(),
        "runtime_contract": EXPERIMENT_RUNTIME_CONTRACT,
    }
    normalized, _ = _validate_implementation(
        implementation, EXPERIMENT_MANIFEST_SCHEMA_V2
    )
    return normalized


def _validate_implementation(
    value: Any, manifest_schema: str
) -> tuple[dict[str, str], dict[str, Any]]:
    implementation = _required_mapping(value, "experiment implementation")
    _reject_unknown_fields(
        implementation,
        _IMPLEMENTATION_FIELDS[manifest_schema],
        "experiment implementation",
    )
    package = _required_text(
        implementation.get("package"), "experiment implementation package"
    )
    version = _required_text(
        implementation.get("version"), "experiment implementation version"
    )
    python_version = _required_text(
        implementation.get("python"), "experiment implementation python"
    )
    if package != _PACKAGE_NAME:
        raise ValueError(f"unsupported experiment implementation package: {package}")
    supported_producers = SUPPORTED_EXPERIMENT_PRODUCERS.get(manifest_schema)
    if supported_producers is None or version not in supported_producers:
        raise ValueError(
            "unsupported experiment producer version for "
            f"{manifest_schema}: {version}"
        )

    if manifest_schema == EXPERIMENT_MANIFEST_SCHEMA_V2:
        runtime_contract = _required_text(
            implementation.get("runtime_contract"),
            "experiment implementation runtime_contract",
        )
    else:
        runtime_contract = EXPERIMENT_RUNTIME_CONTRACT
    if runtime_contract not in SUPPORTED_EXPERIMENT_READERS:
        raise ValueError(
            f"unsupported experiment runtime contract: {runtime_contract}"
        )
    supported_readers = SUPPORTED_EXPERIMENT_READERS[runtime_contract]
    if __version__ not in supported_readers:
        raise ValueError(
            "current package version is not declared compatible with experiment "
            f"runtime {runtime_contract}: {__version__}"
        )

    normalized = {
        "package": package,
        "version": version,
        "python": python_version,
    }
    if manifest_schema == EXPERIMENT_MANIFEST_SCHEMA_V2:
        normalized["runtime_contract"] = runtime_contract
    return normalized, {
        "status": "compatible",
        "runtime_contract": runtime_contract,
        "recorded_package": package,
        "recorded_version": version,
        "current_package": _PACKAGE_NAME,
        "current_version": __version__,
    }


def _required_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _reject_unknown_fields(
    value: Mapping[str, Any], allowed: frozenset[str], label: str
) -> None:
    unknown = sorted(str(key) for key in value if key not in allowed)
    if unknown:
        raise ValueError(f"{label} contains unsupported fields: {', '.join(unknown)}")


def _required_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value.strip()


def _required_sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _nonnegative_integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value


def _validate_spec(spec: Mapping[str, Any]) -> dict[str, Any]:
    _reject_unknown_fields(spec, _EXPERIMENT_SPEC_FIELDS, "experiment spec")
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
    _reject_unknown_fields(
        raw_profile, _MODEL_PROFILE_FIELDS, "experiment model_profile"
    )
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
    if (
        "predictive_validity" in spec
        and spec.get("predictive_validity") != "unmeasured"
    ):
        raise ValueError("experiment spec predictive_validity must be unmeasured")
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
            raise ValueError(
                "price-action experiment includes observations after experiment as_of"
            )


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


def _validate_output_target(output_dir: str | Path) -> Path:
    target = Path(output_dir)
    if target.exists():
        if not target.is_dir():
            raise ValueError("experiment output path must be a directory")
        if next(target.iterdir(), None) is not None:
            raise ValueError("experiment output directory must be empty")
    return target


def _write_new_json(path: Path, value: Any) -> None:
    try:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(value, indent=2, sort_keys=True) + "\n")
    except FileExistsError as exc:
        raise ValueError(
            f"experiment output artifact already exists: {path.name}"
        ) from exc
