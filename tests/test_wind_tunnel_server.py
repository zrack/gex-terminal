import asyncio
import copy
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

from aiohttp import ClientSession

from gex_terminal import wind_tunnel_server as server


class SmallCore:
    """A bounded transport fixture; separate integration tests exercise real models."""

    EXAMPLE_NAMES = ("example",)

    @staticmethod
    def calculation_identity():
        return {"contract_version": "transport-test"}

    @staticmethod
    def catalog():
        return {"sessions": [{"session": "synthetic"}]}

    @staticmethod
    def checkpoints(session):
        if session != "synthetic":
            raise ValueError("private/path/should-not-leak")
        return {"checkpoints": [0, 1]}

    @staticmethod
    def examples(name):
        return {"name": name, "title": "Example", "description": "Synthetic",
                "operation": "calculate", "request": {"spot_shift": 0}}

    @staticmethod
    async def calculate(request):
        if set(request) - {"spot_shift"}:
            raise ValueError("private/path/should-not-leak")
        normalized = {"spot_shift": request.get("spot_shift", 0)}
        return {"schema": "transport-test.v1", "request": normalized,
                "calculation": SmallCore.calculation_identity(),
                "calculation_fingerprint": server.digest(SmallCore.calculation_identity()),
                "value": normalized["spot_shift"] * 2,
                "result_sha256": server.digest(normalized)}

    surface = calculate
    search = calculate


class ReceiptStoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_immutable_save_reopen_reproduce_and_tamper_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            store = server.ReceiptStore(Path(directory) / "Research with spaces")
            try:
                receipt = await server.make_receipt("A named scenario", "calculate", {"spot_shift": 2}, core=SmallCore)
                store.save(receipt)
                store.save(receipt)
                self.assertEqual(len(store.list()), 1)
                loaded = store.load(receipt["receipt_sha256"])
                self.assertEqual(loaded, receipt)
                report = await server.reproduce_receipt(loaded, core=SmallCore)
                self.assertEqual(report["status"], "verified")
                changed = copy.deepcopy(receipt)
                changed["result"]["value"] += 1
                with self.assertRaisesRegex(server.ReceiptError, "checksum"):
                    server.validate_receipt(changed)
                changed["receipt_sha256"] = server.digest({k: v for k, v in changed.items() if k != "receipt_sha256"})
                self.assertEqual((await server.reproduce_receipt(changed, core=SmallCore))["status"], "mismatch")
                target = store.path / (receipt["receipt_sha256"] + ".json")
                target.write_text(json.dumps(changed))
                with self.assertRaisesRegex(server.ReceiptError, "identity"):
                    store.load(receipt["receipt_sha256"])
            finally:
                store.close()

    async def test_unknown_workspace_symlinks_and_traversal_preserve_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "private.json").write_text('{"private":"untouched"}')
            with self.assertRaisesRegex(server.ReceiptError, "empty folder"):
                server.ReceiptStore(root)
            self.assertEqual((root / "private.json").read_text(), '{"private":"untouched"}')
            (root / "linked").symlink_to(root, target_is_directory=True)
            with self.assertRaisesRegex(server.ReceiptError, "symbolic"):
                server.ReceiptStore(root / "linked")
            store = server.ReceiptStore(root / "workspace")
            try:
                with self.assertRaisesRegex(server.ReceiptError, "identifier"):
                    store.load("../private")
                (store.path / ("0" * 64 + ".json")).symlink_to(root / "private.json")
                with self.assertRaisesRegex(server.ReceiptError, "invalid"):
                    store.list()
            finally:
                store.close()

    async def test_workspace_quota_and_duplicate_json_fail_closed(self):
        for payload in (b'{"x":1,"x":2}', b'{"x":NaN}', b'[]', b'{"x":Infinity}'):
            with self.assertRaises(server.ReceiptError):
                server.decode_json(payload)
        with tempfile.TemporaryDirectory() as directory:
            store = server.ReceiptStore(directory)
            try:
                one = await server.make_receipt("One", "calculate", {}, core=SmallCore)
                two = await server.make_receipt("Two", "calculate", {}, core=SmallCore)
                store.save(one)
                with patch.object(server, "MAX_RECEIPTS", 1):
                    with self.assertRaisesRegex(server.ReceiptError, "full"):
                        store.save(two)
                with patch.object(server, "MAX_WORKSPACE_BYTES", 1):
                    with self.assertRaisesRegex(server.ReceiptError, "64 MiB"):
                        store.list()
                self.assertEqual(store.load(one["receipt_sha256"]), one)
            finally:
                store.close()

    async def test_changed_producer_identity_is_rejected_before_execution(self):
        receipt = await server.make_receipt("Original", "calculate", {}, core=SmallCore)
        receipt["result"]["calculation"] = {"contract_version": "unrecognized"}
        receipt["result"]["calculation_fingerprint"] = server.digest(receipt["result"]["calculation"])
        receipt["receipt_sha256"] = server.digest({k: v for k, v in receipt.items() if k != "receipt_sha256"})
        with patch.object(SmallCore, "calculate", side_effect=AssertionError("must not execute")):
            with self.assertRaisesRegex(server.ReceiptError, "identity differs"):
                await server.reproduce_receipt(receipt, core=SmallCore)


class WindTunnelHTTPTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.runner, launch = await server.start_server(Path(self.temp.name) / "research", port=0, core=SmallCore)
        parsed = urlsplit(launch)
        self.origin = f"{parsed.scheme}://{parsed.netloc}"
        self.headers = {"X-GEX-Capability": parsed.fragment.removeprefix("cap=")}
        self.client = ClientSession()

    async def asyncTearDown(self):
        await self.client.close()
        await self.runner.cleanup()
        self.temp.cleanup()

    async def test_read_and_write_require_capability_host_and_origin(self):
        for headers in ({}, {"X-GEX-Capability": "wrong"},
                        {**self.headers, "Origin": "https://foreign.example"},
                        {**self.headers, "Origin": "null"},
                        {**self.headers, "Host": "foreign.example"}):
            async with self.client.get(self.origin + "/api/catalog", headers=headers) as response:
                self.assertEqual(response.status, 403)
            async with self.client.post(self.origin + "/api/calculate", headers=headers, json={}) as response:
                self.assertEqual(response.status, 403)
        async with self.client.get(self.origin + "/api/catalog", headers={**self.headers, "Origin": self.origin}) as response:
            self.assertEqual(response.status, 200)
            self.assertNotIn("Access-Control-Allow-Origin", response.headers)
            self.assertEqual(response.headers["Cache-Control"], "no-store")
            self.assertIn("script-src 'self'", response.headers["Content-Security-Policy"])
            self.assertEqual(await response.json(), SmallCore.catalog())

    async def test_calculate_save_list_export_reproduce_transport_round_trip(self):
        async with self.client.post(self.origin + "/api/calculate", headers=self.headers, json={"spot_shift": 3}) as response:
            self.assertEqual((await response.json())["value"], 6)
        async with self.client.post(self.origin + "/api/receipts", headers=self.headers,
                                    json={"name": "Local test", "kind": "calculate", "request": {"spot_shift": 4}}) as response:
            self.assertEqual(response.status, 200)
            receipt = await response.json()
        receipt_id = receipt["receipt_sha256"]
        async with self.client.get(self.origin + "/api/receipts", headers=self.headers) as response:
            self.assertEqual((await response.json())["receipts"][0]["id"], receipt_id)
        async with self.client.get(self.origin + f"/api/receipts/{receipt_id}/export", headers=self.headers) as response:
            self.assertEqual(await response.json(), receipt)
            self.assertIn("attachment", response.headers["Content-Disposition"])
        async with self.client.post(self.origin + "/api/reproduce", headers=self.headers, json=receipt) as response:
            self.assertEqual((await response.json())["status"], "verified")
        self.assertEqual(self.runner.addresses[0][0], "127.0.0.1")

    async def test_malformed_oversized_paths_and_private_errors(self):
        for payload in ('{"spot_shift":1,"spot_shift":2}', '{"spot_shift":NaN}', '{"unexpected":1}'):
            async with self.client.post(self.origin + "/api/calculate", headers={**self.headers, "Content-Type": "application/json"}, data=payload) as response:
                self.assertEqual(response.status, 400)
                self.assertNotIn("private/path", await response.text())
        async with self.client.post(self.origin + "/api/calculate", headers={**self.headers, "Content-Type": "application/json"},
                                    data=io.BytesIO(b'"' + b'x' * (server.MAX_JSON_BYTES + 1) + b'"')) as response:
            self.assertEqual(response.status, 413)
        for path in ("/api/receipts/not-an-id", "/static/../../private.json", "/api/checkpoints?session=synthetic&session=secret"):
            async with self.client.get(self.origin + path, headers=self.headers) as response:
                self.assertIn(response.status, (400, 404))
                self.assertNotIn(self.temp.name, await response.text())

    async def test_busy_request_and_disconnect_cancel_computation(self):
        started = asyncio.Event()
        cancelled = asyncio.Event()

        async def slow(_):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        with patch.object(SmallCore, "calculate", slow):
            pending = asyncio.create_task(self.client.post(self.origin + "/api/calculate", headers=self.headers, json={}))
            await asyncio.wait_for(started.wait(), 2)
            async with self.client.post(self.origin + "/api/search", headers=self.headers, json={}) as response:
                self.assertEqual(response.status, 429)
            pending.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await pending
            await asyncio.wait_for(cancelled.wait(), 2)
        self.assertFalse(self.runner.app[server.LOCK_KEY].locked())

    async def test_packaged_scripts_are_allowlisted_and_never_cache_session_content(self):
        for path in ("/", "/static/app.css", "/static/vendor/plotly.min.js"):
            async with self.client.get(self.origin + path) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(response.headers["Cache-Control"], "no-store")
                self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])
                self.assertIn("script-src 'self'", response.headers["Content-Security-Policy"])
                self.assertNotIn(self.headers["X-GEX-Capability"], await response.text())
        async with self.client.get(self.origin + "/static/vendor/missing.js") as response:
            self.assertEqual(response.status, 404)

    async def test_real_core_surface_search_save_and_reproduction(self):
        runner, launch = await server.start_server(Path(self.temp.name) / "real core", port=0)
        parsed = urlsplit(launch)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        headers = {"X-GEX-Capability": parsed.fragment.removeprefix("cap=")}
        try:
            async with self.client.post(origin + "/api/surface", headers=headers,
                                        json={"spot_shifts": [-10, 0, 10], "time_advances": [0, 1]}) as response:
                self.assertEqual(response.status, 200)
                result = await response.json()
                self.assertEqual(len(result["points"]), 6)
                self.assertTrue(result["source"]["synthetic"])
                self.assertTrue(all(point["delta_total_net_gex"] == 0 for point in result["points"]))
            example = server.core_module().examples("no-break")
            async with self.client.post(origin + "/api/receipts", headers=headers,
                                        json={"name": "Real core search", "kind": example["operation"], "request": example["request"]}) as response:
                self.assertEqual(response.status, 200)
                receipt = await response.json()
                self.assertEqual(receipt["result"]["outcome"], "no_break_found")
            async with self.client.get(origin + "/api/receipts/" + receipt["receipt_sha256"], headers=headers) as response:
                self.assertEqual(await response.json(), receipt)
            async with self.client.post(origin + "/api/reproduce", headers=headers, json=receipt) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual((await response.json())["status"], "verified")
        finally:
            await runner.cleanup()

    async def test_browser_receipt_transfer_preserves_exact_json_number_representations(self):
        runner, launch = await server.start_server(Path(self.temp.name) / "browser bytes", port=0)
        parsed = urlsplit(launch)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        headers = {"X-GEX-Capability": parsed.fragment.removeprefix("cap=")}
        json_headers = {**headers, "Content-Type": "application/json"}
        try:
            async with self.client.post(origin + "/api/receipts", headers=headers,
                                        json={"name": "Browser → CLI", "kind": "calculate", "request": {"spot_shift": 0}}) as response:
                self.assertEqual(response.status, 200)
                saved_bytes = await response.read()
            self.assertIn(b'"spot_shift":0.0', saved_bytes)
            self.assertIn(b'"iv_shift":0.0', saved_bytes)
            receipt = json.loads(saved_bytes)
            receipt_id = receipt["receipt_sha256"]
            for suffix in ("", "/export"):
                async with self.client.get(origin + "/api/receipts/" + receipt_id + suffix, headers=headers) as response:
                    self.assertEqual(response.status, 200)
                    transferred = await response.read()
                self.assertEqual(transferred, saved_bytes)
                # Browser fetch(...).text() or file.text() is forwarded intact;
                # parsing a separate copy for display does not alter the receipt.
                async with self.client.post(origin + "/api/reproduce", headers=json_headers,
                                            data=transferred.decode("utf-8")) as response:
                    self.assertEqual(response.status, 200)
                    self.assertEqual((await response.json())["status"], "verified")

            # JavaScript JSON.stringify(JSON.parse(...)) emits integral numbers
            # without Python's .0. Reproduce that specific conversion without a
            # Node dependency so CI guards the actual cross-runtime failure.
            def integral_floats_to_ints(value):
                if isinstance(value, dict):
                    return {key: integral_floats_to_ints(item) for key, item in value.items()}
                if isinstance(value, list):
                    return [integral_floats_to_ints(item) for item in value]
                return int(value) if isinstance(value, float) and value.is_integer() else value

            rewritten = server.canonical_bytes(integral_floats_to_ints(receipt))
            self.assertNotEqual(rewritten, saved_bytes)
            self.assertNotIn(b'"spot_shift":0.0', rewritten)
            async with self.client.post(origin + "/api/reproduce", headers=json_headers, data=rewritten) as response:
                self.assertEqual(response.status, 400)
                self.assertIn("checksum", (await response.json())["error"]["message"])

            from gex_terminal.wind_tunnel_cli import read_artifact
            artifact = Path(self.temp.name) / "exported browser receipt.json"
            artifact.write_bytes(saved_bytes)
            self.assertEqual(server.validate_receipt(read_artifact(artifact)), receipt)
        finally:
            await runner.cleanup()


if __name__ == "__main__":
    unittest.main()
