"""Unresolved IV retains quantities across Terminal, portable and browser paths."""
import copy
import hashlib
from datetime import datetime
import json
import unittest

import numpy as np

from gex_terminal.consumer import StatefulGexConsumer
from gex_terminal.engine import IntradayGexEngine
from gex_terminal.market_data_adapter import validate_normalized_message
from gex_terminal.pricing_assumptions import build_pricing_assumptions
from gex_terminal.model_comparison import build_model_comparison_report, model_comparison_to_csv, model_comparison_to_markdown
from gex_terminal.position_model_comparison import (build_position_model_comparison,
                                                  position_model_comparison_to_csv,
                                                  position_model_comparison_to_markdown)
from gex_terminal.session_intake import SessionIntake
from gex_terminal.sensitivity import build_sensitivity_report
from gex_terminal.snapshot import build_snapshot
from gex_terminal.snapshot_formats import snapshot_to_csv, snapshot_to_markdown
from gex_terminal import wind_tunnel as wind
from gex_terminal.wind_tunnel_checkpoint import build_terminal_checkpoint, checkpoint_sha256, validate_checkpoint
from gex_terminal.wind_tunnel_server import make_receipt, reproduce_receipt
from tests.test_session_intake import capture_bytes
from tests.test_wind_tunnel_checkpoint import AS_OF, emit, option
from tests.test_position_model_comparison import _config


def unavailable(contract_id="unpriced", **overrides):
    result = option(contract_id, "P", volume=7, iv=None, iv_source="unavailable",
                  pricing_model="black_76", exercise_style="european",
                  exercise_style_source="provider_cfi", provider_cfi="OPEFPS",
                  iv_provenance={"method": "black_76_bisection", "status": "outside_no_arbitrage_bounds",
                                 "underlying_event_time": AS_OF, "underlying_instrument_id": 202,
                                 "option_price": 1, "lower_bound": 2, "upper_bound": 6000})
    result.update(overrides)
    return result


async def consumer_with(*events):
    consumer = StatefulGexConsumer(IntradayGexEngine(50), data_mode="replay")
    await emit(consumer, {"schema_version": 2, "type": "underlying_tick", "provider": "synthetic",
                          "symbol": "ES", "price": 6000, "event_time": AS_OF})
    for event in events:
        await emit(consumer, event)
    return consumer


class PricingCoverageTests(unittest.IsolatedAsyncioTestCase):
    def test_retained_iv_discloses_original_inversion_rate_instead_of_failed_current_rate(self):
        result = build_pricing_assumptions([{
            "pricing_model": "black_76", "exercise_style": "european", "iv": .2,
            "iv_source": "prior_valid", "accumulated_volume": 7,
            "iv_provenance": {"risk_free_rate": .045, "prior_iv_risk_free_rate": .01},
        }], .045)
        self.assertEqual(result["iv_inversion_risk_free_rates"], [.01])
        self.assertTrue(any("does not reinvert" in note for note in result["limitations"]))

    async def test_mixed_legacy_and_unpriced_v2_expiry_breakdown_refuses_projection(self):
        consumer = await consumer_with(unavailable())
        await emit(consumer, {"type": "options_volume_tick", "strike": 6100, "option_type": "C",
                              "volume": 2, "iv": .2, "expiry": "2026-09-04", "timestamp": AS_OF})
        matrix = await consumer.process_latest_snapshot(.25)
        self.assertEqual(matrix["status"], "no_data")
        self.assertIn("mixed legacy aggregate", matrix["error"])
        self.assertEqual(await consumer.process_expiry_breakdown(.25), {})
        self.assertEqual(sum(row["C"] + row["P"] for row in consumer.chain_state.values()), 9)

    async def test_unavailable_iv_keeps_raw_quantity_and_excludes_only_its_exposure(self):
        consumer = await consumer_with(option("priced", volume=10), unavailable())
        matrix = await consumer.process_latest_snapshot(.25)
        self.assertEqual(sum(row["C"] + row["P"] for row in consumer.chain_state.values()), 17)
        state = consumer.contract_state[("synthetic", "unpriced", "trade_volume")]
        self.assertIsNone(state["iv"])
        coverage = matrix["pricing_coverage"]
        self.assertEqual((coverage["selected_contract_count"], coverage["priced_contract_count"],
                          coverage["unpriced_contract_count"]), (2, 1, 1))
        self.assertEqual((coverage["selected_quantity"], coverage["priced_quantity"], coverage["unpriced_quantity"]), (17, 10, 7))
        self.assertEqual(coverage["unpriced_reasons"], {"outside_no_arbitrage_bounds": 1})
        self.assertEqual(matrix["contract_count"], 1)
        self.assertEqual(matrix["selected_contract_count"], 2)
        self.assertEqual(sum(matrix["put_volume"]), 0)
        self.assertIsNone(matrix["put_wall_strike"])
        self.assertEqual(consumer.fallback_iv_tick_count, 0)
        self.assertEqual(consumer.feed_quality_snapshot()["health"], "degraded")
        snapshot = build_snapshot(symbol="ES", spot=6000, session_open=6000, days_to_expiry=.25,
                                  contract_multiplier=50, risk_free_rate=.045, data=matrix,
                                  chain_state=consumer.chain_state)
        self.assertEqual(snapshot["model"]["pricing_coverage"], coverage)
        self.assertEqual(sum(row["put_volume"] for row in snapshot["strikes"]), 0)
        snapshot["expiry_breakdown"] = {"2026-09-04": None}
        self.assertIn("`2026-09-04`: `unpriced`", snapshot_to_markdown(snapshot))
        self.assertIn("Priced selected quantity: `10/17`", snapshot_to_markdown(snapshot))
        self.assertIn("pricing_coverage", snapshot_to_csv(snapshot))
        comparison = build_model_comparison_report(snapshot)
        self.assertEqual(comparison["pricing_coverage"], coverage)
        self.assertIn("Priced selected quantity: `10/17`", model_comparison_to_markdown(comparison))
        self.assertIn("pricing_coverage", model_comparison_to_csv(comparison))
        artifact = await build_terminal_checkpoint(consumer, fallback_dte=.25)
        self.assertEqual(len(artifact["rows"]), 2)
        result = await wind.calculate({"terminal_checkpoint": artifact, "iv_shift": 1})
        self.assertEqual(result["baseline"]["pricing_coverage"], coverage)
        self.assertEqual(result["scenario"]["pricing_coverage"], coverage)
        np.testing.assert_allclose(result["baseline"]["matrix"]["net_gex"], matrix["net_gex"], rtol=1e-13)
        self.assertEqual(result["baseline"]["counts"]["selected_rows"], 2)
        self.assertEqual(result["baseline"]["summary"]["quantity"], 10)
        self.assertEqual(result["baseline"]["excluded_contracts"][0]["reason"], "iv_unavailable")
        self.assertEqual(result["baseline"]["excluded_contracts"][0]["quantity"], 7)

    async def test_all_unpriced_is_unavailable_instead_of_zero_gex_and_reproduces(self):
        consumer = await consumer_with(unavailable())
        matrix = await consumer.process_latest_snapshot(.25)
        self.assertEqual(matrix["status"], "no_data")
        self.assertNotIn("total_net_gex", matrix)
        self.assertEqual(matrix["pricing_coverage"]["unpriced_quantity"], 7)
        self.assertEqual(await consumer.process_expiry_breakdown(.25), {"2026-09-04": None})
        with self.assertRaisesRegex(ValueError, "available IV"):
            build_snapshot(symbol="ES", spot=6000, session_open=6000, days_to_expiry=.25,
                           contract_multiplier=50, risk_free_rate=.045, data=matrix,
                           chain_state=consumer.chain_state)
        artifact = await build_terminal_checkpoint(consumer, fallback_dte=.25)
        self.assertIsNone(artifact["rows"][0]["iv"])
        receipt = await make_receipt("Unpriced exposure", "calculate", {"terminal_checkpoint": artifact})
        for state in (receipt["result"]["baseline"], receipt["result"]["scenario"]):
            self.assertEqual(state["status"], "no_data")
            self.assertIsNone(state["matrix"])
            self.assertIsNone(state["summary"])
            self.assertEqual(state["pricing_coverage"]["unpriced_quantity"], 7)
        self.assertEqual((await reproduce_receipt(receipt))["status"], "verified")
        with self.assertRaisesRegex(ValueError, "no contracts with available IV"):
            build_sensitivity_report(spot=6000, chain_state=consumer.chain_state,
                                     contract_rows=await consumer.selected_contract_rows(),
                                     days_to_expiry=.25, risk_free_rate=.045, contract_multiplier=50)

    async def test_later_valid_observation_does_not_repair_an_earlier_intake_prefix(self):
        first = unavailable()
        later = {**first, "iv": .2, "iv_source": "provider", "volume": 3,
                 "event_time": "2026-09-04T13:35:01Z"}
        later.pop("iv_provenance")
        events = [{"type": "underlying_tick", "symbol": "ES", "price": 6000, "timestamp": AS_OF}, first, later]
        intake = SessionIntake()
        inspected = intake.inspect(await capture_bytes(events))
        self.assertTrue(any("unavailable IV" in warning for warning in inspected["warnings"]))
        self.assertFalse(any("fallback IV" in warning for warning in inspected["warnings"]))
        prefix = validate_checkpoint(await intake.checkpoint(inspected["intake_id"], 1))
        self.assertIsNone(prefix["rows"][0]["iv"])
        self.assertEqual(prefix["rows"][0]["iv_provenance"]["underlying_event_time"], AS_OF)
        self.assertNotIn("underlying_instrument_id", prefix["rows"][0]["iv_provenance"])
        self.assertEqual((await wind.calculate({"terminal_checkpoint": prefix}))["baseline"]["status"], "no_data")
        final = validate_checkpoint(await intake.checkpoint(inspected["intake_id"], 2))
        self.assertEqual(final["rows"][0]["iv"], .2)
        self.assertEqual(final["rows"][0]["accumulated_volume"], 10)
        self.assertEqual((await wind.calculate({"terminal_checkpoint": final}))["baseline"]["status"], "available")

    async def test_prior_valid_provenance_survives_intake_and_rejects_future_or_changed_values(self):
        first = option("retained", volume=4, event_time=AS_OF)
        retained = {**first, "volume": 3, "iv_source": "prior_valid", "event_time": "2026-09-04T13:35:01Z",
                    "iv_provenance": {"method": "black_76_bisection", "status": "outside_no_arbitrage_bounds",
                                      "failed_inversion_status": "outside_no_arbitrage_bounds", "prior_iv_event_time": AS_OF,
                                      "prior_iv_source": "provider", "prior_iv": .2, "prior_iv_age_ms": 1000,
                                      "maximum_prior_iv_age_ms": 300000, "prior_iv_pricing_model": "black_76",
                                      "prior_iv_risk_free_rate": None}}
        consumer = await consumer_with(first, retained)
        artifact = await build_terminal_checkpoint(consumer, fallback_dte=.25)
        self.assertEqual(artifact["rows"][0]["iv_provenance"], retained["iv_provenance"])
        report = await wind.calculate({"terminal_checkpoint": artifact})
        self.assertEqual(report["baseline"]["contracts"][0]["iv_source"], "prior_valid")
        self.assertTrue(any("earlier valid" in note for note in report["baseline"]["pricing_assumptions"]["limitations"]))
        self.assertEqual(consumer.feed_quality_snapshot()["health"], "degraded")
        self.assertNotIn("feed checks clean", consumer.feed_quality_snapshot()["notes"])
        intake = SessionIntake()
        inspected = intake.inspect(await capture_bytes([
            {"type": "underlying_tick", "symbol": "ES", "price": 6000, "timestamp": AS_OF}, first, retained]))
        self.assertTrue(any("earlier valid IV" in warning for warning in inspected["warnings"]))
        safe = validate_checkpoint(await intake.checkpoint(inspected["intake_id"], 2))
        self.assertEqual(safe["rows"][0]["iv_provenance"], retained["iv_provenance"])
        valid_capture = await capture_bytes([
            {"type": "underlying_tick", "symbol": "ES", "price": 6000, "timestamp": AS_OF},
            first, retained])
        for changes in ({"prior_iv": .3}, {"prior_iv_event_time": "2026-09-04T13:36:00Z"},
                        {"prior_iv_source": "configured_default"}, {"prior_iv_age_ms": 300001},
                        {"status": "converged", "failed_inversion_status": "converged"},
                        {"status": "missing_inversion_input"},
                        # All fields agree on ten minutes, but a capture cannot
                        # widen the product's five-minute retention policy.
                        {"prior_iv_event_time": "2026-09-04T13:25:01Z",
                         "prior_iv_age_ms": 600000, "maximum_prior_iv_age_ms": 600000}):
            bad_event = copy.deepcopy(retained)
            bad_event["iv_provenance"].update(changes)
            with self.subTest(changes=changes, path="normalized"), self.assertRaises(ValueError):
                validate_normalized_message(bad_event)
            records = [json.loads(line) for line in valid_capture.splitlines()]
            records[-2]["message"]["iv_provenance"].update(changes)
            records[-1].pop("content_sha256")
            canonical = lambda row: json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
            records[-1]["content_sha256"] = hashlib.sha256(b"".join(canonical(row) + b"\n" for row in records)).hexdigest()
            bad_capture = b"".join(canonical(row) + b"\n" for row in records)
            with self.subTest(changes=changes, path="intake"), self.assertRaises(ValueError):
                intake.inspect(bad_capture)
            broken = copy.deepcopy(artifact)
            broken["rows"][0]["iv_provenance"].update(changes)
            broken["sha256"] = checkpoint_sha256(broken)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_checkpoint(broken)

    async def test_american_call_put_sensitivity_and_wind_use_same_pricing_model(self):
        common = {"pricing_model": "american_futures_crr", "exercise_style": "american",
                  "exercise_style_source": "provider", "expiry": "2026-10-16",
                  "expiry_timestamp": "2026-10-16T20:00:00Z"}
        consumer = await consumer_with(option("american-call", volume=10, **common),
                                       option("american-put", "P", volume=5, strike=6100, **common), unavailable())
        matrix = await consumer.process_latest_snapshot(.25)
        assumptions = matrix["pricing_assumptions"]
        self.assertTrue(assumptions["early_exercise_modeled"])
        self.assertEqual(assumptions["status"], "american_exercise_modeled")
        self.assertFalse(any("American-style contracts use a European" in item for item in assumptions["limitations"]))
        artifact = await build_terminal_checkpoint(consumer, fallback_dte=.25)
        result = await wind.calculate({"terminal_checkpoint": artifact})
        np.testing.assert_allclose(result["baseline"]["matrix"]["net_gex"], matrix["net_gex"], rtol=1e-13)
        self.assertEqual(result["baseline"]["pricing_assumptions"], assumptions)
        report = build_sensitivity_report(spot=6000, chain_state=consumer.chain_state,
                                         contract_rows=await consumer.selected_contract_rows(),
                                         days_to_expiry=.25, risk_free_rate=.045, contract_multiplier=50,
                                         base_matrix=matrix, as_of=consumer.market_time)
        self.assertEqual(report["scenarios"][0]["total_net_gex"], matrix["total_net_gex"])
        self.assertEqual(report["inputs"]["pricing_coverage"], matrix["pricing_coverage"])

    async def test_old_american_approximation_and_default_iv_remain_explicit_and_unchanged(self):
        old = option("old", pricing_model="black_76", exercise_style="american",
                     exercise_style_source="provider", iv_source="configured_default", iv=.15)
        consumer = await consumer_with(old)
        matrix = await consumer.process_latest_snapshot(.25)
        self.assertNotIn("pricing_coverage", matrix)
        self.assertEqual(matrix["pricing_assumptions"]["status"], "approximation_unmeasured")
        self.assertFalse(matrix["pricing_assumptions"]["early_exercise_modeled"])
        artifact = await build_terminal_checkpoint(consumer, fallback_dte=.25)
        self.assertNotIn("iv_provenance", artifact["rows"][0])
        self.assertEqual(artifact["rows"][0]["pricing_model"], "black_76")
        result = await wind.calculate({"terminal_checkpoint": artifact})
        self.assertNotIn("pricing_coverage", result["baseline"])
        self.assertEqual(result["baseline"]["pricing_assumptions"], matrix["pricing_assumptions"])
        np.testing.assert_allclose(result["baseline"]["matrix"]["net_gex"], matrix["net_gex"], rtol=1e-13)

    async def test_separate_position_views_preserve_partial_and_all_unpriced_coverage(self):
        events = [{"schema_version": 2, "type": "underlying_tick", "provider": "synthetic",
                   "symbol": "ES", "price": 6000, "event_time": AS_OF},
                  option("priced", volume=10, aggressor_side="buy", direction_source="provider"),
                  unavailable(), unavailable("oi-only", volume=100, position_source="open_interest",
                                             volume_semantics="cumulative")]
        report = await build_position_model_comparison({"as_of": AS_OF, "messages": events}, config=_config())
        raw = report["models"]["raw_trade_volume"]
        self.assertEqual(raw["status"], "available")
        self.assertEqual(raw["pricing_coverage"]["priced_quantity"], 10)
        self.assertEqual(raw["pricing_coverage"]["selected_quantity"], 17)
        oi = report["models"]["open_interest"]
        self.assertEqual(oi["status"], "unavailable")
        self.assertNotIn("total_net_gex", oi)
        self.assertEqual(oi["pricing_coverage"]["unpriced_quantity"], 100)
        directional = report["models"]["directionalized_trade_volume"]
        self.assertEqual(directional["pricing_coverage"], raw["pricing_coverage"])
        self.assertIn("prices 10/17 selected quantity", position_model_comparison_to_markdown(report))
        self.assertIn("pricing_coverage", position_model_comparison_to_csv(report))

    async def test_checkpoint_cannot_pair_unavailable_source_with_numeric_iv(self):
        artifact = await build_terminal_checkpoint(await consumer_with(unavailable()), fallback_dte=.25)
        for changes in ({"iv": .15}, {"iv_source": "provider"}):
            broken = copy.deepcopy(artifact)
            broken["rows"][0].update(changes)
            broken["sha256"] = checkpoint_sha256(broken)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_checkpoint(broken)


if __name__ == "__main__":
    unittest.main()
