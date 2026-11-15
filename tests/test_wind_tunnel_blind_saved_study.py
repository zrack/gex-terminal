"""Verify that saved ES and NQ studies bind each call and outcome to an exact cohort."""

import asyncio
from contextlib import AsyncExitStack
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
from urllib.parse import urlsplit

from tests.test_wind_tunnel_blind_review import (
    HORIZON, blind_review_events, rehash_review_receipt, reproduce_with_captures, write_blind_review_fixture,
    write_same_market_review_fixtures,
)
from tests.test_wind_tunnel_blind_study import PREFIX, READY_CASES
from tests.test_wind_tunnel_saved_investigation import saved_flip_events, write_saved_flip_fixture


CALLS = {
    "es-1": {"prediction": "changes", "read": "I expect the first flip to reverse."},
    "es-2": {"prediction": "holds", "read": "I expect the second flip to hold."},
    "es-3": {"prediction": "holds"},
}
NQ_CALLS = {
    "nq-1": {"prediction": "holds", "read": "The first NQ sign may hold."},
    "nq-2": {"prediction": "changes", "read": "The second NQ sign may reverse."},
    "nq-3": {"prediction": "holds"},
}


def no_flip_events(symbol, price_increment=0):
    tick, put, call, *_ = saved_flip_events(symbol)
    last_tick = {**tick, "event_time": HORIZON, "price": tick["price"] + price_increment}
    return [tick, put, {**call, "volume": 1}, last_tick]


async def saved_cohort(directory, symbol="ES", *, extra_cases=0):
    pair = await write_same_market_review_fixtures(directory, symbol)
    short_directory = directory / "short"
    short_directory.mkdir()
    short = await write_blind_review_fixture(short_directory, symbol=symbol, truncated=True)

    no_flip_directory = directory / "no-flip"
    no_flip_directory.mkdir()
    no_flip = await write_saved_flip_fixture(no_flip_directory, no_flip_events(symbol), symbol=symbol)
    captures = {digest: path for path, digest in (pair["right"], pair["left"], short, no_flip)}
    for index in range(5, 5 + extra_cases):
        source = directory / f"case-{index}"
        source.mkdir()
        events = no_flip_events(symbol, price_increment=index)
        path, digest = await write_saved_flip_fixture(source, events, symbol=symbol)
        captures[digest] = path
    return captures


async def dual_cohorts(directory, *, extra_cases=0):
    cohorts = {}
    for symbol in ("ES", "NQ"):
        source = directory / symbol
        source.mkdir()
        cohorts[symbol] = await saved_cohort(source, symbol, extra_cases=extra_cases)
    return cohorts


async def comparison_cohort(directory, symbol, *, price_shift=0):
    """Build one holding and one changing case with slot-specific price evidence."""
    captures = {}
    for outcome in ("holds", "changes"):
        source = directory / outcome
        source.mkdir(parents=True)
        events = blind_review_events(symbol=symbol)
        for event in events:
            if event["event_time"] != HORIZON:
                continue
            if event["type"] == "underlying_tick":
                event["price"] += price_shift + (8 if outcome == "holds" else 0)
            elif outcome == "holds":
                event["volume"] = 1
        path, checksum = await write_saved_flip_fixture(source, events, symbol=symbol)
        captures[checksum] = path
    return captures


def study_capture_flags(cohorts):
    return [item for slot, captures in cohorts.items() for path in captures.values()
            for item in (f"--study-{slot}-capture", str(path))]


async def reproduce_comparison(artifact, cohorts):
    repository = str(Path(__file__).resolve().parents[1])
    python_path = os.pathsep.join(filter(None, (repository, os.environ.get("PYTHONPATH"))))
    command = [sys.executable, "-m", "gex_terminal.wind_tunnel_cli", "reproduce", str(artifact),
               *study_capture_flags(cohorts)]
    return await asyncio.to_thread(subprocess.run, command, cwd=artifact.parent,
                                   env={**os.environ, "PYTHONPATH": python_path},
                                   capture_output=True, text=True, timeout=30)


class SavedBlindStudyTests(unittest.IsolatedAsyncioTestCase):
    async def open_study(self, workspace, study):
        return await self.open_studies(workspace, blind_study=study)

    async def open_studies(self, workspace, **options):
        from aiohttp import ClientSession
        from gex_terminal.wind_tunnel_server import start_server

        resources = await self.enterAsyncContext(AsyncExitStack())
        runner, launch = await start_server(workspace, port=0, **options)
        resources.push_async_callback(runner.cleanup)
        url = urlsplit(launch)
        return await resources.enter_async_context(ClientSession(
            base_url=f"{url.scheme}://{url.netloc}", headers={"X-GEX-Capability": url.fragment.removeprefix("cap=")},
        ))

    async def request(self, client, method, suffix="", *, body=None, **params):
        async with client.request(method, PREFIX + suffix, json=body, params=params) as response:
            self.assertEqual(response.status, 200, await response.text())
            return await response.json()

    async def assert_rejected(self, client, method, suffix, *, body=None, **params):
        async with client.request(method, PREFIX + suffix, json=body, params=params) as response:
            payload = await response.text()
            self.assertIn(response.status, range(400, 500), payload)
            self.assertNotIn('"outcome"', payload)
            self.assertNotIn('"price_path"', payload)

    def assert_blind(self, status):
        self.assertEqual(status["stage"], "blind")
        self.assertIsNone(status.get("result"))
        hidden = {"outcome", "price_path", "actual", "correct", "last_as_of"}
        for key in hidden:
            self.assertNotIn(f'"{key}"', json.dumps(status))

    async def test_saved_es_cohort_gate_scores_and_reopens_exactly_in_original_order(self):
        from gex_terminal.wind_tunnel_blind_saved_study import SavedBlindStudy

        await self.check_saved_cohort(SavedBlindStudy, symbol="ES", spot=5000.0)

    async def test_saved_nq_cohort_gate_scores_and_reopens_exactly_in_original_order(self):
        from gex_terminal.wind_tunnel_blind_saved_study import SavedNQBlindStudy

        await self.check_saved_cohort(SavedNQBlindStudy, symbol="NQ", spot=20000.0)

    async def check_saved_cohort(self, study_type, *, symbol, spot):
        from gex_terminal.wind_tunnel_blind_saved_study import capture_market
        from gex_terminal.wind_tunnel_blind_study import BlindStudy

        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        workspace = directory / "research"
        cases = [f"{symbol.lower()}-{index}" for index in range(1, 5)]
        calls = dict(zip(cases[:3], CALLS.values()))
        captures = await saved_cohort(directory, symbol)
        client = await self.open_study(workspace, study_type(captures))
        initial = await self.request(client, "GET")
        self.assert_blind(initial)
        protocol = initial["protocol"]
        self.assertEqual((protocol["source"], protocol["symbol"], protocol["horizon_minutes"], protocol["baseline"]),
                         ("saved_capture", symbol, 30, "always_holds"))
        self.assertEqual([case["capture_sha256"] for case in initial["cases"]], list(captures))
        self.assertEqual([(case["id"], case["status"]) for case in initial["cases"]], [
            (cases[0], "ready"), (cases[1], "ready"), (cases[2], "ready"), (cases[3], "no_flip"),
        ])
        for case in initial["cases"][:3]:
            self.assertEqual(case["flip"]["source"]["symbol"], symbol)
            self.assertEqual(case["flip"]["source"]["capture_sha256"], case["capture_sha256"])
        self.assertIsNone(initial["cases"][3].get("flip"))
        self.assertNotIn(str(directory), json.dumps(initial))
        await self.assert_rejected(client, "POST", "/save", body={"name": "Too early"})

        missing = {key: call for key, call in calls.items() if key != cases[2]}
        extra = {**calls, cases[3]: {"prediction": "holds"}}
        for invalid in (missing, extra):
            await self.assert_rejected(client, "POST", "/submit", body={"calls": invalid})
            self.assertEqual(await self.request(client, "GET"), initial)

        revealed = await self.request(client, "POST", "/submit", body={"calls": calls})
        result = revealed["result"]
        self.assertEqual(await self.request(client, "POST", "/submit", body={"calls": calls}), revealed)
        changed = {**calls, cases[0]: {**calls[cases[0]], "prediction": "holds"}}
        await self.assert_rejected(client, "POST", "/submit", body={"calls": changed})
        counts = {"total": 4, "scored": 2, "correct": 0, "baseline_correct": 1, "unscored": 1, "no_flip": 1}
        self.assertEqual({key: result["summary"][key] for key in counts}, counts)
        held, flipped, short, no_flip = result["cases"]
        outcomes = ((held, "holds", 1, spot + 9), (flipped, "changes", -1, spot + 1))
        for case, actual, later_sign, final_price in outcomes:
            self.assertEqual(case["status"], "scored")
            self.assertEqual(case["call"], calls[case["id"]])
            self.assertIs(case["correct"], False)
            self.assertEqual(case["actual"], actual)
            self.assertEqual(case["outcome"]["target_as_of"], HORIZON)
            self.assertEqual(case["outcome"]["summary"]["net_sign"], later_sign)
            self.assertEqual(case["outcome"]["price_path"][-1]["as_of"], HORIZON)
            self.assertEqual(case["outcome"]["price_path"][-1]["price"], final_price)
        self.assertEqual(short["status"], "unscored")
        self.assertEqual(short["call"]["prediction"], "holds")
        self.assertIsNone(short["outcome"]["summary"])
        self.assertEqual(short["outcome"]["price_path"][-1]["as_of"], "2026-10-18T15:40:00Z")
        self.assertEqual(no_flip["status"], "no_flip")
        self.assertIsNone(no_flip.get("call"))
        self.assertIsNone(no_flip.get("outcome"))

        name = {"name": "Both saved forecasts missed"}
        receipt = await self.request(client, "POST", "/save", body=name)
        self.assertEqual(receipt["kind"], "blind-saved-study")
        self.assertEqual(receipt["result"], result)
        self.assertEqual(receipt["request"], result["request"])
        self.assertEqual(capture_market(receipt["request"]), symbol)
        self.assertEqual([case["capture_sha256"] for case in receipt["request"]["cases"]], list(captures))
        self.assertEqual([case["sequence"] for case in receipt["request"]["cases"]], [2, 2, 2, None])
        self.assertNotIn(str(directory), json.dumps(receipt))
        self.assertEqual(await self.request(client, "POST", "/save", body=name), receipt)
        receipt_id = receipt["receipt_sha256"]
        ref = {"id": receipt_id}
        export_path = f"/receipts/{receipt_id}/export"

        reverse = dict(reversed(tuple(captures.items())))
        fresh = await self.open_study(workspace, study_type(reverse))
        before = await self.request(fresh, "GET")
        self.assert_blind(before)
        self.assertEqual([case["capture_sha256"] for case in before["cases"]], list(reverse))
        listed = (await self.request(fresh, "GET", "/receipts"))["receipts"]
        self.assertEqual([entry["id"] for entry in listed], [receipt_id])
        self.assertNotIn("name", listed[0])
        await self.assert_rejected(fresh, "GET", export_path)
        reopened = await self.request(fresh, "POST", "/reopen", body=ref)
        self.assertEqual(reopened["result"], result)
        self.assertEqual(reopened["receipt_sha256"], receipt_id)
        self.assertEqual(reopened["name"], name["name"])
        self.assertEqual(await self.request(fresh, "GET", export_path), receipt)

        without_no_flip = dict(tuple(captures.items())[:3])
        replacement_directory = directory / "different-no-flip"
        replacement_directory.mkdir()
        replacement, wrong_digest = await write_saved_flip_fixture(
            replacement_directory, no_flip_events(symbol, price_increment=1), symbol=symbol,
        )
        wrong_cohort = {**without_no_flip, wrong_digest: replacement}
        other = await self.open_study(workspace, study_type(wrong_cohort))
        before = await self.request(other, "GET")
        self.assert_blind(before)
        self.assertEqual(before["cases"][-1]["status"], "no_flip")
        self.assertEqual((await self.request(other, "GET", "/receipts"))["receipts"], [])
        await self.assert_rejected(other, "POST", "/reopen", body=ref)
        self.assertEqual(await self.request(other, "GET"), before)

        synthetic = await self.open_study(workspace, BlindStudy())
        self.assertEqual((await self.request(synthetic, "GET", "/receipts"))["receipts"], [])
        await self.assert_rejected(synthetic, "POST", "/reopen", body=ref)
        await self.request(synthetic, "POST", "/submit", body={"calls": READY_CASES})
        synthetic_receipt = await self.request(synthetic, "POST", "/save", body={"name": "Synthetic-only study"})
        saved_list = (await self.request(fresh, "GET", "/receipts"))["receipts"]
        self.assertEqual([entry["id"] for entry in saved_list], [receipt_id])
        await self.assert_rejected(fresh, "POST", "/reopen", body={"id": synthetic_receipt["receipt_sha256"]})

        if symbol == "NQ":
            from gex_terminal.wind_tunnel_blind_saved_study import SavedBlindStudy

            es_directory = directory / "separate-ES"
            es_directory.mkdir()
            es_path, es_digest = await write_blind_review_fixture(es_directory)
            es_study = await self.open_study(workspace, SavedBlindStudy({es_digest: es_path}))
            self.assert_blind(await self.request(es_study, "GET"))
            self.assertEqual((await self.request(es_study, "GET", "/receipts"))["receipts"], [])
            await self.assert_rejected(es_study, "POST", "/reopen", body=ref)

        artifact = directory / "saved-study.json"
        artifact.write_text(json.dumps(receipt))
        verified = await reproduce_with_captures(artifact, [(symbol, path) for path in reverse.values()])
        self.assertEqual(verified.returncode, 0, verified.stderr)
        output = json.loads(verified.stdout)
        self.assertEqual((output["status"], output["result"]), ("verified", result))
        other_symbol = "ES" if symbol == "NQ" else "NQ"
        for market, wrong_inputs in ((symbol, without_no_flip), (symbol, wrong_cohort), (other_symbol, reverse)):
            rejected = await reproduce_with_captures(artifact, [(market, path) for path in wrong_inputs.values()])
            self.assertNotEqual(rejected.returncode, 0)
            self.assertEqual(rejected.stdout, "")
            self.assertNotIn(str(directory), rejected.stderr)

    async def test_dual_study_switches_markets_with_independent_calls_and_receipts(self):
        from gex_terminal.wind_tunnel_blind_saved_study import SavedBlindStudy, SavedNQBlindStudy

        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        workspace = directory / "research"
        cohorts = await dual_cohorts(directory)
        client = await self.open_studies(workspace, blind_studies={
            "ES": SavedBlindStudy(cohorts["ES"]), "NQ": SavedNQBlindStudy(cohorts["NQ"]),
        })
        self.assertEqual(await self.request(client, "GET", "/sources"), {"symbols": ["ES", "NQ"]})
        await self.assert_rejected(client, "GET", "")
        await self.assert_rejected(client, "GET", "", symbol="YM")
        await self.assert_rejected(client, "GET", "/receipts")
        await self.assert_rejected(client, "POST", "/submit", body={"calls": CALLS})

        calls_by_market = {"ES": CALLS, "NQ": NQ_CALLS}
        receipts = {}
        for symbol, calls in calls_by_market.items():
            blind = await self.request(client, "GET", symbol=symbol)
            self.assert_blind(blind)
            self.assertEqual(blind["protocol"]["symbol"], symbol)
            self.assertEqual([case["capture_sha256"] for case in blind["cases"]], list(cohorts[symbol]))
            partial = dict(tuple(calls.items())[:2])
            await self.assert_rejected(client, "POST", "/submit", body={"calls": partial}, symbol=symbol)
            await self.assert_rejected(client, "POST", "/save", body={"name": "Too early"}, symbol=symbol)
            result = (await self.request(client, "POST", "/submit", body={"calls": calls}, symbol=symbol))["result"]
            self.assertEqual(result["request"]["calls"], calls)
            self.assertEqual(result["summary"]["scored"], 2)
            self.assertEqual(result["summary"]["correct"], 0 if symbol == "ES" else 2)
            self.assertEqual(result["summary"]["baseline_correct"], 1)
            name = {"name": f"{symbol} separate study"}
            await self.assert_rejected(client, "POST", "/save", body=name)
            receipt = await self.request(client, "POST", "/save", body=name, symbol=symbol)
            self.assertEqual(receipt["kind"], "blind-saved-study")
            self.assertEqual(receipt["result"], result)
            self.assertEqual([case["capture_sha256"] for case in receipt["request"]["cases"]], list(cohorts[symbol]))
            receipts[symbol] = receipt

        self.assertNotEqual(receipts["ES"]["receipt_sha256"], receipts["NQ"]["receipt_sha256"])
        fresh = await self.open_studies(workspace, blind_studies={
            "ES": SavedBlindStudy(dict(reversed(tuple(cohorts["ES"].items())))),
            "NQ": SavedNQBlindStudy(dict(reversed(tuple(cohorts["NQ"].items())))),
        })
        for symbol, other in (("ES", "NQ"), ("NQ", "ES")):
            receipt = receipts[symbol]
            receipt_id = receipt["receipt_sha256"]
            export = f"/receipts/{receipt_id}/export"
            self.assertEqual((await self.request(client, "GET", symbol=symbol))["result"], receipt["result"])
            self.assertEqual(await self.request(client, "GET", export, symbol=symbol), receipt)
            await self.assert_rejected(client, "GET", export)
            await self.assert_rejected(client, "GET", export, symbol=other)

            self.assert_blind(await self.request(fresh, "GET", symbol=symbol))
            visible = (await self.request(fresh, "GET", "/receipts", symbol=symbol))["receipts"]
            self.assertEqual([entry["id"] for entry in visible], [receipt_id])
            self.assertNotIn("name", visible[0])
            body = {"id": receipt_id}
            await self.assert_rejected(fresh, "POST", "/reopen", body=body)
            await self.assert_rejected(fresh, "POST", "/reopen", body=body, symbol=other)
            reopened = await self.request(fresh, "POST", "/reopen", body=body, symbol=symbol)
            self.assertEqual(reopened["result"], receipt["result"])
            self.assertEqual(reopened["receipt_sha256"], receipt_id)
            self.assertEqual(await self.request(fresh, "GET", export, symbol=symbol), receipt)

        self.assertEqual((await self.request(fresh, "GET", symbol="ES"))["result"], receipts["ES"]["result"])
        artifact = directory / "es-study.json"
        artifact.write_text(json.dumps(receipts["ES"]))
        mixed = [("ES", path) for path in cohorts["ES"].values()]
        mixed.append(("NQ", next(iter(cohorts["NQ"].values()))))
        rejected = await reproduce_with_captures(artifact, mixed)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertEqual(rejected.stdout, "")
        self.assertNotIn(str(directory), rejected.stderr)

    async def test_paired_study_receipt_restores_both_cohorts_without_replacing_standalone_receipts(self):
        from gex_terminal.wind_tunnel_blind_saved_study import SavedBlindStudy, SavedNQBlindStudy

        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        workspace = directory / "research"
        cohorts = await dual_cohorts(directory)
        pair_route = "/comparison"
        name = {"name": "ES misses versus NQ hits"}
        study_types = {"ES": SavedBlindStudy, "NQ": SavedNQBlindStudy}
        studies = {symbol: study_types[symbol](captures) for symbol, captures in cohorts.items()}
        client = await self.open_studies(workspace, blind_studies=studies)
        self.assertIsNone((await self.request(client, "GET", pair_route))["receipt_sha256"])

        children = {}
        singles = {}
        for symbol, calls in (("ES", CALLS), ("NQ", NQ_CALLS)):
            before = await self.request(client, "GET", symbol=symbol)
            self.assert_blind(before)
            self.assertEqual([case["capture_sha256"] for case in before["cases"]], list(cohorts[symbol]))
            self.assertIsNone((await self.request(client, "GET", pair_route))["receipt_sha256"])
            await self.assert_rejected(client, "POST", f"{pair_route}/save", body=name)
            partial = dict(tuple(calls.items())[:2])
            await self.assert_rejected(client, "POST", "/submit", body={"calls": partial}, symbol=symbol)
            await self.assert_rejected(client, "POST", f"{pair_route}/save", body=name)
            self.assertEqual(await self.request(client, "GET", symbol=symbol), before)
            result = (await self.request(client, "POST", "/submit", body={"calls": calls}, symbol=symbol))["result"]
            self.assertEqual(result["request"]["calls"], calls)
            self.assertEqual(result["summary"]["correct"], 0 if symbol == "ES" else 2)
            children[symbol] = result
            single_name = {"name": f"Standalone {symbol} study"}
            singles[symbol] = await self.request(client, "POST", "/save", body=single_name, symbol=symbol)

        receipt = await self.request(client, "POST", f"{pair_route}/save", body=name)
        self.assertEqual(receipt["kind"], "blind-study-comparison")
        self.assertNotIn(str(directory), json.dumps(receipt))
        for symbol, result in children.items():
            side = symbol.lower()
            self.assertEqual(receipt["result"][side], result)
            self.assertEqual(receipt["request"][side], result["request"])
            self.assertEqual([case["capture_sha256"] for case in receipt["request"][side]["cases"]], list(cohorts[symbol]))
        receipt_id = receipt["receipt_sha256"]
        reference = {"id": receipt_id}
        export_path = f"{pair_route}/receipts/{receipt_id}/export"
        self.assertEqual((await self.request(client, "GET", pair_route))["receipt_sha256"], receipt_id)
        self.assertEqual(await self.request(client, "POST", f"{pair_route}/save", body=name), receipt)
        listing = (await self.request(client, "GET", f"{pair_route}/receipts"))["receipts"]
        self.assertEqual([(row["id"], row["name"]) for row in listing], [(receipt_id, name["name"])])
        self.assertEqual(await self.request(client, "GET", export_path), receipt)
        for symbol, single in singles.items():
            single_id = single["receipt_sha256"]
            entries = (await self.request(client, "GET", "/receipts", symbol=symbol))["receipts"]
            self.assertEqual([entry["id"] for entry in entries], [single_id])
            self.assertEqual(await self.request(client, "GET", f"/receipts/{single_id}/export", symbol=symbol), single)

        reversed_cohorts = {symbol: dict(reversed(tuple(captures.items()))) for symbol, captures in cohorts.items()}
        reversed_studies = {symbol: study_types[symbol](captures) for symbol, captures in reversed_cohorts.items()}
        fresh = await self.open_studies(workspace, blind_studies=reversed_studies)
        for symbol in cohorts:
            self.assert_blind(await self.request(fresh, "GET", symbol=symbol))
        listing = (await self.request(fresh, "GET", f"{pair_route}/receipts"))["receipts"]
        self.assertEqual([row["id"] for row in listing], [receipt_id])
        self.assertNotIn("name", listing[0])
        es_id = singles["ES"]["receipt_sha256"]
        reopened_es = await self.request(fresh, "POST", "/reopen", body={"id": es_id}, symbol="ES")
        self.assertEqual(reopened_es["result"], children["ES"])
        self.assert_blind(await self.request(fresh, "GET", symbol="NQ"))
        listing = (await self.request(fresh, "GET", f"{pair_route}/receipts"))["receipts"]
        self.assertEqual([row["id"] for row in listing], [receipt_id])
        self.assertNotIn("name", listing[0])
        await self.assert_rejected(fresh, "GET", export_path)
        reopened = await self.request(fresh, "POST", f"{pair_route}/reopen", body=reference)
        self.assertEqual(reopened["result"], receipt["result"])
        self.assertEqual(reopened["receipt_sha256"], receipt_id)
        self.assertEqual(reopened["name"], name["name"])
        self.assertEqual(await self.request(fresh, "GET", export_path), receipt)
        self.assertEqual(await self.request(fresh, "GET", f"/receipts/{es_id}/export", symbol="ES"), singles["ES"])
        for symbol, result in children.items():
            status = await self.request(fresh, "GET", symbol=symbol)
            self.assertEqual(status["result"], result)
            self.assertEqual(status["receipt_sha256"], es_id if symbol == "ES" else None)
        nq_id = singles["NQ"]["receipt_sha256"]
        await self.request(fresh, "POST", "/reopen", body={"id": nq_id}, symbol="NQ")
        self.assertEqual(await self.request(fresh, "GET", f"/receipts/{nq_id}/export", symbol="NQ"), singles["NQ"])
        self.assertEqual(await self.request(fresh, "GET", export_path), receipt)

        replacement_directory = directory / "different-nq"
        replacement_directory.mkdir()
        path, digest = await write_saved_flip_fixture(replacement_directory, no_flip_events("NQ", 1), symbol="NQ")
        other_nq = dict(tuple(cohorts["NQ"].items())[:-1])
        other_nq[digest] = path
        mismatched = await self.open_studies(workspace, blind_studies={
            "ES": SavedBlindStudy(cohorts["ES"]), "NQ": SavedNQBlindStudy(other_nq),
        })
        before = {symbol: await self.request(mismatched, "GET", symbol=symbol) for symbol in cohorts}
        self.assertEqual(before["NQ"]["cases"][-1]["status"], "no_flip")
        self.assertEqual((await self.request(mismatched, "GET", f"{pair_route}/receipts"))["receipts"], [])
        await self.assert_rejected(mismatched, "POST", f"{pair_route}/reopen", body=reference)
        for symbol, status in before.items():
            self.assert_blind(status)
            self.assertEqual(await self.request(mismatched, "GET", symbol=symbol), status)

        artifact = directory / "paired-study.json"
        artifact.write_text(json.dumps(receipt))
        flags = [(symbol, path) for symbol in ("NQ", "ES") for path in reversed_cohorts[symbol].values()]
        reproduced = await reproduce_with_captures(artifact, flags)
        self.assertEqual(reproduced.returncode, 0, reproduced.stderr)
        verified = json.loads(reproduced.stdout)
        self.assertEqual((verified["status"], verified["result"]), ("verified", receipt["result"]))
        es_flags = [("ES", path) for path in cohorts["ES"].values()]
        mismatched_flags = es_flags + [("NQ", path) for path in other_nq.values()]
        for wrong_flags in (es_flags, mismatched_flags):
            rejected = await reproduce_with_captures(artifact, wrong_flags)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertEqual(rejected.stdout, "")
            self.assertNotIn(str(directory), rejected.stderr)

    async def test_two_es_studies_keep_independent_scores_and_reproduce_as_one_receipt(self):
        await self.check_explicit_study_pair("ES", "ES")

    async def test_two_nq_studies_keep_independent_scores_and_reproduce_as_one_receipt(self):
        await self.check_explicit_study_pair("NQ", "NQ")

    async def test_explicit_pair_can_put_nq_first_and_es_second(self):
        await self.check_explicit_study_pair("NQ", "ES")

    async def check_explicit_study_pair(self, first_symbol, second_symbol):
        from gex_terminal.wind_tunnel_blind_saved_study import SavedBlindStudy, SavedNQBlindStudy

        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        workspace = directory / "research"
        symbols = {"a": first_symbol, "b": second_symbol}
        study_types = {"ES": SavedBlindStudy, "NQ": SavedNQBlindStudy}
        cohorts = {
            "a": await comparison_cohort(directory / "first", first_symbol),
            "b": await comparison_cohort(directory / "second", second_symbol, price_shift=4),
        }
        self.assertTrue(cohorts["a"].keys().isdisjoint(cohorts["b"]))

        def make_pair(selections):
            return {slot: study_types[symbol](selections[slot]) for slot, symbol in symbols.items()}

        pair = make_pair(cohorts)
        client = await self.open_studies(workspace, blind_study_pair=pair)
        sources = await self.request(client, "GET", "/sources")
        self.assertCountEqual(sources["symbols"], set(symbols.values()))
        self.assertEqual(sources["slots"], [{"id": slot, "symbol": symbol} for slot, symbol in symbols.items()])
        await self.assert_rejected(client, "GET", "")
        await self.assert_rejected(client, "GET", "", symbol=first_symbol)
        await self.assert_rejected(client, "GET", "", slot="c")
        await self.assert_rejected(client, "GET", "", slot="a", symbol=first_symbol)
        await self.assert_rejected(client, "GET", "/comparison", slot="a")

        first_opened = asyncio.Event()
        resume_first = asyncio.Event()
        first_status = pair["a"].status

        async def open_first():
            first_opened.set()
            await resume_first.wait()
            return await first_status()

        # Studies with the same symbol still need separate locks and state.
        with patch.object(pair["a"], "status", side_effect=open_first):
            first = asyncio.create_task(self.request(client, "GET", slot="a"))
            try:
                async with asyncio.timeout(5):
                    await first_opened.wait()
                    second = await self.request(client, "GET", slot="b")
            finally:
                resume_first.set()
                opened_first = await first
        before = {"a": opened_first, "b": second}

        name = {"name": "One side missed both forecasts"}
        self.assertIsNone((await self.request(client, "GET", "/comparison"))["receipt_sha256"])
        children = {}
        for slot, symbol in symbols.items():
            blind = before[slot]
            self.assert_blind(blind)
            self.assertEqual(blind["protocol"]["symbol"], symbol)
            self.assertEqual([case["capture_sha256"] for case in blind["cases"]], list(cohorts[slot]))
            first_id, second_id = (case["id"] for case in blind["cases"])
            self.assertEqual((first_id, second_id), (f"{symbol.lower()}-1", f"{symbol.lower()}-2"))
            calls = {
                first_id: {"prediction": "changes" if slot == "a" else "holds", "read": f"Study {slot.upper()} note"},
                second_id: {"prediction": "holds"},
            }
            await self.assert_rejected(client, "POST", "/submit", body={"calls": {first_id: calls[first_id]}}, slot=slot)
            self.assertEqual(await self.request(client, "GET", slot=slot), blind)
            await self.assert_rejected(client, "POST", "/comparison/save", body=name)
            children[slot] = (await self.request(client, "POST", "/submit", body={"calls": calls}, slot=slot))["result"]
            if slot == "a":
                self.assertEqual(await self.request(client, "GET", slot="b"), before["b"])
                self.assert_blind(await self.request(client, "GET", slot="b"))
            result = children[slot]
            self.assertEqual(result["request"]["calls"], calls)
            self.assertEqual([case["actual"] for case in result["cases"]], ["holds", "changes"])
            self.assertEqual(result["summary"]["correct"], 0 if slot == "a" else 1)
            self.assertEqual(result["summary"]["scored"], 2)
            self.assertEqual(result["summary"]["baseline_correct"], 1)
            miss = result["cases"][1]
            spot = 5000 if symbol == "ES" else 20000
            self.assertIs(miss["correct"], False)
            self.assertEqual(miss["flip"]["source"]["capture_sha256"], list(cohorts[slot])[1])
            self.assertEqual(miss["flip"]["contributions"][0]["contract_id"], f"call-{spot}")
            self.assertEqual(miss["flip"]["counterfactual"]["summary"]["net_sign"], -1)
            self.assertEqual(miss["outcome"]["price_path"][-1]["price"], spot + (1 if slot == "a" else 5))

        single = await self.request(client, "POST", "/save", body={"name": "Study A separately"}, slot="a")
        single_id = single["receipt_sha256"]
        self.assertEqual((await self.request(client, "GET", "/receipts", slot="b"))["receipts"], [])
        await self.assert_rejected(client, "POST", "/reopen", body={"id": single_id}, slot="b")

        receipt = await self.request(client, "POST", "/comparison/save", body=name)
        self.assertEqual(receipt["kind"], "blind-saved-study-comparison")
        self.assertNotIn(str(directory), json.dumps(receipt))
        for slot, result in children.items():
            self.assertEqual(receipt["result"][slot], result)
            self.assertEqual(receipt["request"][slot], result["request"])
        self.assertEqual(await self.request(client, "POST", "/comparison/save", body=name), receipt)
        receipt_id = receipt["receipt_sha256"]
        reference = {"id": receipt_id}
        export = f"/comparison/receipts/{receipt_id}/export"
        self.assertEqual(await self.request(client, "GET", "/comparison"), {"receipt_sha256": receipt_id})
        self.assertEqual(await self.request(client, "GET", export), receipt)

        reversed_cohorts = {slot: dict(reversed(tuple(captures.items()))) for slot, captures in cohorts.items()}
        fresh = await self.open_studies(workspace, blind_study_pair=make_pair(reversed_cohorts))
        for slot, captures in reversed_cohorts.items():
            initial = await self.request(fresh, "GET", slot=slot)
            self.assert_blind(initial)
            self.assertEqual([case["capture_sha256"] for case in initial["cases"]], list(captures))
        listing = (await self.request(fresh, "GET", "/comparison/receipts"))["receipts"]
        self.assertEqual([entry["id"] for entry in listing], [receipt_id])
        self.assertNotIn("name", listing[0])
        await self.assert_rejected(fresh, "GET", export)
        await self.request(fresh, "POST", "/reopen", body={"id": single_id}, slot="a")
        self.assert_blind(await self.request(fresh, "GET", slot="b"))
        listing = (await self.request(fresh, "GET", "/comparison/receipts"))["receipts"]
        self.assertNotIn("name", listing[0])

        reopened = await self.request(fresh, "POST", "/comparison/reopen", body=reference)
        self.assertEqual(reopened, {"result": receipt["result"], "receipt_sha256": receipt_id, **name})
        self.assertEqual(await self.request(fresh, "GET", export), receipt)
        for slot, result in children.items():
            status = await self.request(fresh, "GET", slot=slot)
            self.assertEqual(status["result"], result)
            self.assertEqual([case["capture_sha256"] for case in status["cases"]], list(cohorts[slot]))
            self.assertEqual(status["receipt_sha256"], single_id if slot == "a" else None)

        artifact = directory / "saved-study-comparison.json"
        artifact.write_text(json.dumps(receipt))
        reproduced = await reproduce_comparison(artifact, reversed_cohorts)
        self.assertEqual(reproduced.returncode, 0, reproduced.stderr)
        verified = json.loads(reproduced.stdout)
        self.assertEqual((verified["status"], verified["result"]), ("verified", receipt["result"]))
        if first_symbol == second_symbol:
            swapped = {"a": cohorts["b"], "b": cohorts["a"]}
            other = await self.open_studies(workspace, blind_study_pair=make_pair(swapped))
            statuses = {slot: await self.request(other, "GET", slot=slot) for slot in symbols}
            self.assertEqual((await self.request(other, "GET", "/comparison/receipts"))["receipts"], [])
            await self.assert_rejected(other, "POST", "/comparison/reopen", body=reference)
            for slot, status in statuses.items():
                self.assert_blind(status)
                self.assertEqual(await self.request(other, "GET", slot=slot), status)
            rejected = await reproduce_comparison(artifact, swapped)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertEqual(rejected.stdout, "")
            self.assertNotIn(str(directory), rejected.stderr)

    async def test_dual_study_loads_nq_while_es_waits(self):
        from gex_terminal.wind_tunnel_blind_saved_study import SavedBlindStudy, SavedNQBlindStudy

        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        cohorts = await dual_cohorts(directory)
        es_study = SavedBlindStudy(cohorts["ES"])
        client = await self.open_studies(directory / "research", blind_studies={
            "ES": es_study, "NQ": SavedNQBlindStudy(cohorts["NQ"]),
        })
        es_started = asyncio.Event()
        es_released = asyncio.Event()
        es_status = es_study.status

        async def delayed_es_status():
            es_started.set()
            await es_released.wait()
            return await es_status()

        with patch.object(es_study, "status", side_effect=delayed_es_status):
            pending_es = asyncio.create_task(self.request(client, "GET", symbol="ES"))
            try:
                async with asyncio.timeout(5):
                    await es_started.wait()
                    nq_status = await self.request(client, "GET", symbol="NQ")
                self.assert_blind(nq_status)
                self.assertEqual(nq_status["protocol"]["symbol"], "NQ")
            finally:
                es_released.set()
                released_status = await pending_es
        self.assert_blind(released_status)
        self.assertEqual(released_status["protocol"]["symbol"], "ES")

    async def test_cli_starts_saved_es_studies_and_rejects_identical_copies(self):
        from gex_terminal.wind_tunnel_blind_saved_study import SavedBlindStudy

        await self.check_cli_launch(SavedBlindStudy, symbol="ES")

    async def test_cli_starts_up_to_eight_saved_nq_cases_and_rejects_identical_copies(self):
        from gex_terminal.wind_tunnel_blind_saved_study import SavedNQBlindStudy

        await self.check_cli_launch(SavedNQBlindStudy, symbol="NQ")

    async def check_cli_launch(self, study_type, *, symbol):
        from gex_terminal import wind_tunnel_cli as cli
        from gex_terminal.wind_tunnel_server import ReceiptError

        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        accepted_counts = (1, 4, 8) if symbol == "NQ" else (1, 4)
        captures = await saved_cohort(directory, symbol, extra_cases=5 if symbol == "NQ" else 0)
        paths = list(captures.values())
        command = ["serve", "--blind-study", "--no-browser", "--port", "0"]
        flag = f"--saved-{symbol.lower()}-capture"
        parser = cli.parser()
        seen = []

        async def inspect_launch(_workspace, port, no_browser, _source, *, blind_study):
            self.assertEqual(port, 0)
            self.assertTrue(no_browser)
            self.assertIsInstance(blind_study, study_type)
            status = await blind_study.status()
            self.assert_blind(status)
            self.assertEqual(status["protocol"]["symbol"], symbol)
            seen.append([case["capture_sha256"] for case in status["cases"]])

        with patch.object(cli, "serve_window", AsyncMock(side_effect=inspect_launch)) as launch:
            for size in accepted_counts:
                flags = [arg for path in paths[:size] for arg in (flag, str(path))]
                self.assertEqual(await cli.run(parser.parse_args([*command, *flags])), 0)
            alias = directory / "copy-of-first.gex-session.jsonl"
            alias.write_bytes(paths[0].read_bytes())
            duplicate = [flag, str(paths[0]), flag, str(alias)]
            with self.assertRaises(ReceiptError):
                await cli.run(parser.parse_args([*command, *duplicate]))
            if symbol == "NQ":
                excess = [arg for path in paths for arg in (flag, str(path))]
                with self.assertRaises(ReceiptError):
                    await cli.run(parser.parse_args([*command, *excess]))
            self.assertEqual(launch.await_count, len(accepted_counts))
        self.assertEqual(seen, [list(captures)[:size] for size in accepted_counts])

    async def test_cli_launches_eight_cases_per_market_in_one_window(self):
        from gex_terminal import wind_tunnel_cli as cli
        from gex_terminal.wind_tunnel_blind_saved_study import SavedBlindStudy, SavedNQBlindStudy
        from gex_terminal.wind_tunnel_server import ReceiptError

        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        cohorts = await dual_cohorts(directory, extra_cases=5)
        command = ["serve", "--blind-study", "--no-browser", "--port", "0"]
        parser = cli.parser()

        def flags(es_count, nq_count):
            return [item for symbol, count in (("NQ", nq_count), ("ES", es_count))
                    for path in list(cohorts[symbol].values())[:count]
                    for item in (f"--saved-{symbol.lower()}-capture", str(path))]

        async def inspect_launch(_workspace, port, no_browser, _source, *, blind_studies):
            self.assertEqual(port, 0)
            self.assertTrue(no_browser)
            self.assertEqual(set(blind_studies), {"ES", "NQ"})
            for symbol, study_type in (("ES", SavedBlindStudy), ("NQ", SavedNQBlindStudy)):
                self.assertIsInstance(blind_studies[symbol], study_type)
                status = await blind_studies[symbol].status()
                self.assert_blind(status)
                self.assertEqual(status["protocol"]["symbol"], symbol)
                self.assertEqual([case["capture_sha256"] for case in status["cases"]], list(cohorts[symbol])[:8])

        with patch.object(cli, "serve_window", AsyncMock(side_effect=inspect_launch)) as launch:
            self.assertEqual(await cli.run(parser.parse_args([*command, *flags(8, 8)])), 0)
            for es_count, nq_count in ((9, 1), (1, 9)):
                with self.assertRaises(ReceiptError):
                    await cli.run(parser.parse_args([*command, *flags(es_count, nq_count)]))
            es_path = next(iter(cohorts["ES"].values()))
            cross_copy = directory / "es-copy-tagged-as-nq.gex-session.jsonl"
            cross_copy.write_bytes(es_path.read_bytes())
            with self.assertRaises(ReceiptError):
                await cli.run(parser.parse_args([*command, *flags(1, 0), "--saved-nq-capture", str(cross_copy)]))
            launch.assert_awaited_once()

    async def test_cli_explicit_pair_validates_slots_and_infers_markets_from_captures(self):
        from gex_terminal import wind_tunnel_cli as cli
        from gex_terminal.wind_tunnel_blind_saved_study import SavedBlindStudy
        from gex_terminal.wind_tunnel_server import ReceiptError

        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        a = await comparison_cohort(directory / "first", "ES")
        b = await comparison_cohort(directory / "second", "ES", price_shift=4)
        mixed = await comparison_cohort(directory / "other-market", "NQ")
        es_path = next(iter(a.values()))
        duplicate = directory / "copy.gex-session.jsonl"
        duplicate.write_bytes(es_path.read_bytes())
        reformatted = directory / "reformatted.gex-session.jsonl"
        reformatted.write_text("".join(json.dumps(json.loads(line)) + "\n" for line in es_path.read_text().splitlines()))
        misleading_name = directory / "nq.gex-session.jsonl"
        checksum, path = next(iter(b.items()))
        misleading_name.write_bytes(path.read_bytes())
        b[checksum] = misleading_name
        command = ["serve", "--blind-study", "--no-browser", "--port", "0"]
        parser = cli.parser()

        async def inspect_launch(_workspace, port, no_browser, _source, *, blind_study_pair):
            self.assertEqual(port, 0)
            self.assertTrue(no_browser)
            self.assertEqual(list(blind_study_pair), ["a", "b"])
            for slot, captures in (("a", a), ("b", b)):
                study = blind_study_pair[slot]
                self.assertIsInstance(study, SavedBlindStudy)
                self.assertEqual(study.symbol, "ES")
                self.assertEqual(study.capture_paths, captures)

        with patch.object(cli, "serve_window", AsyncMock(side_effect=inspect_launch)) as launch, \
                patch.object(cli, "serve", AsyncMock()) as ordinary_launch, \
                patch.object(cli, "serve_blind_review", AsyncMock()) as review_launch:
            flags = study_capture_flags({"b": b, "a": a})
            self.assertEqual(await cli.run(parser.parse_args([*command, *flags])), 0)
            for invalid in (
                study_capture_flags({"a": a}),
                study_capture_flags({"b": b}),
                study_capture_flags({"a": a, "b": {**b, **mixed}}),
                study_capture_flags({"a": a, "b": {"duplicate": duplicate}}),
                study_capture_flags({"a": a, "b": {"reformatted": reformatted}}),
                [*flags, "--saved-es-capture", str(es_path)],
            ):
                with self.subTest(flags=invalid), self.assertRaises(ReceiptError):
                    await cli.run(parser.parse_args([*command, *invalid]))
            for mode in ([], ["--blind-review"]):
                with self.assertRaises(ReceiptError):
                    await cli.run(parser.parse_args(["serve", *mode, *flags]))
            launch.assert_awaited_once()
            ordinary_launch.assert_not_awaited()
            review_launch.assert_not_awaited()

        with self.assertRaises(ValueError):
            await self.open_studies(directory / "research", blind_study_pair={
                "a": SavedBlindStudy(a), "b": SavedBlindStudy({**b, **a}),
            })

    async def test_pre_saved_study_synthetic_receipt_still_reproduces_exactly(self):
        from gex_terminal import wind_tunnel as wind
        from gex_terminal.wind_tunnel_blind_study import BlindStudy
        from gex_terminal.wind_tunnel_server import assemble_receipt

        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        study = BlindStudy()
        self.addCleanup(study.close)
        result = await study.submit(READY_CASES)
        receipt = assemble_receipt("Previous synthetic study", "blind-study", result)
        calculation = result["calculation"]
        # Fingerprint of the original synthetic-only implementation.
        calculation["implementation"]["wind_tunnel_blind_study.py"] = (
            "69fa343e78c818517ac46529c4ee22cc963ebdaeae510d74f2bcc61acb6f3386"
        )
        result["calculation_fingerprint"] = wind._sha(calculation)
        rehash_review_receipt(receipt)
        artifact = directory / "previous-synthetic-study.json"
        artifact.write_text(json.dumps(receipt))
        verified = await reproduce_with_captures(artifact, [])
        self.assertEqual(verified.returncode, 0, verified.stderr)
        output = json.loads(verified.stdout)
        self.assertEqual((output["status"], output["result"]), ("verified", result))
