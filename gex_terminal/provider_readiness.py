"""Canonical provider-readiness vocabulary, separate from runtime connection state."""

from __future__ import annotations

from gex_terminal.config import GexConfig


PROVIDER_READINESS_STATES = (
    "offline-certified",
    "delayed",
    "scaffold",
    "live-uncertified",
    "live-certified",
)


def validate_provider_readiness(value: str) -> str:
    normalized = str(value).strip().lower()
    if normalized not in PROVIDER_READINESS_STATES:
        raise ValueError(
            "provider readiness must be one of: "
            + ", ".join(PROVIDER_READINESS_STATES)
        )
    return normalized


def runtime_provider_readiness(config: GexConfig) -> str:
    """Return readiness for the data path in use, not its connection status."""
    if config.data_mode.lower() in {"demo", "replay"}:
        return "offline-certified"
    from gex_terminal.adapters.registry import adapter_info

    return validate_provider_readiness(adapter_info(config.data_provider).status)
