"""Adversarial boundary regressions; all payloads and credentials are invented."""

import asyncio
from collections import deque
import json
import logging
import os
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from websockets.client import ClientProtocol
from websockets.datastructures import Headers
from websockets.uri import parse_uri

from gex_terminal import tradovate_capture as capture
from tests.test_capture_governance import _valid_policy
from tests.test_tradovate_capture import CREDS, FakeHTTP, FakeWebsocket


class MemoryWriter:
    def __init__(self):
        self.records = []

    def write(self, name, record):
        self.records.append((name, record))


def collector():
    adapter = SimpleNamespace(
        auth_payload={"name": "invented-user", "password": "invented-password",
                      "appId": "invented-app", "appVersion": "1.0", "cid": 100,
                      "sec": "invented-secret"},
        access_token="invented-rest-token", md_access_token="invented-md-token",
        rest_url="https://demo.tradovateapi.com/v1",
    )
    manifest = {
        "target": {"symbol": "ES"},
        "limits": {"max_frames": 100, "max_frame_bytes": 65536, "max_requests": 12},
        "counts": {name: 0 for name in (
            "rest_requests", "rest_bodies_captured", "rest_bodies_omitted",
            "frames_received", "frames_captured", "frames_omitted",
            "control_frames_omitted", "events_omitted", "market_data_events_captured",
            "authorization_events_omitted", "unsafe_or_unsupported_events_omitted",
        )},
        "observed": {"quoted_contract_ids": [], "joined_option_quote_contract_ids": []},
    }
    result = capture._Collector(adapter, MemoryWriter(), manifest)
    result._refresh_secrets()
    result.selected_ids = {100, 200}
    result.joined_option_contract_ids = {200}
    return result


def quote_event(contract_id=200):
    return '{ "e" : "md", "d" : { "quotes" : [{"contractId":' + str(contract_id) + ',"timestamp":"2026-10-19T01:00:00Z","entries":{"Trade":{"price":1.0}}}] } }'


class FrameSafetyTests(unittest.TestCase):
    def test_retains_exact_market_event_when_auth_ack_shares_its_frame(self):
        probe = collector()
        event = quote_event()
        probe.frame('a[{"i":1,"s":200,"d":{"userId":123}}, ' + event + ']')
        self.assertEqual(len(probe.writer.records), 1)
        record = probe.writer.records[0][1]
        self.assertIsNone(record["raw_frame"])
        self.assertEqual(record["omitted_event_count"], 1)
        self.assertEqual(record["events"], [{"event_index": 1, "raw_event": event}])
        self.assertNotIn("userId", json.dumps(record))
        self.assertEqual(probe.manifest["observed"]["joined_option_quote_contract_ids"], [200])

    def test_valid_json_whitespace_preserves_exact_event_for_both_frame_prefixes(self):
        event = quote_event()
        for raw in ('a \n [ \t' + event + ' ]', 'm \n ' + event):
            with self.subTest(prefix=raw[0]):
                probe = collector()
                probe.frame(raw)
                self.assertEqual(len(probe.writer.records), 1)
                self.assertEqual(probe.writer.records[0][1]["events"][0]["raw_event"], event)
                self.assertEqual(probe.writer.records[0][1]["raw_frame"], raw)

    def test_private_events_are_omitted_without_changing_benign_market_values(self):
        for field in ("accountId", "access_token", "mdAccessToken", "userId", "password"):
            with self.subTest(field=field):
                probe = collector()
                unsafe = {"e": "md", "d": {"quotes": [{"contractId": 200, field: "private-value"}]}}
                probe.frame('a[' + json.dumps(unsafe) + ',' + quote_event(100) + ']')
                self.assertEqual(len(probe.writer.records), 1)
                record = probe.writer.records[0][1]
                self.assertNotIn("private-value", json.dumps(record))
                self.assertEqual(record["events"][0]["event_index"], 1)
                self.assertIn('"contractId":100', record["events"][0]["raw_event"])
                self.assertIn('"price":1.0', record["events"][0]["raw_event"])

    def test_duplicate_keys_and_credential_literals_never_reach_evidence(self):
        cases = (
            'a[{"e":"md","e":"md","d":{"quotes":[]}}]',
            'a[{"e":"md","d":{"quotes":[],"detail":"invented-md-token"}}]',
            'a[{"e":"md","d":{"quotes":[],"detail":"invented-password"}}]',
            'a[{"e":"md","d":{"quotes":[],"detail":NaN}}]',
        )
        for raw in cases:
            with self.subTest(raw=raw):
                probe = collector()
                probe.frame(raw)
                self.assertEqual(probe.writer.records, [])
                self.assertEqual(probe.counts["frames_omitted"], 1)


class CaptureSafetyTests(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_preflight_has_no_files_or_credential_construction(self):
        cases = (
            {"ack_live_network": False}, {"symbol": "MES"}, {"environment": "paper"},
            {"duration_seconds": True}, {"duration_seconds": float("nan")},
            {"duration_seconds": float("inf")}, {"duration_seconds": 301},
            {"max_option_contracts": True}, {"max_option_contracts": 61},
            {"max_maturities": 0}, {"max_requests": 65}, {"max_frames": 1.5},
            {"max_total_bytes": 32767}, {"max_frame_bytes": 1023},
            {"capture_policy": {}},
        )
        with tempfile.TemporaryDirectory() as directory:
            for index, change in enumerate(cases):
                with self.subTest(change=change):
                    destination = Path(directory).resolve() / str(index)
                    arguments = {"ack_live_network": True, "capture_policy": _valid_policy(), **change}
                    with patch.object(capture, "TradovateAdapter") as adapter:
                        with self.assertRaises(ValueError):
                            await capture.capture_tradovate_payloads(destination, **arguments)
                        adapter.assert_not_called()
                    self.assertFalse(destination.exists())

    async def test_symlink_git_and_existing_destinations_refuse_without_touching_data(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory).resolve()
            actual = parent / "actual"
            actual.mkdir()
            linked = parent / "linked"
            linked.symlink_to(actual, target_is_directory=True)
            checkout = parent / "checkout"
            checkout.mkdir()
            (checkout / ".git").write_text("gitdir: /invented/worktree\n")
            existing = parent / "existing"
            existing.mkdir()
            marker = existing / "marker"
            marker.write_bytes(b"preserve me")
            for destination in (linked / "capture", checkout / "capture", existing):
                with self.subTest(destination=destination), patch.object(capture, "TradovateAdapter") as adapter:
                    with self.assertRaises(ValueError):
                        await capture.capture_tradovate_payloads(
                            destination, capture_policy=_valid_policy(), ack_live_network=True,
                        )
                    adapter.assert_not_called()
            self.assertEqual(marker.read_bytes(), b"preserve me")
            self.assertFalse((actual / "capture").exists())
            self.assertFalse((checkout / "capture").exists())

    async def test_provider_timeout_is_failure_and_private_artifacts_still_finalize(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory).resolve() / "capture"
            with patch.object(capture, "TradovateAdapter"), \
                    patch.object(capture._Collector, "run", AsyncMock(side_effect=TimeoutError("private-text"))):
                manifest = await capture.capture_tradovate_payloads(
                    destination, capture_policy=_valid_policy(), ack_live_network=True,
                )
            self.assertNotEqual(manifest["outcome"], "duration_limit")
            self.assertEqual(manifest["status"], "failed")
            self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o700)
            for name in ("manifest.json", "rest.jsonl", "websocket.jsonl"):
                path = destination / name
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
                self.assertNotIn("private-text", path.read_text())
            self.assertFalse(manifest["review"]["issue_4_may_close"])

    async def test_provider_error_anywhere_in_ack_frame_prevents_success(self):
        for error_first in (False, True):
            probe = collector()
            probe.subscription_ids = {2}
            events = [{"i": 2, "s": 200}, {"e": "md/error", "d": {"errorText": "private diagnostic"}}]
            if error_first:
                events.reverse()
            messages = deque(['a' + json.dumps(events)])
            probe.websocket = SimpleNamespace(recv=AsyncMock(side_effect=lambda: messages.popleft()))
            with self.subTest(error_first=error_first), self.assertRaises(capture._CaptureStop):
                await probe.ack(2)
            self.assertNotIn("private diagnostic", json.dumps(probe.writer.records))

    async def test_contract_library_request_does_not_follow_redirects(self):
        class Response:
            status = 307

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

        class Session:
            def request(self, method, url, **kwargs):
                self.arguments = (method, url, kwargs)
                return Response()

        probe, session = collector(), Session()
        result = await probe.request(session, "POST", "contract/getoptionschain", {"contractId": 100})
        self.assertIsNone(result)
        self.assertIs(session.arguments[2]["allow_redirects"], False)
        self.assertEqual(probe.writer.records[0][1]["http_status"], 307)

    async def test_cancellation_during_socket_cleanup_propagates_and_finalizes_partial(self):
        entered = asyncio.Event()
        aborted = []

        async def close_socket():
            entered.set()
            await asyncio.Event().wait()

        async def finish_run(probe):
            probe.manifest["authentication_passed"] = True
            probe.websocket = SimpleNamespace(
                close=close_socket,
                transport=SimpleNamespace(abort=lambda: aborted.append(True)),
            )

        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory).resolve() / "capture"
            with patch.object(capture, "TradovateAdapter"), patch.object(capture._Collector, "run", finish_run):
                task = asyncio.create_task(capture.capture_tradovate_payloads(
                    destination, capture_policy=_valid_policy(), ack_live_network=True,
                ))
                await asyncio.wait_for(entered.wait(), 1)
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
            manifest = json.loads((destination / "manifest.json").read_text())
            self.assertEqual(manifest["outcome"], "cancelled")
            self.assertEqual(manifest["status"], "partial")
            self.assertFalse(manifest["cleanup_completed"])
            self.assertEqual(aborted, [True])

    async def test_websocket_debug_logger_cannot_export_authorization_token(self):
        probe = collector()
        probe.limits["duration_seconds"] = 30
        probe.adapter.ws_url = "wss://md.tradovateapi.com/v1/websocket"
        probe.authenticate = AsyncMock(return_value=True)
        probe.discover = AsyncMock(return_value=[100, 200])

        async def fake_connect(*args, **kwargs):
            logger = kwargs["logger"]
            self.assertFalse(logger.propagate)
            self.assertFalse(logger.isEnabledFor(logging.DEBUG))
            logger.debug("authorize %s", probe.adapter.md_access_token)
            raise RuntimeError("mocked connection stop")

        with self.assertLogs(level="DEBUG") as logs, patch("websockets.connect", fake_connect):
            logging.getLogger().debug("public test marker")
            with self.assertRaisesRegex(RuntimeError, "mocked connection stop"):
                await probe.run()
        self.assertNotIn("invented-md-token", str(logs.output))

    async def test_heartbeat_failure_interrupts_a_stalled_authorization_ack(self):
        probe = collector()
        receive_cancelled = asyncio.Event()

        async def never_receive():
            try:
                await asyncio.Event().wait()
            finally:
                receive_cancelled.set()

        async def immediate_tick(delay):
            self.assertEqual(delay, 2.5)

        probe.websocket = SimpleNamespace(
            recv=never_receive,
            send=AsyncMock(side_effect=RuntimeError("invented heartbeat send failure")),
        )
        with patch.object(capture.asyncio, "sleep", immediate_tick):
            probe.heartbeat_task = asyncio.create_task(probe.heartbeat())
            with self.assertRaisesRegex(RuntimeError, "heartbeat send failure"):
                await asyncio.wait_for(probe.ack(1), 1)
        self.assertTrue(receive_cancelled.is_set())
        probe.websocket.send.assert_awaited_once_with("[]")
        self.assertEqual(probe.writer.records, [])

    async def test_modern_and_legacy_provider_endpoint_identities_are_accepted(self):
        uri = parse_uri("wss://md.tradovateapi.com/v1/websocket")
        modern = SimpleNamespace(protocol=ClientProtocol(uri))
        # Legacy protocols expose the completed handshake's headers and target.
        legacy = SimpleNamespace(secure=True, host=uri.host, port=uri.port,
                                 path=uri.resource_name, request_headers=Headers())
        for websocket in (modern, legacy):
            with self.subTest(interface="modern" if websocket is modern else "legacy"):
                capture._validate_websocket_target(websocket)

    async def test_redirected_or_unreported_socket_identity_never_receives_credentials(self):
        identities = [
            {"protocol": ClientProtocol(parse_uri(uri))}
            for uri in (
                "wss://redirect.invalid/v1/websocket",
                "ws://md.tradovateapi.com/v1/websocket",
                "wss://md.tradovateapi.com:8443/v1/websocket",
                "wss://md.tradovateapi.com/other",
                "wss://md.tradovateapi.com/v1/websocket?redirected=1",
                "wss://invented:credentials@md.tradovateapi.com/v1/websocket",
            )
        ]
        identities.extend([
            {"host": "redirect.invalid"},
            {"request_headers": Headers({"aUtHoRiZaTiOn": "Basic invented-userinfo"})},
            {"request_headers": None},
            {"protocol": SimpleNamespace(uri=SimpleNamespace(
                secure=True, host="md.tradovateapi.com", port=443,
                resource_name="/v1/websocket",  # Missing user-info identity must fail closed.
            ))},
            {"secure": None, "host": None, "port": None, "path": None},
        ])
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory).resolve()
            for index, identity in enumerate(identities):
                with self.subTest(identity=index):
                    http, websocket = FakeHTTP(), FakeWebsocket()
                    websocket.__dict__.update(identity)
                    destination = parent / str(index)
                    with patch.dict(os.environ, CREDS), \
                            patch("aiohttp.ClientSession", http.session), \
                            patch("websockets.connect", AsyncMock(return_value=websocket)):
                        manifest = await capture.capture_tradovate_payloads(
                            destination, capture_policy=_valid_policy(), ack_live_network=True,
                        )
                    self.assertEqual(manifest["outcome"], "websocket_target_rejected")
                    self.assertEqual(manifest["status"], "partial")
                    self.assertFalse(manifest["websocket_authorized"])
                    self.assertEqual(websocket.sent, [])
                    self.assertEqual(websocket.recv_count, 0)
                    self.assertTrue(websocket.closed)
                    artifacts = "".join(path.read_text() for path in destination.iterdir())
                    self.assertNotIn("private-md-token", artifacts)
                    self.assertNotIn("private-rest-token", artifacts)

    async def test_simultaneous_heartbeat_and_receive_failures_are_both_retrieved(self):
        probe = collector()
        created = []
        original_wait = asyncio.wait

        async def fail_receive():
            raise LookupError("invented private close reason")

        async def fail_heartbeat():
            raise RuntimeError("heartbeat failed")

        class ObservedTask(asyncio.Task):
            def __await__(self):
                self.result_retrieved = True
                return super().__await__()

        def track_task(coroutine):
            task = ObservedTask(coroutine)
            task.result_retrieved = False
            created.append(task)
            return task

        async def simultaneous_completion(tasks, **kwargs):
            # asyncio.wait leaves exception retrieval to the task owner.
            return await original_wait(tasks, return_when=asyncio.ALL_COMPLETED)

        probe.websocket = SimpleNamespace(recv=fail_receive)
        probe.heartbeat_task = asyncio.create_task(fail_heartbeat())
        with patch.object(capture.asyncio, "create_task", track_task), \
                patch.object(capture.asyncio, "wait", simultaneous_completion):
            with self.assertRaisesRegex(RuntimeError, "heartbeat failed"):
                await probe.receive()
        self.assertEqual(len(created), 1)
        self.assertTrue(created[0].done())
        self.assertTrue(created[0].result_retrieved)


if __name__ == "__main__":
    unittest.main()
