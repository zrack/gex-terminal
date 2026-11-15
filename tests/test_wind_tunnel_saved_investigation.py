"""Regression fixtures for reproducible investigations of locally saved sessions."""

import asyncio
from contextlib import AsyncExitStack
import hashlib
from importlib.resources import files
import json
import math
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

from tests.test_session_intake import capture_bytes, messages
from tests.test_wind_tunnel_assets import BROWSER_DOM_HARNESS


def saved_flip_events(symbol="ES"):
    multiplier, strike = (50, 5000) if symbol == "ES" else (20, 20000)
    underlying, _, template, _ = messages(symbol, multiplier)
    underlying = {**underlying, "price": float(strike)}
    template = {**template, "strike": strike}
    put = {**template, "option_type": "P", "contract_id": f"put-{strike}", "volume": 10, "sequence": 1}
    call = {**template, "contract_id": f"call-{strike}", "volume": 40}
    followed = {**underlying, "event_time": "2026-10-18T15:30:04Z", "price": float(strike + 2)}
    next_put = {**put, "volume": 50, "event_time": "2026-10-18T15:30:05Z", "sequence": 3}
    future = {**underlying, "event_time": "2026-10-18T15:30:10Z", "price": float(strike + 200)}
    return [underlying, put, call, dict(call), followed, next_put, future]


def saved_spot_flip_events():
    underlying, put, call, *_ = saved_flip_events()
    expiry = {"expiry_timestamp": "2026-10-18T16:00:00Z", "expiry": "2026-10-18"}
    return [underlying, {**put, **expiry},
            {**call, **expiry, "contract_id": "call-5100", "strike": 5100},
            {**underlying, "price": 5100, "event_time": "2026-10-18T15:30:03Z"}]


async def write_saved_flip_fixture(directory, events=None, *, symbol="ES"):
    path = directory / f"private saved {symbol}.gex-session.jsonl"
    data = await capture_bytes(
        saved_flip_events(symbol) if events is None else events,
        source={"provider": "replay", "mode": "replay", "symbol": symbol, "synthetic": True},
        model_inputs={"days_to_expiry": .01, "risk_free_rate": .045,
                      "contract_multiplier": 50 if symbol == "ES" else 20, "expiry_filter": "all"},
    )
    path.write_bytes(data)
    return path, hashlib.sha256(data).hexdigest()


async def prepare_switch_fixtures(directory):
    from gex_terminal import saved_workspace

    # Same two flips, but NQ has an extra accepted tick before the option updates.
    nq_events = saved_flip_events("NQ")
    nq_events.insert(1, {**nq_events[0], "event_time": "2026-10-18T15:30:01Z"})
    plans = {}
    for symbol, events in (("ES", None), ("NQ", nq_events)):
        path, checksum = await write_saved_flip_fixture(directory, events, symbol=symbol)
        plan = await asyncio.to_thread(saved_workspace.prepare_saved_workspace, path, symbol, directory / symbol)
        if plan["capture_sha256"] != checksum:
            raise AssertionError(f"Preparation changed the {symbol} fixture checksum")
        plans[symbol] = plan
    return plans


class SavedSessionInvestigationTests(unittest.IsolatedAsyncioTestCase):
    async def start_saved_session(self, events=None, *, symbol="ES"):
        from aiohttp import ClientSession
        from gex_terminal import saved_workspace, wind_tunnel_server as server
        from gex_terminal.wind_tunnel_sources import checkpoint_core
        from gex_terminal.wind_tunnel_saved_replay import SavedReplay

        resources = await self.enterAsyncContext(AsyncExitStack())
        directory = Path(resources.enter_context(tempfile.TemporaryDirectory()))
        path, checksum = await write_saved_flip_fixture(directory, events, symbol=symbol)
        plan = await asyncio.to_thread(saved_workspace.prepare_saved_workspace, path, symbol, directory / "workspace")
        replay = SavedReplay(plan["capture_path"], capture_sha256=checksum, symbol=symbol)
        core = checkpoint_core(Path(plan["checkpoint_path"]))
        runner, launch = await server.start_server(directory / "research", port=0, core=core, saved_replay=replay)
        resources.push_async_callback(runner.cleanup)
        parsed = urlsplit(launch)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        headers = {"X-GEX-Capability": parsed.fragment.removeprefix("cap=")}
        client = await resources.enter_async_context(ClientSession(headers=headers))
        return client, origin, path, checksum

    async def post(self, client, origin, endpoint, body, *, expected=200):
        async with client.post(f"{origin}/api/{endpoint}", json=body) as response:
            self.assertEqual(response.status, expected, await response.text())
            return await response.json()

    def assert_reconciled(self, report):
        delta = report["after"]["summary"]["total_net_gex"] - report["before"]["summary"]["total_net_gex"]
        self.assertEqual(report["net_gex_delta"], delta)
        attributed = math.fsum(row["delta_gex"] for row in report["contributions"])
        self.assertEqual(report["attributed_gex_delta"], attributed)
        self.assertTrue(math.isclose(attributed, delta, rel_tol=1e-10, abs_tol=1e-6))

    async def test_direct_cli_prepares_both_capture_flags_with_es_primary(self):
        from gex_terminal import wind_tunnel_cli as cli

        class StartupObserved(Exception):
            pass

        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            es, es_digest = await write_saved_flip_fixture(directory)
            nq, nq_digest = await write_saved_flip_fixture(directory, symbol="NQ")
            workspace = directory / "research"

            async def inspect_startup(selected_workspace, *, port, core, saved_replays, **_):
                self.assertEqual((selected_workspace, port), (workspace, 0))
                catalog = core.catalog()
                self.assertEqual(catalog["sessions"][0]["symbol"], "ES")
                checkpoints = {item["symbol"]: item["checkpoint_sha256"] for item in catalog["saved_checkpoints"]}
                self.assertEqual(set(checkpoints), {"ES", "NQ"})
                for symbol, digest in (("ES", es_digest), ("NQ", nq_digest)):
                    replay = saved_replays[checkpoints[symbol]]
                    self.assertEqual((replay.symbol, replay.capture_sha256), (symbol, digest))
                    self.assertEqual(len((await replay.timeline())["markers"]), 2)
                raise StartupObserved

            # Flag order should not alter which capture opens initially.
            args = cli.parser().parse_args(["serve", "--saved-nq-capture", str(nq), "--saved-es-capture", str(es),
                                            "--workspace", str(workspace), "--port", "0", "--no-browser"])
            with patch.object(cli, "start_server", inspect_startup), self.assertRaises(StartupObserved):
                await cli.run(args)

    async def test_preverified_cli_keeps_nq_primary_and_uses_the_es_receipt_workspace(self):
        from gex_terminal import wind_tunnel_cli as cli

        class StartupObserved(Exception):
            pass

        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            plans = await prepare_switch_fixtures(directory)
            es, nq = plans["ES"], plans["NQ"]
            nq_workspace, es_workspace = directory / "NQ-research", directory / "ES-research"

            async def inspect_startup(workspace, *, core, saved_replays, comparison_workspace, **_):
                self.assertEqual((workspace, comparison_workspace), (nq_workspace, es_workspace))
                self.assertEqual(core.catalog()["sessions"][0]["symbol"], "NQ")
                self.assertEqual(set(saved_replays), {es["checkpoint_sha256"], nq["checkpoint_sha256"]})
                for symbol, plan in plans.items():
                    replay = saved_replays[plan["checkpoint_sha256"]]
                    self.assertEqual((replay.symbol, replay.capture_sha256), (symbol, plan["capture_sha256"]))
                raise StartupObserved

            args = cli.parser().parse_args([
                "serve", "--checkpoint", nq["checkpoint_path"], "--saved-nq-capture", nq["capture_path"],
                "--saved-capture-sha256", nq["capture_sha256"], "--comparison-checkpoint", es["checkpoint_path"],
                "--saved-es-capture", es["capture_path"], "--comparison-capture-sha256", es["capture_sha256"],
                "--workspace", str(nq_workspace), "--comparison-workspace", str(es_workspace), "--no-browser",
            ])
            with patch.object(cli, "start_server", inspect_startup), self.assertRaises(StartupObserved):
                await cli.run(args)

    async def test_exact_flip_markers_removal_and_receipt_round_trip(self):
        from gex_terminal import wind_tunnel_server as server
        from gex_terminal.wind_tunnel_saved_replay import SavedESReplay

        client, origin, path, checksum = await self.start_saved_session()
        source = {"capture_sha256": checksum}
        async with client.get(f"{origin}/api/catalog") as response:
            self.assertEqual(response.status, 200, await response.text())
            catalog = await response.json()
        checkpoint = next(source for source in catalog["sessions"] if source["name"] == "terminal-checkpoint")
        self.assertEqual(checkpoint["investigation_capture"], {"sha256": checksum})
        timeline = await self.post(client, origin, "investigation-timeline", source)
        markers = timeline["markers"]
        self.assertEqual(timeline["method"], "every_accepted_event")
        self.assertEqual(timeline["sample_stride_events"], 1)
        self.assertEqual([(marker["before_sequence"], marker["sequence"]) for marker in markers], [(1, 2), (4, 5)])
        self.assertEqual([(marker["before_sign"], marker["after_sign"]) for marker in markers], [(-1, 1), (1, -1)])
        self.assertEqual(markers[0]["as_of"], markers[0]["before_as_of"])
        self.assertEqual(markers[0]["as_of"], "2026-10-18T15:30:02Z")
        await self.post(client, origin, "investigation-timeline", {"capture_sha256": "0" * 64}, expected=400)

        selected = {**source, "sequence": markers[0]["sequence"]}
        observed = await self.post(client, origin, "investigate-saved", {**selected, "remove_update": False})
        removed = await self.post(client, origin, "investigate-saved", {**selected, "remove_update": True})
        self.assertEqual(observed["event"]["sequence"], 2)
        self.assertEqual(observed["event"]["type"], "options_volume_tick")
        self.assertEqual(observed["before"], removed["before"])
        self.assertEqual(observed["after"], removed["after"])
        before, after, alternative = removed["before"], removed["after"], removed["counterfactual"]
        self.assertEqual([case["spot"] for case in (before, after, alternative)], [5000.0] * 3)
        self.assertEqual([case["summary"]["net_sign"] for case in (before, after, alternative)], [-1, 1, -1])
        self.assertEqual(before["as_of"], alternative["as_of"])
        driver = removed["contributions"][0]
        self.assertEqual((driver["strike"], driver["option_type"]), (5000, "C"))
        self.assertEqual((driver["before_quantity"], driver["after_quantity"], driver["counterfactual_quantity"]), (0, 40, 0))
        self.assert_reconciled(removed)

        receipt = await self.post(client, origin, "receipts", {
            "name": "Saved ES without the call update", "kind": "investigate-saved", "request": removed["request"],
        })
        self.assertEqual(receipt["result"], removed)
        async with client.get(f"{origin}/api/receipts/{receipt['receipt_sha256']}/export") as response:
            self.assertEqual(response.status, 200, await response.text())
            self.assertIn("attachment", response.headers["Content-Disposition"])
            exported = await response.read()
        self.assertNotIn(str(path).encode(), exported)
        self.assertNotIn(b"private-account-path", exported)
        reproduced = await self.post(client, origin, "reproduce", json.loads(exported))
        self.assertEqual(reproduced["status"], "verified")
        self.assertEqual(reproduced["result"], removed)
        saved_bytes = path.read_bytes()
        self.assertEqual(hashlib.sha256(saved_bytes).hexdigest(), checksum)

        # A fresh process may open the same verified content from another path.
        copied = path.with_name("renamed saved ES.gex-session.jsonl")
        copied.write_bytes(saved_bytes)
        matching_input = SavedESReplay(copied)
        self.addCleanup(matching_input.close)
        exact = await server.reproduce_receipt(json.loads(exported), saved_replay=matching_input)
        self.assertEqual(exact["status"], "verified")
        self.assertEqual(exact["result"], removed)
        with self.assertRaises(server.ReceiptError):
            await server.reproduce_receipt(json.loads(exported))
        copied.write_bytes(await capture_bytes(saved_spot_flip_events()))
        wrong_input = SavedESReplay(copied, capture_sha256="0" * 64)
        self.addCleanup(wrong_input.close)
        with self.assertRaises(server.ReceiptError):
            await server.reproduce_receipt(json.loads(exported), saved_replay=wrong_input)

    async def test_underlying_update_reprices_multiple_contracts_without_changing_quantity(self):
        client, origin, _, checksum = await self.start_saved_session(saved_spot_flip_events())
        timeline = await self.post(client, origin, "investigation-timeline", {"capture_sha256": checksum})
        self.assertEqual([marker["sequence"] for marker in timeline["markers"]], [3])
        result = await self.post(client, origin, "investigate-saved", {
            "capture_sha256": checksum, "sequence": 3, "remove_update": True,
        })
        self.assertEqual(result["event"]["type"], "underlying_tick")
        self.assertEqual([result[case]["spot"] for case in ("before", "after", "counterfactual")], [5000, 5100, 5000])
        self.assertEqual(result["counterfactual"]["as_of"], result["after"]["as_of"])
        self.assertEqual(result["counterfactual"]["summary"]["net_sign"], -1)
        self.assertEqual({(row["strike"], row["option_type"]) for row in result["contributions"]}, {(5000, "P"), (5100, "C")})
        self.assertTrue(all(row["before_quantity"] == row["after_quantity"] for row in result["contributions"]))
        self.assert_reconciled(result)

    async def test_nq_timeline_removal_and_market_bound_receipt(self):
        from gex_terminal import wind_tunnel_server as server
        from gex_terminal.wind_tunnel_saved_replay import SavedReplay

        client, origin, path, checksum = await self.start_saved_session(symbol="NQ")
        async with client.get(f"{origin}/api/catalog") as response:
            self.assertEqual(response.status, 200, await response.text())
            catalog = await response.json()
        primary = next(source for source in catalog["sessions"] if source["name"] == "terminal-checkpoint")
        self.assertEqual(primary["symbol"], "NQ")
        self.assertEqual(primary["investigation_capture"]["sha256"], checksum)

        selection = {"capture_sha256": checksum}
        timeline = await self.post(client, origin, "investigation-timeline", selection)
        self.assertEqual([(marker["before_sequence"], marker["sequence"]) for marker in timeline["markers"]],
                         [(1, 2), (4, 5)])
        self.assertEqual(timeline["markers"][0]["before_as_of"], timeline["markers"][0]["as_of"])
        request = {**selection, "sequence": timeline["markers"][0]["sequence"], "remove_update": True}
        operation = "investigate-saved-nq"
        result = await self.post(client, origin, operation, request)
        await self.post(client, origin, "investigate-saved", request, expected=400)
        self.assertEqual(result["source"]["symbol"], "NQ")
        self.assertEqual(result["source"]["contract_multiplier"], 20)
        self.assertEqual(result["event"]["sequence"], request["sequence"])
        self.assertEqual(result["event"]["type"], "options_volume_tick")
        before, after, alternative = (result[key] for key in ("before", "after", "counterfactual"))
        self.assertEqual([point["spot"] for point in (before, after, alternative)], [20000.0] * 3)
        self.assertEqual([point["summary"]["net_sign"] for point in (before, after, alternative)], [-1, 1, -1])
        self.assertEqual(alternative["as_of"], after["as_of"])
        driver = result["contributions"][0]
        self.assertEqual((driver["contract_id"], driver["strike"], driver["option_type"]), ("call-20000", 20000, "C"))
        self.assertEqual((driver["before_quantity"], driver["after_quantity"], driver["counterfactual_quantity"]), (0, 40, 0))
        self.assert_reconciled(result)

        receipt = await self.post(client, origin, "receipts", {
            "name": "Saved NQ without the call update", "kind": operation, "request": result["request"],
        })
        self.assertEqual(receipt["result"], result)
        async with client.get(f"{origin}/api/receipts/{receipt['receipt_sha256']}/export") as response:
            self.assertEqual(response.status, 200, await response.text())
            exported = await response.read()
        self.assertNotIn(str(path).encode(), exported)
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), checksum)

        matching = SavedReplay(path, symbol="NQ")
        self.addCleanup(matching.close)
        reproduced = await server.reproduce_receipt(json.loads(exported), saved_replay=matching)
        self.assertEqual(reproduced["status"], "verified")
        self.assertEqual(reproduced["result"], result)
        wrong_market = SavedReplay(path, capture_sha256=checksum, symbol="ES")
        self.addCleanup(wrong_market.close)
        with self.assertRaises(server.ReceiptError):
            await server.reproduce_receipt(json.loads(exported), saved_replay=wrong_market)

        unrelated, unrelated_checksum = await write_saved_flip_fixture(path.parent, symbol="ES")
        wrong_capture = SavedReplay(unrelated, capture_sha256=unrelated_checksum, symbol="NQ")
        self.addCleanup(wrong_capture.close)
        with self.assertRaises(ValueError):
            await wrong_capture.timeline()

    async def test_same_server_routes_both_captures_and_receipt_workspaces(self):
        from aiohttp import ClientSession
        from gex_terminal import wind_tunnel_server as server
        from gex_terminal.wind_tunnel_saved_replay import SavedReplay
        from gex_terminal.wind_tunnel_sources import checkpoint_core

        resources = await self.enterAsyncContext(AsyncExitStack())
        directory = Path(resources.enter_context(tempfile.TemporaryDirectory()))
        plans = await prepare_switch_fixtures(directory)
        es, nq = plans["ES"], plans["NQ"]
        replay_by_checkpoint = {}
        for symbol, plan in plans.items():
            replay = SavedReplay(plan["capture_path"], plan["capture_sha256"], symbol=symbol)
            resources.callback(replay.close)
            replay_by_checkpoint[plan["checkpoint_sha256"]] = replay
        core = checkpoint_core(Path(es["checkpoint_path"]), [Path(nq["checkpoint_path"])])
        for invalid_checkpoint in (es["checkpoint_sha256"], "0" * 64):
            with self.subTest(invalid_checkpoint=invalid_checkpoint):
                unbound = SavedReplay(nq["capture_path"], nq["capture_sha256"], symbol="NQ")
                resources.callback(unbound.close)
                with self.assertRaises(ValueError):
                    await server.start_server(directory / "invalid", port=0, core=core,
                                              saved_replays={invalid_checkpoint: unbound})
        wrong_digest = SavedReplay(nq["capture_path"], "1" * 64, symbol="NQ")
        resources.callback(wrong_digest.close)
        with self.assertRaises(ValueError):
            await server.start_server(directory / "invalid-digest", port=0, core=core,
                                      saved_replays={**replay_by_checkpoint, nq["checkpoint_sha256"]: wrong_digest})
        workspaces = {symbol: directory / (symbol + "-research") for symbol in plans}
        runner, launch = await server.start_server(
            workspaces["ES"], port=0, core=core, saved_replays=replay_by_checkpoint,
            comparison_workspace=workspaces["NQ"],
        )
        resources.push_async_callback(runner.cleanup)
        parsed = urlsplit(launch)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        headers = {"X-GEX-Capability": parsed.fragment.removeprefix("cap=")}
        client = await resources.enter_async_context(ClientSession(headers=headers))
        async with client.get(f"{origin}/api/catalog") as response:
            self.assertEqual(response.status, 200, await response.text())
            catalog = await response.json()
        primary = next(source for source in catalog["sessions"] if source["name"] == "terminal-checkpoint")
        alternate = next(source for source in catalog["saved_checkpoints"] if source["symbol"] == "NQ")
        for source, plan in ((primary, es), (alternate, nq)):
            self.assertEqual(source["symbol"], plan["symbol"])
            self.assertEqual(source["investigation_capture"], {"sha256": plan["capture_sha256"]})
        self.assertEqual(alternate["checkpoint_sha256"], nq["checkpoint_sha256"])
        self.assertNotIn(str(directory), json.dumps(catalog))

        primary_replay = replay_by_checkpoint[es["checkpoint_sha256"]]
        start_timeline = primary_replay.timeline
        scan_started, release_scan = asyncio.Event(), asyncio.Event()

        async def delayed_primary_timeline():
            scan_started.set()
            await release_scan.wait()
            return await start_timeline()

        with patch.object(primary_replay, "timeline", delayed_primary_timeline):
            async with asyncio.TaskGroup() as tasks:
                es_scan = tasks.create_task(self.post(client, origin, "investigation-timeline", {
                    "capture_sha256": es["capture_sha256"],
                }))
                try:
                    await asyncio.wait_for(scan_started.wait(), 2)
                    nq_timeline = await self.post(client, origin, "investigation-timeline", {
                        "capture_sha256": nq["capture_sha256"],
                    })
                    scenario = await self.post(client, origin, "calculate", {"terminal_checkpoint": alternate["artifact"]})
                    self.assertEqual(scenario["source"]["symbol"], "NQ")
                    self.assertFalse(es_scan.done())
                finally:
                    release_scan.set()
        timelines = {"ES": es_scan.result(), "NQ": nq_timeline}

        receipts = {}
        for symbol, operation, position, strike in (("ES", "investigate-saved", 2, 5000),
                                                     ("NQ", "investigate-saved-nq", 3, 20000)):
            capture = {"capture_sha256": plans[symbol]["capture_sha256"]}
            timeline = timelines[symbol]
            self.assertEqual(timeline["capture_sha256"], capture["capture_sha256"])
            self.assertEqual([marker["sequence"] for marker in timeline["markers"]], [position, position + 3])
            request = {**capture, "sequence": position, "remove_update": True}
            result = await self.post(client, origin, operation, request)
            self.assertEqual(result["source"]["symbol"], symbol)
            self.assertEqual(result["source"]["capture_sha256"], capture["capture_sha256"])
            self.assertEqual(result["event"]["sequence"], position)
            self.assertEqual(result["contributions"][0]["contract_id"], f"call-{strike}")
            self.assertEqual(result["counterfactual"]["as_of"], result["after"]["as_of"])
            self.assertEqual(result["counterfactual"]["summary"]["net_sign"], -1)
            self.assert_reconciled(result)
            receipt = await self.post(client, origin, "receipts", {
                "name": f"Saved {symbol} in shared window", "kind": operation, "request": result["request"],
            })
            receipts[symbol] = receipt
            other = nq if symbol == "ES" else es
            mixed_request = {**request, "capture_sha256": other["capture_sha256"]}
            await self.post(client, origin, operation, mixed_request, expected=400)
            await self.post(client, origin, "receipts", {
                "name": "Wrong capture", "kind": operation, "request": mixed_request,
            }, expected=400)
        await self.post(client, origin, "investigation-timeline", {"capture_sha256": "0" * 64}, expected=400)

        async with client.get(f"{origin}/api/receipts") as response:
            self.assertEqual(response.status, 200, await response.text())
            listed = await response.json()
        self.assertEqual({item["id"] for item in listed["receipts"]},
                         {receipt["receipt_sha256"] for receipt in receipts.values()})
        for symbol in ("NQ", "ES"):
            receipt = receipts[symbol]
            filename = receipt["receipt_sha256"] + ".json"
            self.assertTrue((workspaces[symbol] / filename).is_file())
            self.assertFalse((workspaces["NQ" if symbol == "ES" else "ES"] / filename).exists())
            async with client.get(f"{origin}/api/receipts/{receipt['receipt_sha256']}/export") as response:
                self.assertEqual(response.status, 200, await response.text())
                exported = await response.json()
            self.assertEqual(exported, receipt)
            reproduced = await self.post(client, origin, "reproduce", exported)
            self.assertEqual(reproduced["status"], "verified")
            self.assertEqual(reproduced["result"], receipt["result"])

    async def test_es_only_receipt_still_requires_an_exact_reproduced_result(self):
        from gex_terminal import wind_tunnel as wind, wind_tunnel_server as server
        from gex_terminal.wind_tunnel_saved_receipt_compat import _ES_ONLY_IMPLEMENTATION
        from gex_terminal.wind_tunnel_saved_replay import SavedReplay

        def with_result(envelope, result):
            result = {key: value for key, value in result.items() if key != "result_sha256"}
            result["result_sha256"] = wind._sha(result)
            unsigned = {**envelope, "result": result}
            unsigned.pop("receipt_sha256")
            return {**unsigned, "receipt_sha256": server.digest(unsigned)}

        with tempfile.TemporaryDirectory() as directory:
            path, checksum = await write_saved_flip_fixture(Path(directory))
            replay = SavedReplay(path, capture_sha256=checksum)
            self.addCleanup(replay.close)
            receipt = await server.make_receipt("ES-only receipt", "investigate-saved", {
                "capture_sha256": checksum, "sequence": 2, "remove_update": True,
            }, saved_replay=replay)
            result = receipt["result"]
            identity = result["calculation"]
            legacy_identity = {**identity, "implementation": {**identity["implementation"], **_ES_ONLY_IMPLEMENTATION}}
            legacy = with_result(receipt, {**result, "calculation": legacy_identity,
                                           "calculation_fingerprint": wind._sha(legacy_identity)})
            verified = await server.reproduce_receipt(legacy, saved_replay=replay)
            self.assertEqual(verified["status"], "verified")
            self.assertEqual(verified["result"], legacy["result"])

            altered = {**legacy["result"], "event": {**legacy["result"]["event"], "volume": 41}}
            mismatch = await server.reproduce_receipt(with_result(legacy, altered), saved_replay=replay)
            self.assertEqual(mismatch["status"], "mismatch")


class SavedESReplayTimelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_sampled_brackets_localize_to_exact_accepted_events(self):
        from gex_terminal import wind_tunnel_saved_replay as saved

        with tempfile.TemporaryDirectory() as directory:
            path, checksum = await write_saved_flip_fixture(Path(directory))
            replay = saved.SavedESReplay(path, capture_sha256=checksum)
            try:
                with patch.object(saved, "EXACT_EVENT_LIMIT", 3), patch.object(saved, "MAX_SAMPLED_POINTS", 4):
                    timeline = await replay.timeline()
            finally:
                replay.close()
        self.assertEqual(timeline["method"], "sampled_then_localized")
        self.assertEqual(timeline["sample_stride_events"], 2)
        self.assertEqual(timeline["sampled_points"], 4)
        self.assertEqual(timeline["unresolved_brackets"], 0)
        self.assertEqual([(marker["before_sequence"], marker["sequence"]) for marker in timeline["markers"]], [(1, 2), (4, 5)])


class SavedSessionBrowserTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node.js is needed for the browser workflow harness")
    def test_saved_timeline_click_remove_save_and_reopen(self):
        from gex_terminal import saved_workspace, wind_tunnel as wind
        from gex_terminal.wind_tunnel_checkpoint import checkpoint_sha256, read_checkpoint
        from gex_terminal.wind_tunnel_saved_investigation import investigate_saved
        from gex_terminal.wind_tunnel_saved_replay import SavedReplay

        async def make_fixtures(directory, symbol):
            path, checksum = await write_saved_flip_fixture(directory, symbol=symbol)
            plan = await asyncio.to_thread(saved_workspace.prepare_saved_workspace, path, symbol, directory / "workspace")
            replay = SavedReplay(plan["capture_path"], capture_sha256=checksum, symbol=symbol)
            try:
                timeline = await replay.timeline()
                request = {"capture_sha256": checksum, "sequence": timeline["markers"][0]["sequence"]}
                observed = await investigate_saved(request, replay)
                removed = await investigate_saved({**request, "remove_update": True}, replay)
            finally:
                replay.close()
            core = wind.TerminalCheckpointCore(read_checkpoint(plan["checkpoint_path"]))
            catalog = core.catalog()
            catalog["sessions"][0]["investigation_capture"] = {"sha256": checksum}
            other_checkpoint = read_checkpoint(plan["checkpoint_path"])
            other_checkpoint["source"]["label"] = "Other frozen checkpoint"
            other_checkpoint["sha256"] = checkpoint_sha256(other_checkpoint)
            other_result = await wind.calculate({"terminal_checkpoint": other_checkpoint})
            kind = "investigate-saved" if symbol == "ES" else "investigate-saved-nq"
            receipt = {"kind": kind, "name": f"Remove saved {symbol} update",
                       "request": removed["request"], "result": removed}
            other_receipt = {"kind": "calculate", "name": "Other frozen checkpoint",
                             "request": other_result["request"], "result": other_result}
            return {"symbol": symbol, "catalog": catalog, "checkpoints": wind.checkpoints(wind.DEFAULTS["session"]),
                    "timeline": timeline, "observed": observed, "receipt": receipt, "other_receipt": other_receipt}

        assets = str(files("gex_terminal").joinpath("wind_tunnel_web"))
        for symbol in ("ES", "NQ"):
            with self.subTest(symbol=symbol), tempfile.TemporaryDirectory() as directory:
                fixture = asyncio.run(make_fixtures(Path(directory), symbol))
                result = subprocess.run(
                    [shutil.which("node"), "-e", SAVED_BROWSER_HARNESS, assets],
                    input=json.dumps(fixture), text=True, capture_output=True, timeout=15,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    @unittest.skipUnless(shutil.which("node"), "Node.js is needed for the browser workflow harness")
    def test_switching_reuses_each_timeline_and_reopens_the_receipt_market(self):
        from gex_terminal import wind_tunnel as wind
        from gex_terminal.wind_tunnel_saved_investigation import investigate_saved
        from gex_terminal.wind_tunnel_saved_replay import SavedReplay
        from gex_terminal.wind_tunnel_server import make_receipt
        from gex_terminal.wind_tunnel_sources import checkpoint_core

        async def make_fixtures(directory):
            plans = await prepare_switch_fixtures(directory)
            core = checkpoint_core(Path(plans["ES"]["checkpoint_path"]), [Path(plans["NQ"]["checkpoint_path"])])
            catalog = core.catalog()
            catalog["sessions"][0]["investigation_capture"] = {"sha256": plans["ES"]["capture_sha256"]}
            nq_source = next(item for item in catalog["saved_checkpoints"] if item["symbol"] == "NQ")
            nq_source["investigation_capture"] = {"sha256": plans["NQ"]["capture_sha256"]}
            cases = {}
            for symbol, kind in (("ES", "investigate-saved"), ("NQ", "investigate-saved-nq")):
                plan = plans[symbol]
                replay = SavedReplay(plan["capture_path"], plan["capture_sha256"], symbol=symbol)
                try:
                    timeline = await replay.timeline()
                    request = {"capture_sha256": plan["capture_sha256"], "sequence": timeline["markers"][0]["sequence"]}
                    observed = await investigate_saved(request, replay)
                    receipt = await make_receipt(f"Saved {symbol} update removal", kind,
                                                 {**request, "remove_update": True}, saved_replay=replay)
                finally:
                    replay.close()
                cases[symbol] = {"timeline": timeline, "observed": observed, "receipt": receipt}
            return {"catalog": catalog, "checkpoints": wind.checkpoints(wind.DEFAULTS["session"]), "cases": cases}

        assets = str(files("gex_terminal").joinpath("wind_tunnel_web"))
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [shutil.which("node"), "-e", SWITCH_BROWSER_HARNESS, assets],
                input=json.dumps(asyncio.run(make_fixtures(Path(directory)))), text=True,
                capture_output=True, timeout=15,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


SAVED_BROWSER_HARNESS = BROWSER_DOM_HARNESS + r"""
const {symbol, catalog, checkpoints, timeline, observed, receipt, other_receipt} = JSON.parse(fs.readFileSync(0, 'utf8'));
const operation = receipt.kind;
const createElement = document.createElement;
document.createElement = tag => Object.assign(createElement(tag), {style: {}});
const calls = [];
global.fetch = async (url, options) => {
  assert.equal(options.headers['X-GEX-Capability'], 'local-test-capability');
  const path = url.replace('/api/', '');
  const body = options.body ? JSON.parse(options.body) : null;
  calls.push({path, body});
  const state = {status: 'available', spot: 5000, summary: {total_net_gex: 1, gamma_wall: 5000}};
  let result;
  if (path === 'catalog') result = catalog;
  else if (path.startsWith('checkpoints?session=')) result = checkpoints;
  else if (path === 'calculate') result = {request: body, baseline: state, scenario: state};
  else if (path === 'surface') result = {request: body, axes: {}, points: []};
  else if (path === 'investigation-timeline') result = timeline;
  else if (path === operation) result = body.remove_update ? receipt.result : observed;
  else if (path === 'receipts') result = receipt;
  else if (path === 'reproduce') {
    const expected = body.kind === 'calculate' ? other_receipt : receipt;
    assert.deepEqual(body, expected);
    result = {status: 'verified', result: expected.result};
  } else throw new Error('Unexpected endpoint ' + path);
  return {ok: true, status: 200, json: async () => result};
};
const app = fs.readFileSync(root + '/app.js', 'utf8');
assert(app.includes('  initialize();'));
vm.runInThisContext(app.replace('  initialize();', '  globalThis.initializeBrowser = initialize;'));
const element = id => elements.get('#' + id);
const contents = node => [node.textContent, ...node.children.map(contents)].join(' ');
const settle = () => new Promise(setImmediate);
async function importFile(artifact) {
  const raw = JSON.stringify(artifact);
  await element('receipt-file').listeners.change({target: {files: [{size: raw.length, text: async () => raw}], value: 'receipt.json'}});
  assert.match(element('import-status').textContent, /verified and reopened/i);
}
(async () => {
  await initializeBrowser();
  await settle();
  assert.equal(element('saved-flip-timeline').hidden, false);
  assert.equal(element('saved-flip-heading').textContent, `Saved ${symbol} replay timeline`);
  assert(element('investigate-flip').hidden);
  await element('scan-saved-flips').listeners.click();
  await settle();
  assert.deepEqual(calls.find(x => x.path === 'investigation-timeline').body, {capture_sha256: timeline.capture_sha256});
  const markers = element('saved-flip-markers').children;
  assert.equal(markers.length, 2);
  assert.match(contents(markers[0]), /15:30:02.*Negative → Positive/s);
  await markers[0].listeners.click();
  await settle();
  const selected = {capture_sha256: timeline.capture_sha256, sequence: timeline.markers[0].sequence};
  assert.deepEqual(calls.filter(x => x.path === operation).at(-1).body, {...selected, remove_update: false});
  assert.match(element('investigation-heading').textContent, new RegExp(`^${symbol} net-GEX`));
  assert.match(contents(element('investigation-contract-rows')), /call.*40/i);

  element('remove-call-update').checked = true;
  await element('remove-call-update').listeners.change({target: element('remove-call-update')});
  await settle();
  assert.deepEqual(calls.filter(x => x.path === operation).at(-1).body, {...selected, remove_update: true});
  assert.match(contents(element('investigation-snapshots')), /Negative.*Positive.*Negative/s);
  element('save-investigation').listeners.click();
  assert.equal(element('save-dialog').open, true);
  element('scenario-name').value = receipt.name;
  await element('save-form').listeners.submit({preventDefault() {}});
  assert.deepEqual(calls.filter(x => x.path === 'receipts').at(-1).body, {
    name: receipt.name, kind: operation, request: receipt.request,
  });

  await element('source').listeners.change({target: {value: catalog.bundled_defaults.session}});
  assert(element('saved-flip-timeline').hidden);
  assert(element('flip-investigation').hidden);
  await importFile(other_receipt);
  assert.equal(element('source').value, 'terminal-checkpoint');
  assert(element('saved-flip-timeline').hidden);
  await importFile(receipt);
  assert.equal(element('source').value, `saved-${symbol.toLowerCase()}-replay-${timeline.capture_sha256}`);
  assert.equal(element('saved-flip-timeline').hidden, false);
  assert.equal(element('remove-call-update').checked, true);
  assert.match(contents(element('investigation-snapshots')), /Negative.*Positive.*Negative/s);
})().catch(error => {console.error(error); process.exitCode = 1;});
"""


SWITCH_BROWSER_HARNESS = BROWSER_DOM_HARNESS + r"""
const {catalog, checkpoints, cases} = JSON.parse(fs.readFileSync(0, 'utf8'));
const selectIds = {ES: 'terminal-checkpoint', NQ: `saved-checkpoint-${catalog.saved_checkpoints.find(item => item.symbol === 'NQ').checkpoint_sha256}`};
const paths = Object.fromEntries(Object.values(cases).map(item => [item.receipt.kind, item]));
const captures = Object.fromEntries(Object.values(cases).map(item => [item.timeline.capture_sha256, item]));
const settle = () => new Promise(setImmediate);
const calls = [], saved = new Map();
const createElement = document.createElement;
document.createElement = tag => Object.assign(createElement(tag), {style: {}});
let delayScan = null, delayReport = null;
function holdNextESResponse() {
  let release;
  const promise = new Promise(resolve => {release = resolve;});
  return {promise, release, signal: null};
}
global.fetch = async (url, options) => {
  const path = url.replace('/api/', '');
  const body = options.body ? JSON.parse(options.body) : null;
  calls.push({path, body});
  const state = {status: 'available', spot: 5000, summary: {total_net_gex: 1, gamma_wall: 5000}};
  let result;
  if (path === 'catalog') result = catalog;
  else if (path.startsWith('checkpoints?session=')) result = checkpoints;
  else if (path === 'calculate') result = {request: body, baseline: state, scenario: state};
  else if (path === 'surface') result = {request: body, axes: {}, points: []};
  else if (path === 'investigation-timeline') {
    const selected = captures[body.capture_sha256];
    assert(selected, 'Timeline request must name one registered capture');
    if (selected === cases.ES && delayScan) {
      const waiting = delayScan;
      delayScan = null;
      waiting.signal = options.signal;
      await waiting.promise;
    }
    result = selected.timeline;
  } else if (paths[path]) {
    const selected = paths[path];
    assert.equal(body.capture_sha256, selected.timeline.capture_sha256);
    assert.equal(body.sequence, selected.timeline.markers[0].sequence);
    if (selected === cases.ES && delayReport) {
      const waiting = delayReport;
      delayReport = null;
      waiting.signal = options.signal;
      await waiting.promise;
    }
    result = body.remove_update ? selected.receipt.result : selected.observed;
  } else if (path === 'receipts') {
    if (body) {
      const expected = paths[body.kind].receipt;
      assert.deepEqual(body.request, expected.request);
      saved.set(expected.receipt_sha256, expected);
      result = expected;
    } else result = {receipts: [...saved.values()].map(item => ({...item, id: item.receipt_sha256}))};
  } else if (path.startsWith('receipts/')) result = saved.get(path.split('/')[1]);
  else if (path === 'reproduce') {
    assert.deepEqual(body, saved.get(body.receipt_sha256));
    result = {status: 'verified', result: body.result};
  } else throw new Error('Unexpected endpoint ' + path);
  return {ok: true, status: 200, json: async () => result, text: async () => JSON.stringify(result)};
};
const app = fs.readFileSync(root + '/app.js', 'utf8');
assert(app.includes('  initialize();'));
vm.runInThisContext(app.replace('  initialize();', '  globalThis.initializeBrowser = initialize;'));
const element = id => elements.get('#' + id);
const contents = node => [node.textContent, ...node.children.map(contents)].join(' ');
const firstMarker = () => element('saved-flip-markers').children[0];
async function selectMarket(symbol) {
  await element('source').listeners.change({target: {value: selectIds[symbol]}});
  await settle();
  assert.equal(element('source').value, selectIds[symbol]);
  assert.equal(element('saved-flip-heading').textContent, `Saved ${symbol} replay timeline`);
}
function assertVisibleMarket(symbol) {
  const expected = cases[symbol];
  assert.match(contents(firstMarker()), new RegExp(`Event ${expected.timeline.markers[0].sequence}\\b`));
  assert.equal(element('source').value, selectIds[symbol]);
  assert.match(element('investigation-heading').textContent, new RegExp(`^${symbol} net-GEX`));
  assert.match(contents(element('investigation-contract-rows')), new RegExp(`call-${symbol === 'ES' ? 5000 : 20000}`));
}
async function removeAndSave(symbol) {
  const expected = cases[symbol].receipt;
  element('remove-call-update').checked = true;
  await element('remove-call-update').listeners.change({target: element('remove-call-update')});
  assertVisibleMarket(symbol);
  assert.match(contents(element('investigation-snapshots')), /Negative.*Positive.*Negative/s);
  element('save-investigation').listeners.click();
  element('scenario-name').value = expected.name;
  await element('save-form').listeners.submit({preventDefault() {}});
  assert.deepEqual(calls.filter(call => call.path === 'receipts').at(-1).body,
                   {name: expected.name, kind: expected.kind, request: expected.request});
}
async function reopenSaved(symbol) {
  await element('open-receipts').listeners.click();
  const row = element('receipts-list').children.find(item => contents(item).includes(cases[symbol].receipt.name));
  assert(row, `${symbol} receipt is in the same window's saved list`);
  await row.children[1].children[0].listeners.click();
  assertVisibleMarket(symbol);
  assert.equal(element('remove-call-update').checked, true);
  assert.match(element('investigation-status').textContent, /verified/i);
}
(async () => {
  await initializeBrowser();
  await settle();
  const oldScan = delayScan = holdNextESResponse();
  const esScan = element('scan-saved-flips').listeners.click();
  await settle();
  assert(oldScan.signal);
  await selectMarket('NQ');
  assert(oldScan.signal.aborted);
  await element('scan-saved-flips').listeners.click();
  await firstMarker().listeners.click();
  await removeAndSave('NQ');
  oldScan.release();
  await esScan;
  assertVisibleMarket('NQ');

  await selectMarket('ES');
  if (!firstMarker()) await element('scan-saved-flips').listeners.click();
  const oldReport = delayReport = holdNextESResponse();
  const esReport = firstMarker().listeners.click();
  await settle();
  assert(oldReport.signal);
  await selectMarket('NQ');
  assert(oldReport.signal.aborted);
  oldReport.release();
  await esReport;
  assertVisibleMarket('NQ');
  assert.equal(element('remove-call-update').checked, true);

  await selectMarket('ES');
  assert(element('flip-investigation').hidden, 'Aborted ES report must remain closed');
  await firstMarker().listeners.click();
  await removeAndSave('ES');
  const timelineCalls = calls.filter(call => call.path === 'investigation-timeline').length;
  await reopenSaved('NQ');
  await reopenSaved('ES');
  assert.equal(calls.filter(call => call.path === 'investigation-timeline').length, timelineCalls);
})().catch(error => {console.error(error); process.exitCode = 1;});
"""
