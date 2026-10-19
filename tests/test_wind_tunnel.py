"""Numerical and information-cutoff oracles for conditional Wind Tunnel research."""

import asyncio
import copy
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np

from gex_terminal.consumer import StatefulGexConsumer
from gex_terminal.engine import IntradayGexEngine
from gex_terminal import wind_tunnel as wind


class WindTunnelTests(unittest.IsolatedAsyncioTestCase):
    async def test_zero_shock_is_identity_and_original_request_and_checkpoint_are_immutable(self):
        request = {"session": "wind-tunnel-lab", "model": "raw_trade_volume"}
        before = copy.deepcopy(request)
        report = await wind.calculate(request)
        self.assertEqual(request, before)
        self.assertEqual(report["baseline"], report["scenario"])
        self.assertEqual(report, await wind.calculate(request))
        self.assertEqual(report["comparison"]["net_gex_delta"], 0.0)
        normalized = wind.normalize_request(request)
        checkpoint = await wind._checkpoint(normalized)
        frozen = copy.deepcopy(checkpoint)
        wind._state(checkpoint, {**normalized, "iv_shift": 2, "time_advance": 10, "exclude_nearest_expiry": True})
        self.assertEqual(checkpoint, frozen)
        self.assertFalse(report["limitations"]["future_events_used"])
        self.assertEqual(report["limitations"]["predictive_validity"], "unmeasured")

    async def test_replay_baseline_matches_consumer_for_each_separate_quantity_source(self):
        for session_name in ("wind-tunnel-lab", "nq-research-loop", "zero-gamma-flip"):
            for model in ("raw_trade_volume", "open_interest"):
                with self.subTest(session=session_name, model=model):
                    session = wind._session(session_name)
                    records, _ = wind._messages(session)
                    source = "open_interest" if model == "open_interest" else "trade_volume"
                    consumer = StatefulGexConsumer(IntradayGexEngine(session.contract_multiplier),
                                                  target_underlying=session.symbol, data_mode="replay")
                    for record in records:
                        if record["type"] == "underlying_tick" or record.get("position_source", "trade_volume") == source:
                            await consumer.update_market_state(json.dumps(record))
                    report = await wind.calculate({"session": session_name, "model": model})
                    expected = await consumer.process_latest_snapshot(days_to_expiry=.25,
                                                                      as_of=datetime.fromisoformat(report["source"]["as_of"].replace("Z", "+00:00")))
                    if "error" in expected:
                        self.assertEqual(report["baseline"]["status"], "no_data")
                        continue
                    actual = report["baseline"]["matrix"]
                    for key in ("strikes", "gammas", "call_volume", "put_volume", "call_gex", "put_gex", "net_gex", "total_net_gex", "gamma_wall_strike", "zero_gamma_strike"):
                        np.testing.assert_allclose(actual[key], expected[key], rtol=1e-12, atol=1e-8, err_msg=key)
                    self.assertEqual({row["position_source"] for row in report["baseline"]["contracts"]}, {source})

    async def test_black76_contract_oracle_iv_units_and_underlying_points(self):
        report = await wind.calculate({"spot_shift": 25, "iv_shift": 1, "time_advance": 10})
        state = report["scenario"]
        self.assertEqual(state["spot"], report["baseline"]["spot"] + 25)
        self.assertEqual(state["status"], "available")
        expected_total = 0
        for row in state["contracts"]:
            self.assertAlmostEqual(row["scenario_iv"] - row["base_iv"], .01)
            t = row["remaining_dte"] / 365
            spot, strike, sigma, rate = state["spot"], row["strike"], row["scenario_iv"], .045
            d1 = (math.log(spot / strike) + .5 * sigma * sigma * t) / (sigma * math.sqrt(t))
            expected_gamma = math.exp(-rate * t) * math.exp(-.5 * d1 * d1) / (math.sqrt(2 * math.pi) * spot * sigma * math.sqrt(t))
            expected_gex = expected_gamma * spot * spot * .01 * row["multiplier"] * row["quantity"] * (1 if row["option_type"] == "C" else -1)
            self.assertAlmostEqual(row["gamma"], expected_gamma, places=13)
            self.assertAlmostEqual(row["net_gex"], expected_gex, delta=1e-6)
            expected_total += expected_gex
        self.assertAlmostEqual(state["summary"]["total_net_gex"], expected_total, delta=1e-6)

    async def test_exact_expiry_removes_rows_monotonically_and_never_retargets_exclusion(self):
        # The final checkpoint is 13:35 UTC; near expiry is 14:00, far is 20:00.
        counts = []
        for minutes, expected in ((0, 16), (24.99, 16), (25, 6), (30, 6), (385, 0)):
            state = (await wind.calculate({"time_advance": minutes}))["scenario"]
            counts.append(state["counts"]["selected_rows"])
            self.assertEqual(counts[-1], expected)
            self.assertEqual(state["status"], "available" if expected else "no_data")
            if not expected:
                self.assertIsNone(state["summary"])
                self.assertIsNone(state["matrix"])
        self.assertEqual(counts, sorted(counts, reverse=True))
        for minutes in (0, 25, 30):
            state = (await wind.calculate({"time_advance": minutes, "exclude_nearest_expiry": True}))["scenario"]
            self.assertEqual(state["counts"]["selected_rows"], 6)
            self.assertEqual({row["expiry_timestamp"] for row in state["contracts"]}, {"2026-09-04T20:00:00Z"})
        # An exact instant wins over a potentially local/date-only expiry label.
        request = wind.normalize_request({})
        checkpoint = await wind._checkpoint(request)
        rows = copy.deepcopy(checkpoint.rows)
        for row in rows:
            row["expiry"] = "2026-09-03"
        relabeled = replace(checkpoint, rows=rows)
        self.assertEqual(wind._state(relabeled, request)["counts"]["selected_rows"], 16)

    async def test_legacy_fallback_time_is_explicit_and_expires_without_clamping(self):
        before = await wind.calculate({"session": "zero-gamma-flip", "fallback_dte": .01, "time_advance": 14})
        after = await wind.calculate({"session": "zero-gamma-flip", "fallback_dte": .01, "time_advance": 15})
        self.assertEqual(before["scenario"]["status"], "available")
        self.assertEqual(after["scenario"]["status"], "no_data")
        self.assertEqual({row["expiry_authority"] for row in before["scenario"]["contracts"]}, {"configured_fallback"})
        self.assertEqual({row["pricing_model"] for row in before["scenario"]["contracts"]}, {"black_scholes"})
        self.assertEqual((await wind.calculate({"session": "zero-gamma-flip", "exclude_nearest_expiry": True}))["scenario"]["status"], "no_data")

    async def test_checkpoint_only_uses_accepted_prefix_and_binds_exact_source(self):
        session = wind._session("wind-tunnel-lab")
        records, raw = wind._messages(session)
        start = await wind.calculate({"checkpoint": 0})
        self.assertEqual(start["baseline"]["status"], "no_data")
        # Underlying plus the first contract's OI and trade quantity.
        early = await wind.calculate({"checkpoint": 2})
        self.assertEqual(early["baseline"]["summary"]["contract_count"], 1)
        self.assertEqual(early["baseline"]["spot"], 6000)
        self.assertEqual(early["baseline"]["contracts"][0]["quantity"], records[2]["volume"])
        self.assertEqual(early["source"]["later_events_excluded"], len(records) - 3)
        self.assertEqual(early["source"]["source_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(early["source"]["checkpoint_sha256"], wind._sha(records[:3]))
        self.assertEqual(early["request"]["checkpoint"], 2)
        with self.assertRaises(ValueError):
            await wind.calculate({"checkpoint": len(records)})
        with self.assertRaisesRegex(ValueError, "event time"):
            await wind.calculate({"session": "demo"})

    async def test_directional_proxy_is_separate_and_carries_coverage(self):
        raw = await wind.calculate({})
        oi = await wind.calculate({"model": "open_interest"})
        directional = await wind.calculate({"model": "directionalized_trade_volume"})
        state = directional["scenario"]
        self.assertEqual(state["status"], "available")
        self.assertEqual(state["summary"]["directional_coverage"], 1)
        # In this fixture every call trade is a buy and every put a sell, so
        # passive-counterparty directional GEX has exactly the opposite sign.
        self.assertAlmostEqual(state["summary"]["total_net_gex"], -raw["scenario"]["summary"]["total_net_gex"], delta=1e-6)
        self.assertNotEqual(oi["scenario"]["summary"]["quantity"], raw["scenario"]["summary"]["quantity"])
        self.assertEqual(state["summary"]["quantity"], raw["scenario"]["summary"]["quantity"])
        partial = await wind.calculate({"session": "nq-research-loop", "model": "directionalized_trade_volume", "minimum_directional_coverage": 1})
        self.assertEqual(partial["scenario"]["status"], "insufficient_directional_coverage")
        self.assertLess(partial["scenario"]["directional_coverage"], 1)
        self.assertIsNone(partial["scenario"]["summary"])

    async def test_known_shocks_change_wall_and_net_sign_without_future_events(self):
        left = await wind.calculate({"spot_shift": -50})
        right = await wind.calculate({"spot_shift": 50})
        self.assertEqual(left["baseline"]["summary"]["gamma_wall"], 6000)
        self.assertEqual(left["scenario"]["summary"]["gamma_wall"], 5950)
        self.assertEqual(right["scenario"]["summary"]["gamma_wall"], 6050)
        self.assertEqual(left["baseline"]["summary"]["net_sign"], 1)
        self.assertEqual(left["scenario"]["summary"]["net_sign"], -1)
        self.assertTrue(left["comparison"]["net_sign_changed"])
        self.assertEqual(left["source"], right["source"])

    async def test_search_matches_exhaustive_independent_calculations_and_distance(self):
        request = {"x_values": [-50, -25, 0, 25, 50], "y_values": [-1, 0, 1], "claim": "wall_change"}
        result = await wind.search(request)
        changed = []
        for cell in result["cells"]:
            calculation = await wind.calculate({"spot_shift": cell["x"], "iv_shift": cell["y"]})
            expected = calculation["scenario"]["summary"]["gamma_wall"] != calculation["baseline"]["summary"]["gamma_wall"]
            self.assertEqual(cell["status"], "changed" if expected else "unchanged")
            self.assertEqual(cell["summary"], calculation["scenario"]["summary"])
            if expected:
                changed.append((math.sqrt((cell["x"] / 50) ** 2 + cell["y"] ** 2), cell["x"], cell["y"]))
        expected = min(changed)
        found = result["smallest_change"]
        self.assertEqual((found["distance"], found["x"], found["y"]), expected)
        self.assertEqual(found["scenario"], (await wind.calculate(found["request"]))["scenario"])
        self.assertFalse(result["distance"]["global_minimum_claimed"])
        self.assertEqual(result, await wind.search(request))

    async def test_search_distinguishes_no_break_no_data_invalid_and_model_dissent(self):
        narrow = wind.examples("no-break")
        unchanged = await wind.search(narrow["request"])
        self.assertEqual(unchanged["outcome"], "no_break_found")
        self.assertIsNone(unchanged["smallest_change"])
        exhausted = await wind.search({"session": "nq-research-loop", "exclude_nearest_expiry": True})
        self.assertEqual(exhausted["outcome"], "not_evaluable")
        self.assertTrue(all(cell["status"] == "not_evaluable" for cell in exhausted["cells"]))
        invalid = await wind.search({"x_values": [0], "y_values": [-20, 0]})
        self.assertEqual(invalid["cells"][0]["scenario_status"], "invalid_scenario")
        self.assertEqual(invalid["cells"][0]["status"], "not_evaluable")
        self.assertEqual(invalid["cells"][1]["status"], "unchanged")
        dissent = await wind.search({"claim": "model_disagreement", "x_values": [0], "y_values": [0]})
        self.assertEqual(dissent["outcome"], "break_found")
        self.assertEqual(dissent["smallest_change"]["distance"], 0)
        sign = await wind.search({"claim": "net_sign", "x_values": [-50, 0], "y_values": [0]})
        self.assertEqual([cell["status"] for cell in sign["cells"]], ["changed", "unchanged"])

    async def test_surface_points_reprice_at_declared_price_and_time_and_leave_expiry_gaps(self):
        result = await wind.surface({"spot_shift": 5, "iv_shift": 1, "time_advance": 2,
                                     "spot_shifts": [-25, 0, 25], "time_advances": [0, 24, 385]})
        self.assertEqual(result["axes"]["baseline_underlying_prices"], [5980, 6005, 6030])
        self.assertEqual(result["axes"]["scenario_underlying_prices"], [5985, 6010, 6035])
        self.assertEqual(result["axes"]["scenario_time_advances"], [2, 26, 387])
        for point in result["points"]:
            shift = result["request"]["spot_shifts"][point["spot_index"]]
            minutes = result["request"]["time_advances"][point["time_index"]]
            check = (await wind.calculate({"spot_shift": shift + 5, "iv_shift": 1, "time_advance": minutes + 2}))["scenario"]
            self.assertEqual(point["scenario_status"], check["status"])
            self.assertEqual(point["scenario_total_net_gex"], check["summary"]["total_net_gex"] if check["summary"] else None)
        self.assertTrue(all(point["scenario_status"] == "no_data" for point in result["points"][-3:]))

    async def test_strict_finite_bounded_inputs_and_shapes(self):
        for field in wind.BOUNDS:
            for value in (True, "1", None, float("nan"), float("inf"), 10**1000):
                with self.subTest(field=field, value=repr(value)[:30]), self.assertRaises(ValueError):
                    await wind.calculate({field: value})
        for request in ({"unknown": 1}, {"schema": "unknown"}, {"checkpoint": True}, {"model": "combined"},
                        {"exclude_nearest_expiry": 1}, {"session": "../private"}, {"time_advance": -1},
                        {"iv_shift": 101}, {"spot_shift": 5001}, {"fallback_dte": 0}):
            with self.subTest(request=request), self.assertRaises(ValueError):
                await wind.calculate(request)
        for request in ({"x_axis": []}, {"x_axis": "time_advance", "y_axis": "time_advance"},
                        {"x_values": []}, {"x_values": [0, 0]}, {"x_values": [1, 0]},
                        {"x_values": list(range(42))}, {"claim": "profit"}, {"claim": []},
                        {"claim": "model_disagreement", "comparison_model": "raw_trade_volume"}):
            with self.subTest(request=request), self.assertRaises(ValueError):
                await wind.search(request)

    async def test_large_grid_cooperatively_cancels_at_a_row_boundary(self):
        original = wind._state
        calls = 0
        task = None

        def counted(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 10:
                asyncio.get_running_loop().call_soon(task.cancel)
            return original(*args, **kwargs)

        request = {"x_values": list(range(-20, 21)), "y_values": list(range(-20, 21))}
        with patch.object(wind, "_state", side_effect=counted):
            task = asyncio.create_task(wind.search(request))
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertLess(calls, 100)

    async def test_report_identity_covers_result_and_exact_implementation(self):
        report = await wind.calculate({})
        claimed = report.pop("result_sha256")
        self.assertEqual(claimed, wind._sha(report))
        self.assertEqual(report["calculation_fingerprint"], wind._sha(report["calculation"]))
        self.assertIn("engine.py", report["calculation"]["implementation"])
        self.assertIn("consumer.py", report["calculation"]["implementation"])
        report["scenario"]["summary"]["total_net_gex"] += 1
        self.assertNotEqual(claimed, wind._sha(report))


if __name__ == "__main__":
    unittest.main()
