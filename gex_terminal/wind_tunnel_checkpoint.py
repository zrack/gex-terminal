"""Bounded, allowlisted offline Terminal checkpoint transport.

Checksums establish accidental-change integrity, not authenticity or data rights.
Receipts embed this entire detached input so reproduction needs no source path.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
from typing import Any

from gex_terminal.contracts import (EXERCISE_STYLES, EXERCISE_STYLE_SOURCES, days_until_expiry,
                                    exercise_style_from_cfi, expiry_date, is_zero_dte, parse_market_datetime)
from gex_terminal.pricing_assumptions import (AMERICAN_FUTURES_MODEL, IV_PROVENANCE_FIELDS,
                                             QUALIFIED_IV_SOURCES)

SCHEMA = "gex-terminal.wind-tunnel.terminal-checkpoint.v1"
MAX_BYTES = 2_000_000
MAX_ROWS = 5000
ROW_FIELDS = {
    "contract_id", "provider", "symbol", "strike", "option_type", "expiry", "expiry_timestamp",
    "days_to_expiry", "pricing_model", "position_source", "accumulated_volume", "iv",
    "contract_multiplier", "iv_source", "event_time", "directional_volume", "direction_sources",
    "terminal_selected", "open_interest_reference_date",
}
OPTIONAL_ROW_FIELDS = {"exercise_style", "exercise_style_source", "provider_cfi", "iv_inversion_risk_free_rate",
                       "iv_provenance"}
QUALITY_FIELDS = {"status", "health", "message_count", "malformed_count", "dropped_count",
                  "duplicate_message_count", "cumulative_reset_count", "fallback_iv_tick_count"}


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, OverflowError, RecursionError):
        raise ValueError("Terminal checkpoint must contain finite bounded JSON") from None


def checkpoint_sha256(value: dict) -> str:
    return hashlib.sha256(_canonical({key: item for key, item in value.items() if key != "sha256"})).hexdigest()


def _fields(value: Any, expected: set[str], name: str) -> dict:
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f"Unsupported {name} fields")
    return value


def _number(value: Any, name: str, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    try:
        result = float(value)
    except (OverflowError, ValueError):
        raise ValueError(f"{name} must be finite") from None
    if not math.isfinite(result) or not low <= result <= high:
        raise ValueError(f"{name} outside supported bounds")
    return result


def _text(value: Any, name: str, maximum: int = 160) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= maximum or any(ord(c) < 32 for c in value):
        raise ValueError(f"{name} must be bounded text without control characters")
    return value


def _choice(value: Any, allowed: set[str], name: str) -> None:
    if not isinstance(value, str) or value not in allowed:
        raise ValueError(f"Invalid {name}")


def validate_checkpoint(artifact: Any) -> dict:
    """Validate strict transport and point-in-time semantics; return detached JSON."""
    if isinstance(artifact, str):
        if len(artifact.encode("utf-8")) > MAX_BYTES:
            raise ValueError("Terminal checkpoint exceeds the 2 MB limit")
        try:
            artifact = json.loads(artifact, object_pairs_hook=_unique_fields)
        except (ValueError, RecursionError):
            raise ValueError("Invalid Terminal checkpoint JSON") from None
    _fields(artifact, {"schema", "version", "source", "parameters", "rows", "sha256"}, "Terminal checkpoint")
    if artifact["schema"] != SCHEMA or type(artifact["version"]) is not int or artifact["version"] != 1:
        raise ValueError("Unsupported Terminal checkpoint version")
    raw = _canonical(artifact)
    if len(raw) > MAX_BYTES:
        raise ValueError("Terminal checkpoint exceeds the 2 MB limit")
    if not isinstance(artifact["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", artifact["sha256"]):
        raise ValueError("Invalid Terminal checkpoint checksum")
    if checkpoint_sha256(artifact) != artifact["sha256"]:
        raise ValueError("Terminal checkpoint integrity mismatch")
    source = _fields(artifact["source"], {"label", "symbol", "data_mode", "as_of", "calculation_mode",
                     "expiry_filter", "synthetic", "quality"}, "checkpoint source")
    _text(source["label"], "source label", 120)
    if not isinstance(source["symbol"], str) or not re.fullmatch(r"[A-Z0-9.\-]{1,16}", source["symbol"]):
        raise ValueError("Invalid checkpoint symbol")
    if not isinstance(source["data_mode"], str) or source["data_mode"] not in {"DEMO", "REPLAY"} or type(source["synthetic"]) is not bool:
        raise ValueError("Only demo/replay checkpoint transport is supported")
    if source["synthetic"] != (source["data_mode"] == "DEMO"):
        raise ValueError("Checkpoint synthetic classification must match captured source mode")
    as_of = parse_market_datetime(source["as_of"])
    if as_of is None:
        raise ValueError("Checkpoint as_of requires authoritative market time")
    _choice(source["calculation_mode"], {"legacy_v1", "contract_v2"}, "checkpoint calculation mode")
    _text(source["expiry_filter"], "expiry filter")
    quality = _fields(source["quality"], QUALITY_FIELDS, "checkpoint quality")
    _choice(quality["status"], {"SIM"} if source["data_mode"] == "DEMO" else {"REPLAY", "CONNECTED"}, "checkpoint quality status")
    _choice(quality["health"], {"healthy", "degraded", "down", "stale", "entitlement", "simulated"}, "checkpoint quality health")
    for key in QUALITY_FIELDS - {"status", "health"}:
        if type(quality[key]) is not int or not 0 <= quality[key] <= 10**12:
            raise ValueError("Checkpoint quality counters must be bounded integers")
    parameters = _fields(artifact["parameters"], {"spot", "risk_free_rate", "fallback_dte", "contract_multiplier"}, "checkpoint parameters")
    _number(parameters["spot"], "spot", 1e-12, 1e9)
    _number(parameters["risk_free_rate"], "risk_free_rate", -.1, 1)
    _number(parameters["fallback_dte"], "fallback_dte", .000001, 30)
    _number(parameters["contract_multiplier"], "contract_multiplier", 1e-12, 1e9)
    rows = artifact["rows"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_ROWS:
        raise ValueError("Terminal checkpoint requires between 1 and 5000 rows")
    identities, selected = {}, {}
    for row in rows:
        # Optional additive metadata keeps v1 checkpoints/captures readable and
        # their original checksums intact. Missing style stays unknown.
        if not isinstance(row, dict) or not ROW_FIELDS <= set(row) or set(row) - ROW_FIELDS - OPTIONAL_ROW_FIELDS:
            raise ValueError("Unsupported checkpoint row fields")
        for key in ("contract_id", "provider", "symbol", "expiry"):
            _text(row[key], key)
        if row["symbol"] != source["symbol"]:
            raise ValueError("Checkpoint row symbol/type mismatch")
        _choice(row["option_type"], {"C", "P"}, "checkpoint option type")
        _choice(row["pricing_model"], {"black_scholes", "black_76", AMERICAN_FUTURES_MODEL}, "checkpoint pricing model")
        style = row.get("exercise_style") or "unknown"
        style_source = row.get("exercise_style_source") or "missing"
        _choice(style, EXERCISE_STYLES, "checkpoint exercise style")
        _choice(style_source, EXERCISE_STYLE_SOURCES, "checkpoint exercise style source")
        cfi = row.get("provider_cfi")
        if cfi is not None and (not isinstance(cfi, str) or not re.fullmatch(r"[A-Z]{6}", cfi)):
            raise ValueError("Invalid checkpoint provider CFI")
        if style_source == "provider_cfi" and (cfi is None or exercise_style_from_cfi(cfi) != style):
            raise ValueError("Checkpoint exercise style conflicts with provider CFI")
        if cfi is not None and exercise_style_from_cfi(cfi) != "unknown" and exercise_style_from_cfi(cfi) != style:
            raise ValueError("Checkpoint exercise style conflicts with provider CFI")
        if style != "unknown" and style_source == "missing":
            raise ValueError("Known checkpoint exercise style requires provenance")
        if row.get("iv_inversion_risk_free_rate") is not None:
            _number(row["iv_inversion_risk_free_rate"], "captured IV inversion rate", -.1, 1)
        _choice(row["position_source"], {"trade_volume", "open_interest"}, "checkpoint quantity source")
        _number(row["strike"], "strike", 1e-12, 1e9)
        if row["iv_source"] == "unavailable":
            if row["iv"] is not None:
                raise ValueError("Unavailable checkpoint IV must be null")
        else:
            _number(row["iv"], "iv", 1e-12, 5)
        if type(row["accumulated_volume"]) is not int or not 0 <= row["accumulated_volume"] <= 10**12:
            raise ValueError("Checkpoint quantity must be a bounded integer")
        if type(row["terminal_selected"]) is not bool:
            raise ValueError("terminal_selected must be boolean")
        if row["contract_multiplier"] is not None:
            _number(row["contract_multiplier"], "row multiplier", 1e-12, 1e9)
        if row["days_to_expiry"] is not None:
            _number(row["days_to_expiry"], "row DTE", 1e-12, 36500)
        if row["iv_source"] is not None:
            _choice(row["iv_source"], {"provider", "black_76_inverted", "configured_default", "legacy_unspecified"}
                    | QUALIFIED_IV_SOURCES, "checkpoint IV source")
        if "iv_provenance" in row:
            provenance = row["iv_provenance"]
            if (not isinstance(provenance, dict) or set(provenance) - IV_PROVENANCE_FIELDS
                    or row["iv_source"] not in QUALIFIED_IV_SOURCES):
                raise ValueError("Unsupported checkpoint IV provenance")
            recorded_rate = provenance.get("prior_iv_risk_free_rate") if row["iv_source"] == "prior_valid" else provenance.get("risk_free_rate")
            if row.get("iv_inversion_risk_free_rate") is not None and row["iv_inversion_risk_free_rate"] != recorded_rate:
                raise ValueError("Checkpoint IV inversion rate conflicts with its provenance")
        if row["iv_source"] in QUALIFIED_IV_SOURCES or row["pricing_model"] == AMERICAN_FUTURES_MODEL:
            # Reuse the normalized pricing contract rather than introducing a
            # weaker second policy at the browser handoff boundary.
            from gex_terminal.market_data_adapter import validate_normalized_message
            message = {key: row[key] for key in ("provider", "contract_id", "symbol", "strike",
                       "option_type", "expiry", "pricing_model", "position_source", "iv", "iv_source", "event_time")}
            message.update(schema_version=2, type="options_volume_tick", instrument_class="futures_option",
                           volume_semantics="cumulative", volume=row["accumulated_volume"])
            message.update({key: row[key] for key in ("exercise_style", "exercise_style_source", "provider_cfi", "iv_provenance") if key in row})
            validate_normalized_message(message)
        legacy = source["calculation_mode"] == "legacy_v1"
        event = parse_market_datetime(row["event_time"])
        if (not legacy and event is None) or (event is not None and event > as_of):
            raise ValueError("Checkpoint row has missing or future event time")
        if row["expiry_timestamp"] is not None and parse_market_datetime(row["expiry_timestamp"]) is None:
            raise ValueError("Invalid checkpoint expiry timestamp")
        remaining = days_until_expiry(row["expiry_timestamp"], as_of)
        dated = expiry_date(row["expiry"])
        if (remaining is not None and remaining <= 0) or (remaining is None and dated and dated < as_of.date()):
            raise ValueError("Checkpoint contains expired rows")
        if not legacy:
            selected_filter = source["expiry_filter"].lower()
            if selected_filter == "0dte" and not is_zero_dte(row["expiry_timestamp"] or row["expiry"], as_of):
                raise ValueError("Checkpoint row does not match captured expiry filter")
            if selected_filter not in {"", "all", "0dte"} and row["expiry"].lower() != selected_filter:
                raise ValueError("Checkpoint row does not match captured expiry filter")
        reference = row["open_interest_reference_date"]
        if reference is not None:
            dated_reference = expiry_date(reference)
            if dated_reference is None or dated_reference > as_of.date():
                raise ValueError("Invalid or future OI reference date")
        directional = _fields(row["directional_volume"], {"buy", "sell", "unknown"}, "directional quantity")
        if any(type(n) is not int or n < 0 for n in directional.values()) or sum(directional.values()) != row["accumulated_volume"]:
            raise ValueError("Directional quantities must partition the row quantity")
        if not isinstance(row["direction_sources"], list) or len(row["direction_sources"]) > 2 or any(not isinstance(item, str) or item not in {"provider", "quote_inference"} for item in row["direction_sources"]):
            raise ValueError("Invalid checkpoint direction sources")
        identity = (row["provider"], row["contract_id"])
        key = (*identity, row["position_source"])
        if key in identities:
            raise ValueError("Duplicate checkpoint quantity row")
        identities[key] = row
        if row["terminal_selected"]:
            if identity in selected:
                raise ValueError("Terminal selection must never sum OI and trade volume")
            selected[identity] = row
    for identity in {key[:2] for key in identities}:
        trade = identities.get((*identity, "trade_volume"))
        oi = identities.get((*identity, "open_interest"))
        expected = trade if trade and trade["accumulated_volume"] > 0 else oi or trade
        if trade and oi and any(trade[key] != oi[key] for key in ("strike", "option_type", "expiry", "expiry_timestamp", "days_to_expiry", "pricing_model", "contract_multiplier")):
            raise ValueError("Checkpoint quantity rows disagree on contract identity")
        if trade and oi and any(trade.get(key, "unknown" if key == "exercise_style" else None) != oi.get(key, "unknown" if key == "exercise_style" else None)
                                for key in ("exercise_style", "provider_cfi")):
            raise ValueError("Checkpoint quantity rows disagree on exercise metadata")
        if selected.get(identity) != expected:
            raise ValueError("Terminal selected quantity does not match trade-first/OI-fallback policy")
    if not sum(row["accumulated_volume"] for row in selected.values()):
        raise ValueError("Terminal checkpoint has no positive selected quantity")
    return json.loads(raw)


def checkpoint_transport(artifact: Any) -> str:
    """Preserve numeric JSON tokens across browser parse/stringify boundaries."""
    return _canonical(validate_checkpoint(artifact)).decode("utf-8")


async def build_terminal_checkpoint(consumer, *, fallback_dte: float, source_label: str = "Terminal checkpoint") -> dict:
    frozen = await consumer.capture_wind_tunnel_state()
    rows = []
    for raw in frozen["rows"]:
        row = {key: raw.get(key) for key in ROW_FIELDS}
        row.update({key: raw[key] for key in OPTIONAL_ROW_FIELDS - {"iv_provenance"} if key in raw})
        provenance = raw.get("iv_provenance")
        if raw.get("iv_source") == "black_76_inverted" and isinstance(provenance, dict):
            row["iv_inversion_risk_free_rate"] = provenance.get("risk_free_rate")
        elif raw.get("iv_source") in QUALIFIED_IV_SOURCES and isinstance(provenance, dict):
            row["iv_provenance"] = {key: value for key, value in provenance.items() if key in IV_PROVENANCE_FIELDS}
            rate = provenance.get("prior_iv_risk_free_rate") if raw.get("iv_source") == "prior_valid" else provenance.get("risk_free_rate")
            if rate is not None:
                row["iv_inversion_risk_free_rate"] = rate
        row["directional_volume"] = raw.get("directional_volume") or {"buy": 0, "sell": 0, "unknown": raw["accumulated_volume"]}
        row["direction_sources"] = raw.get("direction_sources") or []
        rows.append(row)
    rows.sort(key=lambda row: (row["provider"], row["contract_id"], row["position_source"]))
    artifact = {"schema": SCHEMA, "version": 1,
                "source": {key: frozen[key] for key in ("symbol", "data_mode", "calculation_mode", "expiry_filter")},
                "parameters": {key: frozen[key] for key in ("spot", "risk_free_rate", "contract_multiplier")},
                "rows": rows}
    artifact["source"].update(label=source_label, as_of=frozen["as_of"].isoformat().replace("+00:00", "Z"),
                              synthetic=frozen["data_mode"] == "DEMO", quality={key: frozen["quality"][key] for key in QUALITY_FIELDS})
    artifact["parameters"]["fallback_dte"] = fallback_dte
    artifact["sha256"] = checkpoint_sha256(artifact)
    return validate_checkpoint(artifact)


def _unique_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate Terminal checkpoint JSON field")
        result[key] = value
    return result


def read_checkpoint(path: str | Path) -> dict:
    source = Path(path)
    if source.is_symlink():
        raise ValueError("Terminal checkpoint input must not be a symlink")
    try:
        descriptor = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    except OSError as error:
        raise ValueError(f"Cannot open Terminal checkpoint input: {error.strerror}") from None
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("Terminal checkpoint input must be a regular file")
        if metadata.st_size > MAX_BYTES:
            raise ValueError("Terminal checkpoint exceeds the 2 MB limit")
    except BaseException:
        os.close(descriptor)
        raise
    with os.fdopen(descriptor, "rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("Terminal checkpoint exceeds the 2 MB limit")
    try:
        value = json.loads(raw, object_pairs_hook=_unique_fields)
    except (ValueError, UnicodeDecodeError, RecursionError):
        raise ValueError("Invalid Terminal checkpoint JSON") from None
    return validate_checkpoint(value)


def write_checkpoint(path: str | Path, artifact: dict) -> Path:
    value = validate_checkpoint(artifact)
    payload = _canonical(value) + b"\n"
    if len(payload) > MAX_BYTES:
        raise ValueError("Terminal checkpoint exceeds the 2 MB file limit")
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
    return destination
