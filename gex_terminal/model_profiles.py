"""Versioned, explicit model profiles for reproducible offline research."""

from __future__ import annotations

import json
import math
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping

from gex_terminal.config import GexConfig


MODEL_PROFILE_SCHEMA = "gex-terminal.model-profile.v1"
MODEL_PROFILE_VERSION = "gex-terminal.gex-model.v2"


def default_model_profile(config: GexConfig) -> dict[str, Any]:
    """Return the complete explicit profile represented by ``config``."""
    return {
        "schema": MODEL_PROFILE_SCHEMA,
        "profile_id": "default",
        "model_version": MODEL_PROFILE_VERSION,
        "symbol": config.symbol,
        "contract_multiplier": config.contract_multiplier,
        "risk_free_rate": config.risk_free_rate,
        "days_to_expiry": config.days_to_expiry,
        "expiry_filter": config.expiry_filter,
        "pricing": {
            "futures_options": "black_76",
            "equity_index_options": "black_scholes",
            "day_count": "ACT/365",
        },
        "position_models": [
            "open_interest",
            "raw_trade_volume",
            "directionalized_trade_volume",
        ],
        "minimum_directional_coverage": 0.5,
        "maximum_underlying_age_seconds": 2.0,
        "predictive_validity": "unmeasured",
    }


def load_model_profile(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("model profile must be a JSON object")
    return validate_model_profile(payload)


def validate_model_profile(profile: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and normalize one public model-profile contract."""
    if profile.get("schema") != MODEL_PROFILE_SCHEMA:
        raise ValueError(f"model profile schema must be {MODEL_PROFILE_SCHEMA}")
    profile_id = str(profile.get("profile_id") or "").strip()
    if not profile_id:
        raise ValueError("model profile requires profile_id")
    if profile.get("model_version") != MODEL_PROFILE_VERSION:
        raise ValueError(f"model_version must be {MODEL_PROFILE_VERSION}")
    symbol = str(profile.get("symbol") or "").strip().upper()
    if not symbol:
        raise ValueError("model profile requires symbol")
    multiplier = _positive_number(profile.get("contract_multiplier"), "contract_multiplier")
    if not multiplier.is_integer():
        raise ValueError("contract_multiplier must be an integer")
    rate = _finite_number(profile.get("risk_free_rate"), "risk_free_rate")
    dte = _positive_number(profile.get("days_to_expiry"), "days_to_expiry")
    expiry_filter = str(profile.get("expiry_filter") or "").strip()
    if not expiry_filter:
        raise ValueError("model profile requires expiry_filter")
    coverage = _finite_number(
        profile.get("minimum_directional_coverage"),
        "minimum_directional_coverage",
    )
    if not 0 <= coverage <= 1:
        raise ValueError("minimum_directional_coverage must be between 0 and 1")
    maximum_age = _finite_number(
        profile.get("maximum_underlying_age_seconds"),
        "maximum_underlying_age_seconds",
    )
    if maximum_age < 0:
        raise ValueError("maximum_underlying_age_seconds must be non-negative")
    pricing = profile.get("pricing")
    if not isinstance(pricing, Mapping) or dict(pricing) != {
        "futures_options": "black_76",
        "equity_index_options": "black_scholes",
        "day_count": "ACT/365",
    }:
        raise ValueError("model profile pricing contract is unsupported")
    position_models = profile.get("position_models")
    expected_models = (
        "open_interest",
        "raw_trade_volume",
        "directionalized_trade_volume",
    )
    if not isinstance(position_models, list) or tuple(position_models) != expected_models:
        raise ValueError("position_models must preserve the OI/raw/directional ladder")
    if profile.get("predictive_validity") != "unmeasured":
        raise ValueError("offline model profiles require predictive_validity=unmeasured")
    return {
        "schema": MODEL_PROFILE_SCHEMA,
        "profile_id": profile_id,
        "model_version": MODEL_PROFILE_VERSION,
        "symbol": symbol,
        "contract_multiplier": int(multiplier),
        "risk_free_rate": rate,
        "days_to_expiry": dte,
        "expiry_filter": expiry_filter,
        "pricing": dict(pricing),
        "position_models": list(expected_models),
        "minimum_directional_coverage": coverage,
        "maximum_underlying_age_seconds": maximum_age,
        "predictive_validity": "unmeasured",
    }


def config_from_model_profile(
    profile: Mapping[str, Any], *, base: GexConfig | None = None
) -> GexConfig:
    """Build deterministic runtime configuration from a validated profile."""
    normalized = validate_model_profile(profile)
    if base is None:
        base = GexConfig(
            symbol=normalized["symbol"],
            symbols=(normalized["symbol"],),
            data_mode="replay",
            data_provider="replay",
            contract_multiplier=int(normalized["contract_multiplier"]),
            risk_free_rate=normalized["risk_free_rate"],
            days_to_expiry=normalized["days_to_expiry"],
            refresh_interval_seconds=1.0,
            stale_after_seconds=10.0,
            replay_path="",
            replay_delay_seconds=0.0,
            tradovate_environment="demo",
            expiry_filter=normalized["expiry_filter"],
            replay_clock="none",
        )
    return replace(
        base,
        symbol=normalized["symbol"],
        symbols=(normalized["symbol"], *tuple(
            symbol for symbol in base.symbols if symbol != normalized["symbol"]
        ))[:4],
        contract_multiplier=int(normalized["contract_multiplier"]),
        risk_free_rate=normalized["risk_free_rate"],
        days_to_expiry=normalized["days_to_expiry"],
        expiry_filter=normalized["expiry_filter"],
    )


def _finite_number(value: Any, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


def _positive_number(value: Any, label: str) -> float:
    number = _finite_number(value, label)
    if number <= 0:
        raise ValueError(f"{label} must be positive")
    return number
