"""Synthetic ACK-frame regressions; these do not certify Tradovate payloads."""

from collections import deque
from datetime import datetime, timezone
import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch

from gex_terminal.adapters.tradovate import TradovateAdapter
from gex_terminal.consumer import StatefulGexConsumer
from gex_terminal.engine import IntradayGexEngine
from tests.test_tradovate_protocol import (
    RecordingConsumer, ScriptedConnector, ScriptedWebSocket,
)


REQUEST_ID = 42


def ack(request_id=REQUEST_ID, status=200):
    return {"i": request_id, "s": status}


def frame(*events):
    return "a" + json.dumps(list(events))


def option_contract(root):
    price, multiplier = (6000.0, 50) if root == "ES" else (20000.0, 20)
    return {
        "id": 41001, "contract_id": "41001", "name": f"{root}U6 C{price:g}",
        "contract_symbol": f"{root}U6 C{price:g}", "symbol": root,
        "strike": price, "option_type": "C", "expiry": "2026-09-18",
        "expiry_timestamp": "2026-09-18T20:00:00Z",
        "instrument_class": "futures_option", "contract_multiplier": multiplier,
        "iv": 0.20,
    }


def option_event(quantity, *, seconds=0, include_oi=False):
    entries = {"TotalTradeVolume": {"size": quantity}}
    if include_oi:
        entries["OpenInterest"] = {"size": 900}
    return {"e": "md", "d": {"quotes": [{
        "contractId": 41001, "timestamp": f"2026-08-04T20:00:{seconds:02d}Z",
        "entries": entries,
    }]}}


def underlying_event(root):
    price = 6000.0 if root == "ES" else 20000.0
    return {"e": "md", "d": {"quotes": [{
        "contractId": 31001, "timestamp": "2026-08-04T20:00:00Z",
        "entries": {"Bid": {"price": price - 0.25}, "Offer": {"price": price + 0.25}},
    }]}}


def error_event(kind):
    return {"e": kind, "d": {"errorText": "Synthetic access denied"}}


def configured_adapter(root, consumer):
    adapter = TradovateAdapter(
        consumer, target_underlying=root,
        contract_multiplier=50 if root == "ES" else 20,
        max_reconnect_attempts=0,
    )
    contract = option_contract(root)
    adapter.contract_metadata = {"41001": contract}
    adapter.underlying_contract = {"id": 31001, "name": f"{root}U6"}
    adapter._register_underlying_metadata(adapter.underlying_contract)
    adapter.access_token = "synthetic-token"
    adapter.md_access_token = "synthetic-token"
    adapter.token = "synthetic-token"
    adapter.discover_option_contracts = AsyncMock(return_value=[contract])
    adapter.keep_alive = AsyncMock(return_value=None)
    return adapter


class BundledAckSocket(ScriptedWebSocket):
    """Produce complete response arrays after each request, with no real I/O."""

    def __init__(self, root, *, error_operation=None, error_kind="md/error", error_before=False):
        super().__init__(auth_status=None, subscription_statuses=())
        self.root = root
        self.error_operation = error_operation
        self.error_kind = error_kind
        self.error_before = error_before

    async def send(self, raw):
        await super().send(raw)
        route, request_text, *_ = raw.split("\n")
        request_id = int(request_text)
        operation = "authorize" if route == "authorize" else "subscribe"
        if route not in {"authorize", "md/subscribeQuote"}:
            return
        if operation == self.error_operation:
            payload = [error_event(self.error_kind), ack(request_id)] if self.error_before else [ack(request_id), error_event(self.error_kind)]
        elif operation == "authorize":
            payload = [ack(request_id), underlying_event(self.root)]
        elif self.subscription_request_count == 1:
            payload = [option_event(125, seconds=1), ack(request_id), option_event(250, seconds=2)]
        else:
            payload = [ack(request_id), option_event(375, seconds=3, include_oi=True)]
        self.frames.append(frame(*payload))


class LifecycleConsumer(StatefulGexConsumer):
    """Real normalization/state handling with observable success transitions."""

    def __init__(self, root):
        super().__init__(IntradayGexEngine(multiplier=50 if root == "ES" else 20),
                         target_underlying=root, data_mode="live")
        self.connected_marks = 0
        self.subscription_marks = []

    def mark_connected(self):
        self.connected_marks += 1
        super().mark_connected()

    def mark_subscribed(self, count):
        self.subscription_marks.append(count)
        super().mark_subscribed(count)


class TradovateAckFrameTests(unittest.IsolatedAsyncioTestCase):
    async def test_quotes_before_after_and_between_acknowledgements_are_all_routed(self):
        layouts = {
            "ack_first": (ack(), option_event(125), option_event(250)),
            "ack_middle": (option_event(125), ack(), option_event(250)),
            "ack_last": (option_event(125), option_event(250), ack()),
            "multiple_ack_positions": (ack(), option_event(125), ack(), option_event(250)),
            "unrelated_response_after_ack": (ack(), option_event(125), ack(99, 403), option_event(250)),
        }
        for root in ("ES", "NQ"):
            for operation in ("authorize", "subscribe"):
                for layout, payload in layouts.items():
                    with self.subTest(root=root, operation=operation, layout=layout):
                        consumer = RecordingConsumer()
                        adapter = configured_adapter(root, consumer)
                        socket = ScriptedWebSocket()
                        socket.frames = deque([frame(*payload)])
                        response = await adapter._await_ack(socket, REQUEST_ID, operation=operation)
                        self.assertEqual(response, ack())
                        self.assertEqual([message["volume"] for message in consumer.messages], [125, 250])
                        self.assertEqual([message["symbol"] for message in consumer.messages], [root, root])
                        self.assertEqual(socket.read_count, 1)

    async def test_error_events_before_or_after_ack_prevent_success(self):
        for root in ("ES", "NQ"):
            for operation in ("authorize", "subscribe"):
                for kind in ("error", "md/error"):
                    for before in (True, False):
                        with self.subTest(root=root, operation=operation, kind=kind, before=before):
                            consumer = RecordingConsumer()
                            adapter = configured_adapter(root, consumer)
                            socket = ScriptedWebSocket()
                            payload = [error_event(kind), ack()] if before else [ack(), error_event(kind)]
                            socket.frames = deque([frame(*payload)])
                            with self.assertRaises(PermissionError):
                                await adapter._await_ack(socket, REQUEST_ID, operation=operation)
                            self.assertEqual(consumer.subscription_status, "error")
                            self.assertEqual(consumer.subscription_error_count, 1)
                            self.assertEqual(consumer.entitlement_error_count, 1)

    async def test_matching_non_200_response_rejects_wait(self):
        for root in ("ES", "NQ"):
            for operation in ("authorize", "subscribe"):
                for status in (0, 401, 403, 500):
                    with self.subTest(root=root, operation=operation, status=status):
                        consumer = RecordingConsumer()
                        adapter = configured_adapter(root, consumer)
                        socket = ScriptedWebSocket()
                        socket.frames = deque([frame(ack(status=status))])
                        rejection = PermissionError if status in (401, 403) else RuntimeError
                        with self.assertRaises(rejection):
                            await adapter._await_ack(socket, REQUEST_ID, operation=operation)
                        self.assertEqual(consumer.subscription_status, "error")
                        self.assertEqual(consumer.entitlement_error_count, int(status in (401, 403)))

    async def test_matching_rejection_after_success_still_rejects_frame(self):
        for operation in ("authorize", "subscribe"):
            for status in (403, 500):
                with self.subTest(operation=operation, status=status):
                    consumer = RecordingConsumer()
                    adapter = configured_adapter("ES", consumer)
                    socket = ScriptedWebSocket()
                    socket.frames = deque([frame(ack(), ack(status=status))])
                    rejection = PermissionError if status == 403 else RuntimeError
                    with self.assertRaises(rejection):
                        await adapter._await_ack(socket, REQUEST_ID, operation=operation)
                    self.assertEqual(consumer.subscription_status, "error")

    async def test_duplicate_success_preserves_first_response_and_drains_frame(self):
        first = {**ack(), "d": {"marker": "first"}}
        second = {**ack(), "d": {"marker": "second"}}
        for operation in ("authorize", "subscribe"):
            with self.subTest(operation=operation):
                consumer = RecordingConsumer()
                adapter = configured_adapter("ES", consumer)
                socket = ScriptedWebSocket()
                socket.frames = deque([frame(first, option_event(125), second, option_event(250))])
                response = await adapter._await_ack(socket, REQUEST_ID, operation=operation)
                self.assertEqual(response, first)
                self.assertEqual([message["volume"] for message in consumer.messages], [125, 250])

    async def test_malformed_trailing_quote_does_not_suppress_valid_quote(self):
        for operation in ("authorize", "subscribe"):
            with self.subTest(operation=operation):
                consumer = RecordingConsumer()
                adapter = configured_adapter("ES", consumer)
                socket = ScriptedWebSocket()
                malformed = {"e": "md", "d": {"quotes": ["invalid-quote"]}}
                socket.frames = deque([frame(ack(), malformed, option_event(250))])
                response = await adapter._await_ack(socket, REQUEST_ID, operation=operation)
                self.assertEqual(response, ack())
                self.assertEqual(consumer.provider_parse_error_count, 1)
                self.assertEqual([message["volume"] for message in consumer.messages], [250])

    async def test_unrelated_ids_and_heartbeats_do_not_satisfy_wait(self):
        for operation in ("authorize", "subscribe"):
            with self.subTest(operation=operation):
                consumer = RecordingConsumer()
                adapter = configured_adapter("ES", consumer)
                socket = ScriptedWebSocket()
                socket.frames = deque([
                    "h", "[]", "o", frame(ack(99), option_event(125)),
                    frame(option_event(250)), frame(ack()),
                ])
                response = await adapter._await_ack(socket, REQUEST_ID, operation=operation)
                self.assertEqual(response, ack())
                self.assertEqual(socket.read_count, 6)
                self.assertEqual([message["volume"] for message in consumer.messages], [125, 250])

    async def test_missing_ack_times_out_after_routing_interleaved_data(self):
        for operation in ("authorize", "subscribe"):
            with self.subTest(operation=operation):
                consumer = RecordingConsumer()
                adapter = configured_adapter("ES", consumer)
                adapter.acknowledgement_timeout_seconds = 0.02
                socket = ScriptedWebSocket(block_after_script=True)
                socket.frames = deque(["h", "[]", frame(ack(99), option_event(125))])
                with self.assertRaises(asyncio.TimeoutError):
                    await adapter._await_ack(socket, REQUEST_ID, operation=operation)
                self.assertTrue(socket.blocked.is_set())
                self.assertEqual(consumer.connected_at_reads, [])
                self.assertEqual(consumer.subscription_marks, [])
                self.assertEqual([message["volume"] for message in consumer.messages], [125])

    async def test_complete_scripted_session_retains_trailing_quotes_in_real_consumer(self):
        for root in ("ES", "NQ"):
            with self.subTest(root=root):
                consumer = LifecycleConsumer(root)
                adapter = configured_adapter(root, consumer)
                socket = BundledAckSocket(root)
                with patch("websockets.connect", return_value=ScriptedConnector(socket)):
                    await adapter.stream_market_data()
                self.assertEqual(consumer.current_spot, 6000.0 if root == "ES" else 20000.0)
                self.assertEqual(consumer.connected_marks, 1)
                self.assertEqual(consumer.subscription_marks, [2])
                self.assertEqual(consumer.contract_state[("tradovate", "41001", "trade_volume")]["accumulated_volume"], 375)
                self.assertEqual(consumer.contract_state[("tradovate", "41001", "open_interest")]["accumulated_volume"], 900)
                snapshot = await consumer.process_latest_snapshot(
                    days_to_expiry=30, as_of=datetime(2026, 8, 4, 20, 0, 3, tzinfo=timezone.utc),
                )
                self.assertNotIn("error", snapshot)
                # Existing consumer policy selects positive trade volume while
                # retaining OI as a separate source, rather than adding them.
                self.assertEqual(snapshot["call_volume"], [375.0])
                self.assertEqual(snapshot["position_sources"], ["trade_volume"])
                self.assertTrue(socket.closed)

    async def test_complete_session_error_frame_never_marks_failed_stage_successful(self):
        for root in ("ES", "NQ"):
            for operation in ("authorize", "subscribe"):
                for kind in ("error", "md/error"):
                    for before in (True, False):
                        with self.subTest(root=root, operation=operation, kind=kind, before=before):
                            consumer = LifecycleConsumer(root)
                            adapter = configured_adapter(root, consumer)
                            socket = BundledAckSocket(root, error_operation=operation,
                                                      error_kind=kind, error_before=before)
                            with patch("websockets.connect", return_value=ScriptedConnector(socket)):
                                await adapter.stream_market_data()
                            self.assertEqual(consumer.connected_marks, int(operation == "subscribe"))
                            self.assertEqual(consumer.subscription_marks, [])
                            self.assertEqual(consumer.subscription_status, "error")
                            self.assertGreaterEqual(consumer.entitlement_error_count, 1)
                            self.assertTrue(socket.closed)

    async def test_cancelling_coalesced_quote_await_cleans_up_without_success_marks(self):
        class WaitingConsumer(LifecycleConsumer):
            def __init__(self):
                super().__init__("ES")
                self.started = asyncio.Event()

            async def update_market_state(self, raw):
                self.started.set()
                await asyncio.Event().wait()

        class WaitingSocket(ScriptedWebSocket):
            def __init__(self, operation):
                super().__init__(auth_status=None, subscription_statuses=())
                self.operation = operation

            async def send(self, raw):
                await super().send(raw)
                route, request_text, *_ = raw.split("\n")
                request_id = int(request_text)
                if route == "authorize":
                    payload = [ack(request_id)]
                    if self.operation == "authorize":
                        payload.append(underlying_event("ES"))
                    self.frames.append(frame(*payload))
                elif route == "md/subscribeQuote":
                    self.frames.append(frame(ack(request_id), option_event(125)))

        for operation in ("authorize", "subscribe"):
            with self.subTest(operation=operation):
                consumer = WaitingConsumer()
                adapter = configured_adapter("ES", consumer)
                socket = WaitingSocket(operation)
                with patch("websockets.connect", return_value=ScriptedConnector(socket)):
                    task = asyncio.create_task(adapter.stream_market_data())
                    try:
                        await asyncio.wait_for(consumer.started.wait(), timeout=0.5)
                        self.assertEqual(consumer.connected_marks, int(operation == "subscribe"))
                        self.assertEqual(consumer.subscription_marks, [])
                    finally:
                        task.cancel()
                        with self.assertRaises(asyncio.CancelledError):
                            await task
                self.assertTrue(socket.closed)
                self.assertEqual(consumer.connection_state, "DISCONNECTED")


if __name__ == "__main__":
    unittest.main()
