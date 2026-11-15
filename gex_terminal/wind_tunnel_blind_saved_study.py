"""Blind studies from an ordered cohort of verified saved futures sessions."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
from importlib.resources import files
from pathlib import Path
import re

from . import wind_tunnel as wind
from . import wind_tunnel_blind_review as review
from .session_capture import LOCAL_CAPTURE_MAX_EVENTS
from .wind_tunnel_blind_replay import HORIZON_MINUTES
from .wind_tunnel_blind_study import BlindStudy, BlindStudyError


OPERATION = "blind-saved-study"
MAX_STUDY_CAPTURES = 8
_PROTOCOL = {
    "id": "es-saved-blind-replay-study-v1",
    "version": 1,
    "title": "Saved ES Blind Replay Study",
    "symbol": "ES",
    "source": "saved_capture",
    "horizon_minutes": HORIZON_MINUTES,
    "baseline": "always_holds",
}


def calculation_identity() -> dict:
    identity = review.calculation_identity()
    package = files("gex_terminal")
    for name in ("wind_tunnel_blind_study.py", "wind_tunnel_blind_saved_study.py"):
        identity["implementation"][name] = hashlib.sha256(package.joinpath(name).read_bytes()).hexdigest()
    return identity


def _is_checksum(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


class SavedBlindStudy(BlindStudy):
    """Use the first reproducible net-GEX flip in each supplied ES capture."""

    operation = OPERATION
    _protocol = _PROTOCOL
    _reproduction = "Requires the original saved ES study captures and a compatible calculation build."
    _binding_error = "The study receipt does not match the original saved ES captures and flip sequences."

    def __init__(self, captures: Mapping[str, Path]) -> None:
        if not isinstance(captures, Mapping) or not 1 <= len(captures) <= MAX_STUDY_CAPTURES:
            raise BlindStudyError(f"Choose 1 to {MAX_STUDY_CAPTURES} distinct saved {self.symbol} captures.")
        if not all(_is_checksum(checksum) for checksum in captures):
            raise BlindStudyError(f"Each saved {self.symbol} study capture requires a SHA-256 checksum.")
        try:
            self.capture_paths = {checksum: Path(path) for checksum, path in captures.items()}
        except (TypeError, ValueError) as exc:
            raise BlindStudyError(f"Choose a local saved {self.symbol} capture file for each study case.") from exc
        super().__init__()

    async def _capture_sources(self) -> list[tuple[Path, str | None]]:
        return [(path, checksum) for checksum, path in self.capture_paths.items()]

    def _calculation_identity(self) -> dict:
        return calculation_identity()


class SavedNQBlindStudy(SavedBlindStudy):
    """Use the first reproducible net-GEX flip in each supplied NQ capture."""

    symbol = "NQ"
    _protocol = {**_PROTOCOL, "id": "nq-saved-blind-replay-study-v1",
                 "title": "Saved NQ Blind Replay Study", "symbol": symbol}
    _reproduction = "Requires the original saved NQ study captures and a compatible calculation build."
    _binding_error = "The study receipt does not match the original saved NQ captures and flip sequences."


_STUDIES = {study.symbol: study for study in (SavedBlindStudy, SavedNQBlindStudy)}


def capture_market(request: Mapping) -> str:
    """Read the market from a request for one of the fixed saved-study protocols."""
    if isinstance(request, Mapping):
        for symbol, study in _STUDIES.items():
            if request.get("protocol_sha256") == wind._sha(study._protocol):
                study._request_timestamp(request)
                return symbol
    raise BlindStudyError("The request does not match a saved blind replay study protocol.")


def _capture_bindings(request: Mapping) -> tuple[str, list[str]]:
    symbol = capture_market(request)
    cases = request["cases"]
    if not isinstance(cases, list) or not 1 <= len(cases) <= MAX_STUDY_CAPTURES:
        raise BlindStudyError(f"A saved {symbol} study receipt requires 1 to {MAX_STUDY_CAPTURES} case bindings.")
    checksums = []
    for index, case in enumerate(cases, start=1):
        if (not isinstance(case, Mapping) or set(case) != {"id", "sequence", "capture_sha256"}
                or case["id"] != f"{symbol.lower()}-{index}" or not _is_checksum(case["capture_sha256"])):
            raise BlindStudyError(f"The saved {symbol} study receipt contains an invalid case binding.")
        sequence = case["sequence"]
        if sequence is not None and (type(sequence) is not int or not 1 <= sequence < LOCAL_CAPTURE_MAX_EVENTS):
            raise BlindStudyError(f"The saved {symbol} study receipt contains an invalid flip sequence.")
        checksums.append(case["capture_sha256"])
    if len(set(checksums)) != len(checksums):
        raise BlindStudyError(f"Each saved {symbol} study case must bind a distinct capture.")
    return symbol, checksums


def capture_ids(request: Mapping) -> list[str]:
    """Read the ordered capture checksums from a bounded saved-study request."""
    return _capture_bindings(request)[1]


async def blind_saved_study(request: Mapping, captures: Mapping[str, Path]) -> dict:
    """Reproduce a study in receipt order from the exact original capture set."""
    symbol, ordered = _capture_bindings(request)
    if not isinstance(captures, Mapping) or set(captures) != set(ordered):
        raise BlindStudyError(f"Reopen with the exact saved {symbol} capture set from the study receipt.")
    study = _STUDIES[symbol]({checksum: captures[checksum] for checksum in ordered})
    return await study._reproduce(request)
