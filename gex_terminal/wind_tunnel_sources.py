"""Explicit, bounded saved checkpoints for one offline Wind Tunnel session.

The operator selects local files at startup. Browser requests carry detached
checkpoint transports; neither source selection nor calculation opens a path.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import stat

from . import wind_tunnel
from .wind_tunnel_checkpoint import checkpoint_transport, read_checkpoint, validate_checkpoint


MAX_COMPARISON_CHECKPOINTS = 2
MAX_REGISTERED_CAPTURE_BYTES = 1024 * 1024 * 1024


class SavedCheckpointCore:
    """Keep the primary source/defaults while advertising explicit alternatives."""

    def __init__(self, primary: dict, comparisons: list[dict] | tuple[dict, ...] = ()):
        if len(comparisons) > MAX_COMPARISON_CHECKPOINTS:
            raise ValueError("Choose at most two additional saved checkpoints")
        self._core = wind_tunnel.TerminalCheckpointCore(primary)
        self._artifacts = []
        seen = set()
        for artifact in (primary, *comparisons):
            checked = validate_checkpoint(artifact)
            if checked["sha256"] not in seen:
                self._artifacts.append(checked)
                seen.add(checked["sha256"])

    def __getattr__(self, name):
        # Delegate dynamically, including new operations and identity functions.
        return getattr(self._core, name)

    def catalog(self) -> dict:
        result = self._core.catalog()
        result["saved_checkpoints"] = [
            {"artifact": checkpoint_transport(artifact),
             "label": f"Saved {artifact['source']['symbol']} checkpoint · {artifact['source']['as_of']}",
             "symbol": artifact["source"]["symbol"],
             "checkpoint_sha256": artifact["sha256"]}
            for artifact in self._artifacts
        ]
        # The added catalog is part of the report digest; numeric identity stays
        # delegated to the same calculation implementation used by receipts.
        result.pop("result_sha256", None)
        result["result_sha256"] = wind_tunnel._sha(result)
        return result


def checkpoint_core(primary_path: Path | None, comparison_paths=()) -> SavedCheckpointCore | None:
    paths = tuple(comparison_paths)
    if len(paths) > MAX_COMPARISON_CHECKPOINTS:
        raise ValueError("Choose at most two additional saved checkpoints")
    if primary_path is None:
        if paths:
            raise ValueError("Additional saved checkpoints require --checkpoint")
        return None
    # Validate every supplied file, including duplicate paths, before startup.
    # A duplicate never hides a corrupt or symlink input.
    primary = read_checkpoint(primary_path)
    comparisons = [read_checkpoint(path) for path in paths]
    return SavedCheckpointCore(primary, comparisons)


def validate_registered_checkpoint(checkpoint_path: Path, capture_path: Path, symbol: str,
                                   checkpoint_sha256: str, capture_sha256: str) -> dict:
    """Check a prior registration without replaying or importing any provider.

    The registry binds a checkpoint to a previously verified frozen capture.
    Hashing the regular local capture detects later changes; the saved checksum
    and strict checkpoint reader bind the detached input used by the browser.
    """
    if symbol not in {"ES", "NQ"} or any(
        not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value)
        for value in (checkpoint_sha256, capture_sha256)
    ):
        raise ValueError("Invalid saved comparison registration")
    checkpoint = read_checkpoint(checkpoint_path)
    if (checkpoint["source"]["symbol"] != symbol or checkpoint["sha256"] != checkpoint_sha256
            or checkpoint["source"]["data_mode"] != "REPLAY"):
        raise ValueError("Saved comparison checkpoint changed or has another symbol")
    descriptor = os.open(capture_path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_REGISTERED_CAPTURE_BYTES:
            raise ValueError("Saved comparison capture must be a bounded regular file")
        checksum, size = hashlib.sha256(), 0
        while block := stream.read(1024 * 1024):
            size += len(block)
            if size > MAX_REGISTERED_CAPTURE_BYTES:
                raise ValueError("Saved comparison capture exceeds its local bound")
            checksum.update(block)
        if checksum.hexdigest() != capture_sha256:
            raise ValueError("Saved comparison capture changed")
    return {"symbol": symbol, "checkpoint_sha256": checkpoint["sha256"]}
