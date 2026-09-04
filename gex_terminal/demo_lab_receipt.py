"""Integrity and compatibility contract for portable Demo Lab packs.

The command-line pack format is public. These Python helpers remain
experimental and may change while the artifact schemas stay versioned.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import re
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping

from gex_terminal import __version__
from gex_terminal.config import GexConfig
from gex_terminal.contracts import NORMALIZED_SCHEMA_VERSION, parse_market_datetime
from gex_terminal.market_data_adapter import validate_normalized_message
from gex_terminal.model_profiles import (
    MODEL_PROFILE_VERSION,
    default_model_profile,
    validate_model_profile,
)
from gex_terminal.replay_catalog import ReplaySession, replay_session_for_name


DEMO_LAB_SCHEMA = "gex-terminal.demo-lab.v2"
REVIEW_RECEIPT_SCHEMA = "gex-terminal.demo-lab-review-receipt.v1"
VERIFICATION_SCHEMA = "gex-terminal.demo-lab-verification.v1"
RUNTIME_SCHEMA = "gex-terminal.demo-lab-runtime.v1"
CANONICAL_JSON_SCHEMA = "gex-terminal.demo-lab-canonical-json.v1"
EPHEMERAL_RUNTIME_FIELDS = frozenset({
    "elapsed_seconds",
    "last_message_age_seconds",
    "last_snapshot_age_seconds",
    "latency_ms",
    "p95_latency_ms",
    "runtime_seconds",
})
REVIEW_RECEIPT_PATH = "review-receipt.json"
PORTABLE_SOURCE_PATH = "inputs/replay.jsonl"
EVIDENCE_CEILING = (
    "reproducible synthetic offline software result only; no live-provider, "
    "dealer-inventory, predictive, execution, or profitability claim"
)
# Compatibility is explicit rather than inferred from version ordering. A
# release must deliberately extend both declarations after proving that the
# receipt and runtime semantics remain compatible.
SUPPORTED_DEMO_LAB_PRODUCERS = {
    REVIEW_RECEIPT_SCHEMA: frozenset({"0.4.0"}),
}
SUPPORTED_DEMO_LAB_READERS = {
    RUNTIME_SCHEMA: frozenset({"0.4.0"}),
}
REQUIRED_SEMANTIC_ARTIFACTS = (
    "manifest.json",
    "snapshot.json",
    "model-comparison.json",
    "position-model-comparison.json",
    "replay_lab.json",
)


def portable_runtime_contract() -> dict[str, Any]:
    """Return the exact runtime family supported by one reproducible pack."""
    return {
        "schema": RUNTIME_SCHEMA,
        "python_implementation": platform.python_implementation(),
        "python_major_minor": f"{sys.version_info.major}.{sys.version_info.minor}",
        "dependencies": {
            "numpy": importlib.metadata.version("numpy"),
            "textual": importlib.metadata.version("textual"),
        },
    }


def stable_json_sha256(value: Any) -> str:
    """Hash decision content with only named ephemeral runtime fields omitted."""
    normalized = _without_ephemeral_runtime(value)
    encoded = json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def write_demo_lab_review_receipt(
    root: str | Path,
    *,
    generated_at: str,
    session: ReplaySession,
    config: GexConfig,
    messages: Iterable[Mapping[str, Any]],
    manifest: Mapping[str, Any],
    quality: Mapping[str, Any],
) -> dict[str, Any]:
    """Bind source, model, runtime, content, and artifacts into one receipt."""
    pack_root = Path(root)
    source_path = _safe_pack_path(pack_root, PORTABLE_SOURCE_PATH)
    observations = inspect_portable_replay(messages, session=session)
    artifact_metadata = _manifest_artifact_metadata(manifest)
    if REVIEW_RECEIPT_PATH not in artifact_metadata:
        raise ValueError("Demo Lab manifest must declare review-receipt.json")

    actual_paths = _pack_file_paths(pack_root, exclude={REVIEW_RECEIPT_PATH})
    expected_paths = set(artifact_metadata) - {REVIEW_RECEIPT_PATH}
    if actual_paths != expected_paths:
        raise ValueError(_path_set_error("Demo Lab artifacts", expected_paths, actual_paths))

    artifacts = [
        {
            "path": path,
            "kind": artifact_metadata[path],
            "bytes": _safe_pack_path(pack_root, path).stat().st_size,
            "sha256": file_sha256(_safe_pack_path(pack_root, path)),
        }
        for path in sorted(actual_paths)
    ]
    content = _semantic_content_hashes(pack_root)
    profile = default_model_profile(config)
    source_digest = file_sha256(source_path)
    receipt: dict[str, Any] = {
        "schema": REVIEW_RECEIPT_SCHEMA,
        "generated_at": generated_at,
        "canonicalization": {
            "schema": CANONICAL_JSON_SCHEMA,
            "omitted_ephemeral_fields": sorted(EPHEMERAL_RUNTIME_FIELDS),
            "generated_at_bound": True,
        },
        "pack": {
            "schema": DEMO_LAB_SCHEMA,
            "manifest": "manifest.json",
            "content_sha256": stable_json_sha256(artifacts),
        },
        "source": {
            "reference": PORTABLE_SOURCE_PATH,
            "catalog_reference": session.source_ref,
            "session_name": session.name,
            "symbol": session.symbol,
            "contract_multiplier": session.contract_multiplier,
            "bytes": source_path.stat().st_size,
            "sha256": source_digest,
            "normalized_schema_versions": observations["normalized_schema_versions"],
            "event_count": observations["event_count"],
            "first_event_time": observations["first_event_time"],
            "last_event_time": observations["last_event_time"],
            "missing_event_time_count": observations["missing_event_time_count"],
            "missing_received_time_count": observations["missing_received_time_count"],
            "missing_expiry_time_count": observations["missing_expiry_time_count"],
            "position_sources": observations["position_sources"],
            "direction_sources": observations["direction_sources"],
            "research_contract": (
                "synthetic_schema_v2_position_ladder"
                if session.research_loop
                else "bundled_replay"
            ),
            "authorization": {
                "source_kind": session.source_kind,
                "rights_status": session.rights_status,
                "redistributable": session.redistributable,
                "synthetic": session.source_kind == "synthetic_fixture",
                "live_data": False,
                "credentials": False,
            },
        },
        "model": {
            "model_version": MODEL_PROFILE_VERSION,
            "profile": profile,
            "profile_sha256": stable_json_sha256(profile),
            "position_models_are_separate": True,
        },
        "application": {
            "package": "gex-terminal",
            "version": __version__,
            "python_interface": "experimental",
        },
        "runtime": portable_runtime_contract(),
        "quality": dict(quality),
        "content": content,
        "artifacts": artifacts,
        "limitations": {
            "position_models_may_not_be_summed": True,
            "participant_classification": "unobserved",
            "opening_closing_classification": "unobserved",
            "predictive_validity": "unmeasured",
            "live_provider_certified": False,
            "authenticity": "unkeyed_hashes_only",
        },
        "evidence_ceiling": EVIDENCE_CEILING,
    }
    receipt["receipt_sha256"] = stable_json_sha256(receipt)
    target = pack_root / REVIEW_RECEIPT_PATH
    target.write_text(
        json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return receipt


def verify_demo_lab_pack(root: str | Path) -> dict[str, Any]:
    """Verify a copied Demo Lab pack and fail closed on any contract drift."""
    pack_root = Path(root)
    if not pack_root.is_dir():
        raise ValueError("Demo Lab pack directory was not found")
    receipt_path = _safe_pack_path(pack_root, REVIEW_RECEIPT_PATH)
    receipt = _load_json_object(receipt_path, "Demo Lab review receipt")
    if receipt.get("schema") != REVIEW_RECEIPT_SCHEMA:
        raise ValueError("Demo Lab review receipt schema is unsupported")
    expected_receipt_hash = str(receipt.get("receipt_sha256") or "")
    unsigned_receipt = dict(receipt)
    unsigned_receipt.pop("receipt_sha256", None)
    if not expected_receipt_hash or stable_json_sha256(unsigned_receipt) != expected_receipt_hash:
        raise ValueError("Demo Lab review receipt content changed")
    if receipt.get("canonicalization") != {
        "schema": CANONICAL_JSON_SCHEMA,
        "omitted_ephemeral_fields": sorted(EPHEMERAL_RUNTIME_FIELDS),
        "generated_at_bound": True,
    }:
        raise ValueError("Demo Lab receipt canonicalization schema is unsupported")

    pack = _require_mapping(receipt.get("pack"), "Demo Lab receipt pack")
    if pack.get("schema") != DEMO_LAB_SCHEMA:
        raise ValueError("Demo Lab pack schema is unsupported")
    if pack.get("manifest") != "manifest.json":
        raise ValueError("Demo Lab manifest reference is unsupported")
    implementation_compatibility = _verify_runtime(receipt)
    session, source_path, messages = _verify_source(pack_root, receipt)
    profile = _verify_model(receipt, session)

    artifacts = receipt.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ValueError("Demo Lab receipt artifacts must be a non-empty array")
    expected_artifacts: dict[str, Mapping[str, Any]] = {}
    for raw in artifacts:
        entry = _require_mapping(raw, "Demo Lab artifact entry")
        reference = str(entry.get("path") or "")
        _safe_pack_path(pack_root, reference)
        if reference in expected_artifacts:
            raise ValueError("Demo Lab receipt contains a duplicate artifact path")
        expected_artifacts[reference] = entry

    actual_paths = _pack_file_paths(pack_root, exclude={REVIEW_RECEIPT_PATH})
    if actual_paths != set(expected_artifacts):
        raise ValueError(
            _path_set_error("Demo Lab receipt artifacts", set(expected_artifacts), actual_paths)
        )
    for reference, entry in expected_artifacts.items():
        artifact_path = _safe_pack_path(pack_root, reference)
        if type(entry.get("bytes")) is not int or entry["bytes"] != artifact_path.stat().st_size:
            raise ValueError(f"Demo Lab artifact size changed: {reference}")
        if str(entry.get("sha256") or "") != file_sha256(artifact_path):
            raise ValueError(f"Demo Lab artifact content changed: {reference}")
    if stable_json_sha256(artifacts) != pack.get("content_sha256"):
        raise ValueError("Demo Lab pack content hash changed")

    manifest = _load_json_object(pack_root / "manifest.json", "Demo Lab manifest")
    if manifest.get("schema") != DEMO_LAB_SCHEMA:
        raise ValueError("Demo Lab manifest schema is unsupported")
    manifest_artifacts = _manifest_artifact_metadata(manifest)
    if set(manifest_artifacts) != {*actual_paths, REVIEW_RECEIPT_PATH}:
        raise ValueError("Demo Lab manifest artifact inventory does not match the pack")
    _verify_manifest_identity(manifest, session, profile)
    _reject_absolute_json_paths(manifest, "Demo Lab manifest")
    _reject_absolute_json_paths(receipt, "Demo Lab review receipt")

    expected_content = _require_mapping(receipt.get("content"), "Demo Lab content hashes")
    actual_content = _semantic_content_hashes(pack_root)
    if dict(expected_content) != actual_content:
        raise ValueError("Demo Lab decision content changed")
    _verify_position_separation(pack_root)

    return {
        "schema": VERIFICATION_SCHEMA,
        "pack": pack_root.name,
        "source": {
            "reference": PORTABLE_SOURCE_PATH,
            "sha256": file_sha256(source_path),
            "event_count": len(messages),
        },
        "content_sha256": pack["content_sha256"],
        "artifact_count": len(artifacts) + 1,
        "bound_artifact_count": len(artifacts),
        "result": {
            "passed": True,
            "predictive_validity": "unmeasured",
            "live_provider_certified": False,
        },
        "implementation_compatibility": implementation_compatibility,
        "evidence_ceiling": EVIDENCE_CEILING,
        "receipt": receipt,
    }


def inspect_portable_replay(
    messages: Iterable[Mapping[str, Any]],
    *,
    session: ReplaySession,
) -> dict[str, Any]:
    """Validate replay identity/timing and summarize its reproducibility fields."""
    loaded = [dict(message) for message in messages]
    if not loaded:
        raise ValueError("portable replay input is empty")
    versions: set[int] = set()
    position_sources: set[str] = set()
    direction_sources: set[str] = set()
    event_times = []
    missing_event_time = 0
    missing_received_time = 0
    option_count = 0
    missing_expiry_time = 0
    supplied_multipliers = []
    providers: set[str] = set()
    known_direction_count = 0
    for message in loaded:
        validate_normalized_message(message)
        version = int(message.get("schema_version", 1))
        versions.add(version)
        symbol = str(message.get("symbol") or "").strip().upper()
        if symbol and symbol != session.symbol:
            raise ValueError("portable replay symbol conflicts with catalog identity")
        provider = str(message.get("provider") or "").strip()
        if provider:
            providers.add(provider)
        exact_event_time = parse_market_datetime(message.get("event_time"))
        received_time = parse_market_datetime(message.get("received_time"))
        if exact_event_time is None:
            missing_event_time += 1
        else:
            event_times.append(exact_event_time)
        if received_time is None:
            missing_received_time += 1
        elif (
            session.research_loop
            and exact_event_time is not None
            and received_time < exact_event_time
        ):
            raise ValueError("portable research loop received_time precedes event_time")
        if message.get("type") != "options_volume_tick":
            continue
        option_count += 1
        source = str(message.get("position_source") or "trade_volume")
        position_sources.add(source)
        direction_source = str(message.get("direction_source") or "unknown")
        if direction_source != "unknown":
            direction_sources.add(direction_source)
        if str(message.get("aggressor_side") or "unknown") != "unknown":
            known_direction_count += 1
        multiplier = message.get("contract_multiplier")
        if multiplier not in (None, ""):
            supplied_multipliers.append(multiplier)
            if (
                isinstance(multiplier, bool)
                or not isinstance(multiplier, (int, float))
                or float(multiplier) != float(session.contract_multiplier)
            ):
                raise ValueError("portable replay multiplier conflicts with catalog identity")
        expiry_time = parse_market_datetime(message.get("expiry_timestamp"))
        if expiry_time is None:
            missing_expiry_time += 1
        elif (
            session.research_loop
            and exact_event_time is not None
            and expiry_time <= exact_event_time
        ):
            raise ValueError("portable research loop expiry must follow event_time")

    if event_times != sorted(event_times):
        raise ValueError("portable replay event_time order regressed")
    if session.research_loop:
        if versions != {2} or 2 > NORMALIZED_SCHEMA_VERSION:
            raise ValueError("portable research loop requires normalized schema v2")
        if missing_event_time or missing_received_time or missing_expiry_time:
            raise ValueError(
                "portable research loop requires exact event, received, and expiry times"
            )
        if position_sources != {"open_interest", "trade_volume"}:
            raise ValueError("portable research loop requires separate OI and trade-volume rows")
        if not direction_sources or not known_direction_count:
            raise ValueError("portable research loop requires directional trade provenance")
        if providers != {"synthetic"}:
            raise ValueError("portable research loop accepts only the synthetic provider")
        if len(supplied_multipliers) != option_count:
            raise ValueError("portable research loop requires a multiplier on every option row")
        if not (
            session.source_kind == "synthetic_fixture"
            and session.rights_status in {"owned", "public_domain", "redistributable"}
            and session.redistributable
        ):
            raise ValueError("portable research loop source authorization is insufficient")

    return {
        "event_count": len(loaded),
        "normalized_schema_versions": sorted(versions),
        "position_sources": sorted(position_sources),
        "direction_sources": sorted(direction_sources),
        "first_event_time": (
            event_times[0].isoformat().replace("+00:00", "Z") if event_times else None
        ),
        "last_event_time": (
            event_times[-1].isoformat().replace("+00:00", "Z") if event_times else None
        ),
        "missing_event_time_count": missing_event_time,
        "missing_received_time_count": missing_received_time,
        "missing_expiry_time_count": missing_expiry_time,
    }


def load_portable_replay(path: str | Path) -> list[dict[str, Any]]:
    """Load JSONL without accepting duplicate keys or non-object messages."""
    loaded = []
    with Path(path).open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            text = line.strip()
            if not text or text.startswith("#"):
                continue
            try:
                message = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid portable replay JSON at line {line_number}") from exc
            if not isinstance(message, Mapping):
                raise ValueError(f"portable replay line {line_number} must be an object")
            loaded.append(dict(message))
    return loaded


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_runtime(receipt: Mapping[str, Any]) -> dict[str, Any]:
    application = _require_mapping(receipt.get("application"), "Demo Lab application")
    if application.get("package") != "gex-terminal":
        raise ValueError("Demo Lab application package is unsupported")
    recorded_version = str(application.get("version") or "")
    supported_producers = SUPPORTED_DEMO_LAB_PRODUCERS.get(REVIEW_RECEIPT_SCHEMA)
    if supported_producers is None or recorded_version not in supported_producers:
        raise ValueError(
            "Demo Lab receipt producer version is unsupported: " + recorded_version
        )
    if application.get("python_interface") != "experimental":
        raise ValueError("Demo Lab Python interface status is unsupported")
    runtime = _require_mapping(receipt.get("runtime"), "Demo Lab runtime")
    runtime_schema = str(runtime.get("schema") or "")
    supported_readers = SUPPORTED_DEMO_LAB_READERS.get(runtime_schema)
    if supported_readers is None:
        raise ValueError("Demo Lab runtime contract is unsupported")
    if __version__ not in supported_readers:
        raise ValueError(
            "Current package version is not declared compatible with Demo Lab runtime "
            f"{runtime_schema}: {__version__}"
        )
    if dict(runtime) != portable_runtime_contract():
        raise ValueError("Demo Lab runtime contract is incompatible")
    return {
        "status": "compatible",
        "runtime_contract": runtime_schema,
        "recorded_package": "gex-terminal",
        "recorded_version": recorded_version,
        "current_package": "gex-terminal",
        "current_version": __version__,
    }


def _verify_source(
    root: Path,
    receipt: Mapping[str, Any],
) -> tuple[ReplaySession, Path, list[dict[str, Any]]]:
    source = _require_mapping(receipt.get("source"), "Demo Lab source")
    if source.get("reference") != PORTABLE_SOURCE_PATH:
        raise ValueError("Demo Lab source reference is unsupported")
    source_path = _safe_pack_path(root, PORTABLE_SOURCE_PATH)
    if source.get("sha256") != file_sha256(source_path):
        raise ValueError("Demo Lab source input changed")
    if type(source.get("bytes")) is not int or source["bytes"] != source_path.stat().st_size:
        raise ValueError("Demo Lab source input size changed")
    session = replay_session_for_name(str(source.get("session_name") or ""))
    if (
        source.get("catalog_reference") != session.source_ref
        or source.get("symbol") != session.symbol
        or source.get("contract_multiplier") != session.contract_multiplier
    ):
        raise ValueError("Demo Lab source identity conflicts with the replay catalog")
    expected_contract = (
        "synthetic_schema_v2_position_ladder" if session.research_loop else "bundled_replay"
    )
    if source.get("research_contract") != expected_contract:
        raise ValueError("Demo Lab source research contract is incompatible")
    authorization = _require_mapping(source.get("authorization"), "Demo Lab authorization")
    expected_authorization = {
        "source_kind": session.source_kind,
        "rights_status": session.rights_status,
        "redistributable": session.redistributable,
        "synthetic": session.source_kind == "synthetic_fixture",
        "live_data": False,
        "credentials": False,
    }
    if dict(authorization) != expected_authorization:
        raise ValueError("Demo Lab source authorization changed or is insufficient")
    messages = load_portable_replay(source_path)
    observations = inspect_portable_replay(messages, session=session)
    for field in (
        "event_count",
        "normalized_schema_versions",
        "position_sources",
        "direction_sources",
        "first_event_time",
        "last_event_time",
        "missing_event_time_count",
        "missing_received_time_count",
        "missing_expiry_time_count",
    ):
        if source.get(field) != observations[field]:
            raise ValueError(f"Demo Lab source observation changed: {field}")
    return session, source_path, messages


def _verify_model(
    receipt: Mapping[str, Any],
    session: ReplaySession,
) -> dict[str, Any]:
    model = _require_mapping(receipt.get("model"), "Demo Lab model")
    if model.get("model_version") != MODEL_PROFILE_VERSION:
        raise ValueError("Demo Lab model version is incompatible")
    if model.get("position_models_are_separate") is not True:
        raise ValueError("Demo Lab position-model separation is not asserted")
    profile = validate_model_profile(
        _require_mapping(model.get("profile"), "Demo Lab model profile")
    )
    if model.get("profile_sha256") != stable_json_sha256(profile):
        raise ValueError("Demo Lab model profile content changed")
    if (
        profile["symbol"] != session.symbol
        or profile["contract_multiplier"] != session.contract_multiplier
    ):
        raise ValueError("Demo Lab model identity conflicts with the source")
    return profile


def _verify_manifest_identity(
    manifest: Mapping[str, Any],
    session: ReplaySession,
    profile: Mapping[str, Any],
) -> None:
    replay = _require_mapping(manifest.get("replay_session"), "Demo Lab replay session")
    inputs = _require_mapping(manifest.get("inputs"), "Demo Lab inputs")
    summary = _require_mapping(manifest.get("summary"), "Demo Lab summary")
    if (
        replay.get("name") != session.name
        or replay.get("path") != session.source_ref
        or replay.get("symbol") != session.symbol
        or replay.get("contract_multiplier") != session.contract_multiplier
        or summary.get("symbol") != session.symbol
        or inputs.get("contract_multiplier") != session.contract_multiplier
        or inputs.get("model_version") != MODEL_PROFILE_VERSION
        or inputs.get("model_profile_sha256") != stable_json_sha256(profile)
    ):
        raise ValueError("Demo Lab manifest identity conflicts with source or model")
    limitations = _require_mapping(manifest.get("limitations"), "Demo Lab limitations")
    if (
        limitations.get("position_models_may_not_be_summed") is not True
        or limitations.get("predictive_validity") != "unmeasured"
        or limitations.get("live_provider_certified") is not False
        or limitations.get("authenticity") != "unkeyed_hashes_only"
    ):
        raise ValueError("Demo Lab manifest limitations are incomplete")


def _verify_position_separation(root: Path) -> None:
    report = _load_json_object(
        root / "position-model-comparison.json",
        "position-model comparison",
    )
    models = _require_mapping(report.get("models"), "position models")
    if set(models) != {
        "open_interest",
        "raw_trade_volume",
        "directionalized_trade_volume",
    }:
        raise ValueError("Demo Lab position-model ladder is incomplete")
    result = _require_mapping(report.get("result"), "position-model result")
    limitations = _require_mapping(report.get("limitations"), "position-model limitations")
    if (
        result.get("models_may_not_be_summed") is not True
        or limitations.get("models_may_not_be_summed") is not True
        or result.get("predictive_validity") != "unmeasured"
    ):
        raise ValueError("Demo Lab position models are not safely separated")


def _semantic_content_hashes(root: Path) -> dict[str, str]:
    hashes = {}
    for reference in REQUIRED_SEMANTIC_ARTIFACTS:
        payload = _load_json_object(_safe_pack_path(root, reference), reference)
        hashes[reference] = stable_json_sha256(payload)
    return hashes


def _manifest_artifact_metadata(manifest: Mapping[str, Any]) -> dict[str, str]:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ValueError("Demo Lab manifest artifacts must be a non-empty array")
    result = {}
    for raw in artifacts:
        entry = _require_mapping(raw, "Demo Lab manifest artifact")
        path = str(entry.get("path") or "")
        kind = str(entry.get("kind") or "")
        if not path or not kind:
            raise ValueError("Demo Lab manifest artifact requires path and kind")
        if path in result:
            raise ValueError("Demo Lab manifest contains a duplicate artifact path")
        result[path] = kind
    return result


def _pack_file_paths(root: Path, *, exclude: set[str]) -> set[str]:
    result = set()
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError("Demo Lab packs may not contain symbolic links")
        if path.is_file():
            reference = path.relative_to(root).as_posix()
            if reference not in exclude:
                result.add(reference)
    return result


def _safe_pack_path(root: Path, reference: str) -> Path:
    if not reference or "\\" in reference:
        raise ValueError("Demo Lab pack reference is empty or non-portable")
    relative = Path(reference)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Demo Lab pack reference escapes the pack")
    root_resolved = root.resolve()
    candidate = root_resolved / relative
    try:
        candidate.resolve().relative_to(root_resolved)
    except ValueError as exc:
        raise ValueError("Demo Lab pack reference escapes the pack") from exc
    if candidate.is_symlink():
        raise ValueError("Demo Lab pack references may not be symbolic links")
    return candidate


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
        )
    except FileNotFoundError as exc:
        raise ValueError(f"{label} is missing") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is not valid JSON") from exc
    if not isinstance(payload, Mapping):
        raise ValueError(f"{label} must be a JSON object")
    return dict(payload)


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key is not allowed: {key}")
        result[key] = value
    return result


def _require_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _without_ephemeral_runtime(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _without_ephemeral_runtime(item)
            for key, item in value.items()
            if key not in EPHEMERAL_RUNTIME_FIELDS
        }
    if isinstance(value, list):
        return [_without_ephemeral_runtime(item) for item in value]
    return value


def _reject_absolute_json_paths(value: Any, label: str) -> None:
    if isinstance(value, Mapping):
        for item in value.values():
            _reject_absolute_json_paths(item, label)
        return
    if isinstance(value, list):
        for item in value:
            _reject_absolute_json_paths(item, label)
        return
    if isinstance(value, str) and (
        value.startswith("/") or re.match(r"^[A-Za-z]:[\\/]", value)
    ):
        raise ValueError(f"{label} contains an absolute path")


def _path_set_error(label: str, expected: set[str], actual: set[str]) -> str:
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    details = []
    if missing:
        details.append("missing=" + ",".join(missing))
    if extra:
        details.append("extra=" + ",".join(extra))
    return f"{label} do not match ({'; '.join(details)})"
