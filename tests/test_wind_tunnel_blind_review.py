"""Verify that a saved-session review reveals and reproduces only its committed outcome."""

import asyncio
from contextlib import AsyncExitStack, closing
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
from urllib.parse import urlsplit

from tests.test_wind_tunnel_saved_investigation import saved_flip_events, write_saved_flip_fixture


FLIP_SEQUENCE = 2
FLIP_CUTOFF = "2026-10-18T15:30:02Z"
HORIZON = "2026-10-18T16:00:02Z"
READ = "The modeled sign may reverse by the 30-minute mark."


def blind_review_events(*, symbol="ES", truncated=False):
    """The exact-horizon put flips the sign, and the later call would undo it."""
    tick, put, call, duplicate, *_ = saved_flip_events(symbol)
    spot = tick["price"]
    same_clock_tick = {**tick, "event_time": FLIP_CUTOFF, "price": spot + 0.5}
    middle_tick = {**tick, "event_time": "2026-10-18T15:40:00Z", "price": spot + 2}
    events = [tick, put, call, duplicate, same_clock_tick, middle_tick]
    if truncated:
        return events

    boundary_put = {**put, "event_time": HORIZON, "volume": 50, "sequence": 3}
    boundary_tick = {**tick, "event_time": HORIZON, "price": spot + 1}
    pre_flip_tick = {**tick, "event_time": "2026-10-18T15:30:01Z", "price": spot - 0.75}
    late_tick = {**tick, "event_time": "2026-10-18T15:50:00Z", "price": spot + 250}
    after_call = {**call, "event_time": "2026-10-18T16:00:03Z", "volume": 1_000, "sequence": 4}
    after_tick = {**tick, "event_time": "2026-10-18T16:00:04Z", "price": spot + 200}
    return [*events, boundary_put, dict(boundary_put), boundary_tick, pre_flip_tick, late_tick, after_call, after_tick]


async def write_blind_review_fixture(directory, *, symbol="ES", truncated=False):
    events = blind_review_events(symbol=symbol, truncated=truncated)
    return await write_saved_flip_fixture(directory, events, symbol=symbol)


async def write_dual_review_fixtures(directory):
    captures = {}
    for symbol in ("ES", "NQ"):
        source = directory / symbol
        source.mkdir()
        captures[symbol] = await write_blind_review_fixture(source, symbol=symbol)
    return captures


async def write_same_market_review_fixtures(directory, symbol):
    left, right = directory / "left", directory / "right"
    left.mkdir()
    right.mkdir()
    right_events = blind_review_events(symbol=symbol)
    for event in right_events:
        if event["event_time"] != HORIZON:
            continue
        if event["type"] == "underlying_tick":
            event["price"] += 8
        else:
            event["volume"] = 1
    return {
        "left": await write_blind_review_fixture(left, symbol=symbol),
        "right": await write_saved_flip_fixture(right, right_events, symbol=symbol),
    }


async def reproduce_with_captures(artifact, captures):
    repository = str(Path(__file__).resolve().parents[1])
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, (repository, os.environ.get("PYTHONPATH"))))}
    command = [sys.executable, "-m", "gex_terminal.wind_tunnel_cli", "reproduce", str(artifact)]
    for symbol, path in captures:
        command.extend((f"--saved-{symbol.lower()}-capture", str(path)))
    return await asyncio.to_thread(subprocess.run, command, cwd=artifact.parent, env=env,
                                   capture_output=True, text=True, timeout=30)


def rehash_review_receipt(receipt):
    from gex_terminal import wind_tunnel as wind
    from gex_terminal.wind_tunnel_server import digest

    result = receipt["result"]
    result.pop("result_sha256")
    result["result_sha256"] = wind._sha(result)
    receipt.pop("receipt_sha256")
    receipt["receipt_sha256"] = digest(receipt)


def legacy_es_receipt(receipt):
    from gex_terminal import wind_tunnel as wind

    legacy = deepcopy(receipt)
    result = legacy["result"]
    calculation = result["calculation"]
    # The blind-specific hashes on the first exported ES-only receipt.
    calculation["implementation"].update({
        "wind_tunnel_blind_replay.py": "848a3951d7213067038209d25e3b72976fe7c7a848bf60dcf3fc5580619278bc",
        "wind_tunnel_blind_review.py": "96f68c2b07d7acf24d5f165d77bb175a4dfca486084ad118dcc5812b20e132f2",
    })
    result["calculation_fingerprint"] = wind._sha(calculation)
    rehash_review_receipt(legacy)
    return legacy


class BlindReviewTests(unittest.IsolatedAsyncioTestCase):
    async def open_review(self, path, checksum, workspace, *, symbol="ES", sequence=FLIP_SEQUENCE):
        return await self.open_blind_window(workspace, {symbol: (path, checksum)}, sequence=sequence)

    async def open_blind_window(self, workspace, captures, *, sequence=None, symbol=None):
        from aiohttp import ClientSession
        from gex_terminal.wind_tunnel_blind_review import BlindReview
        from gex_terminal.wind_tunnel_saved_replay import SavedReplay
        from gex_terminal.wind_tunnel_server import start_server

        resources = await self.enterAsyncContext(AsyncExitStack())
        reviews = {}
        for key, (path, checksum) in captures.items():
            replay = SavedReplay(path, checksum, symbol=symbol or key)
            resources.callback(replay.close)
            reviews[key] = BlindReview(replay, sequence=sequence)
        if len(reviews) == 1:
            runner, launch = await start_server(workspace, port=0, blind_review=next(iter(reviews.values())))
        else:
            runner, launch = await start_server(workspace, port=0, blind_reviews=reviews)
        resources.push_async_callback(runner.cleanup)
        parsed = urlsplit(launch)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        client = await resources.enter_async_context(ClientSession(
            base_url=origin, headers={"X-GEX-Capability": parsed.fragment.removeprefix("cap=")},
        ))
        return client

    async def request(self, client, method, suffix="", *, body=None, expected=200, **params):
        async with client.request(method, f"/api/blind-review{suffix}", json=body, params=params) as response:
            self.assertEqual(response.status, expected, await response.text())
            return await response.json()

    async def assert_rejected(self, client, method, path, body=None, **params):
        async with client.request(method, path, json=body, params=params) as response:
            self.assertIn(response.status, range(400, 500), await response.text())
            self.assertNotIn('"price_path"', await response.text())

    def assert_blind(self, value, *, spot=5000.0):
        # These source and report fields would expose how much of the later
        # session is available, its future prices, or the settled model result.
        hidden = {"outcome", "price_path", "last_as_of", "event_count", "later_events_excluded"}

        def walk(item):
            if isinstance(item, dict):
                self.assertFalse(hidden.intersection(item), item)
                for value in item.values():
                    walk(value)
            elif isinstance(item, list):
                for value in item:
                    walk(value)

        walk(value)
        wire = json.dumps(value)
        future_timestamps = ("2026-10-18T15:40:00", "2026-10-18T16:00:03", "2026-10-18T16:00:04")
        future_prices = tuple(str(spot + change) for change in (0.5, 1, 2, 200))
        for future in (*future_timestamps, *future_prices):
            self.assertNotIn(future, wire)

    def assert_horizon(self, result, *, spot):
        outcome = result["outcome"]
        self.assertEqual(outcome["status"], "available")
        self.assertEqual(outcome["target_as_of"], HORIZON)
        self.assertEqual(outcome["as_of"], HORIZON)
        self.assertEqual(outcome["summary"]["net_sign"], -1)
        self.assertEqual(outcome["coverage"]["excluded_prices"], 2)
        points = outcome["price_path"]
        observed = [(point["sequence"], point["price"]) for point in points]
        self.assertEqual(observed, [(FLIP_SEQUENCE, spot), (4, spot + 0.5), (5, spot + 2), (8, spot + 1)])
        self.assertEqual(points[-1]["as_of"], HORIZON)

    async def test_es_blind_gate_exact_horizon_and_saved_reopen(self):
        await self.check_blind_gate_exact_horizon_and_saved_reopen(symbol="ES", spot=5000.0)

    async def test_nq_blind_gate_exact_horizon_and_saved_reopen(self):
        await self.check_blind_gate_exact_horizon_and_saved_reopen(symbol="NQ", spot=20000.0)

    async def check_blind_gate_exact_horizon_and_saved_reopen(self, *, symbol, spot):
        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        path, checksum = await write_blind_review_fixture(directory, symbol=symbol)
        workspace = directory / "research"
        client = await self.open_review(path, checksum, workspace, symbol=symbol, sequence=None)
        async with client.get("/") as response:
            self.assertEqual(response.status, 200)
            page = await response.text()
            self.assertIn("/static/blind.js", page)
            self.assertNotIn("/static/app.js", page)
        uncommitted = await self.request(client, "GET")
        self.assert_blind(uncommitted, spot=spot)
        self.assertIsNone(uncommitted.get("commit"))
        self.assertIsNone(uncommitted.get("result"))
        flip = uncommitted["flip"]
        self.assertEqual(flip["event"]["sequence"], FLIP_SEQUENCE)
        self.assertEqual(flip["after"]["as_of"], FLIP_CUTOFF)
        self.assertEqual(flip["source"]["capture_sha256"], checksum)
        self.assertEqual(flip["source"]["symbol"], symbol)
        self.assertEqual(flip["after"]["summary"]["net_sign"], 1)

        # Ordinary Wind Tunnel routes can show the final checkpoint, full
        # timeline, or a receipt. A blind launch isolates all of them.
        ordinary_routes = [("GET", "/static/app.js", None), ("GET", "/api/catalog", None),
                           ("GET", "/api/checkpoints?session=terminal-checkpoint", None),
                           ("POST", "/api/investigation-timeline", {"capture_sha256": checksum}),
                           ("POST", "/api/investigate-saved", {"capture_sha256": checksum, "sequence": FLIP_SEQUENCE}),
                           ("POST", "/api/compare-saved-sessions", {}), ("GET", "/api/receipts", None),
                           ("POST", "/api/reproduce", {})]
        for method, endpoint, body in ordinary_routes:
            with self.subTest(endpoint=endpoint):
                await self.assert_rejected(client, method, endpoint, body)

        await self.assert_rejected(client, "POST", "/api/blind-review/reveal", {})
        await self.assert_rejected(client, "POST", "/api/blind-review/save", {"name": "Premature save"})
        await self.assert_rejected(client, "POST", "/api/blind-review/commit", {"read": " \t "})
        self.assert_blind(await self.request(client, "GET"), spot=spot)

        committed = await self.request(client, "POST", "/commit", body={"read": READ})
        self.assertEqual(committed["commit"]["read"], READ)
        self.assert_blind(committed, spot=spot)
        self.assert_blind(await self.request(client, "GET"), spot=spot)
        await self.assert_rejected(client, "POST", "/api/blind-review/commit", {"read": "Another read"})
        await self.assert_rejected(client, "POST", "/api/blind-review/save", {"name": "Premature save"})

        revealed = await self.request(client, "POST", "/reveal", body={})
        result = revealed["result"]
        self.assertEqual(result["commit"], committed["commit"])
        self.assert_horizon(result, spot=spot)
        receipt_name = "Negative at the horizon"
        receipt = await self.request(client, "POST", "/save", body={"name": receipt_name})
        self.assertEqual(receipt["kind"], "blind-review")
        self.assertEqual(receipt["result"], result)
        self.assertNotIn(str(directory), json.dumps(receipt))
        receipt_id = receipt["receipt_sha256"]
        export_path = f"/receipts/{receipt_id}/export"
        self.assertEqual(await self.request(client, "GET", export_path), receipt)
        self.assertEqual(await self.request(client, "POST", "/save", body={"name": receipt_name}), receipt)
        saved = await self.request(client, "GET", "/receipts")
        self.assertEqual([entry["id"] for entry in saved["receipts"]], [receipt_id])

        # Reopening an already committed result is explicit. A fresh blind
        # launch cannot reveal it in the initial response or metadata list.
        reopened_window = await self.open_review(path, checksum, workspace, symbol=symbol)
        self.assert_blind(await self.request(reopened_window, "GET"), spot=spot)
        metadata = await self.request(reopened_window, "GET", "/receipts")
        self.assertNotIn(receipt_name, json.dumps(metadata))
        self.assertNotIn(READ, json.dumps(metadata))
        await self.assert_rejected(reopened_window, "GET", f"/api/blind-review{export_path}")
        reopened = await self.request(reopened_window, "POST", "/reopen", body={"id": receipt_id})
        self.assertEqual(reopened["receipt_sha256"], receipt_id)
        self.assertEqual(reopened["result"], result)
        self.assertEqual(await self.request(reopened_window, "GET", export_path), receipt)

        if symbol == "NQ":
            other_directory = directory / "es"
            other_directory.mkdir()
            es_path, es_checksum = await write_blind_review_fixture(other_directory)
            es_window = await self.open_review(es_path, es_checksum, workspace)
            self.assertEqual((await self.request(es_window, "GET"))["flip"]["source"]["capture_sha256"], es_checksum)
            other_metadata = await self.request(es_window, "GET", "/receipts")
            self.assertEqual(other_metadata["receipts"], [])
            await self.assert_rejected(es_window, "POST", "/api/blind-review/reopen", {"id": receipt_id})

        # Prove exported bytes are consumable without any state from the web process.
        artifact = directory / "review.json"
        artifact.write_text(json.dumps(receipt))
        reproduction = await reproduce_with_captures(artifact, [(symbol, path)])
        self.assertEqual(reproduction.returncode, 0, reproduction.stderr)
        reproduced = json.loads(reproduction.stdout)
        self.assertEqual((reproduced["status"], reproduced["result"]), ("verified", result))

        different_source = directory / "different"
        different_source.mkdir()
        wrong_path, _ = await write_blind_review_fixture(different_source, symbol=symbol, truncated=True)
        other_symbol = "NQ" if symbol == "ES" else "ES"
        for source_symbol, source_path in ((symbol, wrong_path), (other_symbol, path)):
            with self.subTest(source_symbol=source_symbol):
                wrong = await reproduce_with_captures(artifact, [(source_symbol, source_path)])
                self.assertNotEqual(wrong.returncode, 0)
                self.assertEqual(wrong.stdout, "")
                self.assertNotIn(str(directory), wrong.stderr)

        if symbol == "ES":
            archived = legacy_es_receipt(receipt)
            historical_result = archived["result"]
            artifact.write_text(json.dumps(archived))
            historical = await reproduce_with_captures(artifact, [(symbol, path)])
            self.assertEqual(historical.returncode, 0, historical.stderr)
            self.assertEqual(json.loads(historical.stdout)["result"], historical_result)

            historical_result["outcome"]["summary"]["net_sign"] = 1
            rehash_review_receipt(archived)
            artifact.write_text(json.dumps(archived))
            mismatched = await reproduce_with_captures(artifact, [(symbol, path)])
            self.assertNotEqual(mismatched.returncode, 0)
            comparison = json.loads(mismatched.stdout)
            self.assertEqual(comparison["status"], "mismatch")
            self.assertNotEqual(comparison["actual_result_sha256"], comparison["expected_result_sha256"])

    async def test_dual_window_keeps_reads_reveals_and_receipts_separate(self):
        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        workspace = directory / "research"
        captures = await write_dual_review_fixtures(directory)
        spots = {"ES": 5000.0, "NQ": 20000.0}
        client = await self.open_blind_window(workspace, captures)
        self.assertEqual(await self.request(client, "GET", "/sources"), {"symbols": ["ES", "NQ"]})
        await self.assert_rejected(client, "GET", "/api/blind-review")
        await self.assert_rejected(client, "GET", "/api/blind-review", symbol="YM")
        await self.assert_rejected(client, "POST", "/api/blind-review/commit", {"read": READ})

        receipts = {}
        for symbol, spot in spots.items():
            status = await self.request(client, "GET", symbol=symbol)
            self.assertEqual(status["stage"], "blind")
            self.assertIsNone(status["commit"])
            self.assert_blind(status, spot=spot)
            self.assertEqual(status["flip"]["source"]["symbol"], symbol)
            self.assertEqual(status["flip"]["source"]["capture_sha256"], captures[symbol][1])
            metadata = await self.request(client, "GET", "/receipts", symbol=symbol)
            self.assertEqual(metadata["receipts"], [])
            await self.assert_rejected(client, "POST", "/api/blind-review/reveal", {}, symbol=symbol)

            read = f"My {symbol} read before the reveal."
            committed = await self.request(client, "POST", "/commit", body={"read": read}, symbol=symbol)
            self.assertEqual(committed["commit"]["read"], read)
            self.assert_blind(await self.request(client, "GET", symbol=symbol), spot=spot)
            result = (await self.request(client, "POST", "/reveal", body={}, symbol=symbol))["result"]
            self.assertEqual(result["commit"], committed["commit"])
            self.assert_horizon(result, spot=spot)
            receipt = await self.request(client, "POST", "/save", body={"name": f"{symbol} read"}, symbol=symbol)
            self.assertEqual(receipt["result"], result)
            receipts[symbol] = receipt

        fresh = await self.open_blind_window(workspace, captures)
        for symbol, other_symbol in (("ES", "NQ"), ("NQ", "ES")):
            receipt = receipts[symbol]
            receipt_id = receipt["receipt_sha256"]
            export = f"/receipts/{receipt_id}/export"
            status = await self.request(client, "GET", symbol=symbol)
            self.assertEqual(status["result"], receipt["result"])
            self.assertEqual(status["receipt_sha256"], receipt_id)
            self.assertEqual(await self.request(client, "GET", export, symbol=symbol), receipt)
            await self.assert_rejected(client, "GET", f"/api/blind-review{export}", symbol=other_symbol)

            status = await self.request(fresh, "GET", symbol=symbol)
            self.assert_blind(status, spot=spots[symbol])
            metadata = (await self.request(fresh, "GET", "/receipts", symbol=symbol))["receipts"]
            self.assertEqual([entry["id"] for entry in metadata], [receipt_id])
            self.assertNotIn("name", metadata[0])
            await self.assert_rejected(fresh, "POST", "/api/blind-review/reopen",
                                       {"id": receipts[other_symbol]["receipt_sha256"]}, symbol=symbol)
            reopened = await self.request(fresh, "POST", "/reopen", body={"id": receipt_id}, symbol=symbol)
            self.assertEqual(reopened["result"], receipt["result"])
            self.assertEqual(await self.request(fresh, "GET", export, symbol=symbol), receipt)

        self.assertEqual((await self.request(fresh, "GET", symbol="ES"))["result"], receipts["ES"]["result"])

    async def test_comparison_receipt_keeps_both_committed_reviews_exact(self):
        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        workspace = directory / "research"
        captures = await write_dual_review_fixtures(directory)
        client = await self.open_blind_window(workspace, captures)
        spots = {"ES": 5000.0, "NQ": 20000.0}
        pair = "/comparison"
        compare_api = f"/api/blind-review{pair}"
        pair_name = {"name": "Both turned negative at 30 minutes"}
        self.assertIsNone((await self.request(client, "GET", pair))["receipt_sha256"])

        children = {}
        for symbol, spot in spots.items():
            self.assert_blind(await self.request(client, "GET", symbol=symbol), spot=spot)
            await self.assert_rejected(client, "POST", f"{compare_api}/save", pair_name)
            read = f"My {symbol} read before seeing the path."
            committed = await self.request(client, "POST", "/commit", body={"read": read}, symbol=symbol)
            self.assertEqual(committed["commit"]["read"], read)
            self.assert_blind(await self.request(client, "GET", pair), spot=spot)
            await self.assert_rejected(client, "POST", f"{compare_api}/save", pair_name)
            child = (await self.request(client, "POST", "/reveal", body={}, symbol=symbol))["result"]
            self.assertEqual(child["commit"], committed["commit"])
            self.assert_horizon(child, spot=spot)
            children[symbol.lower()] = child

        receipt = await self.request(client, "POST", f"{pair}/save", body=pair_name)
        self.assertEqual(receipt["kind"], "blind-comparison")
        for side, result in children.items():
            self.assertEqual(receipt["result"][side], result)
            self.assertEqual(receipt["request"][side], result["request"])
        self.assertNotIn(str(directory), json.dumps(receipt))
        receipt_id = receipt["receipt_sha256"]
        receipt_ref = {"id": receipt_id}
        export = f"{pair}/receipts/{receipt_id}/export"
        self.assertEqual((await self.request(client, "GET", pair))["receipt_sha256"], receipt_id)
        self.assertEqual(await self.request(client, "POST", f"{pair}/save", body=pair_name), receipt)
        listed = (await self.request(client, "GET", f"{pair}/receipts"))["receipts"]
        self.assertEqual([(entry["id"], entry["name"]) for entry in listed], [(receipt_id, pair_name["name"])])
        self.assertEqual(await self.request(client, "GET", export), receipt)
        for symbol in captures:
            self.assertEqual((await self.request(client, "GET", "/receipts", symbol=symbol))["receipts"], [])

        fresh = await self.open_blind_window(workspace, captures)
        for symbol, spot in spots.items():
            self.assert_blind(await self.request(fresh, "GET", symbol=symbol), spot=spot)
        self.assertIsNone((await self.request(fresh, "GET", pair))["receipt_sha256"])
        listed = (await self.request(fresh, "GET", f"{pair}/receipts"))["receipts"]
        self.assertEqual([entry["id"] for entry in listed], [receipt_id])
        self.assertNotIn("name", listed[0])
        await self.assert_rejected(fresh, "GET", f"/api/blind-review{export}")
        opened = await self.request(fresh, "POST", f"{pair}/reopen", body=receipt_ref)
        self.assertEqual(opened["result"], receipt["result"])
        self.assertEqual(opened["receipt_sha256"], receipt_id)
        self.assertEqual(opened["name"], pair_name["name"])
        self.assertEqual(await self.request(fresh, "GET", export), receipt)
        for symbol in captures:
            status = await self.request(fresh, "GET", symbol=symbol)
            self.assertEqual(status["result"], children[symbol.lower()])

        partial = await self.open_blind_window(workspace, captures)
        await self.request(partial, "GET", symbol="NQ")
        await self.request(partial, "POST", "/commit", body={"read": READ}, symbol="ES")
        await self.request(partial, "POST", "/reveal", body={}, symbol="ES")
        listed = (await self.request(partial, "GET", f"{pair}/receipts"))["receipts"]
        self.assertEqual([entry["id"] for entry in listed], [receipt_id])
        self.assertNotIn("name", listed[0])
        self.assert_blind(await self.request(partial, "GET", symbol="NQ"), spot=spots["NQ"])

        alternate_es = await self.request(partial, "POST", "/save", body={"name": "Alternate ES read"}, symbol="ES")
        await self.request(fresh, "POST", "/reopen", body={"id": alternate_es["receipt_sha256"]}, symbol="ES")
        self.assertIsNone((await self.request(fresh, "GET", pair))["receipt_sha256"])
        await self.assert_rejected(fresh, "GET", f"/api/blind-review{export}")
        self.assertEqual((await self.request(fresh, "GET", symbol="NQ"))["result"], children["nq"])
        await self.request(fresh, "POST", f"{pair}/reopen", body=receipt_ref)
        self.assertEqual(await self.request(fresh, "GET", export), receipt)

        single = await self.open_review(*captures["ES"], workspace=workspace)
        await self.assert_rejected(single, "GET", compare_api)
        await self.assert_rejected(single, "POST", f"{compare_api}/reopen", receipt_ref)

        different = directory / "different-NQ"
        different.mkdir()
        wrong_nq = await write_blind_review_fixture(different, symbol="NQ", truncated=True)
        wrong_window = await self.open_blind_window(workspace, {**captures, "NQ": wrong_nq})
        for symbol in captures:
            await self.request(wrong_window, "GET", symbol=symbol)
        self.assertEqual((await self.request(wrong_window, "GET", f"{pair}/receipts"))["receipts"], [])
        await self.assert_rejected(wrong_window, "POST", f"{compare_api}/reopen", receipt_ref)
        for symbol, spot in spots.items():
            self.assert_blind(await self.request(wrong_window, "GET", symbol=symbol), spot=spot)

        artifact = directory / "blind-comparison.json"
        artifact.write_text(json.dumps(receipt))
        paths = {symbol: path for symbol, (path, _) in captures.items()}
        reproduced = await reproduce_with_captures(artifact, paths.items())
        self.assertEqual(reproduced.returncode, 0, reproduced.stderr)
        result = json.loads(reproduced.stdout)
        self.assertEqual((result["status"], result["result"]), ("verified", receipt["result"]))
        for wrong_paths in ({"ES": paths["ES"]}, {**paths, "NQ": wrong_nq[0]}):
            rejected = await reproduce_with_captures(artifact, wrong_paths.items())
            self.assertNotEqual(rejected.returncode, 0)
            self.assertEqual(rejected.stdout, "")
            self.assertNotIn(str(directory), rejected.stderr)

    async def test_comparison_reproduces_with_pre_nq_es_receipt_and_preserves_original(self):
        from gex_terminal.wind_tunnel_server import ReceiptStore

        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        workspace = directory / "research"
        captures = await write_dual_review_fixtures(directory)
        source = await self.open_review(*captures["ES"], workspace=directory / "legacy-fixture")
        await self.request(source, "POST", "/commit", body={"read": "An archived ES read."})
        await self.request(source, "POST", "/reveal", body={})
        original = await self.request(source, "POST", "/save", body={"name": "Archived ES review"})
        legacy = legacy_es_receipt(original)
        legacy_id = legacy["receipt_sha256"]
        self.assertNotEqual(legacy_id, original["receipt_sha256"])
        with closing(ReceiptStore(workspace)) as store:
            store.save(legacy)

        client = await self.open_blind_window(workspace, captures)
        es_ref = {"id": legacy_id}
        reopened_es = await self.request(client, "POST", "/reopen", body=es_ref, symbol="ES")
        self.assertEqual(reopened_es["result"], legacy["result"])
        self.assert_blind(await self.request(client, "GET", symbol="NQ"), spot=20000.0)
        await self.request(client, "POST", "/commit", body={"read": "A current NQ read."}, symbol="NQ")
        nq = (await self.request(client, "POST", "/reveal", body={}, symbol="NQ"))["result"]
        pair = await self.request(client, "POST", "/comparison/save", body={"name": "Archived ES with current NQ"})
        self.assertEqual(pair["result"]["es"], original["result"])
        self.assertEqual(pair["result"]["nq"], nq)

        fresh = await self.open_blind_window(workspace, captures)
        await self.request(fresh, "POST", "/reopen", body=es_ref, symbol="ES")
        pair_id = pair["receipt_sha256"]
        restored = await self.request(fresh, "POST", "/comparison/reopen", body={"id": pair_id})
        self.assertEqual(restored["result"], pair["result"])
        self.assertEqual(restored["receipt_sha256"], pair_id)
        exported = await self.request(fresh, "GET", f"/comparison/receipts/{pair_id}/export")
        self.assertEqual(exported, pair)
        self.assertEqual(await self.request(fresh, "GET", f"/receipts/{legacy_id}/export", symbol="ES"), legacy)
        standalone = await self.request(fresh, "GET", "/receipts", symbol="ES")
        self.assertEqual([entry["id"] for entry in standalone["receipts"]], [legacy_id])

        artifact = directory / "legacy-es-current-nq.json"
        artifact.write_text(json.dumps(exported))
        reproduced = await reproduce_with_captures(artifact, [(symbol, path) for symbol, (path, _) in captures.items()])
        self.assertEqual(reproduced.returncode, 0, reproduced.stderr)
        result = json.loads(reproduced.stdout)
        self.assertEqual((result["status"], result["result"]), ("verified", pair["result"]))

    async def test_same_market_es_comparison_reopens_with_reversed_captures(self):
        await self.check_same_market_comparison(symbol="ES", spot=5000.0)

    async def test_same_market_nq_comparison_reopens_with_reversed_captures(self):
        await self.check_same_market_comparison(symbol="NQ", spot=20000.0)

    async def check_same_market_comparison(self, *, symbol, spot):
        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        workspace = directory / "research"
        captures = await write_same_market_review_fixtures(directory, symbol)
        client = await self.open_blind_window(workspace, captures, symbol=symbol)
        listed = await self.request(client, "GET", "/sessions")
        self.assertEqual(listed["sessions"], [{"id": slot, "symbol": symbol} for slot in captures])
        await self.assert_rejected(client, "GET", "/api/blind-review")
        await self.assert_rejected(client, "GET", "/api/blind-review", symbol=symbol)
        await self.assert_rejected(client, "POST", "/api/blind-review/commit", {"read": READ}, session="other")

        results = {}
        left_receipt_id = None
        name = {"name": f"Two distinct {symbol} reads"}
        for slot, (_, checksum) in captures.items():
            blind = await self.request(client, "GET", session=slot)
            self.assert_blind(blind, spot=spot)
            self.assertIsNone(blind["commit"])
            self.assertEqual(blind["flip"]["event"]["sequence"], FLIP_SEQUENCE)
            self.assertEqual(blind["flip"]["source"]["capture_sha256"], checksum)
            if slot == "right":
                self.assertEqual((await self.request(client, "GET", "/receipts", session=slot))["receipts"], [])
                await self.assert_rejected(client, "POST", "/api/blind-review/reopen", {"id": left_receipt_id},
                                           session=slot)
            await self.assert_rejected(client, "POST", "/api/blind-review/reveal", {}, session=slot)
            read = f"My {slot} {symbol} read before the reveal."
            commit = await self.request(client, "POST", "/commit", body={"read": read}, session=slot)
            self.assertEqual(commit["commit"]["read"], read)
            await self.assert_rejected(client, "POST", "/api/blind-review/comparison/save", name)
            result = (await self.request(client, "POST", "/reveal", body={}, session=slot))["result"]
            self.assertEqual(result["commit"], commit["commit"])
            results[slot] = result
            if slot == "left":
                standalone = await self.request(client, "POST", "/save", body={"name": "Left read"}, session=slot)
                left_receipt_id = standalone["receipt_sha256"]

        self.assert_horizon(results["left"], spot=spot)
        later = results["right"]["outcome"]
        self.assertEqual(later["target_as_of"], HORIZON)
        self.assertEqual(later["summary"]["net_sign"], 1)
        self.assertEqual([point["price"] for point in later["price_path"]], [spot, spot + 0.5, spot + 2, spot + 9])

        receipt = await self.request(client, "POST", "/comparison/save", body=name)
        self.assertEqual(receipt["kind"], "blind-session-comparison")
        for slot, result in results.items():
            self.assertEqual(receipt["result"][slot], result)
            self.assertEqual(receipt["request"][slot], {"symbol": symbol, "review": result["request"]})
        receipt_id = receipt["receipt_sha256"]
        export = f"/comparison/receipts/{receipt_id}/export"
        self.assertEqual(await self.request(client, "GET", export), receipt)
        self.assertEqual(await self.request(client, "POST", "/comparison/save", body=name), receipt)

        reversed_captures = {"left": captures["right"], "right": captures["left"]}
        fresh = await self.open_blind_window(workspace, reversed_captures, symbol=symbol)
        for slot in reversed_captures:
            self.assert_blind(await self.request(fresh, "GET", session=slot), spot=spot)
        metadata = (await self.request(fresh, "GET", "/comparison/receipts"))["receipts"]
        self.assertEqual([row["id"] for row in metadata], [receipt_id])
        self.assertNotIn("name", metadata[0])
        reopened = await self.request(fresh, "POST", "/comparison/reopen", body={"id": receipt_id})
        reversed_results = {"left": results["right"], "right": results["left"]}
        self.assertEqual(reopened["result"], receipt["result"])
        self.assertEqual(reopened["results_by_session"], reversed_results)
        for slot, result in reversed_results.items():
            self.assertEqual((await self.request(fresh, "GET", session=slot))["result"], result)
        self.assertEqual(await self.request(fresh, "GET", export), receipt)

        artifact = directory / "same-market-comparison.json"
        artifact.write_text(json.dumps(receipt))
        reversed_paths = [(symbol, path) for path, _ in reversed_captures.values()]
        verified = await reproduce_with_captures(artifact, reversed_paths)
        self.assertEqual(verified.returncode, 0, verified.stderr)
        reproduced = json.loads(verified.stdout)
        self.assertEqual((reproduced["status"], reproduced["result"]), ("verified", receipt["result"]))

        wrong = directory / "wrong"
        wrong.mkdir()
        wrong_capture = await write_blind_review_fixture(wrong, symbol=symbol, truncated=True)
        wrong_window = await self.open_blind_window(workspace, {**captures, "right": wrong_capture}, symbol=symbol)
        for slot in captures:
            await self.request(wrong_window, "GET", session=slot)
        self.assertEqual((await self.request(wrong_window, "GET", "/comparison/receipts"))["receipts"], [])
        await self.assert_rejected(wrong_window, "POST", "/api/blind-review/comparison/reopen", {"id": receipt_id})
        self.assert_blind(await self.request(wrong_window, "GET", session="left"), spot=spot)
        first_source = (symbol, captures["left"][0])
        for second_source in (first_source, (symbol, wrong_capture[0])):
            rejected = await reproduce_with_captures(artifact, [first_source, second_source])
            self.assertNotEqual(rejected.returncode, 0)
            self.assertEqual(rejected.stdout, "")
            self.assertNotIn(str(directory), rejected.stderr)

    async def test_cli_same_market_launch_uses_explicit_first_flip_only(self):
        from gex_terminal import wind_tunnel_cli as cli
        from gex_terminal.wind_tunnel_server import ReceiptError

        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        captures = await write_same_market_review_fixtures(directory, "NQ")
        command = ["serve", "--blind-review", "--no-browser", "--flip-sequence", "6"]
        for path, _ in captures.values():
            command.extend(("--saved-nq-capture", str(path)))

        async def inspect_launch(_workspace, _port, _no_browser, _source, *, blind_reviews):
            self.assertEqual(list(blind_reviews), ["left", "right"])
            for slot, sequence in (("left", 6), ("right", FLIP_SEQUENCE)):
                status = await blind_reviews[slot].status()
                self.assertEqual(status["flip"]["source"]["symbol"], "NQ")
                self.assertEqual(status["flip"]["source"]["capture_sha256"], captures[slot][1])
                self.assertEqual(status["flip"]["event"]["sequence"], sequence)

        parser = cli.parser()
        with patch.object(cli, "serve_window", AsyncMock(side_effect=inspect_launch)) as launch:
            self.assertEqual(await cli.run(parser.parse_args(command)), 0)
            left_path = captures["left"][0]
            copied_capture = directory / left_path.name
            copied_capture.write_bytes(left_path.read_bytes())
            with self.assertRaises(ReceiptError):
                await cli.run(parser.parse_args([*command[:-1], str(copied_capture)]))
            launch.assert_awaited_once()

    async def test_dual_window_can_load_nq_while_es_is_busy(self):
        from gex_terminal.wind_tunnel_blind_review import BlindReview

        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        captures = await write_dual_review_fixtures(directory)
        client = await self.open_blind_window(directory / "research", captures)
        es_started = asyncio.Event()
        es_release = asyncio.Event()
        original_status = BlindReview.status

        async def delay_es_status(review):
            if review.replay.symbol == "ES":
                es_started.set()
                await es_release.wait()
            return await original_status(review)

        with patch.object(BlindReview, "status", delay_es_status):
            es_status = asyncio.create_task(self.request(client, "GET", symbol="ES"))
            try:
                async with asyncio.timeout(5):
                    await es_started.wait()
                    nq = await self.request(client, "GET", symbol="NQ")
                self.assertEqual(nq["stage"], "blind")
                self.assertEqual(nq["flip"]["source"]["capture_sha256"], captures["NQ"][1])
            finally:
                es_release.set()
                es = await es_status
        self.assertEqual(es["flip"]["source"]["capture_sha256"], captures["ES"][1])

    async def test_cli_dual_launch_uses_explicit_es_flip_and_first_nq_flip(self):
        from gex_terminal import wind_tunnel_cli as cli
        from gex_terminal.wind_tunnel_server import ReceiptError

        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        captures = await write_dual_review_fixtures(directory)
        es_path, es_checksum = captures["ES"]
        nq_path, nq_checksum = captures["NQ"]
        command = ["serve", "--blind-review", "--no-browser", "--port", "0", "--flip-sequence", "6",
                   "--saved-es-capture", str(es_path), "--saved-nq-capture", str(nq_path)]

        async def inspect_launch(_workspace, port, no_browser, _source, *, blind_reviews):
            self.assertEqual(port, 0)
            self.assertTrue(no_browser)
            self.assertEqual(set(blind_reviews), {"ES", "NQ"})
            for symbol, sequence, checksum in (("ES", 6, es_checksum), ("NQ", FLIP_SEQUENCE, nq_checksum)):
                status = await blind_reviews[symbol].status()
                self.assertEqual(status["stage"], "blind")
                self.assertEqual(status["flip"]["source"]["capture_sha256"], checksum)
                self.assertEqual(status["flip"]["event"]["sequence"], sequence)

        parser = cli.parser()
        with patch.object(cli, "serve_window", AsyncMock(side_effect=inspect_launch)) as launch:
            self.assertEqual(await cli.run(parser.parse_args(command)), 0)
            duplicate_symbol = parser.parse_args([*command, "--saved-es-capture", str(es_path)])
            with self.assertRaises(ReceiptError):
                await cli.run(duplicate_symbol)
            launch.assert_awaited_once()

    async def test_short_capture_reveals_observed_price_path_without_horizon_sign(self):
        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        path, checksum = await write_blind_review_fixture(directory, truncated=True)
        client = await self.open_review(path, checksum, directory / "research")
        self.assert_blind(await self.request(client, "GET"))
        await self.request(client, "POST", "/commit", body={"read": READ})
        reveal = await self.request(client, "POST", "/reveal", body={})
        outcome = reveal["result"]["outcome"]
        self.assertEqual(outcome["target_as_of"], HORIZON)
        self.assertEqual(outcome["status"], "unavailable")
        self.assertIsNone(outcome["summary"])
        self.assertTrue(outcome["reason"])
        self.assertEqual(outcome["price_path"][-1]["as_of"], "2026-10-18T15:40:00Z")
        self.assertEqual(outcome["price_path"][-1]["price"], 5002.0)

    async def test_reprices_at_target_using_prior_observations_without_filling_a_price_tick(self):
        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        tick, put, call, *_ = saved_flip_events("ES")
        call = {**call, "expiry": "2026-10-18", "expiry_timestamp": "2026-10-18T16:00:00Z"}
        last_observed = "2026-10-18T15:59:59Z"
        events = [tick, put, call, {**tick, "event_time": last_observed},
                  {**tick, "event_time": "2026-10-18T16:00:03Z", "price": 5200.0}]
        path, checksum = await write_saved_flip_fixture(directory, events, symbol="ES")
        client = await self.open_review(path, checksum, directory / "research")
        before = await self.request(client, "GET")
        self.assertEqual(before["flip"]["after"]["summary"]["net_sign"], 1)
        await self.request(client, "POST", "/commit", body={"read": READ})
        outcome = (await self.request(client, "POST", "/reveal", body={}))["result"]["outcome"]
        self.assertEqual(outcome["status"], "available")
        self.assertEqual(outcome["target_as_of"], HORIZON)
        self.assertEqual(outcome["valuation_as_of"], HORIZON)
        self.assertEqual(outcome["as_of"], last_observed)
        self.assertEqual(outcome["summary"]["net_sign"], -1)
        self.assertEqual(outcome["price_path"][-1]["as_of"], last_observed)
        self.assertEqual(outcome["price_path"][-1]["price"], 5000.0)

    async def test_excludes_prices_from_the_replacement_future_and_marks_sign_unavailable(self):
        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        tick, put, call, *_ = saved_flip_events("ES")
        old_tick = {**tick, "contract_id": "ES-original"}
        new_tick = {**tick, "contract_id": "ES-replacement", "price": 5200.0}
        events = [old_tick,
                  {**put, "underlying_contract_id": "ES-original"},
                  {**call, "underlying_contract_id": "ES-original"},
                  {**old_tick, "event_time": "2026-10-18T15:40:00Z", "price": 5002.0},
                  {**new_tick, "event_time": "2026-10-18T15:45:00Z"},
                  {**new_tick, "event_time": HORIZON}]
        path, checksum = await write_saved_flip_fixture(directory, events, symbol="ES")
        client = await self.open_review(path, checksum, directory / "research")
        self.assert_blind(await self.request(client, "GET"))
        await self.request(client, "POST", "/commit", body={"read": READ})
        outcome = (await self.request(client, "POST", "/reveal", body={}))["result"]["outcome"]
        self.assertEqual(outcome["status"], "unavailable")
        self.assertIsNone(outcome["summary"])
        self.assertEqual(outcome["coverage"]["excluded_prices"], 2)
        self.assertFalse(outcome["coverage"]["same_underlying"])
        self.assertEqual([point["price"] for point in outcome["price_path"]], [5000.0, 5002.0])
