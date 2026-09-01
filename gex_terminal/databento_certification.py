"""Explicit, redacted certification probe for Databento live ingestion."""

from __future__ import annotations

import asyncio
import json
import math
import time
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from gex_terminal.adapters.databento import ADAPTER_INFO, DatabentoAdapter
from gex_terminal.consumer import StatefulGexConsumer
from gex_terminal.databento_certification_policy import (
    DatabentoCertificationPolicy,
    resolve_databento_certification_policy,
    validate_contract_multiplier,
)
from gex_terminal.engine import IntradayGexEngine
from gex_terminal.redaction import redact_text


CERTIFICATION_SCHEMA = "gex-terminal.databento-certification.v2"
CERTIFICATION_SHUTDOWN_TIMEOUT_SECONDS = 3.0
_OI_STATUSES = {
    "observed",
    "unavailable",
    "unsupported",
    "entitlement_denied",
    "not_requested",
}
_LIFECYCLE_STATES = {
    "initialized",
    "connecting",
    "subscribing",
    "streaming",
    "completed",
    "cancelled",
    "provider_error",
    "connection_error",
    "subscription_error",
}
_DATABENTO_SCHEMAS = {"definition", "mbp-1", "trades", "statistics"}
_DATABENTO_REQUIRED_SCHEMAS = {"definition", "mbp-1", "trades"}


async def build_databento_certification_report(
    *,
    symbol: str,
    contract_multiplier: float,
    risk_free_rate: float,
    duration_seconds: float = 10.0,
    maximum_underlying_age_seconds: float = 2.0,
    ack_live_network: bool = False,
    policy: str | Mapping[str, Any] | DatabentoCertificationPolicy | None = None,
) -> dict[str, Any]:
    """Run a bounded read-only Databento live-data probe."""
    if not ack_live_network:
        raise ValueError(
            "Databento certification requires --ack-live-network; the probe uses "
            "credentials and opens read-only external market-data subscriptions"
        )
    selected_policy = resolve_databento_certification_policy(
        symbol=symbol,
        policy=policy,
    )
    validated_multiplier = validate_contract_multiplier(
        selected_policy,
        contract_multiplier,
    )
    duration_seconds = _positive_finite(duration_seconds, "duration_seconds")
    maximum_underlying_age_seconds = _positive_finite(
        maximum_underlying_age_seconds,
        "maximum_underlying_age_seconds",
    )
    risk_free_rate = _finite_float(risk_free_rate, "risk_free_rate")
    configured_maximum_age_ms = maximum_underlying_age_seconds * 1000.0
    if (
        configured_maximum_age_ms
        > selected_policy.thresholds.maximum_underlying_age_ms
    ):
        raise ValueError(
            "maximum_underlying_age_seconds exceeds certification policy maximum "
            f"of {selected_policy.thresholds.maximum_underlying_age_ms / 1000.0:g}"
        )

    consumer = StatefulGexConsumer(
        IntradayGexEngine(multiplier=validated_multiplier),
        target_underlying=selected_policy.symbol,
        data_mode="live",
    )
    adapter = DatabentoAdapter(
        consumer,
        target_underlying=selected_policy.symbol,
        risk_free_rate=risk_free_rate,
        max_underlying_age_seconds=maximum_underlying_age_seconds,
    )
    errors: list[str] = []
    task: asyncio.Task | None = None
    probe_started = time.monotonic()
    probe_window_completed = False
    try:
        task = asyncio.create_task(adapter.stream_market_data())
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=duration_seconds)
        except TimeoutError:
            probe_window_completed = True
    except Exception as exc:
        errors.append(_redacted_error(exc, adapter.api_key))
    finally:
        if task and not task.done():
            task.cancel()
            done, _pending = await asyncio.wait(
                {task},
                timeout=CERTIFICATION_SHUTDOWN_TIMEOUT_SECONDS,
            )
            if task not in done:
                errors.append(
                    "TimeoutError: adapter shutdown exceeded the bounded grace period"
                )
                task.cancel()
            else:
                try:
                    task.result()
                except asyncio.CancelledError:
                    pass
                except Exception as exc:
                    errors.append(_redacted_error(exc, adapter.api_key))
        elif task and task.done():
            try:
                task.result()
            except Exception as exc:
                errors.append(_redacted_error(exc, adapter.api_key))
    probe_elapsed_seconds = max(0.0, time.monotonic() - probe_started)

    diagnostics: Mapping[str, Any] = {}
    diagnostics_available = False
    diagnostics_method = getattr(adapter, "diagnostics", None)
    if callable(diagnostics_method):
        try:
            candidate = diagnostics_method()
            if isinstance(candidate, Mapping):
                diagnostics = candidate
                diagnostics_available = True
            else:
                errors.append("ValueError: adapter diagnostics must be a mapping")
        except Exception as exc:
            errors.append(_redacted_error(exc, adapter.api_key))

    quality = consumer.feed_quality_snapshot()
    all_states = [
        state
        for state in consumer.contract_state.values()
        if isinstance(state, Mapping)
    ]
    trade_states = [
        state
        for state in all_states
        if str(state.get("position_source") or "trade_volume") == "trade_volume"
    ]
    state_iv_sources = {
        str(state.get("iv_source") or "unknown") for state in trade_states
    }
    observed_symbols = sorted(
        {
            str(state.get("symbol") or "").upper()
            for state in trade_states
            if str(state.get("symbol") or "").strip()
        }
    )
    observed_multipliers = sorted(
        {
            float(state["contract_multiplier"])
            for state in trade_states
            if _is_positive_finite(state.get("contract_multiplier"))
        }
    )
    symbol_mismatch_count = sum(
        1
        for state in trade_states
        if str(state.get("symbol") or "").upper() != selected_policy.symbol
    )
    multiplier_mismatch_count = sum(
        1
        for state in trade_states
        if state.get("contract_multiplier") not in (None, "")
        and not _numbers_match(
            state.get("contract_multiplier"),
            selected_policy.canonical_contract_multiplier,
        )
    )
    multiplier_observation_count = sum(
        state.get("contract_multiplier") not in (None, "")
        for state in trade_states
    )
    contract_multiplier_coverage = _coverage(
        multiplier_observation_count,
        len(trade_states),
    )
    distinct_expiries = {
        str(state.get("expiry"))
        for state in trade_states
        if str(state.get("expiry") or "") not in {"", "session"}
    }
    distinct_strikes = {
        float(state["strike"])
        for state in trade_states
        if _is_finite(state.get("strike"))
    }

    thresholds = selected_policy.thresholds
    provider_frames = _non_negative_int(quality.get("frame_count", 0))
    definitions = _counter(adapter, "_definition_count")
    underlying_quotes = _counter(adapter, "_underlying_quote_count")
    option_trades = _counter(adapter, "_option_trade_count")
    normalized_option_states = len(trade_states)
    timing_failure_count = sum(
        _counter(adapter, attribute)
        for attribute in (
            "_stale_underlying_count",
            "_future_underlying_count",
            "_missing_underlying_time_count",
        )
    )
    fresh_underlying_observations = max(0, option_trades - timing_failure_count)
    fresh_underlying_coverage = _coverage(
        fresh_underlying_observations,
        option_trades,
    )

    sequence_diagnostics = _mapping(diagnostics.get("sequence_integrity"))
    fallback_sequence_observations = sum(
        state.get("last_sequence") is not None for state in trade_states
    )
    sequence_observations = _diagnostic_count(
        sequence_diagnostics,
        "observed",
        fallback_sequence_observations,
    )
    sequence_discontinuities = _diagnostic_count(
        sequence_diagnostics,
        "venue_sequence_discontinuities",
        0,
    )
    sequence_skipped_values = _diagnostic_count(
        sequence_diagnostics,
        "venue_sequence_skipped_values",
        0,
    )
    sequence_bad_book_flags = _diagnostic_count(
        sequence_diagnostics,
        "maybe_bad_book_flags",
        0,
    )
    sequence_duplicates = _diagnostic_count(
        sequence_diagnostics,
        "duplicates",
        _non_negative_int(getattr(consumer, "duplicate_message_count", 0)),
    )
    sequence_out_of_order = _diagnostic_count(
        sequence_diagnostics,
        "out_of_order",
        0,
    )
    # The trades schema is a subset of venue events, so nonconsecutive venue
    # sequences and duplicates are observations, not standalone loss evidence.
    sequence_violations = sequence_bad_book_flags + sequence_out_of_order
    sequence_coverage = _coverage(sequence_observations, option_trades)
    sequence_integrity = _coverage(
        max(0, sequence_observations - sequence_violations),
        sequence_observations,
    )

    model_diagnostics = _mapping(diagnostics.get("model_inputs"))
    inverted_iv_count = _diagnostic_count(
        model_diagnostics,
        "black_76_inverted_ticks",
        _counter(adapter, "_inverted_iv_count"),
    )
    fallback_iv_count = _diagnostic_count(
        model_diagnostics,
        "fallback_iv_ticks",
        _counter(adapter, "_iv_fallback_count"),
    )
    provider_iv_count = _diagnostic_count(
        model_diagnostics,
        "provider_iv_ticks",
        _counter(
            adapter,
            "_provider_iv_count",
            default=max(0, option_trades - inverted_iv_count - fallback_iv_count),
        ),
    )
    inversion_failure_count = _diagnostic_count(
        model_diagnostics,
        "iv_inversion_failures",
        fallback_iv_count,
    )
    usable_iv_count = provider_iv_count + inverted_iv_count
    usable_iv_coverage = _coverage(usable_iv_count, option_trades)
    fallback_iv_coverage = _coverage(fallback_iv_count, option_trades)
    inversion_failure_coverage = _coverage(inversion_failure_count, option_trades)

    state_underlying_ages = [
        float(provenance["underlying_price_age_ms"])
        for state in trade_states
        for provenance in [_mapping(state.get("iv_provenance"))]
        if _is_non_negative_finite(provenance.get("underlying_price_age_ms"))
    ]
    underlying_age_observations = _diagnostic_count(
        model_diagnostics,
        "underlying_age_observations",
        len(state_underlying_ages),
    )
    underlying_age_min = _diagnostic_optional_float(
        model_diagnostics,
        "underlying_age_ms_min",
        min(state_underlying_ages) if state_underlying_ages else None,
    )
    underlying_age_max = _diagnostic_optional_float(
        model_diagnostics,
        "underlying_age_ms_max",
        max(state_underlying_ages) if state_underlying_ages else None,
    )
    underlying_age_mean = _diagnostic_optional_float(
        model_diagnostics,
        "underlying_age_ms_mean",
        (
            sum(state_underlying_ages) / len(state_underlying_ages)
            if state_underlying_ages
            else None
        ),
    )
    inverted_iv_age_coverage = (
        1.0
        if inverted_iv_count == 0
        else _coverage(underlying_age_observations, inverted_iv_count)
    )

    open_interest_diagnostics = _mapping(diagnostics.get("open_interest"))
    oi_observations = _diagnostic_count(
        open_interest_diagnostics,
        "observations",
        _counter(adapter, "_open_interest_count"),
    )
    oi_provider_observations = _diagnostic_count(
        open_interest_diagnostics,
        "provider_observations",
        oi_observations,
    )
    statistics_requested = bool(
        open_interest_diagnostics.get("statistics_requested", False)
    )
    oi_status_candidate = str(
        open_interest_diagnostics.get("status")
        or ("observed" if oi_observations else "not_requested")
    )
    oi_status_valid = bool(
        oi_status_candidate in _OI_STATUSES
        and (
            (
                oi_status_candidate == "observed"
                and statistics_requested
                and oi_observations > 0
            )
            or (
                oi_status_candidate == "not_requested"
                and not statistics_requested
                and oi_observations == 0
            )
            or (
                oi_status_candidate
                in {"unavailable", "unsupported", "entitlement_denied"}
                and statistics_requested
                and oi_observations == 0
            )
        )
    )
    oi_status = oi_status_candidate if oi_status_valid else "unsupported"
    open_interest_observed = bool(oi_status == "observed" and oi_observations > 0)

    lifecycle_diagnostics = _mapping(diagnostics.get("lifecycle"))
    lifecycle_available = bool(lifecycle_diagnostics)
    lifecycle_state_candidate = str(
        lifecycle_diagnostics.get("state") or "unobserved"
    )
    lifecycle_state = (
        lifecycle_state_candidate
        if lifecycle_state_candidate in _LIFECYCLE_STATES
        else "unobserved"
    )
    provider_error_count = _diagnostic_count(
        lifecycle_diagnostics,
        "provider_error_count",
        0,
    )
    stop_error_count = _diagnostic_count(
        lifecycle_diagnostics,
        "stop_error_count",
        0,
    )
    clean_stop = _diagnostic_optional_bool(
        lifecycle_diagnostics,
        "clean_stop",
    )
    reconnect_callback_registered = _diagnostic_optional_bool(
        lifecycle_diagnostics,
        "reconnect_callback_registered",
    )
    reconnect_callback_registration_error_count = _diagnostic_count(
        lifecycle_diagnostics,
        "reconnect_callback_registration_error_count",
        0,
    )
    reconnect_callback_error_count = _diagnostic_count(
        lifecycle_diagnostics,
        "reconnect_callback_error_count",
        0,
    )
    subscriptions_diagnostics = _mapping(diagnostics.get("subscriptions"))
    requested_schemas, unrecognized_requested_schemas = _safe_schema_list(
        subscriptions_diagnostics.get("requested_schemas")
    )
    request_id_schemas, unrecognized_request_id_schemas = _safe_schema_list(
        subscriptions_diagnostics.get("request_id_schemas")
    )
    failed_schemas, unrecognized_failed_schemas = _safe_schema_list(
        subscriptions_diagnostics.get("failed_schemas")
    )
    subscriptions_available = bool(subscriptions_diagnostics)
    required_subscriptions_requested = bool(
        subscriptions_available
        and _DATABENTO_REQUIRED_SCHEMAS.issubset(requested_schemas)
    )
    required_request_ids_returned = bool(
        subscriptions_available
        and _DATABENTO_REQUIRED_SCHEMAS.issubset(request_id_schemas)
    )
    required_subscription_failures = sorted(
        _DATABENTO_REQUIRED_SCHEMAS.intersection(failed_schemas)
    )
    unrecognized_schema_labels = (
        unrecognized_requested_schemas
        + unrecognized_request_id_schemas
        + unrecognized_failed_schemas
    )

    coverage = {
        "provider_frames": _minimum_check(
            provider_frames,
            thresholds.minimum_provider_frames,
        ),
        "definitions": _minimum_check(
            definitions,
            thresholds.minimum_definitions,
        ),
        "underlying_quotes": _minimum_check(
            underlying_quotes,
            thresholds.minimum_underlying_quotes,
        ),
        "option_trades": _minimum_check(
            option_trades,
            thresholds.minimum_option_trades,
        ),
        "normalized_option_states": _minimum_check(
            normalized_option_states,
            thresholds.minimum_normalized_option_states,
        ),
        "distinct_expiries": _minimum_check(
            len(distinct_expiries),
            thresholds.minimum_distinct_expiries,
        ),
        "distinct_strikes": _minimum_check(
            len(distinct_strikes),
            thresholds.minimum_distinct_strikes,
        ),
        "fresh_underlying_coverage": _minimum_check(
            fresh_underlying_coverage,
            thresholds.minimum_fresh_underlying_coverage,
        ),
        "sequence_observations": _minimum_check(
            sequence_observations,
            thresholds.minimum_sequence_observations,
        ),
        "sequence_coverage": _minimum_check(
            sequence_coverage,
            thresholds.minimum_sequence_coverage,
        ),
        "sequence_integrity": _minimum_check(
            sequence_integrity,
            thresholds.minimum_sequence_integrity,
        ),
        "contract_multiplier_coverage": _minimum_check(
            contract_multiplier_coverage,
            thresholds.minimum_contract_multiplier_coverage,
        ),
        "usable_iv_coverage": _minimum_check(
            usable_iv_coverage,
            thresholds.minimum_usable_iv_coverage,
        ),
        "inverted_iv_age_coverage": _minimum_check(
            inverted_iv_age_coverage,
            thresholds.minimum_inverted_iv_age_coverage,
        ),
        "fallback_iv_coverage": _maximum_check(
            fallback_iv_coverage,
            thresholds.maximum_fallback_iv_coverage,
        ),
        "inversion_failure_coverage": _maximum_check(
            inversion_failure_coverage,
            thresholds.maximum_inversion_failure_coverage,
        ),
        "maximum_underlying_age_ms": _maximum_optional_check(
            underlying_age_max,
            thresholds.maximum_underlying_age_ms,
            required=inverted_iv_count > 0,
        ),
    }

    transport_checks = (
        bool(adapter._connected_once),
        quality.get("subscription_status") == "subscribed",
        required_subscriptions_requested,
        required_request_ids_returned,
        not required_subscription_failures,
        unrecognized_schema_labels == 0,
        coverage["provider_frames"]["passed"],
        _non_negative_int(quality.get("parse_error_count", 0)) == 0,
        diagnostics_available,
        lifecycle_available,
        lifecycle_state != "unobserved",
        provider_error_count == 0,
        clean_stop is True,
        stop_error_count == 0,
        reconnect_callback_registered is True,
        reconnect_callback_registration_error_count == 0,
        reconnect_callback_error_count == 0,
        probe_window_completed,
        not errors,
    )
    transport_certified = bool(
        all(transport_checks)
    )
    chain_coverage_names = (
        "definitions",
        "underlying_quotes",
        "option_trades",
        "normalized_option_states",
        "distinct_expiries",
        "distinct_strikes",
        "fresh_underlying_coverage",
        "sequence_observations",
        "sequence_coverage",
        "sequence_integrity",
        "contract_multiplier_coverage",
    )
    target_identity_certified = bool(
        selected_policy.symbol == str(adapter.target_underlying).upper()
        and selected_policy.dataset == str(adapter.dataset)
        and symbol_mismatch_count == 0
        and multiplier_mismatch_count == 0
    )
    chain_ingestion_certified = bool(
        transport_certified
        and target_identity_certified
        and all(coverage[name]["passed"] for name in chain_coverage_names)
        and _counter(adapter, "_dropped_before_definition_count") == 0
        and _counter(adapter, "_dropped_before_underlying_count") == 0
        and _counter(adapter, "_dropped_underlying_mismatch_count") == 0
        and _counter(adapter, "_crossed_underlying_book_count") == 0
        and _counter(adapter, "_incomplete_underlying_book_count") == 0
        and oi_status_valid
    )
    quantitative_coverage_names = (
        "usable_iv_coverage",
        "inverted_iv_age_coverage",
        "fallback_iv_coverage",
        "inversion_failure_coverage",
        "maximum_underlying_age_ms",
    )
    quantitative_gex_input_certified = bool(
        chain_ingestion_certified
        and usable_iv_count > 0
        and all(coverage[name]["passed"] for name in quantitative_coverage_names)
    )

    invariant_checks = {
        "adapter_diagnostics_available": diagnostics_available,
        "lifecycle_diagnostics_available": lifecycle_available,
        "connected_once": bool(adapter._connected_once),
        "subscription_active": quality.get("subscription_status") == "subscribed",
        "required_subscriptions_requested": required_subscriptions_requested,
        "required_subscription_request_ids_returned": (
            required_request_ids_returned
        ),
        "no_required_subscription_failures": not required_subscription_failures,
        "subscription_schema_labels_recognized": unrecognized_schema_labels == 0,
        "no_parse_errors": (
            _non_negative_int(quality.get("parse_error_count", 0)) == 0
        ),
        "no_report_errors": not errors,
        "lifecycle_state_recognized": (
            lifecycle_available and lifecycle_state != "unobserved"
        ),
        "no_provider_errors": lifecycle_available and provider_error_count == 0,
        "clean_stop": lifecycle_available and clean_stop is True,
        "no_stop_errors": lifecycle_available and stop_error_count == 0,
        "reconnect_callback_registered": (
            lifecycle_available and reconnect_callback_registered is True
        ),
        "no_reconnect_callback_registration_errors": (
            lifecycle_available
            and reconnect_callback_registration_error_count == 0
        ),
        "no_reconnect_callback_errors": (
            lifecycle_available and reconnect_callback_error_count == 0
        ),
        "probe_window_completed": probe_window_completed,
        "target_identity": target_identity_certified,
        "no_trades_before_definition": (
            _counter(adapter, "_dropped_before_definition_count") == 0
        ),
        "no_trades_before_underlying": (
            _counter(adapter, "_dropped_before_underlying_count") == 0
        ),
        "no_underlying_identity_mismatches": (
            _counter(adapter, "_dropped_underlying_mismatch_count") == 0
        ),
        "no_crossed_underlying_books": (
            _counter(adapter, "_crossed_underlying_book_count") == 0
        ),
        "no_incomplete_underlying_books": (
            _counter(adapter, "_incomplete_underlying_book_count") == 0
        ),
        "open_interest_status_recognized": oi_status_valid,
        "adapter_remains_live_uncertified": ADAPTER_INFO.status == "live-uncertified",
    }
    chain_ingestion_certified = bool(
        chain_ingestion_certified and all(invariant_checks.values())
    )
    quantitative_gex_input_certified = bool(
        quantitative_gex_input_certified and chain_ingestion_certified
    )
    open_interest_window_validated = bool(
        open_interest_observed and chain_ingestion_certified
    )
    failed_checks = sorted(
        [name for name, check in coverage.items() if not check["passed"]]
        + [name for name, passed in invariant_checks.items() if not passed]
    )

    return {
        "schema": CERTIFICATION_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "probe": {
            "read_only": True,
            "orders_touched": False,
            "requested_duration_seconds": float(duration_seconds),
            "elapsed_seconds": probe_elapsed_seconds,
            "window_completed": probe_window_completed,
        },
        "policy": selected_policy.to_dict(),
        "target": {
            "dataset": adapter.dataset,
            "symbol": adapter.target_underlying,
            "option_parent": f"{adapter.target_underlying}.OPT",
            "underlying_continuous": f"{adapter.target_underlying}.v.0",
            "configured_contract_multiplier": validated_multiplier,
            "canonical_contract_multiplier": (
                selected_policy.canonical_contract_multiplier
            ),
            "observed_symbols": observed_symbols,
            "observed_contract_multipliers": observed_multipliers,
            "symbol_mismatch_count": symbol_mismatch_count,
            "contract_multiplier_mismatch_count": multiplier_mismatch_count,
            "contract_multiplier_observations": multiplier_observation_count,
            "contract_multiplier_coverage": contract_multiplier_coverage,
            "identity_certified": target_identity_certified,
        },
        "authentication": {
            "api_key_present": bool(adapter.api_key),
            "sdk_version": adapter._sdk_version,
            "challenge_response_session_started": adapter._connected_once,
        },
        "transport": {
            "subscription_status": quality.get("subscription_status"),
            "subscription_ids_observed": len(adapter.subscription_ids),
            "provider_frames": quality.get("frame_count", 0),
            "parse_errors": quality.get("parse_error_count", 0),
            "dropped_messages": quality.get("dropped_count", 0),
            "entitlement_errors": quality.get("entitlement_error_count", 0),
        },
        "lifecycle": {
            "diagnostics_available": diagnostics_available,
            "state": lifecycle_state,
            "connected_once": bool(
                lifecycle_diagnostics.get("connected_once", adapter._connected_once)
            ),
            "stream_completed": bool(
                lifecycle_diagnostics.get("stream_completed", False)
            ),
            "cancelled": bool(lifecycle_diagnostics.get("cancelled", False)),
            "stop_called": _diagnostic_optional_bool(
                lifecycle_diagnostics,
                "stop_called",
            ),
            "clean_stop": clean_stop,
            "disconnect_count": _diagnostic_count(
                lifecycle_diagnostics,
                "disconnect_count",
                0,
            ),
            "subscription_error_count": _diagnostic_count(
                lifecycle_diagnostics,
                "subscription_error_count",
                0,
            ),
            "provider_error_count": provider_error_count,
            "stop_error_count": stop_error_count,
            "reconnect_policy_requested": _diagnostic_optional_bool(
                lifecycle_diagnostics,
                "reconnect_policy_requested",
            ),
            "reconnect_callback_registered": reconnect_callback_registered,
            "reconnect_callback_registration_error_count": (
                reconnect_callback_registration_error_count
            ),
            "reconnect_callback_error_count": reconnect_callback_error_count,
            "reconnect_events_observed": _diagnostic_count(
                lifecycle_diagnostics,
                "reconnect_events_observed",
                0,
            ),
            "reconnect_boundaries_observed": _diagnostic_count(
                lifecycle_diagnostics,
                "reconnect_boundaries_observed",
                0,
            ),
            "post_reconnect_frames": _diagnostic_count(
                lifecycle_diagnostics,
                "post_reconnect_frames",
                0,
            ),
            "reconnect_observed": _diagnostic_optional_bool(
                lifecycle_diagnostics,
                "reconnect_observed",
            ),
            "resubscription_observed": _diagnostic_optional_bool(
                lifecycle_diagnostics,
                "resubscription_observed",
            ),
        },
        "subscriptions": {
            "statistics_requested": bool(
                subscriptions_diagnostics.get(
                    "statistics_requested",
                    statistics_requested,
                )
            ),
            "requested_schemas": requested_schemas,
            "request_id_schemas": request_id_schemas,
            "failed_schemas": failed_schemas,
            "unrecognized_schema_labels": unrecognized_schema_labels,
            "ids_observed": _diagnostic_count(
                subscriptions_diagnostics,
                "ids_observed",
                len(adapter.subscription_ids),
            ),
            "required_schemas": sorted(_DATABENTO_REQUIRED_SCHEMAS),
            "required_schemas_requested": required_subscriptions_requested,
            "required_requests_submitted": required_request_ids_returned,
            "required_schema_failures": required_subscription_failures,
            "identifiers_emitted": False,
        },
        "chain": {
            "definitions_observed": definitions,
            "underlying_quotes_observed": underlying_quotes,
            "option_trades_observed": option_trades,
            "normalized_option_states": normalized_option_states,
            "distinct_expiries_observed": len(distinct_expiries),
            "distinct_strikes_observed": len(distinct_strikes),
            "trades_before_definition": _counter(
                adapter, "_dropped_before_definition_count"
            ),
            "trades_before_underlying": _counter(
                adapter, "_dropped_before_underlying_count"
            ),
            "underlying_contract_mismatches": _counter(
                adapter, "_dropped_underlying_mismatch_count"
            ),
            "stale_underlying_prices": _counter(
                adapter, "_stale_underlying_count"
            ),
            "future_underlying_prices": _counter(
                adapter, "_future_underlying_count"
            ),
            "missing_underlying_event_times": _counter(
                adapter, "_missing_underlying_time_count"
            ),
            "fresh_underlying_observations": fresh_underlying_observations,
            "fresh_underlying_coverage": fresh_underlying_coverage,
            "crossed_underlying_books": _counter(
                adapter, "_crossed_underlying_book_count"
            ),
            "incomplete_underlying_books": _counter(
                adapter, "_incomplete_underlying_book_count"
            ),
            "sequence_observations": sequence_observations,
            "venue_sequence_discontinuities": sequence_discontinuities,
            "venue_sequence_skipped_values": sequence_skipped_values,
            "maybe_bad_book_flags": sequence_bad_book_flags,
            "sequence_duplicates": sequence_duplicates,
            "sequence_out_of_order": sequence_out_of_order,
            "sequence_coverage": sequence_coverage,
            "sequence_integrity": sequence_integrity,
        },
        "open_interest": {
            "status": oi_status,
            "status_valid": oi_status_valid,
            "statistics_requested": statistics_requested,
            "provider_observations": oi_provider_observations,
            "observations": oi_observations,
            "observed_in_window": open_interest_observed,
            "window_validated": open_interest_window_validated,
            "position_source": "open_interest",
            "combined_with_trade_volume": False,
        },
        "model_inputs": {
            "iv_sources_observed": sorted(state_iv_sources),
            "provider_iv_ticks": provider_iv_count,
            "black_76_inverted_ticks": inverted_iv_count,
            "fallback_iv_ticks": fallback_iv_count,
            "iv_inversion_failures": inversion_failure_count,
            "usable_iv_ticks": usable_iv_count,
            "usable_iv_coverage": usable_iv_coverage,
            "fallback_iv_coverage": fallback_iv_coverage,
            "inversion_failure_coverage": inversion_failure_coverage,
            "underlying_age_observations": underlying_age_observations,
            "underlying_age_ms_min": underlying_age_min,
            "underlying_age_ms_max": underlying_age_max,
            "underlying_age_ms_mean": underlying_age_mean,
            "inverted_iv_age_coverage": inverted_iv_age_coverage,
            "risk_free_rate": float(risk_free_rate),
            "pricing_model": "black_76",
            "maximum_underlying_age_ms": adapter.max_underlying_age_seconds * 1000.0,
        },
        "coverage": coverage,
        "invariant_checks": invariant_checks,
        "result": {
            "transport_certified": transport_certified,
            "chain_ingestion_certified": chain_ingestion_certified,
            "quantitative_gex_input_certified": quantitative_gex_input_certified,
            "target_identity_certified": target_identity_certified,
            "open_interest_observed": open_interest_observed,
            "open_interest_window_validated": open_interest_window_validated,
            "failed_checks": failed_checks,
            "adapter_registry_status": ADAPTER_INFO.status,
            "live_readiness_promoted": False,
        },
        "evidence_ceiling": {
            "transport": "measured only for this credential, dataset, symbol, and run window",
            "policy": "thresholds are repository-owned pre-live choices, not empirical proof of market sufficiency",
            "sequence": "integrity uses provider maybe-bad-book flags and observed ordering; trade-schema sequence discontinuities are descriptive only",
            "open_interest": "an observed statistics frame validates normalization only for this successful bounded window; it does not prove recurring entitlement or complete chain coverage",
            "iv": "trade-price inversion against the latest observed futures midpoint; not a synchronized executable option quote",
            "scripted_diagnostics": "offline scripted callbacks do not prove provider-side reconnect, entitlement, or payload behavior",
            "positioning": "trade volume and aggressor side do not reveal dealer inventory",
            "predictive_market_validity": "unmeasured",
        },
        "errors": list(dict.fromkeys(errors)),
    }


def _minimum_check(observed: int | float, required: int | float) -> dict[str, Any]:
    return {
        "observed": observed,
        "required_minimum": required,
        "passed": bool(observed >= required),
    }


def _maximum_check(observed: int | float, required: int | float) -> dict[str, Any]:
    return {
        "observed": observed,
        "required_maximum": required,
        "passed": bool(observed <= required),
    }


def _maximum_optional_check(
    observed: float | None,
    required_maximum: float,
    *,
    required: bool,
) -> dict[str, Any]:
    return {
        "observed": observed,
        "required_maximum": required_maximum,
        "observation_required": required,
        "passed": bool(
            (observed is not None and observed <= required_maximum)
            if required
            else observed is None or observed <= required_maximum
        ),
    }


def _coverage(numerator: int | float, denominator: int | float) -> float:
    if denominator <= 0:
        return 0.0
    return min(1.0, max(0.0, float(numerator) / float(denominator)))


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _counter(adapter: Any, attribute: str, default: int = 0) -> int:
    return _non_negative_int(getattr(adapter, attribute, default))


def _diagnostic_count(
    diagnostics: Mapping[str, Any],
    field_name: str,
    default: int,
) -> int:
    if field_name not in diagnostics:
        return _non_negative_int(default)
    return _non_negative_int(diagnostics.get(field_name))


def _diagnostic_optional_float(
    diagnostics: Mapping[str, Any],
    field_name: str,
    default: float | None,
) -> float | None:
    if field_name not in diagnostics:
        return default
    value = diagnostics.get(field_name)
    if value is None or not _is_non_negative_finite(value):
        return None
    return float(value)


def _diagnostic_optional_bool(
    diagnostics: Mapping[str, Any],
    field_name: str,
) -> bool | None:
    value = diagnostics.get(field_name)
    return value if isinstance(value, bool) else None


def _safe_schema_list(value: Any) -> tuple[list[str], int]:
    if not isinstance(value, (list, tuple, set, frozenset)):
        return [], 0
    observed = [str(item) for item in value]
    safe = sorted({item for item in observed if item in _DATABENTO_SCHEMAS})
    return safe, sum(item not in _DATABENTO_SCHEMAS for item in observed)


def _non_negative_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, number)


def _positive_finite(value: Any, field_name: str) -> float:
    number = _finite_float(value, field_name)
    if number <= 0:
        raise ValueError(f"{field_name} must be positive")
    return number


def _finite_float(value: Any, field_name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be finite")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be finite") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field_name} must be finite")
    return number


def _is_finite(value: Any) -> bool:
    try:
        return not isinstance(value, bool) and math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _is_positive_finite(value: Any) -> bool:
    return _is_finite(value) and float(value) > 0


def _is_non_negative_finite(value: Any) -> bool:
    return _is_finite(value) and float(value) >= 0


def _numbers_match(left: Any, right: Any) -> bool:
    if not _is_finite(left) or not _is_finite(right):
        return False
    return math.isclose(float(left), float(right), rel_tol=0.0, abs_tol=1e-12)


def write_databento_certification_report(
    report: dict[str, Any], output_path: str | Path
) -> Path:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.suffix.lower() == ".json":
        content = json.dumps(report, indent=2, sort_keys=True) + "\n"
    elif target.suffix.lower() in {".md", ".markdown"}:
        content = _format_markdown(report)
    else:
        raise ValueError("Databento certification output must end in .json or .md")
    target.write_text(content, encoding="utf-8")
    return target


def _format_markdown(report: dict[str, Any]) -> str:
    result = report["result"]
    transport = report["transport"]
    chain = report["chain"]
    model = report["model_inputs"]
    policy = report["policy"]
    open_interest = report["open_interest"]
    lines = [
        "# Databento Certification",
        "",
        f"Generated: {report['generated_at']}",
        f"Dataset: {report['target']['dataset']}",
        f"Symbol: {report['target']['symbol']}",
        f"Policy: `{policy['policy_id']}` (v{policy['version']})",
        f"Canonical multiplier: {policy['canonical_contract_multiplier']:g}",
        "",
        "## Result",
        "",
        f"- Transport certified: **{str(result['transport_certified']).lower()}**",
        f"- Chain ingestion certified: **{str(result['chain_ingestion_certified']).lower()}**",
        f"- Quantitative GEX input certified: **{str(result['quantitative_gex_input_certified']).lower()}**",
        f"- Target identity certified: **{str(result['target_identity_certified']).lower()}**",
        f"- Adapter registry status: `{result['adapter_registry_status']}`",
        f"- Live readiness promoted: **{str(result['live_readiness_promoted']).lower()}**",
        "",
        "## Evidence",
        "",
        f"- Subscription status: {transport['subscription_status']}",
        f"- Lifecycle state: {report['lifecycle']['state']}",
        f"- Clean stop: {report['lifecycle']['clean_stop']}",
        f"- Reconnect callback registered: {report['lifecycle']['reconnect_callback_registered']}",
        f"- Reconnect events observed: {report['lifecycle']['reconnect_events_observed']}",
        f"- Post-reconnect frames: {report['lifecycle']['post_reconnect_frames']}",
        f"- Provider frames: {transport['provider_frames']}",
        f"- Definitions observed: {chain['definitions_observed']}",
        f"- Underlying quotes observed: {chain['underlying_quotes_observed']}",
        f"- Option trades observed: {chain['option_trades_observed']}",
        f"- Distinct expiries observed: {chain['distinct_expiries_observed']}",
        f"- Distinct strikes observed: {chain['distinct_strikes_observed']}",
        f"- Fresh-underlying coverage: {chain['fresh_underlying_coverage']:.3f}",
        f"- Sequence coverage: {chain['sequence_coverage']:.3f}",
        f"- Sequence integrity: {chain['sequence_integrity']:.3f}",
        f"- Maybe-bad-book flags: {chain['maybe_bad_book_flags']}",
        f"- Stale underlying prices: {chain['stale_underlying_prices']}",
        f"- Future-dated underlying prices: {chain['future_underlying_prices']}",
        f"- Crossed underlying books: {chain['crossed_underlying_books']}",
        f"- Incomplete underlying books: {chain['incomplete_underlying_books']}",
        f"- Provider-IV ticks: {model['provider_iv_ticks']}",
        f"- Black-76 inverted ticks: {model['black_76_inverted_ticks']}",
        f"- Fallback-IV ticks: {model['fallback_iv_ticks']}",
        f"- IV inversion failures: {model['iv_inversion_failures']}",
        f"- Usable-IV coverage: {model['usable_iv_coverage']:.3f}",
        f"- Maximum underlying age observed (ms): {model['underlying_age_ms_max']}",
        f"- OI status: `{open_interest['status']}`",
        f"- OI observations: {open_interest['observations']}",
        f"- OI observed in window: {open_interest['observed_in_window']}",
        f"- OI window validated: {open_interest['window_validated']}",
        "",
        "## Policy checks",
        "",
    ]
    for name, check in report["coverage"].items():
        requirement_name = (
            "required_minimum"
            if "required_minimum" in check
            else "required_maximum"
        )
        lines.append(
            f"- {name}: observed `{check['observed']}`, "
            f"{requirement_name.replace('_', ' ')} `{check[requirement_name]}`, "
            f"passed **{str(check['passed']).lower()}**"
        )
    lines.extend([
        "",
        "## Evidence ceiling",
        "",
        f"- Transport: {report['evidence_ceiling']['transport']}",
        f"- Policy: {report['evidence_ceiling']['policy']}",
        f"- Sequence: {report['evidence_ceiling']['sequence']}",
        f"- Open interest: {report['evidence_ceiling']['open_interest']}",
        f"- IV: {report['evidence_ceiling']['iv']}",
        f"- Scripted diagnostics: {report['evidence_ceiling']['scripted_diagnostics']}",
        f"- Positioning: {report['evidence_ceiling']['positioning']}",
        f"- Predictive market validity: {report['evidence_ceiling']['predictive_market_validity']}",
    ])
    if report["errors"]:
        lines.extend(("", "## Errors", ""))
        lines.extend(f"- {error}" for error in report["errors"])
    return "\n".join(lines) + "\n"


def _redacted_error(exc: Exception, api_key: str | None) -> str:
    message = redact_text(
        str(exc),
        secrets=(api_key,) if api_key else (),
    )
    return f"{type(exc).__name__}: {message[:500]}"
