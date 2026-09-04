"""Versioned, fail-closed policy for bounded Databento certification runs.

The thresholds in this module are repository-owned certification choices. They
are not claims about current Databento entitlements, market coverage, or the
amount of evidence required to establish predictive validity.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from numbers import Real
from typing import Any, Mapping


CERTIFICATION_POLICY_SCHEMA = "gex-terminal.databento-certification-policy.v1"
CERTIFICATION_POLICY_VERSION = 1
CERTIFICATION_POLICY_IDENTITY_SCHEMA = (
    "gex-terminal.databento-certification-policy-identity.v1"
)
CERTIFICATION_POLICY_CANONICALIZATION = "gex-terminal.canonical-json.v1"
CANONICAL_CONTRACT_MULTIPLIERS = {"ES": 50.0, "NQ": 20.0}


def _finite_float(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{field_name} must be finite")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be finite") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field_name} must be finite")
    return number


@dataclass(frozen=True)
class DatabentoCertificationThresholds:
    """Quantitative gates for one symbol-scoped certification window."""

    minimum_provider_frames: int
    minimum_definitions: int
    minimum_underlying_quotes: int
    minimum_option_trades: int
    minimum_normalized_option_states: int
    minimum_distinct_expiries: int
    minimum_distinct_strikes: int
    minimum_sequence_observations: int
    minimum_fresh_underlying_coverage: float
    minimum_sequence_coverage: float
    minimum_sequence_integrity: float
    minimum_contract_multiplier_coverage: float
    minimum_usable_iv_coverage: float
    minimum_inverted_iv_age_coverage: float
    maximum_fallback_iv_coverage: float
    maximum_inversion_failure_coverage: float
    maximum_underlying_age_ms: float

    def __post_init__(self) -> None:
        minimum_counts = (
            "minimum_provider_frames",
            "minimum_definitions",
            "minimum_underlying_quotes",
            "minimum_option_trades",
            "minimum_normalized_option_states",
            "minimum_distinct_expiries",
            "minimum_distinct_strikes",
            "minimum_sequence_observations",
        )
        for field_name in minimum_counts:
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{field_name} must be a positive integer")

        minimum_coverages = (
            "minimum_fresh_underlying_coverage",
            "minimum_sequence_coverage",
            "minimum_sequence_integrity",
            "minimum_contract_multiplier_coverage",
            "minimum_usable_iv_coverage",
            "minimum_inverted_iv_age_coverage",
        )
        for field_name in minimum_coverages:
            value = _finite_float(getattr(self, field_name), field_name)
            if not 0.0 < value <= 1.0:
                raise ValueError(f"{field_name} must be greater than 0 and at most 1")

        maximum_coverages = (
            "maximum_fallback_iv_coverage",
            "maximum_inversion_failure_coverage",
        )
        for field_name in maximum_coverages:
            value = _finite_float(getattr(self, field_name), field_name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{field_name} must be between 0 and 1")

        maximum_age = _finite_float(
            self.maximum_underlying_age_ms,
            "maximum_underlying_age_ms",
        )
        if maximum_age <= 0:
            raise ValueError("maximum_underlying_age_ms must be positive")

    def to_dict(self) -> dict[str, int | float]:
        return asdict(self)


@dataclass(frozen=True)
class DatabentoCertificationPolicy:
    """Immutable identity and thresholds for one supported futures root."""

    policy_id: str
    version: int
    symbol: str
    canonical_contract_multiplier: float
    thresholds: DatabentoCertificationThresholds
    provider: str = "databento"
    dataset: str = "GLBX.MDP3"
    schema: str = CERTIFICATION_POLICY_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != CERTIFICATION_POLICY_SCHEMA:
            raise ValueError(f"unsupported certification policy schema: {self.schema}")
        if (
            isinstance(self.version, bool)
            or not isinstance(self.version, int)
            or self.version != CERTIFICATION_POLICY_VERSION
        ):
            raise ValueError(f"unsupported certification policy version: {self.version}")
        if not isinstance(self.policy_id, str) or not self.policy_id.strip():
            raise ValueError("certification policy requires policy_id")
        if self.provider != "databento":
            raise ValueError("Databento certification policy provider must be databento")
        if not isinstance(self.dataset, str) or not self.dataset.strip():
            raise ValueError("certification policy requires dataset")
        if str(self.symbol) not in CANONICAL_CONTRACT_MULTIPLIERS:
            raise ValueError(f"unsupported Databento certification symbol: {self.symbol}")
        multiplier = _finite_float(
            self.canonical_contract_multiplier,
            "canonical_contract_multiplier",
        )
        if multiplier <= 0:
            raise ValueError("canonical_contract_multiplier must be positive")
        expected_multiplier = CANONICAL_CONTRACT_MULTIPLIERS[str(self.symbol)]
        if not math.isclose(
            multiplier,
            expected_multiplier,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError(
                f"{self.symbol} canonical_contract_multiplier must be "
                f"{expected_multiplier:g}"
            )
        if not isinstance(self.thresholds, DatabentoCertificationThresholds):
            raise ValueError(
                "certification policy thresholds must be "
                "DatabentoCertificationThresholds"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "policy_id": self.policy_id,
            "version": self.version,
            "provider": self.provider,
            "dataset": self.dataset,
            "symbol": self.symbol,
            "canonical_contract_multiplier": float(
                self.canonical_contract_multiplier
            ),
            "thresholds": self.thresholds.to_dict(),
        }


def certification_policy_identity(
    policy: DatabentoCertificationPolicy,
) -> dict[str, str | int]:
    """Return a canonical identity for the complete registered policy content."""
    if not isinstance(policy, DatabentoCertificationPolicy):
        raise ValueError(
            "certification policy identity requires DatabentoCertificationPolicy"
        )
    encoded = json.dumps(
        policy.to_dict(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return {
        "schema": CERTIFICATION_POLICY_IDENTITY_SCHEMA,
        "canonicalization": CERTIFICATION_POLICY_CANONICALIZATION,
        "policy_schema": policy.schema,
        "policy_id": policy.policy_id,
        "policy_version": policy.version,
        "sha256": hashlib.sha256(encoded).hexdigest(),
    }


def _prelive_thresholds() -> DatabentoCertificationThresholds:
    return DatabentoCertificationThresholds(
        minimum_provider_frames=50,
        minimum_definitions=24,
        minimum_underlying_quotes=5,
        minimum_option_trades=20,
        minimum_normalized_option_states=12,
        minimum_distinct_expiries=2,
        minimum_distinct_strikes=8,
        minimum_sequence_observations=12,
        minimum_fresh_underlying_coverage=1.0,
        minimum_sequence_coverage=1.0,
        minimum_sequence_integrity=1.0,
        minimum_contract_multiplier_coverage=1.0,
        minimum_usable_iv_coverage=1.0,
        minimum_inverted_iv_age_coverage=1.0,
        maximum_fallback_iv_coverage=0.0,
        maximum_inversion_failure_coverage=0.0,
        maximum_underlying_age_ms=2_000.0,
    )


ES_PRELIVE_V1 = DatabentoCertificationPolicy(
    policy_id="databento-es-prelive-v1",
    version=CERTIFICATION_POLICY_VERSION,
    symbol="ES",
    canonical_contract_multiplier=50.0,
    thresholds=_prelive_thresholds(),
)

NQ_PRELIVE_V1 = DatabentoCertificationPolicy(
    policy_id="databento-nq-prelive-v1",
    version=CERTIFICATION_POLICY_VERSION,
    symbol="NQ",
    canonical_contract_multiplier=20.0,
    thresholds=_prelive_thresholds(),
)


_POLICIES_BY_ID = {
    ES_PRELIVE_V1.policy_id: ES_PRELIVE_V1,
    NQ_PRELIVE_V1.policy_id: NQ_PRELIVE_V1,
}
_DEFAULT_POLICY_BY_SYMBOL = {
    ES_PRELIVE_V1.symbol: ES_PRELIVE_V1,
    NQ_PRELIVE_V1.symbol: NQ_PRELIVE_V1,
}


def resolve_databento_certification_policy(
    *,
    symbol: str,
    policy: str | Mapping[str, Any] | DatabentoCertificationPolicy | None = None,
) -> DatabentoCertificationPolicy:
    """Resolve and validate a policy before any adapter or credential use."""
    normalized_symbol = str(symbol).strip().upper()
    if policy is None:
        selected = _DEFAULT_POLICY_BY_SYMBOL.get(normalized_symbol)
        if selected is None:
            raise ValueError(
                f"unsupported Databento certification symbol: {normalized_symbol or '<empty>'}"
            )
    elif isinstance(policy, str):
        selected = _POLICIES_BY_ID.get(policy)
        if selected is None:
            raise ValueError(f"unknown Databento certification policy: {policy}")
    elif isinstance(policy, DatabentoCertificationPolicy):
        selected = policy
    elif isinstance(policy, Mapping):
        selected = _policy_from_mapping(policy)
    else:
        raise ValueError("unsupported Databento certification policy value")

    if selected.symbol != normalized_symbol:
        raise ValueError(
            f"certification policy {selected.policy_id} targets {selected.symbol}, "
            f"not {normalized_symbol or '<empty>'}"
        )
    registered = _POLICIES_BY_ID.get(selected.policy_id)
    if registered is not None and selected != registered:
        raise ValueError(
            f"registered certification policy content mismatch: {selected.policy_id}"
        )
    return selected


def validate_contract_multiplier(
    policy: DatabentoCertificationPolicy,
    contract_multiplier: float,
) -> float:
    """Return a finite canonical multiplier or reject the run before I/O."""
    multiplier = _finite_float(contract_multiplier, "contract_multiplier")
    if not math.isclose(
        multiplier,
        float(policy.canonical_contract_multiplier),
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        raise ValueError(
            f"contract_multiplier {multiplier:g} does not match "
            f"{policy.symbol} policy {policy.policy_id} canonical multiplier "
            f"{policy.canonical_contract_multiplier:g}"
        )
    return multiplier


def _policy_from_mapping(values: Mapping[str, Any]) -> DatabentoCertificationPolicy:
    allowed = {
        "schema",
        "policy_id",
        "version",
        "provider",
        "dataset",
        "symbol",
        "canonical_contract_multiplier",
        "thresholds",
    }
    unknown = sorted(set(values) - allowed)
    if unknown:
        raise ValueError(
            "unknown Databento certification policy field(s): " + ", ".join(unknown)
        )
    threshold_values = values.get("thresholds")
    if not isinstance(threshold_values, Mapping):
        raise ValueError("certification policy requires a thresholds mapping")
    try:
        thresholds = DatabentoCertificationThresholds(**dict(threshold_values))
        return DatabentoCertificationPolicy(
            schema=values.get("schema", CERTIFICATION_POLICY_SCHEMA),
            policy_id=values["policy_id"],
            version=values["version"],
            provider=values.get("provider", "databento"),
            dataset=values.get("dataset", "GLBX.MDP3"),
            symbol=str(values["symbol"]).upper(),
            canonical_contract_multiplier=values["canonical_contract_multiplier"],
            thresholds=thresholds,
        )
    except KeyError as exc:
        raise ValueError(
            f"certification policy missing required field: {exc.args[0]}"
        ) from exc
    except TypeError as exc:
        raise ValueError(f"invalid certification policy thresholds: {exc}") from exc
