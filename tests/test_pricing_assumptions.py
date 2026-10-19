"""Pricing qualifications survive provider, state and offline transport paths."""
import copy
from datetime import datetime
import json
import unittest

from gex_terminal.adapters.databento import DatabentoAdapter
from gex_terminal.contracts import exercise_style_from_cfi
from gex_terminal.market_data_adapter import validate_normalized_message
from gex_terminal.pricing_assumptions import build_pricing_assumptions
from gex_terminal.session_intake import _safe_message
from gex_terminal import wind_tunnel
from gex_terminal.wind_tunnel_checkpoint import build_terminal_checkpoint, checkpoint_sha256, validate_checkpoint
from tests.databento_test_cases import EVENT, adapter_for, definition, quote, trade, statistics


class ExerciseMetadataTests(unittest.TestCase):
    def test_cfi_character_is_exercise_authority_without_symbol_guessing(self):
        for cfi, expected in (("OCAFPS", "american"), ("OPAFPS", "american"),
                              ("OCEFPS", "european"), ("OPEFPS", "european"),
                              ("OCXFPS", "unknown"), ("FCEFPS", "unknown"),
                              (None, "unknown"), ("bad", "unknown")):
            with self.subTest(cfi=cfi):
                self.assertEqual(exercise_style_from_cfi(cfi), expected)
        for root in ("ES", "NQ"):
            quarterly = DatabentoAdapter._normalize_definition_record(definition(root))
            self.assertEqual(quarterly["exercise_style"], "unknown")

    def test_definition_trade_statistics_and_intake_preserve_exercise_provenance(self):
        for cfi, expected in (("OCAFPS", "american"), ("OCEFPS", "european"), (None, "unknown")):
            metadata = DatabentoAdapter._normalize_definition_record(definition(cfi=cfi))
            messages = [DatabentoAdapter._normalize_option_trade_record(trade(), {101: metadata}),
                        DatabentoAdapter._normalize_statistics_record(statistics(), {101: metadata})]
            for message in messages:
                validate_normalized_message(message)
                self.assertEqual(message["exercise_style"], expected)
                projected = _safe_message(message)
                self.assertEqual(projected["exercise_style"], expected)
                self.assertEqual(projected["exercise_style_source"], "provider_cfi" if cfi else "missing")
                self.assertEqual(projected.get("provider_cfi"), cfi)

    def test_conflicting_or_unproven_exercise_metadata_is_rejected(self):
        metadata = DatabentoAdapter._normalize_definition_record(definition(cfi="OCAFPS"))
        message = DatabentoAdapter._normalize_option_trade_record(trade(), {101: metadata})
        for changes in ({"exercise_style": "european"}, {"exercise_style": "bermudan"},
                        {"exercise_style_source": "missing"}, {"provider_cfi": "private path"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_normalized_message({**message, **changes})

    def test_model_qualification_distinguishes_american_european_unknown_and_rates(self):
        for style, expected in (("american", "approximation_unmeasured"),
                                ("european", "european_exercise_confirmed"),
                                ("unknown", "exercise_style_unknown")):
            result = build_pricing_assumptions([{"pricing_model": "black_76", "exercise_style": style,
                                                 "iv_provenance": {"risk_free_rate": .045}}], .03)
            self.assertEqual(result["status"], expected)
            self.assertFalse(result["early_exercise_modeled"])
            self.assertEqual(result["risk_free_rate_source"], "configured")
            self.assertEqual(result["risk_free_rate"], .03)
            self.assertEqual(result["iv_inversion_risk_free_rates"], [.045])
            self.assertIn("not observed", result["rate_note"])
            self.assertEqual(result["day_count"], "ACT/365")
            self.assertTrue(any("does not reinvert" in item for item in result["limitations"]))
        self.assertEqual(build_pricing_assumptions([], .045)["status"], "exercise_style_unknown")


class PricingQualificationFlowTests(unittest.IsolatedAsyncioTestCase):
    async def _consumer(self, cfi="OCAFPS"):
        adapter, consumer = adapter_for("NQ")
        metadata = DatabentoAdapter._normalize_definition_record(definition("NQ", cfi=cfi))
        await consumer.update_market_state(json.dumps(adapter._normalize_underlying_quote(quote("NQ"))))
        message = adapter._normalize_option_trade_record(trade(), {101: metadata})
        self.assertTrue(await consumer.update_market_state(json.dumps(message)))
        return consumer, message

    async def test_provider_style_survives_snapshot_checkpoint_and_wind_calculation(self):
        consumer, _ = await self._consumer()
        snapshot = await consumer.process_latest_snapshot(.25)
        self.assertEqual(snapshot["pricing_assumptions"]["status"], "approximation_unmeasured")
        artifact = await build_terminal_checkpoint(consumer, fallback_dte=.25)
        self.assertEqual(artifact["rows"][0]["provider_cfi"], "OCAFPS")
        result = await wind_tunnel.calculate({"terminal_checkpoint": artifact})
        self.assertEqual(result["baseline"]["pricing_assumptions"], snapshot["pricing_assumptions"])
        self.assertAlmostEqual(result["baseline"]["summary"]["total_net_gex"], snapshot["total_net_gex"])
        self.assertEqual(result["baseline"]["contracts"][0]["exercise_style"], "american")
        self.assertEqual(result["scenario"]["pricing_assumptions"]["risk_free_rate"], .045)

    async def test_legacy_checkpoint_without_new_fields_retains_integrity_and_warns_unknown(self):
        consumer, _ = await self._consumer(None)
        artifact = await build_terminal_checkpoint(consumer, fallback_dte=.25)
        for row in artifact["rows"]:
            for field in ("exercise_style", "exercise_style_source", "provider_cfi"):
                row.pop(field, None)
        artifact["sha256"] = checkpoint_sha256(artifact)
        self.assertEqual(validate_checkpoint(artifact), artifact)
        result = await wind_tunnel.calculate({"terminal_checkpoint": artifact})
        self.assertEqual(result["baseline"]["pricing_assumptions"]["status"], "exercise_style_unknown")
        self.assertIn("unqualified", result["baseline"]["pricing_assumptions"]["summary"])

    async def test_omitted_metadata_cannot_erase_known_style_or_cross_quantity_enrichment(self):
        consumer, message = await self._consumer()
        omitted = {key: value for key, value in message.items()
                   if key not in {"exercise_style", "exercise_style_source", "provider_cfi"}}
        self.assertTrue(await consumer.update_market_state(json.dumps(omitted)))
        oi = {**omitted, "position_source": "open_interest", "volume_semantics": "cumulative", "volume": 100,
              "aggressor_side": "unknown", "direction_source": "unknown"}
        self.assertTrue(await consumer.update_market_state(json.dumps(oi)))
        artifact = await build_terminal_checkpoint(consumer, fallback_dte=.25)
        self.assertTrue(all(row["exercise_style"] == "american" for row in artifact["rows"]))
        self.assertTrue(all(row["provider_cfi"] == "OCAFPS" for row in artifact["rows"]))
        conflicted = {**message, "exercise_style": "european", "provider_cfi": "OCEFPS"}
        self.assertFalse(await consumer.update_market_state(json.dumps(conflicted)))
        self.assertTrue(all(row["exercise_style"] == "american" for row in consumer.contract_state.values()))

    async def test_checkpoint_rejects_conflicting_cfi_even_with_recomputed_checksum(self):
        consumer, _ = await self._consumer()
        artifact = await build_terminal_checkpoint(consumer, fallback_dte=.25)
        broken = copy.deepcopy(artifact)
        broken["rows"][0]["exercise_style"] = "european"
        broken["sha256"] = checkpoint_sha256(broken)
        with self.assertRaisesRegex(ValueError, "CFI"):
            validate_checkpoint(broken)

    async def test_lowercase_cfi_accepted_at_ingress_is_canonical_in_checkpoint(self):
        consumer, message = await self._consumer(None)
        enriched = {**message, "exercise_style": "american", "exercise_style_source": "provider_cfi", "provider_cfi": "ocafps"}
        validate_normalized_message(enriched)
        self.assertTrue(await consumer.update_market_state(json.dumps(enriched)))
        artifact = await build_terminal_checkpoint(consumer, fallback_dte=.25)
        self.assertEqual(artifact["rows"][0]["provider_cfi"], "OCAFPS")
        self.assertEqual(validate_checkpoint(artifact), artifact)

    async def test_no_data_retains_source_pricing_model_qualification(self):
        consumer, _ = await self._consumer()
        artifact = await build_terminal_checkpoint(consumer, fallback_dte=.25)
        result = await wind_tunnel.calculate({"terminal_checkpoint": artifact, "exclude_nearest_expiry": True})
        self.assertEqual(result["scenario"]["status"], "no_data")
        self.assertEqual(result["scenario"]["pricing_assumptions"]["models"], ["black_76"])
        absent_oi = await wind_tunnel.calculate({"terminal_checkpoint": artifact, "model": "open_interest"})
        self.assertEqual(absent_oi["scenario"]["status"], "no_data")
        self.assertEqual(absent_oi["scenario"]["pricing_assumptions"]["models"], ["black_76"])

    async def test_native_sdk_definitions_preserve_cfi_through_full_adapter_path(self):
        try:
            import databento_dbn as dbn
        except ImportError:
            self.skipTest("optional Databento SDK is not installed")
        nanos = lambda value: int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1e9)
        for root, cfi, style, multiplier in (("ES", "OCAFPS", "american", 50),
                                             ("NQ", "OPEFPS", "european", 20)):
            with self.subTest(root=root, cfi=cfi):
                definition_record = dbn.InstrumentDefMsg(
                    publisher_id=1, instrument_id=101, ts_event=nanos(EVENT), ts_recv=nanos(EVENT),
                    min_price_increment=250000000, display_factor=1000000000,
                    raw_symbol=f"{root}U6 {'P' if cfi[1] == 'P' else 'C'}6000", asset=root,
                    security_type="OOF", cfi=cfi, underlying=f"{root}U6", underlying_id=202,
                    instrument_class=dbn.InstrumentClass.PUT if cfi[1] == "P" else dbn.InstrumentClass.CALL,
                    security_update_action=dbn.SecurityUpdateAction.ADD,
                    expiration=nanos("2026-08-13T20:00:00Z"),
                    unit_of_measure_qty=multiplier * 1000000000, unit_of_measure="IPNT",
                    strike_price=6000000000000,
                )
                adapter, consumer = adapter_for(root)
                for record in (definition_record, quote(root), trade()):
                    await adapter._handle_live_record(record)
                self.assertEqual(adapter.contract_metadata[101]["provider_cfi"], cfi)
                state = consumer.contract_state[("databento", "101", "trade_volume")]
                self.assertEqual(state["exercise_style"], style)
                self.assertEqual(state["provider_cfi"], cfi)
                artifact = await build_terminal_checkpoint(consumer, fallback_dte=.25)
                self.assertEqual(artifact["rows"][0]["exercise_style"], style)

    async def test_iv_inversion_rate_provenance_survives_checkpoint_without_private_provenance(self):
        consumer, _ = await self._consumer()
        metadata = DatabentoAdapter._normalize_definition_record(definition("NQ", cfi="OCAFPS"))
        inverted = DatabentoAdapter._normalize_option_trade_record(
            trade(iv=None), {101: metadata}, underlying_price=22000,
            underlying_event_time=EVENT, risk_free_rate=.02,
        )
        self.assertEqual(inverted["iv_source"], "black_76_inverted")
        self.assertTrue(await consumer.update_market_state(json.dumps(inverted)))
        artifact = await build_terminal_checkpoint(consumer, fallback_dte=.25)
        self.assertEqual(artifact["rows"][0]["iv_inversion_risk_free_rate"], .02)
        self.assertNotIn("iv_provenance", artifact["rows"][0])
        result = await wind_tunnel.calculate({"terminal_checkpoint": artifact})
        qualification = result["baseline"]["pricing_assumptions"]
        self.assertEqual(qualification["iv_inversion_risk_free_rates"], [.02])
        self.assertTrue(any("does not reinvert" in item for item in qualification["limitations"]))


if __name__ == "__main__":
    unittest.main()
