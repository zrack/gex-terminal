"""Exercise the blind call gate, scoring and portable synthetic study receipts."""

from contextlib import AsyncExitStack
from datetime import datetime, timedelta
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
from urllib.parse import urlsplit

from tests.test_wind_tunnel_blind_review import rehash_review_receipt, reproduce_with_captures


PREFIX = "/api/blind-study"
READY_CASES = {
    "es-1": {"prediction": "holds", "read": "The sign may hold through the horizon."},
    "es-2": {"prediction": "changes", "read": "A reversal is possible within 30 minutes."},
    "es-3": {"prediction": "holds"},
}
MISSED_CASES = {
    "es-1": {"prediction": "changes", "read": "The first sign may reverse."},
    "es-2": {"prediction": "holds", "read": "The second sign may hold."},
    "es-3": {"prediction": "holds"},
}


class BlindStudyTests(unittest.IsolatedAsyncioTestCase):
    async def open_study(self, workspace, *, study=None):
        from aiohttp import ClientSession
        from gex_terminal.wind_tunnel_blind_study import BlindStudy
        from gex_terminal.wind_tunnel_server import start_server

        resources = await self.enterAsyncContext(AsyncExitStack())
        runner, launch = await start_server(workspace, port=0, blind_study=BlindStudy() if study is None else study)
        resources.push_async_callback(runner.cleanup)
        url = urlsplit(launch)
        return await resources.enter_async_context(ClientSession(
            base_url=f"{url.scheme}://{url.netloc}", headers={"X-GEX-Capability": url.fragment.removeprefix("cap=")},
        ))

    async def request(self, client, method, suffix="", *, body=None):
        async with client.request(method, PREFIX + suffix, json=body) as response:
            self.assertEqual(response.status, 200, await response.text())
            return await response.json()

    async def assert_rejected(self, client, method, path, body=None):
        async with client.request(method, path, json=body) as response:
            message = await response.text()
            self.assertIn(response.status, range(400, 500), message)
            self.assertNotIn('"price_path"', message)
            self.assertNotIn('"outcome"', message)

    def assert_hidden(self, value):
        hidden = {"result", "outcome", "price_path", "actual", "correct", "baseline_correct", "last_as_of"}
        if isinstance(value, dict):
            for key, item in value.items():
                if key in hidden:
                    self.assertIsNone(item, f"Unsubmitted study exposed {key}")
                self.assert_hidden(item)
        elif isinstance(value, list):
            for item in value:
                self.assert_hidden(item)

    async def test_complete_call_set_reveals_at_once_and_locks_its_predictions(self):
        from gex_terminal import wind_tunnel_blind_study as study_core

        world = Path(self.enterContext(tempfile.TemporaryDirectory()))
        study = study_core.BlindStudy()
        reveal_outcome = study_core.reveal_outcome

        async def observe_commit(*args):
            locked = await study.status()
            self.assertEqual(locked["stage"], "committed")
            self.assertEqual(locked["calls"], READY_CASES)
            self.assertTrue(locked["submitted_at"])
            self.assert_hidden(locked)
            return await reveal_outcome(*args)

        horizon = self.enterContext(patch.object(study_core, "reveal_outcome", side_effect=observe_commit))
        client = await self.open_study(world / "research", study=study)
        initial = await self.request(client, "GET")
        self.assertEqual(initial["stage"], "blind")
        self.assert_hidden(initial)
        protocol = initial["protocol"]
        self.assertEqual((protocol["symbol"], protocol["source"], protocol["horizon_minutes"], protocol["baseline"]),
                         ("ES", "synthetic", 30, "always_holds"))
        self.assertEqual([(case["id"], case["status"]) for case in initial["cases"]], [
            ("es-1", "ready"), ("es-2", "ready"), ("es-3", "ready"), ("es-4", "no_flip"),
        ])
        for case in initial["cases"][:3]:
            self.assertEqual(case["flip"]["source"]["symbol"], "ES")
        self.assertIsNone(initial["cases"][3].get("flip"))

        async with client.get("/api/blind-study", headers={"X-GEX-Capability": "invalid"}) as response:
            self.assertEqual(response.status, 403)
        await self.assert_rejected(client, "GET", "/api/catalog")
        await self.assert_rejected(client, "GET", "/api/blind-review")
        await self.assert_rejected(client, "GET", "/api/receipts")
        await self.assert_rejected(client, "POST", PREFIX + "/save", {"name": "Premature study"})

        missing_short_case = {case: call for case, call in READY_CASES.items() if case != "es-3"}
        extra_no_flip = {**READY_CASES, "es-4": {"prediction": "holds"}}
        invalid_prediction = {**READY_CASES, "es-1": {"prediction": "guess"}}
        invalid_note = {**READY_CASES, "es-1": {"prediction": "holds", "read": 24}}
        for calls in ({}, missing_short_case, extra_no_flip, invalid_prediction, invalid_note):
            await self.assert_rejected(client, "POST", PREFIX + "/submit", {"calls": calls})
            self.assertEqual(await self.request(client, "GET"), initial)
        horizon.assert_not_awaited()

        revealed = await self.request(client, "POST", "/submit", body={"calls": READY_CASES})
        result = revealed["result"]
        self.assertEqual(result["protocol"], initial["protocol"])
        self.assertEqual(result["summary"]["scored"], 2)
        self.assertEqual(result["summary"]["correct"], 2)
        self.assertEqual(result["summary"]["baseline_correct"], 1)
        self.assertEqual([case["correct"] for case in result["cases"] if case["status"] == "scored"], [True, True])
        self.assertEqual((await self.request(client, "GET"))["result"], result)
        self.assertEqual(await self.request(client, "POST", "/submit", body={"calls": READY_CASES}), revealed)
        await self.assert_rejected(client, "POST", PREFIX + "/submit", {"calls": MISSED_CASES})
        self.assertEqual((await self.request(client, "GET"))["result"], result)
        self.assertEqual(horizon.await_count, 3)

    async def test_outcome_failure_keeps_the_complete_submission_locked_for_retry(self):
        from gex_terminal import wind_tunnel_blind_study as study_core

        study = study_core.BlindStudy()
        self.addCleanup(study.close)
        with patch.object(study_core, "reveal_outcome", side_effect=ValueError("Interrupted")) as interrupted:
            with self.assertRaises(study_core.BlindStudyError):
                await study.submit(READY_CASES)
            locked = await study.status()
            self.assertEqual(locked["stage"], "committed")
            self.assertEqual(locked["calls"], READY_CASES)
            self.assert_hidden(locked)
            with self.assertRaises(study_core.BlindStudyError):
                await study.submit(MISSED_CASES)
            interrupted.assert_awaited_once()

        retried = await study.submit(READY_CASES)
        self.assertEqual(retried["request"]["submitted_at"], locked["submitted_at"])
        self.assertEqual(retried["request"]["calls"], locked["calls"])
        self.assertEqual(retried["summary"]["correct"], 2)

    async def test_receipt_reopens_exact_miss_evidence_and_reproduces_offline(self):
        world = Path(self.enterContext(tempfile.TemporaryDirectory()))
        workspace = world / "research"
        client = await self.open_study(workspace)
        submission = await self.request(client, "POST", "/submit", body={"calls": MISSED_CASES})
        result = submission["result"]
        expected = {"total": 4, "scored": 2, "correct": 0, "baseline_correct": 1, "unscored": 1, "no_flip": 1}
        self.assertEqual({field: result["summary"][field] for field in expected}, expected)
        cases = {case["id"]: case for case in result["cases"]}
        for identity, actual in (("es-1", "holds"), ("es-2", "changes")):
            case = cases[identity]
            self.assertEqual(case["status"], "scored")
            self.assertEqual(case["call"], MISSED_CASES[identity])
            self.assertEqual(case["actual"], actual)
            self.assertIs(case["correct"], False)
            outcome = case["outcome"]
            self.assertEqual(outcome["status"], "available")
            after = case["flip"]["after"]
            self.assertEqual(after["summary"]["net_sign"] == outcome["summary"]["net_sign"], actual == "holds")
            horizon = datetime.fromisoformat(outcome["target_as_of"])
            self.assertEqual(horizon - datetime.fromisoformat(after["as_of"]), timedelta(minutes=30))
            path = outcome["price_path"]
            self.assertGreater(len(path), 1)
            self.assertEqual(path[0]["as_of"], after["as_of"])
            self.assertTrue(all(datetime.fromisoformat(point["as_of"]) <= horizon for point in path))

        short = cases["es-3"]
        self.assertEqual(short["status"], "unscored")
        self.assertEqual(short["call"]["prediction"], "holds")
        self.assertIsNone(short.get("correct"))
        self.assertIsNone(short.get("actual"))
        self.assertEqual(short["outcome"]["status"], "unavailable")
        self.assertIsNone(short["outcome"]["summary"])
        self.assertEqual(cases["es-4"]["status"], "no_flip")
        for field in ("flip", "call", "outcome", "correct", "actual"):
            self.assertIsNone(cases["es-4"].get(field))

        name = "Both forecasts missed"
        receipt = await self.request(client, "POST", "/save", body={"name": name})
        identity = receipt["receipt_sha256"]
        export = f"/receipts/{identity}/export"
        self.assertEqual(receipt["kind"], "blind-study")
        self.assertEqual(receipt["result"], result)
        self.assertEqual(receipt["request"], result["request"])
        self.assertNotIn(str(world), json.dumps(receipt))
        self.assertEqual(await self.request(client, "POST", "/save", body={"name": name}), receipt)
        self.assertEqual(await self.request(client, "GET", export), receipt)

        fresh = await self.open_study(workspace)
        self.assert_hidden(await self.request(fresh, "GET"))
        metadata = (await self.request(fresh, "GET", "/receipts"))["receipts"]
        self.assertEqual([entry["id"] for entry in metadata], [identity])
        self.assert_hidden(metadata)
        self.assertNotIn("name", metadata[0])
        self.assertNotIn(name, json.dumps(metadata))
        await self.assert_rejected(fresh, "GET", PREFIX + export)
        reopened = await self.request(fresh, "POST", "/reopen", body={"id": identity})
        self.assertEqual(reopened["result"], result)
        self.assertEqual(reopened["receipt_sha256"], identity)
        self.assertEqual(reopened["name"], name)
        self.assertEqual(await self.request(fresh, "GET", export), receipt)

        artifact = world / "study.json"
        artifact.write_text(json.dumps(receipt))
        reproduced = await reproduce_with_captures(artifact, [])
        self.assertEqual(reproduced.returncode, 0, reproduced.stderr)
        verified = json.loads(reproduced.stdout)
        self.assertEqual((verified["status"], verified["result"]), ("verified", result))

        # A matching checksum alone cannot make edited study scores reproducible.
        receipt["result"]["summary"]["correct"] = 2
        rehash_review_receipt(receipt)
        artifact.write_text(json.dumps(receipt))
        edited = await reproduce_with_captures(artifact, [])
        self.assertNotEqual(edited.returncode, 0)
        mismatch = json.loads(edited.stdout)
        self.assertEqual(mismatch["status"], "mismatch")
        self.assertNotEqual(mismatch["actual_result_sha256"], mismatch["expected_result_sha256"])

    async def test_cli_launch_uses_built_in_study_and_rejects_capture_inputs(self):
        from gex_terminal import wind_tunnel_cli as cli
        from gex_terminal.wind_tunnel_blind_study import BlindStudy
        from gex_terminal.wind_tunnel_server import ReceiptError

        workspace = Path(self.enterContext(tempfile.TemporaryDirectory())) / "study"
        command = ["serve", "--blind-study", "--workspace", str(workspace), "--port", "0", "--no-browser"]
        parser = cli.parser()
        with patch.object(cli, "serve_window", new_callable=AsyncMock) as launch:
            self.assertEqual(await cli.run(parser.parse_args(command)), 0)
            self.assertEqual(launch.await_args.args[:3], (workspace, 0, True))
            self.assertIsInstance(launch.await_args.kwargs["blind_study"], BlindStudy)
            for extra in (["--checkpoint", "unneeded.json"], ["--flip-sequence", "2"]):
                with self.assertRaises(ReceiptError):
                    await cli.run(parser.parse_args([*command, *extra]))
            launch.assert_awaited_once()
