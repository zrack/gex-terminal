"""Bind saved flip investigations to explicit frozen catalog checkpoints."""

import asyncio
import json
import re


def _valid_digest(value) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _checkpoint_entries(catalog):
    for source in catalog.get("sessions", ()):
        if source.get("name") == "terminal-checkpoint":
            yield source, source.get("source_sha256"), True
    for source in catalog.get("saved_checkpoints", ()):
        yield source, source.get("checkpoint_sha256"), False


def _matches_checkpoint(source, primary, replay):
    if replay.symbol != source.get("symbol"):
        return False
    transport = source.get("terminal_checkpoint" if primary else "artifact")
    if not isinstance(transport, str):
        return False
    checkpoint = json.loads(transport)
    expected = f"Saved {replay.symbol} capture {replay.capture_sha256[:16]} · final event"
    return checkpoint["source"]["label"] == expected


class SavedReplayRegistry:
    def __init__(self, core, bindings=None, *, single=None):
        self._bindings = dict(bindings or {})
        self._single = single
        self.comparison_symbol = None
        if not self._bindings:
            self._replays = (single,) if single is not None else ()
        else:
            self._replays = tuple(self._bindings.values())
            digests = {replay.capture_sha256 for replay in self._replays}
            symbols = {replay.symbol for replay in self._replays}
            if (single is not None or len(self._bindings) > 2
                    or len(digests) != len(self._replays)
                    or not symbols <= {"ES", "NQ"} or not all(map(_valid_digest, digests))
                    or not all(map(_valid_digest, self._bindings))):
                raise ValueError("Saved replays require distinct verified capture and checkpoint bindings.")
            entries = list(_checkpoint_entries(core.catalog()))
            primary = next((checksum for _, checksum, main in entries if main), None)
            matched = {checksum for source, checksum, main in entries if checksum in self._bindings
                       and _matches_checkpoint(source, main, self._bindings[checksum])}
            if primary not in self._bindings or matched != self._bindings.keys():
                raise ValueError("Saved replay bindings must match the catalog checkpoints and markets.")
            other = symbols - {self._bindings[primary].symbol}
            self.comparison_symbol = next(iter(other), None)
        self._locks = {replay: asyncio.Lock() for replay in self._replays}

    def decorate_catalog(self, catalog: dict) -> bool:
        changed = False
        for source, checksum, primary in _checkpoint_entries(catalog):
            replay = self._bindings.get(checksum)
            if replay is None and primary:
                replay = self._single
            if replay is not None and replay.symbol == source.get("symbol") and replay.capture_sha256:
                source["investigation_capture"] = {"sha256": replay.capture_sha256}
                changed = True
        return changed

    def select(self, request):
        if not isinstance(request, dict):
            return None
        checksum = request.get("capture_sha256")
        if not _valid_digest(checksum):
            return None
        if self._single is not None and self._single.capture_sha256 is None:
            return self._single
        return next((replay for replay in self._replays if replay.capture_sha256 == checksum), None)

    def lock(self, replay):
        return self._locks.get(replay)

    def close(self) -> None:
        for replay in self._replays:
            replay.close()
