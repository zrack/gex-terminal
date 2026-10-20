"""Offline dual-model parity, fixed-grid semantics and portable receipts."""
import copy
import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from aiohttp import ClientSession

from gex_terminal.consumer import StatefulGexConsumer
from gex_terminal.engine import IntradayGexEngine
from gex_terminal import wind_tunnel as wind
from gex_terminal import wind_tunnel_server as server
from gex_terminal.wind_tunnel_checkpoint import build_terminal_checkpoint


async def saved_checkpoint(symbol="ES", *, known=True, unpriced=True, iv=.2):
    """Small observed-shape fixture; no historical captures enter the package."""
    spot, multiplier = (6000, 50) if symbol == "ES" else (20000, 20)
    consumer = StatefulGexConsumer(IntradayGexEngine(multiplier), target_underlying=symbol, data_mode="replay")
    base = {"schema_version": 2, "provider": "synthetic", "symbol": symbol,
            "event_time": "2026-09-04T13:35:00Z"}
    assert await consumer.update_market_state(json.dumps({**base, "type": "underlying_tick", "price": spot}))
    for contract_id, side, strike, quantity in (("call", "C", spot, 10), ("put", "P", spot + 50, 7),
                                                ("unpriced", "P", spot + 100, 3)):
        if contract_id == "unpriced" and not unpriced:
            continue
        unavailable = contract_id == "unpriced"
        event = {**base, "type": "options_volume_tick", "contract_id": contract_id,
                 "strike": strike, "option_type": side, "volume": quantity,
                 "volume_semantics": "incremental", "position_source": "trade_volume",
                 "iv": None if unavailable else iv, "iv_source": "unavailable" if unavailable else "provider",
                 "instrument_class": "futures_option", "pricing_model": "black_76",
                 "exercise_style": "european", "exercise_style_source": "provider_cfi",
                 "provider_cfi": "OPEFPS", "expiry": "2026-09-05",
                 "expiry_timestamp": "2026-09-05T20:00:00Z",
                 "aggressor_side": ("buy" if side == "C" else "sell") if known else "unknown",
                 "direction_source": "provider" if known else "unknown", "contract_multiplier": multiplier}
        if unavailable:
            event["iv_provenance"] = {"method": "black_76_bisection", "status": "outside_no_arbitrage_bounds",
                                      "option_price": 1, "lower_bound": 2, "upper_bound": spot}
        assert await consumer.update_market_state(json.dumps(event))
    return await build_terminal_checkpoint(consumer, fallback_dte=.25)


class WindTunnelModelComparisonTests(unittest.IsolatedAsyncioTestCase):
    async def test_bundled_pair_matches_two_existing_calculations_and_freezes_prefix_once(self):
        for session in ("wind-tunnel-lab", "nq-research-loop"):
            request = {"session": session, "spot_shift": 12, "iv_shift": .5, "time_advance": 5}
            original = copy.deepcopy(request)
            with patch.object(wind, "_checkpoint", new=AsyncMock(wraps=wind._checkpoint)) as checkpoint:
                actual = await wind.models(request)
                checkpoint.assert_awaited_once()
            self.assertEqual(request, original)
            self.assertIsNone(actual["grid"])
            self.assertEqual([item["model"] for item in actual["models"]],
                             ["raw_trade_volume", "directionalized_trade_volume"])
            for item in actual["models"]:
                expected = await wind.calculate({**request, "model": item["model"]})
                self.assertEqual(actual["source"], expected["source"])
                for field in ("baseline", "scenario", "comparison"):
                    self.assertEqual(item[field], expected[field])
            self.assertFalse(actual["limitations"]["future_events_used"])
            self.assertTrue(actual["limitations"]["models_may_not_be_summed"])
            self.assertEqual(actual, await wind.models(request))

    async def test_saved_es_nq_pair_preserves_transport_coverage_exclusions_and_details(self):
        for symbol in ("ES", "NQ"):
            artifact = await saved_checkpoint(symbol)
            frozen = copy.deepcopy(artifact)
            core = wind.TerminalCheckpointCore(artifact)
            request = {"spot_shift": 25, "iv_shift": 1, "time_advance": 30, "model": "open_interest"}
            actual = await core.models(request)
            self.assertEqual(actual["request"]["model"], "terminal_selected")
            self.assertEqual(actual["source"]["checkpoint_sha256"], artifact["sha256"])
            self.assertEqual(actual["source"]["symbol"], symbol)
            self.assertIsInstance(actual["request"]["terminal_checkpoint"], str)
            for item in actual["models"]:
                expected = await core.calculate({**request, "model": item["model"]})
                for field in ("baseline", "scenario", "comparison"):
                    self.assertEqual(item[field], expected[field])
                for state in (item["baseline"], item["scenario"]):
                    self.assertEqual(state["pricing_coverage"]["selected_quantity"], 20)
                    self.assertEqual(state["pricing_coverage"]["priced_quantity"], 17)
                    self.assertEqual(state["pricing_coverage"]["unpriced_quantity"], 3)
                    self.assertEqual([row["contract_id"] for row in state["excluded_contracts"]], ["unpriced"])
                    self.assertEqual(state["excluded_contracts"][0]["iv_provenance"]["status"], "outside_no_arbitrage_bounds")
            self.assertEqual(actual["models"][1]["scenario"]["directional_coverage"], 1)
            self.assertEqual(artifact, frozen)

    async def test_grid_is_fixed_cartesian_and_ignores_current_shocks_and_expiry_exclusion(self):
        for symbol, width in (("ES", 25), ("NQ", 100)):
            artifact = await saved_checkpoint(symbol)
            core = wind.TerminalCheckpointCore(artifact)
            request = {"grid": True, "spot_shift": 321, "iv_shift": -100,
                       "time_advance": 43200, "exclude_nearest_expiry": True}
            with patch("socket.socket", side_effect=AssertionError("offline comparisons must not open sockets")), \
                 patch("socket.create_connection", side_effect=AssertionError("offline comparisons must not connect")):
                report = await core.models(request)
            grid = report["grid"]
            self.assertEqual(grid["axes"], {"spot_shifts": [-width, 0, width], "iv_shifts": [-1, 0, 1],
                                             "time_advances": [0, 30, 60]})
            self.assertEqual(grid["case_count"], 54)
            self.assertEqual(len(grid["cases"]), 54)
            self.assertEqual(len({(case["model"], case["spot_shift"], case["iv_shift"], case["time_advance"])
                                  for case in grid["cases"]}), 54)
            for case in grid["cases"]:
                expected = await core.calculate({key: case[key] for key in ("model", "spot_shift", "iv_shift", "time_advance")})
                state = expected["scenario"]
                self.assertEqual(case["status"], "available")
                self.assertEqual(case["total_net_gex"], state["summary"]["total_net_gex"])
                self.assertEqual(case["gamma_wall_strike"], state["summary"]["gamma_wall"])
                self.assertEqual(case["pricing_coverage"], state["pricing_coverage"])
                self.assertEqual(case["pricing_coverage"]["unpriced_quantity"], 3)
                self.assertEqual(case["counts"]["excluded_nearest_rows"], 0)
                self.assertEqual(case["counts"]["expired_rows"], 0)
                if case["model"] == "directionalized_trade_volume":
                    self.assertIsNone(case["call_wall_strike"])
                    self.assertIsNone(case["put_wall_strike"])
            for summary in grid["summaries"]:
                self.assertEqual(summary["case_count"], 27)
                self.assertEqual(summary["evaluable_count"], 27)
                self.assertEqual(sum(summary["net_sign_counts"].values()), 27)

    async def test_missing_direction_invalid_iv_no_data_and_zero_wall_are_not_agreement(self):
        unknown = wind.TerminalCheckpointCore(await saved_checkpoint(known=False))
        report = await unknown.models({"grid": True})
        self.assertEqual(report["models"][1]["scenario"]["status"], "insufficient_directional_coverage")
        self.assertIsNone(report["agreement"]["scenario"]["net_sign_matches"])
        self.assertIsNone(report["agreement"]["scenario"]["gamma_wall_matches"])
        summary = report["grid"]["summaries"][1]
        self.assertEqual(summary["not_evaluable_count"], 27)
        for field in ("net_sign_stable", "gamma_wall_stable", "baseline_net_sign_matches", "net_gex_range"):
            self.assertIsNone(summary[field])
        invalid = await wind.models({"iv_shift": -100})
        self.assertTrue(all(item["scenario"]["status"] == "invalid_scenario" for item in invalid["models"]))
        self.assertIsNone(invalid["agreement"]["scenario"]["net_sign_matches"])
        no_data = await wind.models({"checkpoint": 0})
        self.assertEqual(no_data["agreement"]["baseline"]["status"], "not_evaluable")
        # Zero exposure has a valid zero sign but no meaningful dominant wall.
        zero_state = {"model": "raw_trade_volume", "status": "available", "summary": {"net_sign": 0, "gamma_wall": None}}
        agreement = wind._model_agreement([zero_state, {**zero_state, "model": "directionalized_trade_volume"}])
        self.assertTrue(agreement["net_sign_matches"])
        self.assertIsNone(agreement["gamma_wall_matches"])
        below = await wind.models({"session": "nq-research-loop", "minimum_directional_coverage": 1, "grid": True})
        self.assertEqual(below["models"][1]["baseline"]["status"], "insufficient_directional_coverage")
        self.assertIsNone(below["grid"]["summaries"][1]["net_sign_stable"])

    async def test_partial_grid_is_not_reported_stable_and_cancellation_stops_cells(self):
        core = wind.TerminalCheckpointCore(await saved_checkpoint(iv=.005))
        partial = await core.models({"grid": True})
        for summary in partial["grid"]["summaries"]:
            self.assertEqual(summary["status_counts"]["invalid_scenario"], 9)
            self.assertEqual(summary["evaluable_count"], 18)
            self.assertIsNone(summary["net_sign_stable"])
            self.assertIsNone(summary["gamma_wall_stable"])
            self.assertIsNone(summary["baseline_net_sign_matches"])
        evaluate = wind._state
        calls = 0

        def cancel_during_grid(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 7:
                asyncio.current_task().cancel()
            return evaluate(*args, **kwargs)

        with patch.object(wind, "_state", side_effect=cancel_during_grid):
            with self.assertRaises(asyncio.CancelledError):
                await asyncio.create_task(core.models({"grid": True}))
        self.assertEqual(calls, 7)

    async def test_grid_expiry_drops_are_reported_and_source_has_no_later_events(self):
        early = await wind.models({"checkpoint": 2, "grid": True})
        self.assertGreater(early["source"]["later_events_excluded"], 0)
        self.assertEqual(early["models"][0]["baseline"]["summary"]["contract_count"], 1)
        report = await wind.models({"grid": True})
        counts = {case["time_advance"]: case["counts"]["selected_rows"] for case in report["grid"]["cases"]}
        self.assertGreater(counts[0], counts[30])
        self.assertEqual(counts[30], counts[60])
        self.assertFalse(report["limitations"]["future_events_used"])

    def test_strict_models_request(self):
        normalized = wind.normalize_request({}, "models")
        self.assertIs(normalized["grid"], False)
        self.assertEqual(normalized["model"], "raw_trade_volume")
        for request in ({"grid": 1}, {"grid": None}, {"grid": []}, {"spot_shifts": [-25, 0, 25]},
                        {"operation": "calculate"}, {"model": "unknown"}):
            with self.subTest(request=request), self.assertRaises(ValueError):
                wind.normalize_request(request, "models")
        with self.assertRaisesRegex(ValueError, "Unknown Wind Tunnel fields"):
            wind.normalize_request({"grid": True}, "calculate")

    async def test_models_receipt_save_reopen_reproduce_and_tamper(self):
        core = wind.TerminalCheckpointCore(await saved_checkpoint("NQ"))
        receipt = await server.make_receipt("Saved NQ model comparison", "models", {"grid": True, "spot_shift": 100}, core=core)
        with tempfile.TemporaryDirectory() as directory:
            store = server.ReceiptStore(Path(directory) / "comparisons")
            try:
                store.save(receipt)
                loaded = store.load(receipt["receipt_sha256"])
                # Embedded source makes the receipt portable without its core.
                self.assertEqual((await server.reproduce_receipt(loaded))["status"], "verified")
                changed = copy.deepcopy(loaded)
                changed["result"]["grid"]["cases"][0]["total_net_gex"] += 1
                with self.assertRaisesRegex(server.ReceiptError, "checksum"):
                    server.validate_receipt(changed)
            finally:
                store.close()


class WindTunnelModelsHTTPTests(unittest.IsolatedAsyncioTestCase):
    async def test_explicit_models_deadline_is_shared_by_all_three_routes(self):
        class Request:
            app = {server.LOCK_KEY: asyncio.Lock()}

        async def operation():
            return {"status": "available"}

        real_timeout = asyncio.timeout
        for kind, seconds in (("calculate", 60), ("models", 300), (None, 60)):
            with patch.object(server.asyncio, "timeout", wraps=real_timeout) as timeout:
                self.assertEqual((await server.run_bounded(Request(), operation, kind=kind)).status, 200)
                timeout.assert_called_once_with(seconds)

    async def test_real_models_route_and_receipt_transport(self):
        from urllib.parse import urlsplit
        with tempfile.TemporaryDirectory() as directory:
            core = wind.TerminalCheckpointCore(await saved_checkpoint())
            runner, launch = await server.start_server(Path(directory) / "research", port=0, core=core)
            parsed = urlsplit(launch)
            origin = f"{parsed.scheme}://{parsed.netloc}"
            headers = {"X-GEX-Capability": parsed.fragment.removeprefix("cap=")}
            bounded_patch = patch.object(server, "run_bounded", wraps=server.run_bounded)
            bounded = bounded_patch.start()
            try:
                async with ClientSession() as client:
                    async with client.post(origin + "/api/models", headers=headers,
                                           json={"spot_shift": 25, "iv_shift": 1, "time_advance": 30}) as response:
                        self.assertEqual(response.status, 200)
                        report = await response.json()
                        self.assertEqual(report["schema"], "gex-terminal.wind-tunnel.models.v1")
                        self.assertEqual(len(report["models"]), 2)
                    async with client.post(origin + "/api/receipts", headers=headers,
                                           json={"name": "Model comparison", "kind": "models", "request": report["request"]}) as response:
                        self.assertEqual(response.status, 200)
                        receipt = await response.json()
                    async with client.get(origin + "/api/receipts/" + receipt["receipt_sha256"] + "/export", headers=headers) as response:
                        self.assertEqual(response.status, 200)
                        exported = await response.json()
                        self.assertEqual(exported, receipt)
                    async with client.post(origin + "/api/reproduce", headers=headers, json=exported) as response:
                        self.assertEqual(response.status, 200)
                        self.assertEqual((await response.json())["status"], "verified")
                    async with client.post(origin + "/api/models", json={}) as response:
                        self.assertEqual(response.status, 403)
                    async with client.post(origin + "/api/models", headers=headers, json={"grid": 1}) as response:
                        self.assertEqual(response.status, 400)
                    self.assertEqual([call.kwargs["kind"] for call in bounded.await_args_list], ["models"] * 4)
            finally:
                bounded_patch.stop()
                await runner.cleanup()
