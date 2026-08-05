"""Stable paths to data files shipped inside the installed package."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path


def package_data_path(*parts: str) -> Path:
    """Resolve an installed package-data resource to its filesystem path."""
    resource = files("gex_terminal").joinpath("data", *parts)
    return Path(str(resource)).resolve()


def replay_data_path(name: str) -> Path:
    return package_data_path("replays", name)


def provider_fixture_path(name: str) -> Path:
    return package_data_path("provider_fixtures", name)


def replay_data_dir() -> Path:
    return package_data_path("replays")


def provider_fixture_dir() -> Path:
    return package_data_path("provider_fixtures")


def portable_package_data_reference(path: str | Path) -> str:
    """Return a stable identity for packaged data while preserving other paths.

    Package resources resolve to checkout- or environment-specific absolute paths
    for I/O.  Those locations must not leak into persisted reports, so callers use
    this helper at serialization boundaries.
    """
    candidate = Path(path)
    try:
        relative = candidate.resolve().relative_to(package_data_path())
    except ValueError:
        return str(path)
    return (Path("gex_terminal") / "data" / relative).as_posix()
