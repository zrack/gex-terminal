import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gex_terminal.databento_certification import (
    CERTIFICATION_SCHEMA,
    build_databento_certification_report,
    write_databento_certification_report,
)
from gex_terminal.databento_certification_policy import (
    ES_PRELIVE_V1,
    NQ_PRELIVE_V1,
)


class _PassingAdapter:
    def __init__(self, consumer, **kwargs):
        self.consumer = consumer
        self.target_underlying = kwargs["target_underlying"].upper()
        self.dataset = "GLBX.MDP3"
        self.api_key = "never-export-this-key"
        self.subscription_ids = [1, 2, 3]
        self._sdk_version = "test"
        self._connected_once = False
        self._definition_count = 0
        self._underlying_quote_count = 0
        self._option_trade_count = 0
        self._open_interest_count = 0
        self._inverted_iv_count = 0
        self._iv_fallback_count = 0
        self._dropped_before_definition_count = 0
        self._dropped_before_underlying_count = 0
        self._dropped_underlying_mismatch_count = 0
        self._stale_underlying_count = 0
        self._future_underlying_count = 0
        self._missing_underlying_time_count = 0
        self._crossed_underlying_book_count = 0
        self._incomplete_underlying_book_count = 0
        self.max_underlying_age_seconds = 2.0

    async def _populate(self):
        self._connected_once = True
        self._definition_count = 24
        self._underlying_quote_count = 5
        self._option_trade_count = 20
        self._inverted_iv_count = 20
        self.consumer.mark_connected()
        self.consumer.mark_subscribed(4)
        for _ in range(50):
            self.consumer.record_provider_frame()
        await self.consumer.update_market_state(json.dumps({
            "schema_version": 2,
            "type": "underlying_tick",
            "provider": "databento",
            "symbol": self.target_underlying,
            "price": 6000.0,
            "event_time": "2026-08-06T16:00:00Z",
        }))
        multiplier = 50.0 if self.target_underlying == "ES" else 20.0
        for index in range(12):
            expiry = "2026-08-20" if index % 2 == 0 else "2026-08-27"
            await self.consumer.update_market_state(json.dumps({
                "schema_version": 2,
                "type": "options_volume_tick",
                "provider": "databento",
                "contract_id": str(101 + index),
                "symbol": self.target_underlying,
                "strike": 6000.0 + index * 5.0,
                "option_type": "C" if index % 2 == 0 else "P",
                "volume": 10,
                "volume_semantics": "incremental",
                "position_source": "trade_volume",
                "iv": 0.22,
                "iv_source": "black_76_inverted",
                "iv_provenance": {
                    "method": "black_76_bisection",
                    "status": "converged",
                    "option_price": 100.0,
                    "option_price_source": "databento_trade",
                    "underlying_price": 6000.0,
                    "underlying_price_source": "databento_mbp1_midpoint",
                    "underlying_price_age_ms": 1000.0,
                    "maximum_underlying_age_ms": 2000.0,
                    "risk_free_rate": 0.045,
                    "time_to_expiry_years": 0.04,
                    "iterations": 30,
                    "absolute_price_error": 1e-9,
                },
                "expiry": expiry,
                "expiry_timestamp": f"{expiry}T20:00:00Z",
                "instrument_class": "futures_option",
                "pricing_model": "black_76",
                "contract_multiplier": multiplier,
                "sequence": index + 1,
                "event_time": "2026-08-06T16:00:01Z",
            }))

    def _after_population(self):
        pass

    async def stream_market_data(self):
        await self._populate()
        self._after_population()
        await asyncio.Event().wait()

    def diagnostics(self):
        return {
            "lifecycle": {
                "state": "cancelled",
                "connected_once": True,
                "stream_completed": False,
                "cancelled": True,
                "stop_called": True,
                "clean_stop": True,
                "disconnect_count": 1,
                "subscription_error_count": 0,
                "provider_error_count": 0,
                "stop_error_count": 0,
                "reconnect_policy_requested": True,
                "reconnect_callback_registered": True,
                "reconnect_callback_registration_error_count": 0,
                "reconnect_callback_error_count": 0,
                "reconnect_events_observed": 0,
                "reconnect_boundaries_observed": 0,
                "post_reconnect_frames": 0,
                "reconnect_observed": False,
                "resubscription_observed": False,
            },
            "subscriptions": {
                "statistics_requested": True,
                "requested_schemas": [
                    "definition",
                    "mbp-1",
                    "trades",
                    "statistics",
                ],
                "request_id_schemas": [
                    "definition",
                    "mbp-1",
                    "trades",
                    "statistics",
                ],
                "failed_schemas": [],
                "ids_observed": 4,
            },
            "sequence_integrity": {
                "observed": 20,
                "venue_sequence_discontinuities": 0,
                "venue_sequence_skipped_values": 0,
                "maybe_bad_book_flags": 0,
                "duplicates": 0,
                "out_of_order": 0,
            },
            "open_interest": {
                "status": "unavailable",
                "statistics_requested": True,
                "observations": 0,
            },
            "model_inputs": {
                "provider_iv_ticks": 0,
                "black_76_inverted_ticks": 20,
                "fallback_iv_ticks": 0,
                "iv_inversion_failures": 0,
                "underlying_age_observations": 20,
                "underlying_age_ms_min": 500.0,
                "underlying_age_ms_max": 1000.0,
                "underlying_age_ms_mean": 750.0,
            },
        }


class _InsufficientCoverageAdapter(_PassingAdapter):
    def _after_population(self):
        self._definition_count = 1
        self._underlying_quote_count = 1
        self._option_trade_count = 1
        self._inverted_iv_count = 1

    def diagnostics(self):
        diagnostics = super().diagnostics()
        diagnostics["sequence_integrity"]["observed"] = 1
        diagnostics["model_inputs"]["underlying_age_observations"] = 1
        return diagnostics


class _ObservedMultiplierMismatchAdapter(_PassingAdapter):
    def _after_population(self):
        first_state = next(iter(self.consumer.contract_state.values()))
        first_state["contract_multiplier"] = 999.0


class _MissingMultiplierAdapter(_PassingAdapter):
    def _after_population(self):
        first_state = next(iter(self.consumer.contract_state.values()))
        first_state["contract_multiplier"] = None


class _FallbackIvAdapter(_PassingAdapter):
    def diagnostics(self):
        diagnostics = super().diagnostics()
        diagnostics["model_inputs"].update({
            "provider_iv_ticks": 5,
            "black_76_inverted_ticks": 14,
            "fallback_iv_ticks": 1,
            "iv_inversion_failures": 1,
        })
        return diagnostics


class _UncleanStopAdapter(_PassingAdapter):
    def diagnostics(self):
        diagnostics = super().diagnostics()
        diagnostics["lifecycle"]["clean_stop"] = False
        diagnostics["lifecycle"]["stop_error_count"] = 1
        return diagnostics


class _OptionalOiEntitlementDeniedAdapter(_PassingAdapter):
    def _after_population(self):
        self.consumer.record_entitlement_error()
        self.consumer.mark_subscribed(3)

    def diagnostics(self):
        diagnostics = super().diagnostics()
        diagnostics["subscriptions"].update({
            "request_id_schemas": ["definition", "mbp-1", "trades"],
            "failed_schemas": ["statistics"],
            "ids_observed": 3,
        })
        diagnostics["open_interest"].update({
            "status": "entitlement_denied",
            "observations": 0,
        })
        diagnostics["lifecycle"]["subscription_error_count"] = 1
        return diagnostics


class _LegacyDiagnosticsAdapter(_PassingAdapter):
    diagnostics = None


class _EarlyEofAdapter(_PassingAdapter):
    async def stream_market_data(self):
        await self._populate()
        self._after_population()

    def diagnostics(self):
        diagnostics = super().diagnostics()
        diagnostics["lifecycle"].update({
            "state": "completed",
            "stream_completed": True,
            "cancelled": False,
        })
        return diagnostics


class _EarlyEofObservedOiAdapter(_EarlyEofAdapter):
    def diagnostics(self):
        diagnostics = super().diagnostics()
        diagnostics["open_interest"].update({
            "status": "observed",
            "statistics_requested": True,
            "provider_observations": 1,
            "observations": 1,
        })
        return diagnostics


class _UnknownLifecycleAdapter(_PassingAdapter):
    def diagnostics(self):
        diagnostics = super().diagnostics()
        diagnostics["lifecycle"]["state"] = "mystery"
        return diagnostics


class _MissingLifecycleAdapter(_PassingAdapter):
    def diagnostics(self):
        diagnostics = super().diagnostics()
        diagnostics.pop("lifecycle")
        return diagnostics


class _IncoherentOiAdapter(_PassingAdapter):
    def diagnostics(self):
        diagnostics = super().diagnostics()
        diagnostics["open_interest"].update({
            "statistics_requested": True,
            "status": "not_requested",
            "observations": 0,
        })
        return diagnostics


class _MaybeBadBookAdapter(_PassingAdapter):
    def diagnostics(self):
        diagnostics = super().diagnostics()
        diagnostics["sequence_integrity"]["maybe_bad_book_flags"] = 1
        return diagnostics


class DatabentoCertificationTests(unittest.IsolatedAsyncioTestCase):
    async def test_requires_explicit_live_network_acknowledgement(self):
        with self.assertRaisesRegex(ValueError, "ack-live-network"):
            await build_databento_certification_report(
                symbol="ES",
                contract_multiplier=50,
                risk_free_rate=0.045,
            )

    async def test_builds_redacted_passing_report(self):
        with patch(
            "gex_terminal.databento_certification.DatabentoAdapter",
            _PassingAdapter,
        ):
            report = await build_databento_certification_report(
                symbol="ES",
                contract_multiplier=50,
                risk_free_rate=0.045,
                duration_seconds=0.1,
                ack_live_network=True,
            )

        self.assertEqual(report["schema"], CERTIFICATION_SCHEMA)
        self.assertTrue(report["result"]["transport_certified"])
        self.assertTrue(report["result"]["chain_ingestion_certified"])
        self.assertTrue(report["result"]["quantitative_gex_input_certified"])
        self.assertEqual(report["policy"]["policy_id"], ES_PRELIVE_V1.policy_id)
        self.assertEqual(report["chain"]["distinct_expiries_observed"], 2)
        self.assertEqual(report["chain"]["distinct_strikes_observed"], 12)
        self.assertEqual(report["target"]["contract_multiplier_coverage"], 1.0)
        self.assertEqual(report["model_inputs"]["provider_iv_ticks"], 0)
        self.assertEqual(report["model_inputs"]["black_76_inverted_ticks"], 20)
        self.assertEqual(report["model_inputs"]["underlying_age_ms_max"], 1000.0)
        self.assertEqual(report["open_interest"]["status"], "unavailable")
        self.assertFalse(report["open_interest"]["observed_in_window"])
        self.assertFalse(report["open_interest"]["window_validated"])
        self.assertFalse(report["result"]["open_interest_observed"])
        self.assertFalse(report["result"]["open_interest_window_validated"])
        self.assertFalse(report["open_interest"]["combined_with_trade_volume"])
        self.assertEqual(report["lifecycle"]["state"], "cancelled")
        self.assertTrue(report["lifecycle"]["clean_stop"])
        self.assertTrue(report["lifecycle"]["reconnect_callback_registered"])
        self.assertFalse(report["lifecycle"]["reconnect_observed"])
        self.assertTrue(report["probe"]["window_completed"])
        self.assertGreaterEqual(report["probe"]["elapsed_seconds"], 0.09)
        self.assertEqual(
            report["subscriptions"]["requested_schemas"],
            ["definition", "mbp-1", "statistics", "trades"],
        )
        self.assertFalse(report["subscriptions"]["identifiers_emitted"])
        self.assertTrue(report["subscriptions"]["required_requests_submitted"])
        self.assertEqual(report["model_inputs"]["iv_sources_observed"], ["black_76_inverted"])
        self.assertEqual(report["evidence_ceiling"]["predictive_market_validity"], "unmeasured")
        self.assertEqual(report["result"]["adapter_registry_status"], "live-uncertified")
        self.assertFalse(report["result"]["live_readiness_promoted"])
        self.assertEqual(report["result"]["failed_checks"], [])
        self.assertTrue(all(report["invariant_checks"].values()))
        self.assertEqual(
            set(report["coverage"]["distinct_expiries"]),
            {"observed", "required_minimum", "passed"},
        )
        self.assertNotIn("never-export-this-key", json.dumps(report))

    async def test_insufficient_coverage_fails_closed_with_required_values(self):
        with patch(
            "gex_terminal.databento_certification.DatabentoAdapter",
            _InsufficientCoverageAdapter,
        ):
            report = await build_databento_certification_report(
                symbol="ES",
                contract_multiplier=50,
                risk_free_rate=0.045,
                duration_seconds=0.1,
                ack_live_network=True,
            )

        self.assertTrue(report["result"]["transport_certified"])
        self.assertFalse(report["result"]["chain_ingestion_certified"])
        self.assertFalse(report["result"]["quantitative_gex_input_certified"])
        definitions = report["coverage"]["definitions"]
        self.assertEqual(definitions["observed"], 1)
        self.assertEqual(definitions["required_minimum"], 24)
        self.assertFalse(definitions["passed"])
        self.assertIn("definitions", report["result"]["failed_checks"])

    async def test_rejects_unsupported_symbol_policy_and_multiplier(self):
        with self.assertRaisesRegex(ValueError, "unsupported.*symbol"):
            await build_databento_certification_report(
                symbol="YM",
                contract_multiplier=5,
                risk_free_rate=0.045,
                ack_live_network=True,
            )
        with self.assertRaisesRegex(ValueError, "unknown.*policy"):
            await build_databento_certification_report(
                symbol="ES",
                contract_multiplier=50,
                risk_free_rate=0.045,
                policy="missing-policy-v1",
                ack_live_network=True,
            )
        with self.assertRaisesRegex(ValueError, "canonical multiplier"):
            await build_databento_certification_report(
                symbol="ES",
                contract_multiplier=20,
                risk_free_rate=0.045,
                ack_live_network=True,
            )

    async def test_es_and_nq_policies_cannot_cross_certify(self):
        with self.assertRaisesRegex(ValueError, "targets ES, not NQ"):
            await build_databento_certification_report(
                symbol="NQ",
                contract_multiplier=20,
                risk_free_rate=0.045,
                policy=ES_PRELIVE_V1,
                ack_live_network=True,
            )
        with patch(
            "gex_terminal.databento_certification.DatabentoAdapter",
            _PassingAdapter,
        ):
            report = await build_databento_certification_report(
                symbol="NQ",
                contract_multiplier=20,
                risk_free_rate=0.045,
                policy=NQ_PRELIVE_V1.policy_id,
                duration_seconds=0.1,
                ack_live_network=True,
            )
        self.assertEqual(report["policy"]["symbol"], "NQ")
        self.assertEqual(report["policy"]["canonical_contract_multiplier"], 20.0)
        self.assertTrue(report["result"]["target_identity_certified"])

    async def test_observed_multiplier_mismatch_blocks_chain_certification(self):
        with patch(
            "gex_terminal.databento_certification.DatabentoAdapter",
            _ObservedMultiplierMismatchAdapter,
        ):
            report = await build_databento_certification_report(
                symbol="ES",
                contract_multiplier=50,
                risk_free_rate=0.045,
                duration_seconds=0.1,
                ack_live_network=True,
            )
        self.assertEqual(report["target"]["contract_multiplier_mismatch_count"], 1)
        self.assertFalse(report["result"]["target_identity_certified"])
        self.assertFalse(report["result"]["chain_ingestion_certified"])

    async def test_missing_observed_multiplier_fails_coverage_closed(self):
        with patch(
            "gex_terminal.databento_certification.DatabentoAdapter",
            _MissingMultiplierAdapter,
        ):
            report = await build_databento_certification_report(
                symbol="ES",
                contract_multiplier=50,
                risk_free_rate=0.045,
                duration_seconds=0.1,
                ack_live_network=True,
            )
        check = report["coverage"]["contract_multiplier_coverage"]
        self.assertEqual(check["observed"], 11 / 12)
        self.assertEqual(check["required_minimum"], 1.0)
        self.assertFalse(check["passed"])
        self.assertFalse(report["result"]["chain_ingestion_certified"])

    async def test_iv_sources_are_separate_and_fallback_fails_quantitative_gate(self):
        with patch(
            "gex_terminal.databento_certification.DatabentoAdapter",
            _FallbackIvAdapter,
        ):
            report = await build_databento_certification_report(
                symbol="ES",
                contract_multiplier=50,
                risk_free_rate=0.045,
                duration_seconds=0.1,
                ack_live_network=True,
            )
        self.assertEqual(report["model_inputs"]["provider_iv_ticks"], 5)
        self.assertEqual(report["model_inputs"]["black_76_inverted_ticks"], 14)
        self.assertEqual(report["model_inputs"]["fallback_iv_ticks"], 1)
        self.assertEqual(report["model_inputs"]["iv_inversion_failures"], 1)
        self.assertTrue(report["result"]["chain_ingestion_certified"])
        self.assertFalse(report["result"]["quantitative_gex_input_certified"])
        self.assertIn("fallback_iv_coverage", report["result"]["failed_checks"])
        self.assertIn(
            "inversion_failure_coverage",
            report["result"]["failed_checks"],
        )

    async def test_unclean_stop_fails_transport_closed(self):
        with patch(
            "gex_terminal.databento_certification.DatabentoAdapter",
            _UncleanStopAdapter,
        ):
            report = await build_databento_certification_report(
                symbol="ES",
                contract_multiplier=50,
                risk_free_rate=0.045,
                duration_seconds=0.1,
                ack_live_network=True,
            )
        self.assertFalse(report["result"]["transport_certified"])
        self.assertFalse(report["invariant_checks"]["clean_stop"])
        self.assertIn("clean_stop", report["result"]["failed_checks"])
        self.assertIn("no_stop_errors", report["result"]["failed_checks"])

    async def test_optional_oi_entitlement_denial_does_not_block_trade_path(self):
        with patch(
            "gex_terminal.databento_certification.DatabentoAdapter",
            _OptionalOiEntitlementDeniedAdapter,
        ):
            report = await build_databento_certification_report(
                symbol="ES",
                contract_multiplier=50,
                risk_free_rate=0.045,
                duration_seconds=0.1,
                ack_live_network=True,
            )
        self.assertEqual(report["transport"]["entitlement_errors"], 1)
        self.assertEqual(report["open_interest"]["status"], "entitlement_denied")
        self.assertFalse(report["open_interest"]["window_validated"])
        self.assertEqual(
            report["subscriptions"]["failed_schemas"],
            ["statistics"],
        )
        self.assertEqual(
            report["subscriptions"]["required_schema_failures"],
            [],
        )
        self.assertTrue(report["result"]["transport_certified"])
        self.assertTrue(report["result"]["chain_ingestion_certified"])
        self.assertTrue(report["result"]["quantitative_gex_input_certified"])
        self.assertFalse(report["result"]["open_interest_window_validated"])

    async def test_all_explicit_oi_states_are_preserved_without_volume_substitution(self):
        for status in (
            "observed",
            "unavailable",
            "unsupported",
            "entitlement_denied",
            "not_requested",
        ):
            with self.subTest(status=status):
                observations = 1 if status == "observed" else 0

                class _StatusAdapter(_PassingAdapter):
                    def diagnostics(self):
                        diagnostics = super().diagnostics()
                        diagnostics["open_interest"].update({
                            "status": status,
                            "observations": observations,
                            "statistics_requested": status != "not_requested",
                        })
                        return diagnostics

                with patch(
                    "gex_terminal.databento_certification.DatabentoAdapter",
                    _StatusAdapter,
                ):
                    report = await build_databento_certification_report(
                        symbol="ES",
                        contract_multiplier=50,
                        risk_free_rate=0.045,
                        duration_seconds=0.1,
                        ack_live_network=True,
                    )
                self.assertEqual(report["open_interest"]["status"], status)
                self.assertEqual(
                    report["open_interest"]["observed_in_window"],
                    status == "observed",
                )
                self.assertEqual(
                    report["open_interest"]["window_validated"],
                    status == "observed",
                )
                self.assertFalse(
                    report["open_interest"]["combined_with_trade_volume"]
                )

    async def test_legacy_test_double_without_diagnostics_returns_fail_closed_report(self):
        with patch(
            "gex_terminal.databento_certification.DatabentoAdapter",
            _LegacyDiagnosticsAdapter,
        ):
            report = await build_databento_certification_report(
                symbol="ES",
                contract_multiplier=50,
                risk_free_rate=0.045,
                duration_seconds=0.1,
                ack_live_network=True,
            )
        self.assertFalse(report["lifecycle"]["diagnostics_available"])
        self.assertEqual(report["lifecycle"]["state"], "unobserved")
        self.assertFalse(report["result"]["chain_ingestion_certified"])
        self.assertIn("sequence_coverage", report["result"]["failed_checks"])

    async def test_early_eof_cannot_certify_a_requested_window(self):
        with patch(
            "gex_terminal.databento_certification.DatabentoAdapter",
            _EarlyEofAdapter,
        ):
            report = await build_databento_certification_report(
                symbol="ES",
                contract_multiplier=50,
                risk_free_rate=0.045,
                duration_seconds=0.1,
                ack_live_network=True,
            )

        self.assertFalse(report["probe"]["window_completed"])
        self.assertFalse(report["result"]["transport_certified"])
        self.assertFalse(report["result"]["chain_ingestion_certified"])
        self.assertIn("probe_window_completed", report["result"]["failed_checks"])

        with patch(
            "gex_terminal.databento_certification.DatabentoAdapter",
            _EarlyEofObservedOiAdapter,
        ):
            oi_report = await build_databento_certification_report(
                symbol="ES",
                contract_multiplier=50,
                risk_free_rate=0.045,
                duration_seconds=0.1,
                ack_live_network=True,
            )
        self.assertTrue(oi_report["result"]["open_interest_observed"])
        self.assertFalse(
            oi_report["result"]["open_interest_window_validated"]
        )

    async def test_unknown_lifecycle_state_blocks_chain_and_quantitative_results(self):
        with patch(
            "gex_terminal.databento_certification.DatabentoAdapter",
            _UnknownLifecycleAdapter,
        ):
            report = await build_databento_certification_report(
                symbol="ES",
                contract_multiplier=50,
                risk_free_rate=0.045,
                duration_seconds=0.1,
                ack_live_network=True,
            )

        self.assertFalse(report["result"]["transport_certified"])
        self.assertFalse(report["result"]["chain_ingestion_certified"])
        self.assertFalse(report["result"]["quantitative_gex_input_certified"])
        self.assertIn(
            "lifecycle_state_recognized",
            report["result"]["failed_checks"],
        )

    async def test_missing_lifecycle_diagnostics_fail_closed(self):
        with patch(
            "gex_terminal.databento_certification.DatabentoAdapter",
            _MissingLifecycleAdapter,
        ):
            report = await build_databento_certification_report(
                symbol="ES",
                contract_multiplier=50,
                risk_free_rate=0.045,
                duration_seconds=0.1,
                ack_live_network=True,
            )

        self.assertFalse(report["result"]["transport_certified"])
        self.assertFalse(report["result"]["chain_ingestion_certified"])
        self.assertFalse(report["result"]["quantitative_gex_input_certified"])
        self.assertIn(
            "lifecycle_diagnostics_available",
            report["result"]["failed_checks"],
        )

    async def test_open_interest_request_status_must_be_coherent(self):
        with patch(
            "gex_terminal.databento_certification.DatabentoAdapter",
            _IncoherentOiAdapter,
        ):
            report = await build_databento_certification_report(
                symbol="ES",
                contract_multiplier=50,
                risk_free_rate=0.045,
                duration_seconds=0.1,
                ack_live_network=True,
            )

        self.assertFalse(report["open_interest"]["status_valid"])
        self.assertFalse(report["result"]["chain_ingestion_certified"])
        self.assertIn(
            "open_interest_status_recognized",
            report["result"]["failed_checks"],
        )

    async def test_trade_sequence_discontinuity_is_descriptive_but_bad_book_fails(self):
        class _DiscontinuityAdapter(_PassingAdapter):
            def diagnostics(self):
                diagnostics = super().diagnostics()
                diagnostics["sequence_integrity"].update({
                    "venue_sequence_discontinuities": 3,
                    "venue_sequence_skipped_values": 8,
                })
                return diagnostics

        with patch(
            "gex_terminal.databento_certification.DatabentoAdapter",
            _DiscontinuityAdapter,
        ):
            descriptive = await build_databento_certification_report(
                symbol="ES",
                contract_multiplier=50,
                risk_free_rate=0.045,
                duration_seconds=0.1,
                ack_live_network=True,
            )
        self.assertTrue(descriptive["coverage"]["sequence_integrity"]["passed"])
        self.assertTrue(descriptive["result"]["chain_ingestion_certified"])

        with patch(
            "gex_terminal.databento_certification.DatabentoAdapter",
            _MaybeBadBookAdapter,
        ):
            bad_book = await build_databento_certification_report(
                symbol="ES",
                contract_multiplier=50,
                risk_free_rate=0.045,
                duration_seconds=0.1,
                ack_live_network=True,
            )
        self.assertFalse(bad_book["coverage"]["sequence_integrity"]["passed"])
        self.assertFalse(bad_book["result"]["chain_ingestion_certified"])

    async def test_writes_json_and_markdown(self):
        with patch(
            "gex_terminal.databento_certification.DatabentoAdapter",
            _PassingAdapter,
        ):
            report = await build_databento_certification_report(
                symbol="NQ",
                contract_multiplier=20,
                risk_free_rate=0.045,
                duration_seconds=0.1,
                ack_live_network=True,
            )
        with tempfile.TemporaryDirectory() as temp_dir:
            json_path = write_databento_certification_report(
                report, Path(temp_dir) / "report.json"
            )
            md_path = write_databento_certification_report(
                report, Path(temp_dir) / "report.md"
            )
            self.assertEqual(json.loads(json_path.read_text())["schema"], CERTIFICATION_SCHEMA)
            markdown = md_path.read_text()
            self.assertIn("Transport certified: **true**", markdown)
            self.assertIn("OI observed in window: False", markdown)
            self.assertIn("OI window validated: False", markdown)
            self.assertIn("Open interest: an observed statistics frame", markdown)
            self.assertIn("Policy checks", markdown)


if __name__ == "__main__":
    unittest.main()
