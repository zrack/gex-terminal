"""Exact offline comparison reuse and compact display/full receipt boundaries."""
import copy
import json
import unittest
from unittest.mock import patch

import numpy as np

from gex_terminal.consumer import StatefulGexConsumer
from gex_terminal.engine import IntradayGexEngine
from gex_terminal import wind_tunnel as wind
from gex_terminal import wind_tunnel_server as server
from gex_terminal.wind_tunnel_checkpoint import build_terminal_checkpoint


async def checkpoint_fixture(symbol="ES", *, known=True, mixed_cohort=False):
    spot, multiplier = (6000, 50) if symbol == "ES" else (20000, 20)
    consumer = StatefulGexConsumer(IntradayGexEngine(multiplier), target_underlying=symbol, data_mode="replay")
    base = {"schema_version": 2, "provider": "synthetic", "symbol": symbol,
            "event_time": "2026-09-04T13:35:00Z"}
    assert await consumer.update_market_state(json.dumps({**base, "type": "underlying_tick", "price": spot}))
    for number, (side, source, model) in enumerate((
        ("C", "trade_volume", "black_76"), ("P", "trade_volume", "black_76"),
        ("C", "trade_volume", "american_futures_crr"), ("P", "trade_volume", "american_futures_crr"),
        ("P", "trade_volume", "black_76"),
        *(([("C", "open_interest", "black_76")]) if mixed_cohort else []),
    )):
        unavailable = number == 4
        event = {**base, "type": "options_volume_tick", "contract_id": f"contract-{number}",
                 "strike": spot + number * 10, "option_type": side, "volume": 3 + number,
                 "volume_semantics": "cumulative" if source == "open_interest" else "incremental",
                 "position_source": source, "iv": None if unavailable else .2 + number * .005,
                 "iv_source": "unavailable" if unavailable else "provider",
                 "instrument_class": "futures_option", "pricing_model": model,
                 "exercise_style": "american" if model == "american_futures_crr" else "european",
                 "exercise_style_source": "provider", "expiry": f"2026-09-{5 + number % 2:02d}",
                 "expiry_timestamp": f"2026-09-{5 + number % 2:02d}T20:00:00Z",
                 "aggressor_side": ("buy" if side == "C" else "sell") if known else "unknown",
                 "direction_source": "provider" if known else "unknown", "contract_multiplier": multiplier}
        if unavailable:
            event["iv_provenance"] = {"method": "black_76_bisection", "status": "outside_no_arbitrage_bounds",
                                      "option_price": 1, "lower_bound": 2, "upper_bound": spot}
        if source == "open_interest":
            event.pop("aggressor_side")
            event.pop("direction_source")
        assert await consumer.update_market_state(json.dumps(event))
    return await build_terminal_checkpoint(consumer, fallback_dte=.25)


class _NoReuse:
    def gamma(self, engine, *args, **kwargs):
        return IntradayGexEngine.calculate_gamma(engine, *args, **kwargs)


class CompactComparisonTests(unittest.IsolatedAsyncioTestCase):
    async def test_prepared_rows_preserve_nested_source_and_detach_full_output_metadata(self):
        artifact = await checkpoint_fixture()
        request = wind.normalize_request({"terminal_checkpoint": artifact})
        checkpoint = await wind._checkpoint(request)
        frozen = copy.deepcopy(checkpoint.rows)
        state = wind._state(checkpoint, request)
        self.assertEqual(checkpoint.rows, frozen)
        expected = copy.deepcopy(state)
        # A caller may edit exported diagnostics without changing another
        # calculation, its source checkpoint, or the other state's output.
        state["contracts"][0]["directional_volume"]["buy"] = 999999
        state["contracts"][0]["direction_sources"].append("caller edit")
        state["excluded_contracts"][0]["iv_provenance"]["lower_bound"] = 999999
        self.assertEqual(checkpoint.rows, frozen)
        self.assertEqual(wind._state(checkpoint, request), expected)
        models = await wind.models({"terminal_checkpoint": artifact})
        other = copy.deepcopy(models["models"][1]["baseline"])
        models["models"][0]["baseline"]["contracts"][0]["directional_volume"]["buy"] = 999999
        models["models"][0]["baseline"]["excluded_contracts"][0]["iv_provenance"].clear()
        self.assertEqual(models["models"][1]["baseline"], other)
        self.assertEqual(artifact["rows"], list(frozen))

    async def test_compact_states_preserve_every_field_except_contribution_rows(self):
        for symbol in ("ES", "NQ"):
            artifact = await checkpoint_fixture(symbol)
            original = copy.deepcopy(artifact)
            core = wind.TerminalCheckpointCore(artifact)
            request = {"spot_shift": 17, "iv_shift": .5, "time_advance": 30, "grid": True}
            with patch("socket.socket", side_effect=AssertionError("offline only")):
                full = await core.models(request)
                compact = await core.models({**request, "detail_level": "compact"})
            for left, right in zip(full["models"], compact["models"]):
                self.assertEqual(left["comparison"], right["comparison"])
                for state in ("baseline", "scenario"):
                    self.assertTrue(left[state]["contracts"])
                    self.assertNotIn("contracts", right[state])
                    self.assertEqual({key: value for key, value in left[state].items() if key != "contracts"}, right[state])
                    self.assertTrue(right[state]["excluded_contracts"])
                    self.assertEqual(right[state]["pricing_coverage"]["unpriced_quantity"], 7)
                    self.assertIn("iv_freshness", right[state])
            self.assertEqual(full["grid"], compact["grid"])
            self.assertEqual(full["agreement"], compact["agreement"])
            self.assertNotIn("terminal_checkpoint", compact["request"])
            self.assertEqual(compact["request"]["terminal_checkpoint_sha256"], artifact["sha256"])
            self.assertIn("terminal_checkpoint", full["request"])
            # A display projection cannot silently become a portable receipt request.
            with self.assertRaisesRegex(ValueError, "Unknown Wind Tunnel fields"):
                await core.models(compact["request"])
            self.assertEqual(artifact, original)

    async def test_compact_receipt_is_explicitly_recomputed_with_full_portable_evidence(self):
        core = wind.TerminalCheckpointCore(await checkpoint_fixture())
        request = {"detail_level": "compact", "spot_shift": -25, "iv_shift": 1, "time_advance": 60}
        original = copy.deepcopy(request)
        receipt = await server.make_receipt("Complete model evidence", "models", request, core=core)
        self.assertEqual(request, original)
        self.assertEqual(receipt["request"]["detail_level"], "full")
        self.assertIn("terminal_checkpoint", receipt["request"])
        for item in receipt["result"]["models"]:
            self.assertTrue(item["baseline"]["contracts"])
            self.assertTrue(item["scenario"]["contracts"])
        self.assertEqual((await server.reproduce_receipt(receipt))["status"], "verified")
        changed = copy.deepcopy(receipt)
        changed["request"]["detail_level"] = "compact"
        changed["result"]["request"]["detail_level"] = "compact"
        changed["receipt_sha256"] = server.digest({key: value for key, value in changed.items() if key != "receipt_sha256"})
        with self.assertRaisesRegex(server.ReceiptError, "full portable detail"):
            server.validate_receipt(changed)

    async def test_compact_transport_is_smaller_without_checkpoint_or_contract_echoes(self):
        core = wind.TerminalCheckpointCore(await checkpoint_fixture())
        full = await core.models({})
        compact = await core.models({"detail_level": "compact"})
        self.assertLess(len(server.canonical_bytes(compact)), len(server.canonical_bytes(full)) * .75)
        for name in ("baseline", "scenario"):
            for item in compact["models"]:
                self.assertIn("matrix", item[name])
                self.assertIn("spot", item[name])

    def test_detail_level_is_models_only_and_rejects_ambiguous_values(self):
        self.assertEqual(wind.normalize_request({}, "models")["detail_level"], "full")
        self.assertEqual(wind.normalize_request({"detail_level": "compact"}, "models")["detail_level"], "compact")
        for value in (None, True, [], {}, "", "summary", 1):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "detail_level"):
                wind.normalize_request({"detail_level": value}, "models")
        for operation in ("calculate", "surface", "search"):
            with self.assertRaisesRegex(ValueError, "Unknown Wind Tunnel fields"):
                wind.normalize_request({"detail_level": "compact"}, operation)

    async def test_grid_reuses_exact_gamma_work_once_per_coordinate(self):
        core = wind.TerminalCheckpointCore(await checkpoint_fixture())
        original_gamma = IntradayGexEngine.calculate_gamma
        calls = []

        def count_gamma(engine, *args, **kwargs):
            calls.append((args[0], args[3]))
            return original_gamma(engine, *args, **kwargs)

        with patch.object(IntradayGexEngine, "calculate_gamma", count_gamma):
            cached = await core.models({"grid": True})
        self.assertEqual(len(calls), 27)  # Two models, baseline/scenario and contribution rows share exact inputs.
        with patch.object(wind, "_GammaCache", _NoReuse):
            uncached = await core.models({"grid": True})
        self.assertEqual(cached, uncached)

    async def test_differing_quantity_cohorts_rates_shocks_and_exclusions_match_uncached(self):
        core = wind.TerminalCheckpointCore(await checkpoint_fixture(mixed_cohort=True))
        for request in ({}, {"risk_free_rate": .08, "iv_shift": 1, "spot_shift": -25, "time_advance": 60},
                        {"exclude_nearest_expiry": True}, {"iv_shift": -100}, {"time_advance": 43200}):
            cached = await core.models(request)
            with patch.object(wind, "_GammaCache", _NoReuse):
                expected = await core.models(request)
            self.assertEqual(cached, expected)
        baseline = await core.models({})
        self.assertNotEqual(baseline["models"][0]["baseline"]["summary"]["contract_count"],
                            baseline["models"][1]["baseline"]["summary"]["contract_count"])

    async def test_unavailable_direction_and_mutated_responses_do_not_taint_next_request(self):
        core = wind.TerminalCheckpointCore(await checkpoint_fixture(known=False))
        request = {"detail_level": "compact", "grid": True}
        original = await core.models(request)
        self.assertEqual(original["models"][1]["scenario"]["status"], "insufficient_directional_coverage")
        self.assertIsNone(original["models"][1]["scenario"]["summary"])
        self.assertIsNone(original["agreement"]["scenario"]["net_sign_matches"])
        frozen = copy.deepcopy(original)
        original["models"][0]["scenario"]["matrix"]["net_gex"][0] = 12345
        original["models"][0]["scenario"]["excluded_contracts"].clear()
        self.assertEqual(frozen, await core.models(request))


class ExactGammaCacheTests(unittest.TestCase):
    def arguments(self):
        return dict(S=6000., K=np.array([6000., 6050.]), t=np.array([.1, .2]), r=.045,
                    sigma=np.array([.2, .25]), pricing_model=np.array(["american_futures_crr", "black_76"]),
                    carry_rate=np.array([0., 0.]), option_types=np.array(["C", "P"]))

    def test_all_ordered_pricing_inputs_are_keyed_and_cached_arrays_are_detached_read_only(self):
        engine, cache = IntradayGexEngine(50), wind._GammaCache()
        first = self.arguments()
        expected = IntradayGexEngine.calculate_gamma(engine, **first)
        actual = cache.gamma(engine, **first)
        np.testing.assert_array_equal(actual, expected)
        self.assertIs(actual, cache.gamma(engine, **copy.deepcopy(first)))
        with self.assertRaises(ValueError):
            actual[0] = 10
        first["K"][0] = 6010
        self.assertNotEqual(cache.gamma(engine, **first)[0], actual[0])
        variants = []
        for name, value in (("S", 6010.), ("r", .08), ("K", np.array([5990., 6050.])),
                            ("t", np.array([.12, .2])), ("sigma", np.array([.22, .25])),
                            ("pricing_model", np.array(["black_76", "black_scholes"])),
                            ("carry_rate", np.array([.01, 0.])), ("option_types", np.array(["P", "P"]))):
            variant = self.arguments()
            variant[name] = value
            variants.append(variant)
        reversed_rows = self.arguments()
        for name in ("K", "t", "sigma", "pricing_model", "carry_rate", "option_types"):
            reversed_rows[name] = reversed_rows[name][::-1]
        variants.append(reversed_rows)
        for arguments in variants:
            with self.subTest(arguments=arguments):
                result = cache.gamma(engine, **arguments)
                self.assertIsNot(result, actual)
                np.testing.assert_array_equal(result, IntradayGexEngine.calculate_gamma(engine, **arguments))

    def test_entry_and_byte_limits_evict_without_affecting_values(self):
        engine, cache = IntradayGexEngine(50), wind._GammaCache()
        cache.MAX_ENTRIES, cache.MAX_BYTES = 2, 96  # Each two-row entry is 16 bytes + a 32-byte digest.
        original = cache.gamma(engine, **self.arguments())
        for rate in (.05, .06, .07):
            arguments = {**self.arguments(), "r": rate}
            np.testing.assert_array_equal(cache.gamma(engine, **arguments), IntradayGexEngine.calculate_gamma(engine, **arguments))
            self.assertLessEqual(len(cache._values), 2)
            self.assertLessEqual(cache.bytes, 96)
        self.assertIsNot(cache.gamma(engine, **self.arguments()), original)
        tiny = wind._GammaCache()
        tiny.MAX_BYTES = 1
        tiny.gamma(engine, **self.arguments())
        self.assertEqual(tiny.bytes, 0)
        self.assertEqual(len(tiny._values), 0)
