import asyncio
import json
import logging
import math
import time
import numpy as np
from datetime import datetime, timezone
from typing import Dict, Any

from gex_terminal.contracts import (
    canonical_option_contract,
    contract_storage_key,
    days_until_expiry,
    expiry_date,
    is_zero_dte,
    parse_market_datetime,
)
from gex_terminal.engine import IntradayGexEngine
from gex_terminal.feed_quality import build_feed_quality_snapshot
from gex_terminal.market_data_adapter import validate_normalized_message

LOGGER = logging.getLogger(__name__)


def _finite_runtime_number(value: object, name: str) -> float:
    try:
        number = float(value)
    except (OverflowError, TypeError, ValueError):
        raise ValueError(f"{name} must be numeric") from None
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite")
    return number


def _positive_runtime_number(value: object, name: str) -> float:
    number = _finite_runtime_number(value, name)
    if number <= 0:
        raise ValueError(f"{name} must be greater than 0")
    return number


class StatefulGexConsumer:
    def __init__(
        self,
        engine: IntradayGexEngine,
        target_underlying: str = "ES",
        risk_free_rate: float = 0.045,
        data_mode: str = "live",
        stale_after_seconds: float = 10.0,
        expiry_filter: str = "all",
    ):
        self.engine = engine
        self.target_underlying = target_underlying
        self.risk_free_rate = _finite_runtime_number(
            risk_free_rate,
            "risk_free_rate",
        )
        self.data_mode = data_mode.upper()
        self.stale_after_seconds = _positive_runtime_number(
            stale_after_seconds,
            "stale_after_seconds",
        )
        self.expiry_filter = expiry_filter
        
        # Compatibility summaries consumed by the existing TUI/export surface.
        self.chain_state: Dict[float, Dict[str, Any]] = {}
        self.expiry_state: Dict[str, Dict[float, Dict[str, Any]]] = {}
        self._legacy_chain_state: Dict[float, Dict[str, Any]] = {}
        self._legacy_expiry_state: Dict[str, Dict[float, Dict[str, Any]]] = {}
        # {(provider, contract_id, position_source): mutable v2 contract state}
        self.contract_state: Dict[tuple[str, str, str], Dict[str, Any]] = {}
        self._v1_option_count = 0
        self._v2_option_count = 0
        self._option_update_serial = 0
        self.current_spot: float = 0.0
        self.session_open: float = 0.0
        self.market_time: datetime | None = None
        self.last_message_at: float | None = None
        self.last_snapshot_at: float | None = None
        self.connection_state: str = "SIM" if self.data_mode == "DEMO" else "DISCONNECTED"
        self.message_count: int = 0
        self.malformed_message_count: int = 0
        self.dropped_message_count: int = 0
        self.entitlement_error_count: int = 0
        self.provider_frame_count: int = 0
        self.provider_parse_error_count: int = 0
        self.reconnect_count: int = 0
        self.subscribed_symbol_count: int = 0
        self.subscription_status: str = "not_subscribed"
        self.duplicate_message_count: int = 0
        self.cumulative_reset_count: int = 0
        self.fallback_iv_tick_count: int = 0
        self.quality_notes: tuple[str, ...] = ()
        self.simulated_latency_ms: float | None = None
        
        # Lock to ensure thread-safe state mutations during high-frequency bursts
        self.state_lock = asyncio.Lock()

    @property
    def runtime_status(self) -> str:
        if self.data_mode == "DEMO":
            return "SIM"
        if self.data_mode == "REPLAY":
            return "REPLAY" if self.current_spot and self.chain_state else "CONNECTED"
        if self.connection_state == "DISCONNECTED":
            return "DISCONNECTED"
        if self.last_message_at is None:
            return "CONNECTED"
        if time.monotonic() - self.last_message_at > self.stale_after_seconds:
            return "STALE"
        return "LIVE"

    def mark_connected(self) -> None:
        self.connection_state = "CONNECTED"

    async def reset_state(
        self,
        *,
        data_mode: str | None = None,
        target_underlying: str | None = None,
        risk_free_rate: float | None = None,
        stale_after_seconds: float | None = None,
    ) -> None:
        """Clear market state before loading a fresh offline or provider session."""
        next_mode = (data_mode or self.data_mode).upper()
        next_risk_free_rate = (
            self.risk_free_rate
            if risk_free_rate is None
            else _finite_runtime_number(risk_free_rate, "risk_free_rate")
        )
        next_stale_after_seconds = (
            self.stale_after_seconds
            if stale_after_seconds is None
            else _positive_runtime_number(
                stale_after_seconds,
                "stale_after_seconds",
            )
        )
        async with self.state_lock:
            self.data_mode = next_mode
            if target_underlying:
                self.target_underlying = target_underlying
            self.risk_free_rate = next_risk_free_rate
            self.stale_after_seconds = next_stale_after_seconds
            self.chain_state.clear()
            self.expiry_state.clear()
            self._legacy_chain_state.clear()
            self._legacy_expiry_state.clear()
            self.contract_state.clear()
            self._v1_option_count = 0
            self._v2_option_count = 0
            self._option_update_serial = 0
            self.current_spot = 0.0
            self.session_open = 0.0
            self.market_time = None
            self.last_message_at = None
            self.last_snapshot_at = None
            self.connection_state = "SIM" if next_mode == "DEMO" else "DISCONNECTED"
            self.message_count = 0
            self.malformed_message_count = 0
            self.dropped_message_count = 0
            self.entitlement_error_count = 0
            self.provider_frame_count = 0
            self.provider_parse_error_count = 0
            self.reconnect_count = 0
            self.subscribed_symbol_count = 0
            self.subscription_status = "not_subscribed"
            self.duplicate_message_count = 0
            self.cumulative_reset_count = 0
            self.fallback_iv_tick_count = 0
            self.quality_notes = ()
            self.simulated_latency_ms = None

    def mark_disconnected(self) -> None:
        self.connection_state = "DISCONNECTED"

    def mark_reconnected(self) -> None:
        self.reconnect_count += 1
        self.connection_state = "CONNECTED"

    def mark_subscribed(self, symbol_count: int) -> None:
        self.subscribed_symbol_count = max(0, int(symbol_count))
        self.subscription_status = "subscribed" if symbol_count else "empty"

    def mark_subscription_error(self) -> None:
        self.subscription_status = "error"

    def record_entitlement_error(self) -> None:
        self.entitlement_error_count += 1

    def record_provider_frame(self) -> None:
        self.provider_frame_count += 1

    def record_provider_parse_error(self) -> None:
        self.provider_parse_error_count += 1
        self.malformed_message_count += 1

    def record_dropped_message(self) -> None:
        self.dropped_message_count += 1

    def record_quality_note(self, note: str) -> None:
        """Attach a provider/model caveat without mutating health counters."""
        cleaned = str(note).strip()
        if cleaned:
            self.quality_notes = tuple(dict.fromkeys((*self.quality_notes, cleaned)))

    def feed_quality_snapshot(
        self,
        *,
        latency_ms: float = 0.0,
        p95_latency_ms: float = 0.0,
        now: float | None = None,
    ) -> dict:
        now = time.monotonic() if now is None else now
        last_message_age = None
        if self.last_message_at is not None:
            last_message_age = max(0.0, now - self.last_message_at)
        last_snapshot_age = None
        if self.last_snapshot_at is not None:
            last_snapshot_age = max(0.0, now - self.last_snapshot_at)

        latency_value = latency_ms
        p95_value = p95_latency_ms
        if self.simulated_latency_ms is not None:
            latency_value = max(latency_ms, self.simulated_latency_ms)
            p95_value = max(p95_latency_ms, self.simulated_latency_ms)

        snapshot = build_feed_quality_snapshot(
            status=self.runtime_status,
            data_mode=self.data_mode,
            connection_state=self.connection_state,
            message_count=self.message_count,
            malformed_count=self.malformed_message_count,
            dropped_count=self.dropped_message_count,
            entitlement_error_count=self.entitlement_error_count,
            frame_count=self.provider_frame_count,
            parse_error_count=self.provider_parse_error_count,
            reconnect_count=self.reconnect_count,
            subscribed_symbol_count=self.subscribed_symbol_count,
            subscription_status=self.subscription_status,
            last_message_age_seconds=last_message_age,
            last_snapshot_age_seconds=last_snapshot_age,
            stale_after_seconds=self.stale_after_seconds,
            latency_ms=latency_value,
            p95_latency_ms=p95_value,
        ).to_dict()
        if self.quality_notes:
            snapshot["notes"] = list(dict.fromkeys((*snapshot["notes"], *self.quality_notes)))
        if self.duplicate_message_count:
            snapshot["notes"] = list(dict.fromkeys((
                *snapshot["notes"],
                f"{self.duplicate_message_count} duplicate option update(s) ignored",
            )))
        if self.cumulative_reset_count:
            snapshot["notes"] = list(dict.fromkeys((
                *snapshot["notes"],
                f"{self.cumulative_reset_count} cumulative volume counter reset(s)",
            )))
        snapshot["duplicate_message_count"] = self.duplicate_message_count
        snapshot["cumulative_reset_count"] = self.cumulative_reset_count
        if self.fallback_iv_tick_count:
            existing_notes = tuple(
                note for note in snapshot["notes"] if note != "feed checks clean"
            )
            snapshot["notes"] = list(dict.fromkeys((
                *existing_notes,
                f"{self.fallback_iv_tick_count} option tick(s) used labeled fallback IV",
            )))
            if snapshot["health"] not in {"down", "entitlement", "stale"}:
                snapshot["health"] = "degraded"
        snapshot["fallback_iv_tick_count"] = self.fallback_iv_tick_count
        return snapshot

    async def update_market_state(self, raw_message: str):
        """
        Parse one normalized message and update contract-aware market state.

        Schema-v1 option messages are treated as incremental legacy events.
        Schema-v2 messages carry stable identity and declare whether ``volume``
        is an incremental trade size or a cumulative counter.
        """
        try:
            data = json.loads(raw_message)
            validate_normalized_message(data)
            event_time = parse_market_datetime(data.get("event_time") or data.get("timestamp"))
            
            # 1. Update Underlying Spot Price
            if data.get("type") == "underlying_tick":
                if data.get("symbol") != self.target_underlying:
                    self.dropped_message_count += 1
                    return
                async with self.state_lock:
                    self.current_spot = float(data["price"])
                    if self.session_open == 0.0:
                        self.session_open = self.current_spot
                    if event_time is not None:
                        if self.market_time is None or event_time >= self.market_time:
                            self.market_time = event_time
                    self.last_message_at = time.monotonic()
                    self.message_count += 1
                return

            # 2. Update Options Traded Volume
            if data.get("type") == "options_volume_tick":
                contract = canonical_option_contract(
                    data,
                    target_underlying=self.target_underlying,
                )
                if contract["symbol"] != self.target_underlying:
                    self.dropped_message_count += 1
                    return

                async with self.state_lock:
                    if contract["schema_version"] >= 2:
                        if not self._update_v2_contract_locked(contract, data):
                            return
                        if contract.get("iv_source") == "configured_default":
                            self.fallback_iv_tick_count += 1
                        self._v2_option_count += 1
                    else:
                        self._update_v1_projection_locked(contract, data)
                        self._v1_option_count += 1
                    if event_time is not None:
                        if self.market_time is None or event_time >= self.market_time:
                            self.market_time = event_time
                    self.last_message_at = time.monotonic()
                    self.message_count += 1
                return

            self.dropped_message_count += 1

        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            self.malformed_message_count += 1
            LOGGER.error("Failed parsing normalized market-data message: %s", e)

    def _update_v1_projection_locked(
        self,
        contract: Dict[str, Any],
        message: Dict[str, Any],
    ) -> None:
        """Apply the original v1 last-IV/incremental-volume behavior exactly."""
        strike = float(contract["strike"])
        option_type = str(contract["option_type"])
        volume = int(message["volume"])
        iv = float(message.get("iv", 0.15))
        row = self._legacy_chain_state.setdefault(
            strike,
            {"C": 0, "P": 0, "iv": iv},
        )
        row[option_type] += volume
        row["iv"] = iv

        expiry = message.get("expiry")
        if expiry is not None:
            bucket = self._legacy_expiry_state.setdefault(str(expiry), {})
            expiry_row = bucket.setdefault(
                strike,
                {"C": 0, "P": 0, "iv": iv},
            )
            expiry_row[option_type] += volume
            expiry_row["iv"] = iv
        self._rebuild_public_projections_locked()

    def _update_v2_contract_locked(
        self,
        contract: Dict[str, Any],
        message: Dict[str, Any],
    ) -> bool:
        state_key = contract_storage_key(contract)
        existing = self.contract_state.get(state_key)
        sequence = contract.get("sequence")
        if (
            existing is not None
            and sequence is not None
            and existing.get("last_sequence") is not None
            and sequence <= existing["last_sequence"]
        ):
            self.duplicate_message_count += 1
            return False

        if existing is not None:
            immutable_fields = ("symbol", "strike", "option_type", "expiry")
            changed = [
                field
                for field in immutable_fields
                if existing.get(field) != contract.get(field)
            ]
            if changed:
                raise ValueError(
                    "contract identity changed for "
                    f"{contract['provider']}:{contract['contract_id']}: "
                    f"{', '.join(changed)}"
                )

        volume = int(message["volume"])
        previous = int(existing.get("accumulated_volume", 0) if existing else 0)
        previous_directional = dict(
            existing.get("directional_volume", {}) if existing else {}
        )
        directional_volume = {
            "buy": int(previous_directional.get("buy", 0)),
            "sell": int(previous_directional.get("sell", 0)),
            "unknown": int(previous_directional.get("unknown", 0)),
        }
        direction_sources = set(existing.get("direction_sources", ()) if existing else ())
        if contract["volume_semantics"] == "cumulative":
            accumulated = volume
            directional_volume = {"buy": 0, "sell": 0, "unknown": volume}
            direction_sources.clear()
            if existing is not None and volume < previous:
                self.cumulative_reset_count += 1
        else:
            accumulated = previous + volume
            side = str(contract.get("aggressor_side") or "unknown")
            directional_volume[side] += volume
            source = str(contract.get("direction_source") or "unknown")
            if side != "unknown" and source != "unknown":
                direction_sources.add(source)

        self._option_update_serial += 1
        state = dict(existing or {})
        state.update(contract)
        state.update({
            "iv": float(message.get("iv", 0.15)),
            "accumulated_volume": accumulated,
            "last_reported_volume": volume,
            "last_sequence": sequence,
            "last_update_serial": self._option_update_serial,
            "directional_volume": directional_volume,
            "direction_sources": sorted(direction_sources),
        })
        self.contract_state[state_key] = state
        self._rebuild_public_projections_locked()
        return True

    def _rebuild_public_projections_locked(self) -> None:
        chain = {
            strike: dict(values)
            for strike, values in self._legacy_chain_state.items()
        }
        expiries = {
            label: {strike: dict(values) for strike, values in bucket.items()}
            for label, bucket in self._legacy_expiry_state.items()
        }
        ordered = sorted(
            self._select_position_states(list(self.contract_state.values()))[0],
            key=lambda state: int(state.get("last_update_serial", 0)),
        )
        for state in ordered:
            strike = float(state["strike"])
            option_type = str(state["option_type"])
            volume = int(state.get("accumulated_volume", 0))
            iv = float(state.get("iv", 0.15))
            row = chain.setdefault(strike, {"C": 0, "P": 0, "iv": iv})
            row[option_type] += volume
            row["iv"] = iv

            expiry = str(state.get("expiry") or "session")
            if expiry != "session":
                bucket = expiries.setdefault(expiry, {})
                expiry_row = bucket.setdefault(
                    strike,
                    {"C": 0, "P": 0, "iv": iv},
                )
                expiry_row[option_type] += volume
                expiry_row["iv"] = iv
        self.chain_state = chain
        self.expiry_state = expiries

    async def process_latest_snapshot(
        self,
        days_to_expiry: float,
        *,
        expiry_filter: str | None = None,
        as_of: datetime | None = None,
        expiry_days: dict[str, float] | None = None,
    ) -> dict:
        """
        Compute the current GEX profile from contract-level state.

        ``days_to_expiry`` remains the documented fallback for legacy events or
        providers that do not yet supply exact expiry metadata.
        """
        async with self.state_lock:
            if not self.chain_state or self.current_spot == 0.0:
                return {"error": "Insufficient data state to compute matrix."}
            contracts = [dict(state) for state in self.contract_state.values()]
            aggregate = {
                strike: dict(values) for strike, values in self.chain_state.items()
            }
            projected_buckets = {
                label: {strike: dict(values) for strike, values in bucket.items()}
                for label, bucket in self.expiry_state.items()
            }
            spot = self.current_spot
            market_time = self.market_time
            v1_count = self._v1_option_count
            v2_count = self._v2_option_count
            self.last_snapshot_at = time.monotonic()

        selected_filter = (expiry_filter or self.expiry_filter or "all").strip()
        reference_time = as_of or market_time or datetime.now(timezone.utc)
        if reference_time.tzinfo is None:
            raise ValueError("as_of must include a timezone")

        # Contract-aware pricing is only authoritative for a pure v2 option set.
        # Mixed sessions retain the original strike-level path and say so.
        contracts, position_conflicts = self._select_position_states(contracts)
        pure_v2 = bool(contracts) and v1_count == 0
        expired_count = 0
        selected_count = 0
        if pure_v2:
            selected_contracts = self._filter_contract_states(
                contracts,
                selected_filter,
                reference_time,
            )
            selected_contracts, expired_count = self._active_contract_states(
                selected_contracts,
                reference_time,
            )
            if not selected_contracts:
                return {
                    "error": f"No active option contracts match expiry filter '{selected_filter}'."
                }
            selected_count = len(selected_contracts)
            data = self._contract_matrix(
                selected_contracts,
                spot,
                days_to_expiry,
                reference_time,
                expiry_days=expiry_days,
            )
        else:
            selected_map = self._legacy_filter_map(
                aggregate,
                projected_buckets,
                selected_filter,
                reference_time,
            )
            if not selected_map:
                return {
                    "error": f"No option contracts match expiry filter '{selected_filter}'."
                }
            data = self._legacy_matrix(selected_map, spot, days_to_expiry)
            data["directionalized"] = {
                "model": "aggressor_directionalized_volume",
                "status": "unsupported_legacy_schema",
                "directional_coverage": 0.0,
                "known_direction_volume": 0.0,
                "unknown_direction_volume": float(
                    sum(
                        int(row.get("C", 0)) + int(row.get("P", 0))
                        for row in selected_map.values()
                    )
                ),
                "participant_classification": "unobserved",
                "opening_closing_classification": "unobserved",
                "predictive_validity": "unmeasured",
            }
            selected_count = len(selected_map)

        data["expiry_filter"] = selected_filter
        data["available_expiries"] = list(self.available_expiries(contracts))
        data["calculation_mode"] = (
            "contract_v2"
            if pure_v2
            else ("mixed_legacy_fallback" if v1_count and v2_count else "legacy_v1")
        )
        data["normalized_schema_versions"] = (
            [1, 2]
            if v1_count and v2_count
            else ([2] if pure_v2 else [1])
        )
        data["legacy_contract_fallback_count"] = len(contracts) if v1_count else 0
        data["selected_contract_count"] = selected_count
        data["expired_contract_count"] = expired_count
        data["position_sources"] = sorted({
            str(state.get("position_source") or "trade_volume")
            for state in (selected_contracts if pure_v2 else ())
        }) if pure_v2 else ["legacy_volume_proxy"]
        data["position_source_conflict_count"] = position_conflicts
        data["as_of"] = reference_time.astimezone(timezone.utc).isoformat().replace(
            "+00:00", "Z"
        )
        return data

    async def process_expiry_breakdown(self, days_to_expiry: float, expiry_days: dict | None = None) -> dict:
        """Return total net GEX grouped by expiry.

        When ticks have carried an ``expiry`` tag, each expiry bucket is priced with
        its own days-to-expiry (from ``expiry_days``, falling back to ``days_to_expiry``).
        When no per-expiry data exists, returns a single session bucket computed from
        the aggregate chain state.
        """
        expiry_days = expiry_days or {}
        async with self.state_lock:
            if not self.chain_state or self.current_spot == 0.0:
                return {}
            spot = self.current_spot
            contracts = [dict(state) for state in self.contract_state.values()]
            market_time = self.market_time
            buckets = {
                label: {strike: dict(values) for strike, values in strikes.items()}
                for label, strikes in self.expiry_state.items()
            }
            aggregate = {strike: dict(values) for strike, values in self.chain_state.items()}

        contracts, _ = self._select_position_states(contracts)
        pure_v2 = bool(contracts) and self._v1_option_count == 0
        if pure_v2:
            reference_time = market_time or datetime.now(timezone.utc)
            grouped: Dict[str, list[Dict[str, Any]]] = {}
            active_contracts, _ = self._active_contract_states(
                contracts,
                reference_time,
            )
            for state in active_contracts:
                label = str(state.get("expiry") or "session")
                grouped.setdefault(label, []).append(state)
            if not grouped:
                return {}
            if set(grouped) == {"session"}:
                data = self._contract_matrix(
                    grouped["session"],
                    spot,
                    days_to_expiry,
                    reference_time,
                    expiry_days=expiry_days,
                )
                return {f"{days_to_expiry:g}DTE": float(data["total_net_gex"])}

            breakdown = {}
            for label, states in sorted(grouped.items()):
                override = expiry_days.get(label)
                data = self._contract_matrix(
                    states,
                    spot,
                    days_to_expiry,
                    reference_time,
                    expiry_override=override,
                    expiry_days=expiry_days,
                )
                breakdown[label] = float(data["total_net_gex"])
            return breakdown

        if not buckets:
            label = f"{days_to_expiry:g}DTE"
            return {label: self._bucket_net_gex(aggregate, spot, days_to_expiry)}

        breakdown = {}
        for label, strikes in buckets.items():
            dte = expiry_days.get(label, days_to_expiry)
            breakdown[label] = self._bucket_net_gex(strikes, spot, dte)
        return breakdown

    def available_expiries(
        self,
        contracts: list[Dict[str, Any]] | None = None,
    ) -> tuple[str, ...]:
        """Return stable non-session expiry labels present in contract state."""
        values = contracts if contracts is not None else list(self.contract_state.values())
        contract_values = {
            str(state.get("expiry"))
            for state in values
            if state.get("expiry") not in (None, "", "session")
        }
        return tuple(sorted(contract_values | set(self.expiry_state)))

    def set_expiry_filter(self, expiry_filter: str) -> None:
        self.expiry_filter = expiry_filter.strip() or "all"

    async def selected_contract_rows(
        self,
        *,
        expiry_filter: str | None = None,
        as_of: datetime | None = None,
    ) -> list[Dict[str, Any]]:
        """Return the same active v2 position rows used by snapshot pricing."""
        async with self.state_lock:
            if self._v1_option_count or not self.contract_state:
                return []
            contracts = [dict(state) for state in self.contract_state.values()]
            reference_time = as_of or self.market_time or datetime.now(timezone.utc)
        selected, _ = self._select_position_states(contracts)
        selected = self._filter_contract_states(
            selected,
            expiry_filter or self.expiry_filter or "all",
            reference_time,
        )
        active, _ = self._active_contract_states(selected, reference_time)
        return active

    def _filter_contract_states(
        self,
        contracts: list[Dict[str, Any]],
        expiry_filter: str,
        as_of: datetime,
    ) -> list[Dict[str, Any]]:
        normalized = expiry_filter.lower()
        if normalized in {"", "all"}:
            return contracts
        if normalized == "0dte":
            return [
                state
                for state in contracts
                if is_zero_dte(
                    state.get("expiry_timestamp") or state.get("expiry"),
                    as_of,
                )
            ]
        return [
            state
            for state in contracts
            if str(state.get("expiry", "")).lower() == normalized
        ]

    @staticmethod
    def _select_position_states(
        contracts: list[Dict[str, Any]],
    ) -> tuple[list[Dict[str, Any]], int]:
        """Choose one exposure basis per provider contract.

        Intraday trade volume is preferred when it is positive; open interest is
        the fallback. Both states remain in ``contract_state`` for provenance,
        but they are never silently summed in a calculation.
        """
        grouped: Dict[tuple[str, str], list[Dict[str, Any]]] = {}
        for state in contracts:
            key = (str(state.get("provider")), str(state.get("contract_id")))
            grouped.setdefault(key, []).append(state)

        selected = []
        conflicts = 0
        for states in grouped.values():
            if len(states) > 1:
                conflicts += len(states) - 1
            trade = [
                state
                for state in states
                if state.get("position_source") == "trade_volume"
                and int(state.get("accumulated_volume", 0)) > 0
            ]
            open_interest = [
                state
                for state in states
                if state.get("position_source") == "open_interest"
            ]
            candidates = trade or open_interest or states
            selected.append(max(
                candidates,
                key=lambda state: int(state.get("last_update_serial", 0)),
            ))
        return selected, conflicts

    @staticmethod
    def _active_contract_states(
        contracts: list[Dict[str, Any]],
        as_of: datetime,
    ) -> tuple[list[Dict[str, Any]], int]:
        active = []
        expired = 0
        reference_date = as_of.astimezone(timezone.utc).date()
        for state in contracts:
            remaining = days_until_expiry(state.get("expiry_timestamp"), as_of)
            if remaining is not None and remaining <= 0:
                expired += 1
                continue
            dated_expiry = expiry_date(state.get("expiry"))
            if remaining is None and dated_expiry is not None and dated_expiry < reference_date:
                # A date-only expiry cannot establish an intraday settlement
                # instant, but a prior UTC calendar date is definitively past.
                expired += 1
                continue
            active.append(state)
        return active, expired

    def _legacy_filter_map(
        self,
        aggregate: Dict[float, Dict[str, Any]],
        buckets: Dict[str, Dict[float, Dict[str, Any]]],
        expiry_filter: str,
        as_of: datetime,
    ) -> Dict[float, Dict[str, Any]]:
        normalized = expiry_filter.lower()
        if normalized in {"", "all"}:
            return aggregate
        if normalized == "0dte":
            selected_labels = [
                label for label in buckets if is_zero_dte(label, as_of)
            ]
        else:
            selected_labels = [
                label for label in buckets if label.lower() == normalized
            ]
        merged: Dict[float, Dict[str, Any]] = {}
        for label in selected_labels:
            for strike, state in buckets[label].items():
                row = merged.setdefault(
                    float(strike),
                    {"C": 0, "P": 0, "iv": float(state["iv"])},
                )
                row["C"] += int(state["C"])
                row["P"] += int(state["P"])
                row["iv"] = float(state["iv"])
        return merged

    def _contract_matrix(
        self,
        contracts: list[Dict[str, Any]],
        spot: float,
        fallback_days: float,
        as_of: datetime,
        *,
        expiry_override: float | None = None,
        expiry_days: dict[str, float] | None = None,
    ) -> dict:
        strikes = np.array([state["strike"] for state in contracts], dtype=float)
        ivs = np.array([state.get("iv", 0.15) for state in contracts], dtype=float)
        calls = np.array([
            state.get("accumulated_volume", 0)
            if state["option_type"] == "C"
            else 0
            for state in contracts
        ], dtype=float)
        puts = np.array([
            state.get("accumulated_volume", 0)
            if state["option_type"] == "P"
            else 0
            for state in contracts
        ], dtype=float)
        dtes = np.array([
            self._contract_days_to_expiry(
                state,
                fallback_days,
                as_of,
                expiry_override=expiry_override,
                expiry_days=expiry_days,
            )
            for state in contracts
        ], dtype=float)
        pricing_models = np.array([
            state.get("pricing_model", "black_scholes") for state in contracts
        ], dtype=object)
        multipliers = np.array([
            state.get("contract_multiplier") or self.engine.multiplier
            for state in contracts
        ], dtype=float)

        matrix = self.engine.compute_intraday_gex_matrix(
            spot_price=spot,
            strikes=strikes,
            days_to_expiry=dtes,
            risk_free_rate=self.risk_free_rate,
            implied_vols=ivs,
            accumulated_call_vol=calls,
            accumulated_put_vol=puts,
            pricing_model=pricing_models,
            contract_multipliers=multipliers,
        )
        directional = self.engine.compute_directionalized_gex_matrix(
            spot_price=spot,
            strikes=strikes,
            days_to_expiry=dtes,
            risk_free_rate=self.risk_free_rate,
            implied_vols=ivs,
            buy_aggressor_vol=np.array([
                state.get("directional_volume", {}).get("buy", 0)
                for state in contracts
            ], dtype=float),
            sell_aggressor_vol=np.array([
                state.get("directional_volume", {}).get("sell", 0)
                for state in contracts
            ], dtype=float),
            unknown_aggressor_vol=np.array([
                state.get("directional_volume", {}).get(
                    "unknown", state.get("accumulated_volume", 0)
                )
                for state in contracts
            ], dtype=float),
            pricing_model=pricing_models,
            contract_multipliers=multipliers,
        )
        directional["direction_sources"] = sorted({
            source
            for state in contracts
            for source in state.get("direction_sources", ())
        })
        matrix["directionalized"] = directional
        iv_sources = [str(state.get("iv_source") or "unknown") for state in contracts]
        matrix["iv_sources"] = sorted(set(iv_sources))
        matrix["iv_source_counts"] = {
            source: iv_sources.count(source) for source in sorted(set(iv_sources))
        }
        matrix["iv_inversion_methods"] = sorted({
            str(state.get("iv_provenance", {}).get("method"))
            for state in contracts
            if isinstance(state.get("iv_provenance"), dict)
            and state.get("iv_provenance", {}).get("method")
        })
        return matrix

    @staticmethod
    def _contract_days_to_expiry(
        state: Dict[str, Any],
        fallback_days: float,
        as_of: datetime,
        *,
        expiry_override: float | None = None,
        expiry_days: dict[str, float] | None = None,
    ) -> float:
        derived = days_until_expiry(
            state.get("expiry_timestamp"),
            as_of,
        )
        if derived is not None:
            return float(derived)
        if expiry_override is not None:
            return float(expiry_override)
        if expiry_days:
            override = expiry_days.get(str(state.get("expiry") or "session"))
            if override is not None:
                return float(override)
        explicit = state.get("days_to_expiry")
        if explicit is not None:
            return float(explicit)
        return float(fallback_days)

    async def drop_strikes(self, strikes: list[float] | tuple[float, ...]) -> int:
        """Remove strikes from canonical and projected state for quality tests."""
        targets = {float(strike) for strike in strikes}
        async with self.state_lock:
            for strike in targets:
                self._legacy_chain_state.pop(strike, None)
                for bucket in self._legacy_expiry_state.values():
                    bucket.pop(strike, None)
            keys = [
                key
                for key, state in self.contract_state.items()
                if float(state["strike"]) in targets
            ]
            for key in keys:
                self.contract_state.pop(key, None)
            self._rebuild_public_projections_locked()
        return len(keys)

    def _legacy_matrix(
        self,
        strikes_map: Dict[float, Dict[str, Any]],
        spot: float,
        days_to_expiry: float,
    ) -> dict:
        sorted_strikes = sorted(strikes_map)
        return self.engine.compute_intraday_gex_matrix(
            spot_price=spot,
            strikes=np.array(sorted_strikes, dtype=float),
            days_to_expiry=days_to_expiry,
            risk_free_rate=self.risk_free_rate,
            implied_vols=np.array(
                [strikes_map[k]["iv"] for k in sorted_strikes], dtype=float
            ),
            accumulated_call_vol=np.array(
                [strikes_map[k]["C"] for k in sorted_strikes], dtype=float
            ),
            accumulated_put_vol=np.array(
                [strikes_map[k]["P"] for k in sorted_strikes], dtype=float
            ),
        )

    def _bucket_net_gex(self, strikes_map: Dict[float, Dict[str, Any]], spot: float, days_to_expiry: float) -> float:
        """Compute total net dollar GEX for one strike->volume bucket."""
        if not strikes_map:
            return 0.0
        sorted_strikes = sorted(strikes_map.keys())
        strikes_arr = np.array(sorted_strikes, dtype=float)
        iv_arr = np.array([strikes_map[k]["iv"] for k in sorted_strikes], dtype=float)
        call_arr = np.array([strikes_map[k]["C"] for k in sorted_strikes], dtype=float)
        put_arr = np.array([strikes_map[k]["P"] for k in sorted_strikes], dtype=float)
        matrix = self.engine.compute_intraday_gex_matrix(
            spot_price=spot,
            strikes=strikes_arr,
            days_to_expiry=days_to_expiry,
            risk_free_rate=self.risk_free_rate,
            implied_vols=iv_arr,
            accumulated_call_vol=call_arr,
            accumulated_put_vol=put_arr,
        )
        return float(matrix["total_net_gex"])

    async def continuous_calculation_loop(
        self,
        interval_seconds: float = 2.0,
        days_to_expiry: float = 0.01,
    ):
        """Asynchronous worker loop that periodically calculates GEX from memory state."""
        LOGGER.info("Starting calculation dispatcher...")
        while True:
            await asyncio.sleep(interval_seconds)
            results = await self.process_latest_snapshot(days_to_expiry=days_to_expiry)
            
            if "error" not in results:
                LOGGER.info(
                    f"Spot: {self.current_spot:.2f} | "
                    f"Gamma Wall: {results['gamma_wall_strike']} | "
                    f"Zero GEX Node: {results['zero_gamma_strike']}"
                )
