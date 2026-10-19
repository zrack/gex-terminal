"""Full-session checkpoints remain portable without expanding capture uploads."""
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

from aiohttp import ClientSession, ClientTimeout

from gex_terminal import wind_tunnel as wind
from gex_terminal import wind_tunnel_checkpoint as checkpoint
from gex_terminal import wind_tunnel_server as server
from gex_terminal.session_intake import MAX_CAPTURE_BYTES, MAX_EVENTS
from tests.test_pricing_coverage import consumer_with, unavailable
from tests.test_wind_tunnel_checkpoint import option


async def large_checkpoint():
    consumer = await consumer_with(
        option("priced", pricing_model="black_76", exercise_style="european",
               exercise_style_source="provider_cfi", provider_cfi="OCEFPS"), unavailable(),
    )
    artifact = await checkpoint.build_terminal_checkpoint(consumer, fallback_dte=.25)
    bases = {row["contract_id"]: row for row in artifact["rows"]}
    artifact["source"]["label"] = "Synthetic full-session transport regression"
    artifact["rows"] = []
    for index in range(4500):
        row = copy.deepcopy(bases["unpriced" if index % 50 == 0 else "priced"])
        row["contract_id"] = f"synthetic-full-session-{index:04}"
        row["strike"] = 5900 + index % 80 * 5
        artifact["rows"].append(row)
    artifact["sha256"] = checkpoint.checkpoint_sha256(artifact)
    return checkpoint.validate_checkpoint(artifact)


class FullSessionTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_large_checkpoint_http_save_export_and_reproduction_preserve_all_rows(self):
        artifact = await large_checkpoint()
        opaque = checkpoint.checkpoint_transport(artifact)
        self.assertGreater(len(opaque.encode()), 2_000_000)
        self.assertLess(len(opaque.encode()), checkpoint.MAX_BYTES)
        self.assertEqual(checkpoint.validate_checkpoint(opaque), artifact)
        with tempfile.TemporaryDirectory(prefix="gex full-session transport ") as directory:
            path = Path(directory) / "checkpoint.json"
            checkpoint.write_checkpoint(path, artifact)
            original_hash = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(checkpoint.read_checkpoint(path), artifact)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), original_hash)
            runner, launch = await server.start_server(Path(directory) / "research", port=0,
                                                        core=wind.TerminalCheckpointCore(artifact))
            parsed = urlsplit(launch)
            origin = f"{parsed.scheme}://{parsed.netloc}"
            headers = {"X-GEX-Capability": parsed.fragment.removeprefix("cap=")}
            try:
                async with ClientSession(timeout=ClientTimeout(total=90)) as client:
                    request_bytes = server.canonical_bytes({"name": "Full session", "kind": "calculate",
                                                            "request": {"terminal_checkpoint": opaque}})
                    async with client.post(origin + "/api/receipts", headers={**headers, "Content-Type": "application/json"},
                                           data=io.BytesIO(request_bytes)) as response:
                        body = await response.read()
                        self.assertEqual(response.status, 200, body[:500])
                    self.assertGreater(len(body), 4 * 1024 * 1024)
                    self.assertLess(len(body), server.MAX_JSON_BYTES)
                    receipt = server.decode_json(body)
                    server.validate_receipt(receipt)
                    for state in (receipt["result"]["baseline"], receipt["result"]["scenario"]):
                        self.assertEqual(state["pricing_coverage"]["selected_contract_count"], 4500)
                        self.assertEqual(state["pricing_coverage"]["unpriced_contract_count"], 90)
                    receipt_id = receipt["receipt_sha256"]
                    async with client.get(origin + f"/api/receipts/{receipt_id}/export", headers=headers) as response:
                        self.assertEqual(response.status, 200)
                        self.assertEqual(await response.read(), body)
                    async with client.post(origin + "/api/reproduce", headers={**headers, "Content-Type": "application/json"},
                                           data=io.BytesIO(body)) as response:
                        self.assertEqual(response.status, 200)
                        reproduced = await response.json()
                    self.assertEqual(reproduced["status"], "verified")
                    self.assertEqual(reproduced["result"], receipt["result"])
                    stored = Path(directory) / "research" / f"{receipt_id}.json"
                    self.assertEqual(stored.read_bytes(), body)
                    self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), original_hash)
            finally:
                await runner.cleanup()

    async def test_browser_capture_intake_rejects_oversize_content_length_and_chunked_before_decode(self):
        self.assertEqual(MAX_CAPTURE_BYTES, 4 * 1024 * 1024)
        self.assertEqual(MAX_EVENTS, 5000)
        with tempfile.TemporaryDirectory(prefix="gex intake boundaries ") as directory:
            runner, launch = await server.start_server(directory, port=0)
            parsed = urlsplit(launch)
            origin = f"{parsed.scheme}://{parsed.netloc}"
            headers = {"X-GEX-Capability": parsed.fragment.removeprefix("cap="),
                       "Content-Type": "application/octet-stream"}

            async def chunks():
                yield b"x" * (2 * 1024 * 1024)
                yield b"x" * (2 * 1024 * 1024)
                yield b"x"

            try:
                with patch.object(server.SessionIntake, "inspect", side_effect=AssertionError("decode must not run")) as inspect:
                    async with ClientSession() as client:
                        for body in (io.BytesIO(b"x" * (MAX_CAPTURE_BYTES + 1)), chunks()):
                            async with client.post(origin + "/api/intake", headers=headers, data=body) as response:
                                self.assertEqual(response.status, 413)
                                self.assertIn("4 MiB", (await response.json())["error"]["message"])
                    inspect.assert_not_called()
            finally:
                await runner.cleanup()

    async def test_checkpoint_row_and_byte_caps_remain_finite(self):
        artifact = await large_checkpoint()
        artifact["rows"].extend(copy.deepcopy(artifact["rows"][:501]))
        artifact["sha256"] = checkpoint.checkpoint_sha256(artifact)
        with self.assertRaisesRegex(ValueError, "5000"):
            checkpoint.validate_checkpoint(artifact)
        with self.assertRaisesRegex(ValueError, "8 MiB"):
            checkpoint.validate_checkpoint(" " * (checkpoint.MAX_BYTES + 1))
        with self.assertRaisesRegex(server.ReceiptError, "32 MiB"):
            server.decode_json(b" " * (server.MAX_JSON_BYTES + 1))

    async def test_receipt_validation_keeps_legacy_canonical_bytes_and_digest(self):
        receipt = await server.make_receipt("Legacy small receipt", "calculate", {"spot_shift": 1})
        original = server.canonical_bytes(receipt)
        digest = receipt["receipt_sha256"]
        self.assertEqual(server.validate_receipt(server.decode_json(original)), receipt)
        self.assertEqual(server.canonical_bytes(receipt), original)
        self.assertEqual(receipt["receipt_sha256"], digest)
        tampered = copy.deepcopy(receipt)
        tampered["request"]["spot_shift"] = 2
        with self.assertRaises(server.ReceiptError):
            server.validate_receipt(tampered)


if __name__ == "__main__":
    unittest.main()
