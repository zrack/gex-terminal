"""Real loopback coverage for guided local capture intake and portable research."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import urlsplit

from aiohttp import ClientSession

from gex_terminal import wind_tunnel_server as server
from gex_terminal.session_capture import CapturedSessionWriter
from gex_terminal.wind_tunnel import TerminalCheckpointCore


class SessionIntakeHTTPTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.runner, launch = await server.start_server(self.root / "research", port=0)
        url = urlsplit(launch)
        self.origin = f"{url.scheme}://{url.netloc}"
        self.headers = {"Origin": self.origin, "X-GEX-Capability": url.fragment.removeprefix("cap=")}
        self.client = ClientSession(headers=self.headers)
        self.capture = self.root / "fixture.gex-session.jsonl"
        writer = CapturedSessionWriter(self.capture, source={
            "synthetic": True, "provider": "replay", "mode": "replay", "symbol": "ES",
            "private": "/private/account-123", "label": "private-label",
        }, model_inputs={"symbol": "ES", "contract_multiplier": 50,
                         "days_to_expiry": 1, "risk_free_rate": .045}, label="private-label")
        await writer.start()
        for message in (
            {"type": "underlying_tick", "symbol": "ES", "price": 5000.0,
             "event_time": "2026-10-18T15:30:00Z"},
            {"type": "options_volume_tick", "strike": 5000.0, "option_type": "C",
             "volume": 100, "iv": .2, "event_time": "2026-10-18T15:30:01Z",
             "secret_extension": "/private/account-123"},
            {"type": "underlying_tick", "symbol": "ES", "price": 5010.0,
             "event_time": "2026-10-18T15:31:00Z"},
        ):
            await writer.append(message)
        await writer.finalize()
        self.payload = self.capture.read_bytes()

    async def asyncTearDown(self):
        await self.client.close()
        await self.runner.cleanup()
        self.temp.cleanup()

    async def inspect(self):
        async with self.client.post(self.origin + "/api/intake", data=self.payload,
                                    headers={"Content-Type": "application/octet-stream"}) as response:
            self.assertEqual(response.status, 200, await response.text())
            return await response.json()

    async def freeze(self, intake, sequence=1):
        async with self.client.post(self.origin + "/api/intake/checkpoint", json={
            "intake_id": intake["intake_id"], "sequence": sequence,
        }) as response:
            self.assertEqual(response.status, 200, await response.text())
            return (await response.json())["terminal_checkpoint"]

    async def test_real_prefix_save_export_and_fresh_server_reproduce_without_capture(self):
        intake = await self.inspect()
        self.assertEqual(intake["event_count"], 3)
        self.assertNotIn("/private/account-123", json.dumps(intake))
        self.assertNotIn("private-label", json.dumps(intake))
        opaque = await self.freeze(intake)
        artifact = json.loads(opaque)
        self.assertEqual(artifact["parameters"]["spot"], 5000.0)
        self.assertEqual(artifact["source"]["as_of"], "2026-10-18T15:30:01Z")
        self.assertIn(intake["content_sha256"], artifact["source"]["label"])
        self.assertNotIn("private", opaque)
        request = TerminalCheckpointCore(artifact).catalog()["sessions"][0]["defaults"]
        request["terminal_checkpoint"] = opaque
        async with self.client.post(self.origin + "/api/calculate", json=request) as response:
            self.assertEqual(response.status, 200, await response.text())
            self.assertEqual((await response.json())["comparison"]["net_gex_delta"], 0)
        async with self.client.post(self.origin + "/api/receipts", json={
            "name": "Guided intake", "kind": "calculate", "request": request,
        }) as response:
            self.assertEqual(response.status, 200, await response.text())
            saved = await response.json()
        async with self.client.get(self.origin + "/api/receipts/" + saved["receipt_sha256"] + "/export") as response:
            self.assertEqual(response.status, 200)
            receipt = await response.read()
        self.assertEqual(len(list((self.root / "research").glob("*.json"))), 2)  # owner + receipt only
        self.capture.unlink()
        registry = self.runner.app[server.INTAKE_KEY]
        await self.runner.cleanup()
        self.assertEqual(registry._sessions, {})
        fresh, launch = await server.start_server(self.root / "fresh", port=0)
        try:
            url = urlsplit(launch)
            origin = f"{url.scheme}://{url.netloc}"
            async with ClientSession(headers={"Origin": origin, "X-GEX-Capability": url.fragment.removeprefix("cap=")}) as client:
                async with client.post(origin + "/api/reproduce", data=receipt,
                                       headers={"Content-Type": "application/json"}) as response:
                    self.assertEqual(response.status, 200, await response.text())
                    self.assertEqual((await response.json())["status"], "verified")
        finally:
            await fresh.cleanup()

    async def test_boundary_size_content_type_and_path_authority(self):
        async with ClientSession() as unauthenticated:
            async with unauthenticated.post(self.origin + "/api/intake", data=self.payload) as response:
                self.assertEqual(response.status, 403)
        for extra in ({"Origin": "https://untrusted.example"}, {"Host": "localhost:8765"}):
            async with self.client.post(self.origin + "/api/intake", data=self.payload, headers=extra) as response:
                self.assertEqual(response.status, 403)
        async with self.client.post(self.origin + "/api/intake", json={"path": str(self.capture)}) as response:
            self.assertEqual(response.status, 400)
            self.assertNotIn(str(self.capture), await response.text())
        async with self.client.post(self.origin + "/api/intake", data=io.BytesIO(b"x" * (server.MAX_JSON_BYTES + 1)),
                                    headers={"Content-Type": "application/octet-stream"}) as response:
            self.assertEqual(response.status, 413)
        async with self.client.post(self.origin + "/api/intake", data=b'{"private":"/secret"}',
                                    headers={"Content-Type": "application/octet-stream"}) as response:
            self.assertEqual(response.status, 400)
            self.assertNotIn("/secret", await response.text())
        self.assertEqual(self.runner.app[server.INTAKE_KEY]._sessions, {})

    async def test_invalid_checkpoint_busy_and_discard_preserve_valid_intake(self):
        intake = await self.inspect()
        for sequence in (-1, 3, True, 1.5, "1"):
            async with self.client.post(self.origin + "/api/intake/checkpoint", json={
                "intake_id": intake["intake_id"], "sequence": sequence,
            }) as response:
                self.assertEqual(response.status, 400)
        async with self.client.post(self.origin + "/api/intake/checkpoint", json={
            "intake_id": intake["intake_id"], "sequence": 0,
        }) as response:
            self.assertEqual(response.status, 400)
        self.assertEqual(json.loads(await self.freeze(intake))["parameters"]["spot"], 5000.0)
        async with self.runner.app[server.LOCK_KEY]:
            async with self.client.post(self.origin + "/api/intake", data=self.payload,
                                        headers={"Content-Type": "application/octet-stream"}) as response:
                self.assertEqual(response.status, 429)
        async with self.client.delete(self.origin + "/api/intake/" + intake["intake_id"]) as response:
            self.assertEqual(response.status, 200)
        async with self.client.post(self.origin + "/api/intake/checkpoint", json={
            "intake_id": intake["intake_id"], "sequence": 1,
        }) as response:
            self.assertEqual(response.status, 400)
        self.assertEqual(self.runner.app[server.INTAKE_KEY]._sessions, {})
