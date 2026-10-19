import asyncio
import hashlib
import json
import logging
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gex_terminal.capture_governance import CAPTURE_POLICY_SCHEMA
from gex_terminal.tradovate_capture import CAPTURE_SCHEMA, capture_tradovate_payloads


def valid_policy():
    return {
        "schema": CAPTURE_POLICY_SCHEMA, "policy_id": "tradovate-private-capture-test",
        "rights": {"status": "licensed", "basis": "Constructed offline fixture only", "redistributable": False},
        "retention": {"mode": "time_limited", "days": 7, "storage": "private local", "owner": "operator"},
        "redaction": {"status": "required", "profile": "manual raw payload review", "review_before_sharing": True},
        "research_use": {"status": "prohibited", "scope": "protocol inspection only"},
    }


CREDS = {
    "TRADOVATE_NAME": "private-api-user", "TRADOVATE_PASSWORD": "private-password",
    "TRADOVATE_APP_ID": "private-app-id", "TRADOVATE_APP_VERSION": "1.0",
    "TRADOVATE_CID": "100", "TRADOVATE_SEC": "private-app-secret",
}


class FakeContent:
    def __init__(self, body):
        self.body = body

    async def iter_chunked(self, size):
        for start in range(0, len(self.body), size):
            yield self.body[start:start + size]


class FakeResponse:
    def __init__(self, payload, status=200):
        self.status = status
        self.content = FakeContent(payload.encode() if isinstance(payload, str) else json.dumps(payload).encode())

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class FakeHTTP:
    def __init__(self):
        self.requests = []
        self.sessions = []
        self.responses = {
            "auth/accesstokenrequest": {"accessToken": "private-rest-token", "mdAccessToken": "private-md-token", "userId": 9900},
            "product/find": {"id": 1, "name": "ES"},
            "contractMaturity/deps": [{"id": 10, "productId": 1, "isFront": True, "expirationDate": "2099-12-01"}],
            "contract/deps": [{"id": 101, "name": "ESZ9", "contractMaturityId": 10}],
            "contract/getoptionschain": {
                "products": [{"id": 2, "productType": "Options"}],
                "contractMaturities": [{"id": 20, "productId": 2, "underlyingId": 101}],
                "contracts": [{"id": 201, "name": "provider-call-name", "contractMaturityId": 20},
                              {"id": 202, "name": "provider-put-name", "contractMaturityId": 20}],
            },
        }

    def session(self, **kwargs):
        self.sessions.append(kwargs)
        owner = self

        class Session:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            def request(self, method, url, **request_kwargs):
                path = url.split("/v1/")[1]
                owner.requests.append((method, path, request_kwargs))
                response = owner.responses[path]
                return response if isinstance(response, FakeResponse) else FakeResponse(response)

        return Session()


class FakeWebsocket:
    def __init__(self):
        self.frames = ["o", 'a[{"i":1,"s":200,"d":{"accessToken":"private-md-token"}}]']
        self.sent = []
        self.closed = False
        self.connect_kwargs = None
        self.fail_receive = None
        self.quote_ids = None
        self.recv_count = 0
        # Legacy websockets exposes the negotiated endpoint on the protocol;
        # modern clients expose protocol.uri. Both must pass the same pin.
        self.secure = True
        self.host = "md.tradovateapi.com"
        self.port = 443
        self.path = "/v1/websocket"
        self.user_info = None
        self.request_headers = {}

    async def send(self, raw):
        self.sent.append(raw)
        if raw.startswith("md/subscribeQuote\n"):
            _, request_id, _, body = raw.split("\n")
            contract_id = json.loads(body)["symbol"]
            events = [{"i": int(request_id), "s": 200, "d": {}}]
            if self.quote_ids is None or contract_id in self.quote_ids:
                events.append({"e": "md", "d": {"quotes": [{"contractId": contract_id,
                    "timestamp": "2026-10-19T15:01:00Z", "entries": {"Trade": {"price": "100.0"},
                    "TotalTradeVolume": {"size": 3}}, "unrecognizedProviderField": {"observed": True}}]}})
            self.frames.append("a" + json.dumps(events, separators=(",", ":")))

    async def recv(self):
        self.recv_count += 1
        if self.frames:
            return self.frames.pop(0)
        if self.fail_receive:
            raise self.fail_receive
        await asyncio.Future()

    async def close(self):
        self.closed = True


class TradovateCaptureTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.target = Path(self.temp.name).resolve() / "private-capture"
        self.http = FakeHTTP()
        self.ws = FakeWebsocket()

    async def capture(self, **kwargs):
        async def connect(url, **options):
            self.ws.connect_kwargs = options
            self.assertEqual(url, "wss://md.tradovateapi.com/v1/websocket")
            return self.ws

        parameters = {"symbol": "ES", "environment": "demo", "capture_policy": valid_policy(),
                      "ack_live_network": True, "duration_seconds": 0.15}
        parameters.update(kwargs)
        with patch.dict(os.environ, CREDS), patch("aiohttp.ClientSession", self.http.session), patch("websockets.connect", connect):
            return await capture_tradovate_payloads(self.target, **parameters)

    def records(self, filename):
        return [json.loads(line) for line in (self.target / filename).read_text().splitlines()]

    async def test_end_to_end_preserves_bare_provider_shapes_without_iv_or_strike(self):
        report = await self.capture()
        self.assertEqual(report["schema"], CAPTURE_SCHEMA)
        self.assertEqual(report["status"], "complete")
        self.assertEqual(report["outcome"], "duration_limit")
        self.assertTrue(report["cleanup_completed"])
        self.assertTrue(self.ws.closed)
        self.assertEqual(report["observed"]["joined_option_quote_contract_ids"], [201, 202])
        self.assertEqual(report["counts"]["rest_requests"], 4)
        self.assertEqual(report["selection"]["chain_contract_ids"], [201, 202])
        self.assertEqual(report["adapter_registry_status"], "scaffold")
        self.assertFalse(report["review"]["issue_4_may_close"])
        self.assertEqual(report["review"]["redaction_status"], "unreviewed")
        chain = self.records("rest.jsonl")[-1]
        self.assertEqual(chain["method"], "POST")
        self.assertEqual(chain["arguments"], {"contractId": 101})
        self.assertEqual(json.loads(chain["raw_body"]), self.http.responses["contract/getoptionschain"])
        md = self.records("websocket.jsonl")[0]
        quote = json.loads(md["events"][1]["raw_event"])["d"]["quotes"][0]
        self.assertEqual(quote["entries"]["Trade"]["price"], "100.0")
        self.assertTrue(quote["unrecognizedProviderField"]["observed"])
        self.assertNotIn("iv", quote)
        self.assertEqual(stat.S_IMODE(self.target.stat().st_mode), 0o700)
        for filename, receipt in report["files"].items():
            path = self.target / filename
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(receipt["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertEqual(receipt["bytes"], path.stat().st_size)
        self.assertEqual(stat.S_IMODE((self.target / "manifest.json").stat().st_mode), 0o600)

    async def test_authentication_and_outgoing_messages_never_enter_capture(self):
        report = await self.capture()
        files = "".join(path.read_text() for path in self.target.iterdir())
        for value in (*[CREDS[key] for key in CREDS if key not in {"TRADOVATE_CID", "TRADOVATE_APP_VERSION"}],
                      "private-rest-token", "private-md-token", '"userId":9900'):
            self.assertNotIn(value, files)
        self.assertNotIn("Authorization", files)
        self.assertNotIn("md/subscribeQuote", files)
        self.assertEqual(report["counts"]["authorization_events_omitted"], 1)
        self.assertTrue(any("private-md-token" in value for value in self.ws.sent))
        self.assertTrue(all(options["allow_redirects"] is False for _, _, options in self.http.requests))

    async def test_mixed_authorization_frame_retains_later_raw_event_slice(self):
        md = '{ "e": "md", "d": {"quotes":[{"contractId":201,"nativeMystery": "preserved"}]}}'
        self.ws.frames[1] = 'a [ {"i":1,"s":200,"d":{"accessToken":"private-md-token"}}, ' + md + " ]"
        report = await self.capture()
        record = self.records("websocket.jsonl")[0]
        self.assertEqual(record["events"], [{"event_index": 1, "raw_event": md}])
        self.assertIsNone(record["raw_frame"])
        self.assertEqual(record["omitted_event_count"], 1)
        self.assertEqual(report["status"], "complete")

    async def test_existing_normalizer_discovery_and_routing_are_never_called(self):
        with patch("gex_terminal.adapters.tradovate.TradovateAdapter.discover_option_contracts", side_effect=AssertionError("normalizer discovery")), \
             patch("gex_terminal.adapters.tradovate.TradovateAdapter._route_quote", side_effect=AssertionError("normalizer routing")):
            self.assertEqual((await self.capture())["status"], "complete")

    async def test_request_cap_stops_before_additional_network_and_reports_partial(self):
        report = await self.capture(max_requests=1)
        self.assertEqual(report["outcome"], "request_limit")
        self.assertEqual(report["status"], "partial")
        self.assertEqual(report["counts"]["rest_requests"], 1)
        self.assertEqual(len(self.http.requests), 2)  # auth plus one allowlisted request
        self.assertIsNone(self.ws.connect_kwargs)

    async def test_frame_cap_includes_open_and_omitted_authorization(self):
        report = await self.capture(max_frames=3)
        self.assertEqual(report["outcome"], "frame_limit")
        self.assertEqual(report["status"], "partial")
        self.assertEqual(report["counts"]["frames_received"], 3)
        self.assertEqual(self.ws.recv_count, 3)
        self.assertTrue(self.ws.closed)

    async def test_contract_cap_does_not_require_strike_callput_expiration_or_iv(self):
        report = await self.capture(max_option_contracts=1)
        self.assertEqual(report["selection"]["chain_contract_ids"], [201])
        self.assertTrue(report["selection"]["option_selection_limited"])
        self.assertEqual(report["counts"]["subscriptions_acknowledged"], 2)

    async def test_underlying_only_frames_cannot_report_complete(self):
        self.ws.quote_ids = {101}
        report = await self.capture()
        self.assertEqual(report["status"], "partial")
        self.assertEqual(report["observed"]["joined_option_quote_contract_ids"], [])

    async def test_unclassified_chain_samples_remain_partial_even_with_quotes(self):
        self.http.responses["contract/getoptionschain"].pop("products")
        self.http.responses["contract/getoptionschain"].pop("contractMaturities")
        report = await self.capture()
        self.assertTrue(report["selection"]["unclassified_chain_contracts_sampled"])
        self.assertEqual(report["observed"]["quoted_contract_ids"], [101, 201, 202])
        self.assertEqual(report["status"], "partial")

    async def test_provider_timeout_is_not_a_normal_observation_deadline(self):
        self.ws.fail_receive = TimeoutError("private unlabelled provider text")
        report = await self.capture()
        self.assertEqual(report["outcome"], "transport_timeout")
        self.assertEqual(report["status"], "partial")
        self.assertNotIn("private unlabelled provider text", json.dumps(report))

    async def test_non_success_body_is_not_saved_or_followed_as_redirect(self):
        self.http.responses["contract/getoptionschain"] = FakeResponse({"accountId": 111, "errorText": "private diagnostic"}, status=307)
        report = await self.capture()
        record = self.records("rest.jsonl")[-1]
        self.assertEqual(record["http_status"], 307)
        self.assertEqual(record["omission"], "non_success_body")
        self.assertNotIn("raw_body", record)
        self.assertEqual(report["status"], "partial")

    async def test_auth_response_body_bound_never_exports_authentication(self):
        self.http.responses["auth/accesstokenrequest"] = {"accessToken": "private-token" * 1000}
        report = await self.capture(max_frame_bytes=1024)
        self.assertEqual(report["outcome"], "authentication_response_size_limit")
        self.assertEqual(report["status"], "failed")
        self.assertEqual(self.records("rest.jsonl"), [])
        self.assertEqual(report["counts"]["rest_requests"], 0)

    async def test_debug_socket_logger_is_private_without_mutating_application_logging(self):
        root_level = logging.getLogger().level
        logging.getLogger().setLevel(logging.DEBUG)
        try:
            await self.capture()
            logger = self.ws.connect_kwargs["logger"]
            self.assertFalse(logger.propagate)
            self.assertFalse(logger.isEnabledFor(logging.DEBUG))
            self.assertEqual(logging.getLogger().level, logging.DEBUG)
        finally:
            logging.getLogger().setLevel(root_level)

    async def test_operator_cancellation_still_writes_private_partial_manifest(self):
        self.ws.quote_ids = set()
        task = asyncio.create_task(self.capture(duration_seconds=10))
        for _ in range(100):
            if self.ws.connect_kwargs is not None and self.ws.sent:
                break
            await asyncio.sleep(0.001)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        report = json.loads((self.target / "manifest.json").read_text())
        self.assertEqual(report["outcome"], "cancelled")
        self.assertEqual(report["status"], "partial")
        self.assertTrue(self.ws.closed)

    async def test_nq_functional_capture_uses_actual_grouped_ids_without_model_defaults(self):
        self.http.responses["product/find"]["name"] = "NQ"
        self.http.responses["contract/deps"][0]["name"] = "NQZ9"
        report = await self.capture(symbol="NQ", environment="live")
        self.assertEqual(report["target"], {"provider": "tradovate", "symbol": "NQ", "environment": "live"})
        self.assertEqual(report["status"], "complete")
        self.assertEqual(self.http.requests[1][2]["params"], {"name": "NQ"})
        self.assertEqual(report["observed"]["joined_option_quote_contract_ids"], [201, 202])

    async def test_maturity_cap_prefers_front_and_omits_expired_maturities(self):
        self.http.responses["contractMaturity/deps"] = [
            {"id": 9, "expirationDate": "2001-01-01", "isFront": True},
            {"id": 11, "expirationDate": "2099-01-01", "isFront": False},
            {"id": 10, "expirationDate": "2099-12-01", "isFront": True},
        ]
        report = await self.capture(max_maturities=1)
        requests = [options for _, path, options in self.http.requests if path == "contract/deps"]
        self.assertEqual([request["params"] for request in requests], [{"masterid": 10}])
        self.assertTrue(report["selection"]["maturity_selection_limited"])

    async def test_total_byte_cap_includes_manifest_and_preserves_partial_hashes(self):
        self.http.responses["contract/getoptionschain"]["providerMetadata"] = "x" * 20000
        report = await self.capture(max_total_bytes=32768)
        self.assertEqual(report["outcome"], "byte_limit")
        self.assertEqual(report["status"], "partial")
        self.assertTrue(report["truncated"])
        self.assertLessEqual(sum(path.stat().st_size for path in self.target.iterdir()), 32768)
        for filename, receipt in report["files"].items():
            self.assertEqual(receipt["sha256"], hashlib.sha256((self.target / filename).read_bytes()).hexdigest())

    async def test_oversized_contract_response_stops_before_capture_or_subscriptions(self):
        self.http.responses["contract/getoptionschain"]["providerMetadata"] = "x" * 2000
        report = await self.capture(max_frame_bytes=1024)
        self.assertEqual(report["outcome"], "response_size_limit")
        self.assertEqual(report["status"], "partial")
        self.assertEqual(len(self.records("rest.jsonl")), 3)
        self.assertIsNone(self.ws.connect_kwargs)

    async def test_oversized_incoming_wire_frame_stops_and_closes_socket(self):
        self.ws.frames.append("a" + json.dumps([{"e": "md", "d": {"quotes": [], "metadata": "x" * 2000}}]))
        report = await self.capture(max_frame_bytes=1024)
        self.assertEqual(report["outcome"], "frame_size_limit")
        self.assertTrue(self.ws.closed)
        self.assertEqual(report["status"], "partial")

    async def test_failed_heartbeat_stops_capture_and_closes_owned_socket(self):
        original_send = self.ws.send

        async def fail_heartbeat(raw):
            if raw == "[]":
                raise RuntimeError("unlabelled private heartbeat failure")
            await original_send(raw)

        self.ws.send = fail_heartbeat
        with patch("gex_terminal.tradovate_capture.HEARTBEAT_SECONDS", 0.001):
            report = await self.capture()
        self.assertEqual(report["outcome"], "capture_failed")
        self.assertEqual(report["error_type"], "RuntimeError")
        self.assertEqual(report["status"], "partial")
        self.assertTrue(self.ws.closed)
        self.assertNotIn("unlabelled private heartbeat failure", json.dumps(report))

    async def test_stalled_cleanup_has_its_own_bounded_allowance_and_aborts(self):
        aborted = []

        class Transport:
            def abort(self):
                aborted.append(True)

        self.ws.transport = Transport()

        async def stalled_close():
            await asyncio.Future()

        self.ws.close = stalled_close
        with patch("gex_terminal.tradovate_capture._CLEANUP_ALLOWANCE_SECONDS", 0.02):
            report = await self.capture()
        self.assertEqual(aborted, [True])
        self.assertFalse(report["cleanup_completed"])
        self.assertEqual(report["status"], "partial")

    async def test_nested_provider_diagnostics_are_omitted_without_text(self):
        self.http.responses["contract/getoptionschain"]["contracts"][0]["diagnostic"] = {"errorText": "private provider diagnostic"}
        report = await self.capture()
        self.assertEqual(report["status"], "partial")
        self.assertNotIn("private provider diagnostic", (self.target / "rest.jsonl").read_text())
        self.assertEqual(report["counts"]["rest_bodies_omitted"], 1)


if __name__ == "__main__":
    unittest.main()
