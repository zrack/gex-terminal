"""Deterministic protocol tests for the Tradovate market-data adapter.

These tests deliberately model the provider boundary instead of relying on a
live account.  They encode the SockJS/WebSocket acknowledgement ordering and
the nested market-data quote shape that the adapter must translate into the
project's normalized schema-v2 contract.
"""

from __future__ import annotations

import asyncio
from collections import deque
import json
import os
import unittest
from unittest.mock import AsyncMock, patch

from gex_terminal.adapters.tradovate import TradovateAdapter
from gex_terminal.consumer import StatefulGexConsumer
from gex_terminal.engine import IntradayGexEngine


FAKE_CREDENTIALS = {
    "TRADOVATE_NAME": "protocol-test-user",
    "TRADOVATE_PASSWORD": "protocol-test-password",
    "TRADOVATE_APP_ID": "protocol-test-app",
    "TRADOVATE_APP_VERSION": "1.0",
    "TRADOVATE_CID": "100",
    "TRADOVATE_SEC": "protocol-test-secret",
}


def _option_contract() -> dict:
    return {
        "id": 41001,
        "contract_id": "41001",
        "name": "ESU6 C6000",
        "contract_symbol": "ESU6 C6000",
        "symbol": "ES",
        "strike": 6000.0,
        "option_type": "C",
        "expiry": "2026-09-18",
        "expiry_timestamp": "2026-09-18T20:00:00Z",
        "instrument_class": "futures_option",
        "contract_multiplier": 50,
        "iv": 0.20,
    }


def _metadata_by_contract_id() -> dict[str, dict]:
    contract = _option_contract()
    return {contract["contract_id"]: contract}


def _market_data_frame(entries: dict, *, contract_id: int = 41001) -> str:
    payload = [{
        "e": "md",
        "d": {
            "quotes": [{
                "contractId": contract_id,
                "timestamp": "2026-08-04T20:00:00Z",
                "entries": entries,
            }],
        },
    }]
    return "a" + json.dumps(payload)


class RecordingConsumer:
    """Small consumer double that records protocol state transitions."""

    def __init__(self):
        self.messages: list[dict] = []
        self.socket: ScriptedWebSocket | None = None
        self.connection_state = "DISCONNECTED"
        self.subscription_status = "not_subscribed"
        self.connected_at_reads: list[int] = []
        self.subscription_marks: list[tuple[int, int]] = []
        self.subscription_error_count = 0
        self.entitlement_error_count = 0
        self.provider_frame_count = 0
        self.provider_parse_error_count = 0
        self.dropped_message_count = 0
        self.subscribed = asyncio.Event()

    def _reads(self) -> int:
        return self.socket.read_count if self.socket is not None else -1

    async def update_market_state(self, raw_message: str) -> None:
        self.messages.append(json.loads(raw_message))

    def mark_connected(self) -> None:
        self.connection_state = "CONNECTED"
        self.connected_at_reads.append(self._reads())

    def mark_reconnected(self) -> None:
        self.connection_state = "CONNECTED"
        self.connected_at_reads.append(self._reads())

    def mark_disconnected(self) -> None:
        self.connection_state = "DISCONNECTED"

    def mark_subscribed(self, symbol_count: int) -> None:
        self.subscription_status = "subscribed" if symbol_count else "empty"
        self.subscription_marks.append((int(symbol_count), self._reads()))
        self.subscribed.set()

    def mark_subscription_error(self) -> None:
        self.subscription_status = "error"
        self.subscription_error_count += 1

    def record_entitlement_error(self) -> None:
        self.entitlement_error_count += 1

    def record_provider_frame(self) -> None:
        self.provider_frame_count += 1

    def record_provider_parse_error(self) -> None:
        self.provider_parse_error_count += 1

    def record_dropped_message(self) -> None:
        self.dropped_message_count += 1


class ScriptedWebSocket:
    """Fake socket that emits the open frame and request-correlated replies."""

    def __init__(
        self,
        *,
        auth_status: int | None = 200,
        subscription_statuses: tuple[int, ...] = (200, 200),
        block_after_script: bool = False,
    ):
        self.auth_status = auth_status
        self.subscription_statuses = subscription_statuses
        self.block_after_script = block_after_script
        self.frames = deque(["o"])
        self.sent: list[tuple[str, int]] = []
        self.read_count = 0
        self.subscription_request_count = 0
        self.closed = False
        self.blocked = asyncio.Event()

    def __aiter__(self):
        return self

    async def __anext__(self) -> str:
        if self.frames:
            self.read_count += 1
            return self.frames.popleft()
        if self.block_after_script and not self.closed:
            self.blocked.set()
            await asyncio.Event().wait()
        raise StopAsyncIteration

    async def recv(self) -> str:
        return await self.__anext__()

    async def send(self, frame: str) -> None:
        self.sent.append((frame, self.read_count))
        parts = frame.split("\n")
        route = parts[0] if parts else ""
        request_id = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else -1

        if route == "authorize" and self.auth_status is not None:
            self.frames.append(self._response(request_id, self.auth_status))
        elif route == "md/subscribeQuote":
            index = self.subscription_request_count
            self.subscription_request_count += 1
            if index < len(self.subscription_statuses):
                status = self.subscription_statuses[index]
                self.frames.append(self._response(request_id, status))

    async def close(self) -> None:
        self.closed = True

    @staticmethod
    def _response(request_id: int, status: int) -> str:
        body = {"i": request_id, "s": status}
        if status >= 400:
            body["d"] = {"errorText": "Access denied"}
        return "a" + json.dumps([body])


class ScriptedConnector:
    def __init__(self, websocket: ScriptedWebSocket):
        self.websocket = websocket
        self.yielded = False

    def __aiter__(self):
        return self

    async def __aenter__(self) -> ScriptedWebSocket:
        return self.websocket

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def __anext__(self) -> ScriptedWebSocket:
        if self.yielded:
            raise StopAsyncIteration
        self.yielded = True
        return self.websocket


class FakeResponse:
    def __init__(
        self,
        status: int,
        *,
        payload: dict | None = None,
        headers: dict[str, str] | None = None,
        text: str = "",
    ):
        self.status = status
        self.payload = payload or {}
        self.headers = headers or {}
        self._text = text

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def json(self) -> dict:
        return dict(self.payload)

    async def text(self) -> str:
        return self._text


class FakeClientSession:
    def __init__(self, responses: list[FakeResponse]):
        self.responses = deque(responses)
        self.posts: list[tuple[str, dict]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    def post(self, url: str, *, json: dict, **kwargs) -> FakeResponse:
        self.posts.append((url, dict(json)))
        return self.responses.popleft()


class TradovateWebSocketProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def _run_stream(
        self,
        websocket: ScriptedWebSocket,
    ) -> tuple[TradovateAdapter, RecordingConsumer]:
        consumer = RecordingConsumer()
        consumer.socket = websocket
        adapter = TradovateAdapter(
            consumer=consumer,
            target_underlying="ES",
            max_reconnect_attempts=0,
        )
        adapter.access_token = "secret-token"
        adapter.md_access_token = "secret-token"
        adapter.token = "secret-token"
        adapter.discover_option_contracts = AsyncMock(return_value=[_option_contract()])
        adapter.keep_alive = AsyncMock(return_value=None)
        connector = ScriptedConnector(websocket)

        with patch("websockets.connect", return_value=connector):
            await adapter.stream_market_data()
        return adapter, consumer

    async def test_authorization_uses_raw_token_and_gates_subscriptions_on_ack(self):
        websocket = ScriptedWebSocket(auth_status=None)

        _, consumer = await self._run_stream(websocket)

        sent_frames = [frame for frame, _ in websocket.sent]
        self.assertEqual(sent_frames, ["authorize\n1\n\nsecret-token"])
        self.assertEqual(websocket.sent[0][1], 1, "authorize must wait for the open frame")
        self.assertEqual(consumer.subscription_marks, [])
        self.assertEqual(consumer.subscription_status, "not_subscribed")

    async def test_connected_and_subscribed_states_are_ack_gated(self):
        websocket = ScriptedWebSocket()

        _, consumer = await self._run_stream(websocket)

        subscribe_sends = [
            read_count
            for frame, read_count in websocket.sent
            if frame.startswith("md/subscribeQuote\n")
        ]
        self.assertEqual(consumer.connected_at_reads, [2])
        self.assertEqual(len(subscribe_sends), 2)
        self.assertTrue(all(read_count >= 2 for read_count in subscribe_sends))
        self.assertEqual(consumer.subscription_marks, [(2, 4)])

    async def test_subscription_error_ack_sets_error_state(self):
        websocket = ScriptedWebSocket(subscription_statuses=(200, 403))

        _, consumer = await self._run_stream(websocket)

        self.assertEqual(consumer.subscription_status, "error")
        self.assertEqual(consumer.subscription_error_count, 1)
        self.assertGreaterEqual(consumer.entitlement_error_count, 1)

    async def test_cancellation_cleans_up_socket_or_subscriptions(self):
        websocket = ScriptedWebSocket(block_after_script=True)
        consumer = RecordingConsumer()
        consumer.socket = websocket
        adapter = TradovateAdapter(
            consumer=consumer,
            target_underlying="ES",
            max_reconnect_attempts=0,
        )
        adapter.access_token = "secret-token"
        adapter.md_access_token = "secret-token"
        adapter.token = "secret-token"
        adapter.discover_option_contracts = AsyncMock(return_value=[_option_contract()])
        adapter.keep_alive = AsyncMock(return_value=None)
        connector = ScriptedConnector(websocket)

        with patch("websockets.connect", return_value=connector):
            task = asyncio.create_task(adapter.stream_market_data())
            await asyncio.wait_for(consumer.subscribed.wait(), timeout=1.0)
            await asyncio.wait_for(websocket.blocked.wait(), timeout=1.0)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        unsubscribe_frames = [
            frame
            for frame, _ in websocket.sent
            if frame.startswith("md/unsubscribeQuote\n")
        ]
        self.assertTrue(
            unsubscribe_frames or websocket.closed,
            "cancellation must unsubscribe active quotes or close the socket",
        )
        self.assertEqual(consumer.connection_state, "DISCONNECTED")


class TradovateQuoteProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_nested_entries_join_by_contract_id_and_emit_v2_volume(self):
        consumer = RecordingConsumer()
        adapter = TradovateAdapter(consumer=consumer, target_underlying="ES")
        adapter.contract_metadata = _metadata_by_contract_id()

        await adapter._parse_and_route(_market_data_frame({
            "Trade": {"price": 21.25, "size": 3},
            "Bid": {"price": 21.00, "size": 8},
            "Offer": {"price": 21.50, "size": 6},
            "TotalTradeVolume": {"size": 125},
        }))

        self.assertEqual(len(consumer.messages), 1)
        message = consumer.messages[0]
        self.assertEqual(message["type"], "options_volume_tick")
        self.assertEqual(message["schema_version"], 2)
        self.assertEqual(message["provider"], "tradovate")
        self.assertEqual(message["contract_id"], "41001")
        self.assertEqual(message["contract_symbol"], "ESU6 C6000")
        self.assertEqual(message["symbol"], "ES")
        self.assertEqual(message["strike"], 6000.0)
        self.assertEqual(message["option_type"], "C")
        self.assertEqual(message["expiry"], "2026-09-18")
        self.assertEqual(message["instrument_class"], "futures_option")
        self.assertEqual(message["pricing_model"], "black_76")
        self.assertEqual(message["volume"], 125)
        self.assertEqual(message["volume_semantics"], "cumulative")
        self.assertEqual(message["position_source"], "trade_volume")
        self.assertEqual(message["event_time"], "2026-08-04T20:00:00Z")

    async def test_discovered_contract_without_iv_uses_labeled_fallback(self):
        consumer = RecordingConsumer()
        adapter = TradovateAdapter(consumer=consumer, target_underlying="ES")
        metadata = TradovateAdapter._option_metadata({
            "id": 41001,
            "name": "ESU6 C6000",
            "strikePrice": 6000,
            "callPut": "C",
            "expirationTime": "2026-09-18T20:00:00Z",
        })
        adapter.contract_metadata = {"41001": metadata}

        await adapter._parse_and_route(_market_data_frame({
            "TotalTradeVolume": {"size": 125},
        }))

        self.assertNotIn("iv", metadata)
        self.assertEqual(consumer.messages[0]["iv"], adapter.default_iv)
        self.assertEqual(consumer.messages[0]["iv_source"], "configured_default")
        self.assertEqual(adapter._iv_fallback_count, 1)

    async def test_repeated_total_trade_volume_is_idempotent(self):
        consumer = StatefulGexConsumer(
            IntradayGexEngine(multiplier=50),
            target_underlying="ES",
            data_mode="live",
        )
        adapter = TradovateAdapter(consumer=consumer, target_underlying="ES")
        adapter.contract_metadata = _metadata_by_contract_id()
        frame = _market_data_frame({"TotalTradeVolume": {"size": 125}})

        await adapter._parse_and_route(frame)
        await adapter._parse_and_route(frame)

        state = consumer.contract_state[("tradovate", "41001", "trade_volume")]
        self.assertEqual(state["accumulated_volume"], 125)
        self.assertEqual(consumer.chain_state[6000.0]["C"], 125)

    async def test_open_interest_fallback_is_explicitly_labeled(self):
        consumer = RecordingConsumer()
        adapter = TradovateAdapter(consumer=consumer, target_underlying="ES")
        adapter.contract_metadata = _metadata_by_contract_id()

        await adapter._parse_and_route(_market_data_frame({
            "OpenInterest": {"size": 900},
        }))

        self.assertEqual(len(consumer.messages), 1)
        message = consumer.messages[0]
        self.assertEqual(message["volume"], 900)
        self.assertEqual(message["volume_semantics"], "cumulative")
        self.assertEqual(message["position_source"], "open_interest")

    async def test_positive_open_interest_wins_over_zero_total_trade_volume(self):
        consumer = RecordingConsumer()
        adapter = TradovateAdapter(consumer=consumer, target_underlying="ES")
        adapter.contract_metadata = _metadata_by_contract_id()

        await adapter._parse_and_route(_market_data_frame({
            "TotalTradeVolume": {"size": 0},
            "OpenInterest": {"size": 900},
        }))

        self.assertEqual(len(consumer.messages), 2)
        messages = {
            message["position_source"]: message for message in consumer.messages
        }
        self.assertEqual(messages["trade_volume"]["volume"], 0)
        self.assertEqual(messages["open_interest"]["volume"], 900)

    async def test_session_reset_clears_stale_trade_volume_before_oi_fallback(self):
        consumer = StatefulGexConsumer(
            IntradayGexEngine(multiplier=50),
            target_underlying="ES",
            data_mode="live",
        )
        consumer.current_spot = 6000.0
        adapter = TradovateAdapter(consumer=consumer, target_underlying="ES")
        adapter.contract_metadata = _metadata_by_contract_id()

        await adapter._parse_and_route(_market_data_frame({
            "TotalTradeVolume": {"size": 125},
            "OpenInterest": {"size": 900},
        }))
        await adapter._parse_and_route(_market_data_frame({
            "TotalTradeVolume": {"size": 0},
            "OpenInterest": {"size": 950},
        }))

        trade = consumer.contract_state[("tradovate", "41001", "trade_volume")]
        open_interest = consumer.contract_state[("tradovate", "41001", "open_interest")]
        data = await consumer.process_latest_snapshot(days_to_expiry=30.0)
        self.assertEqual(trade["accumulated_volume"], 0)
        self.assertEqual(open_interest["accumulated_volume"], 950)
        self.assertEqual(consumer.cumulative_reset_count, 1)
        self.assertEqual(data["call_volume"], [950.0])
        self.assertEqual(data["position_sources"], ["open_interest"])


class TradovateRestProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_authentication_honors_retry_after_before_retrying_429(self):
        session = FakeClientSession([
            FakeResponse(
                429,
                headers={"Retry-After": "2"},
                text="rate limited",
            ),
            FakeResponse(200, payload={"accessToken": "redacted-access-token"}),
        ])
        sleep = AsyncMock()

        with (
            patch.dict(os.environ, FAKE_CREDENTIALS, clear=True),
            patch("aiohttp.ClientSession", return_value=session),
            patch("gex_terminal.adapters.tradovate.asyncio.sleep", sleep),
        ):
            adapter = TradovateAdapter(consumer=None, target_underlying="ES")
            authenticated = await adapter.authenticate()

        self.assertTrue(authenticated)
        self.assertEqual(adapter.token, "redacted-access-token")
        self.assertEqual(len(session.posts), 2)
        sleep.assert_awaited_once_with(2.0)


if __name__ == "__main__":
    unittest.main()
