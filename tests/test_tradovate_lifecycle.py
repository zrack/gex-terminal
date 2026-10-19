"""Synthetic HTTP/socket lifecycle coverage; no provider account is contacted."""

from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime, timedelta, timezone
import json
import os
import unittest
from unittest.mock import AsyncMock, patch

from gex_terminal.adapters.tradovate import TradovateAdapter


_CREDENTIALS = {
    "TRADOVATE_NAME": "offline-user",
    "TRADOVATE_PASSWORD": "offline-password",
    "TRADOVATE_APP_ID": "offline-app",
    "TRADOVATE_APP_VERSION": "1.0",
    "TRADOVATE_CID": "123",
    "TRADOVATE_SEC": "offline-client-secret",
}


class _Response:
    def __init__(self, status, payload=None, headers=None):
        self.status = status
        self.payload = payload or {}
        self.headers = headers or {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def json(self):
        return self.payload


class _Session:
    def __init__(self, responses):
        self.responses = deque(responses)
        self.requests = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    def post(self, url, **kwargs):
        self.requests.append(("POST", url, kwargs))
        return self.responses.popleft()

    def get(self, url, **kwargs):
        self.requests.append(("GET", url, kwargs))
        return self.responses.popleft()


class _Consumer:
    def __init__(self):
        self.transitions = []
        self.entitlement_errors = 0

    def mark_connected(self):
        self.transitions.append("connected")

    def mark_reconnected(self):
        self.transitions.append("reconnected")

    def mark_disconnected(self):
        self.transitions.append("disconnected")

    def mark_subscribed(self, count):
        self.transitions.append(("subscribed", count))

    def mark_subscription_error(self):
        self.transitions.append("subscription_error")

    def record_entitlement_error(self):
        self.entitlement_errors += 1


class _Socket:
    def __init__(self, *, interrupt=False, block=False):
        self.frames = deque(["o"])
        self.sent = []
        self.interrupt = interrupt
        self.block = block
        self.waiting = asyncio.Event()
        self.closed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.frames:
            return self.frames.popleft()
        await asyncio.sleep(0)  # Let session-owned background tasks start.
        if self.interrupt:
            raise ConnectionResetError("scripted connection interruption")
        if self.block:
            self.waiting.set()
            await asyncio.Event().wait()
        raise StopAsyncIteration

    async def recv(self):
        return await self.__anext__()

    async def send(self, frame):
        self.sent.append(frame)
        route, _, request_id = frame.partition("\n")
        if route in {"authorize", "md/subscribeQuote"}:
            self.frames.append("a" + json.dumps([{
                "i": int(request_id.split("\n", 1)[0]), "s": 200,
            }]))

    async def close(self):
        self.closed = True


class TradovateAuthenticationLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_rejected_or_challenged_authentication_does_not_expose_response(self):
        cases = (
            (_Response(401, {"errorText": "private-provider-account"}), "http_401"),
            (_Response(403, {"errorText": "private-provider-account"}), "http_403"),
            (_Response(200, {"p-ticket": "private-challenge"}), "challenge_required"),
            (_Response(200, {"errorText": "private-provider-account"}), "no_access_token"),
        )
        for response, reason in cases:
            with self.subTest(reason=reason):
                session = _Session([response])
                with (
                    patch.dict(os.environ, _CREDENTIALS, clear=True),
                    patch("aiohttp.ClientSession", return_value=session),
                    self.assertLogs("gex_terminal.adapters.tradovate", level="ERROR") as logs,
                ):
                    adapter = TradovateAdapter(None)
                    self.assertFalse(await adapter.authenticate())
                self.assertEqual(adapter.auth_failure_reason, reason)
                self.assertIsNone(adapter.access_token)
                self.assertIsNone(adapter.md_access_token)
                self.assertEqual(len(session.requests), 1)
                self.assertNotIn("private-provider-account", "\n".join(logs.output))
                self.assertNotIn("private-challenge", "\n".join(logs.output))

    async def test_authentication_retry_exhaustion_is_bounded(self):
        for status in (429, 500, 502, 503, 504):
            with self.subTest(status=status):
                session = _Session([_Response(status) for _ in range(3)])
                with (
                    patch.dict(os.environ, _CREDENTIALS, clear=True),
                    patch("aiohttp.ClientSession", return_value=session),
                    patch("gex_terminal.adapters.tradovate.asyncio.sleep", new_callable=AsyncMock) as sleep,
                    self.assertLogs("gex_terminal.adapters.tradovate", level="ERROR"),
                ):
                    adapter = TradovateAdapter(None, max_http_attempts=3)
                    self.assertFalse(await adapter.authenticate())
                self.assertEqual(adapter.auth_failure_reason, f"http_{status}")
                self.assertEqual(len(session.requests), 3)
                self.assertEqual([call.args[0] for call in sleep.await_args_list], [1.0, 2.0])

    async def test_distinct_tokens_and_capabilities_survive_renewal(self):
        session = _Session([_Response(200, {
            "accessToken": "new-rest-token", "mdAccessToken": "new-md-token",
            "expirationTime": "2026-10-18T20:00:00Z",
            "hasLive": False, "hasMarketData": True,
        })])
        adapter = TradovateAdapter(None)
        adapter._apply_token_payload({
            "accessToken": "old-rest-token", "mdAccessToken": "old-md-token",
            "hasLive": True, "hasMarketData": False,
        })
        with patch("aiohttp.ClientSession", return_value=session) as create_session:
            self.assertTrue(await adapter.renew_access_token())
        self.assertEqual(create_session.call_args.kwargs["headers"], {
            "Authorization": "Bearer old-rest-token",
        })
        self.assertEqual(session.requests[0][0], "GET")
        self.assertTrue(session.requests[0][1].endswith("/auth/renewAccessToken"))
        self.assertEqual(adapter.access_token, "new-rest-token")
        self.assertEqual(adapter.token, "new-rest-token")
        self.assertEqual(adapter.md_access_token, "new-md-token")
        self.assertEqual(adapter.auth_capabilities, {"has_live": False, "has_market_data": True})
        self.assertEqual(adapter.expiration_time, datetime(2026, 10, 18, 20, tzinfo=timezone.utc))

    async def test_successful_authentication_keeps_rest_and_market_data_tokens_distinct(self):
        session = _Session([_Response(200, {
            "accessToken": "auth-rest-token", "mdAccessToken": "auth-md-token",
            "hasLive": True, "hasMarketData": False,
        })])
        with (
            patch.dict(os.environ, _CREDENTIALS, clear=True),
            patch("aiohttp.ClientSession", return_value=session),
        ):
            adapter = TradovateAdapter(None)
            self.assertTrue(await adapter.authenticate())
        self.assertEqual(adapter.access_token, "auth-rest-token")
        self.assertEqual(adapter.md_access_token, "auth-md-token")
        self.assertEqual(adapter.auth_capabilities, {"has_live": True, "has_market_data": False})
        self.assertTrue(session.requests[0][1].endswith("/auth/accesstokenrequest"))
        self.assertEqual(session.requests[0][2]["json"]["password"], "offline-password")

    async def test_renewal_failure_preserves_tokens_and_records_entitlement(self):
        for response in (_Response(403), _Response(200, {"errorText": "private-account"})):
            with self.subTest(status=response.status):
                consumer = _Consumer()
                adapter = TradovateAdapter(consumer)
                adapter._apply_token_payload({"accessToken": "rest-token", "mdAccessToken": "md-token"})
                session = _Session([response])
                with (
                    patch("aiohttp.ClientSession", return_value=session),
                    self.assertLogs("gex_terminal.adapters.tradovate", level="WARNING") as logs,
                ):
                    self.assertFalse(await adapter.renew_access_token())
                self.assertEqual((adapter.access_token, adapter.md_access_token), ("rest-token", "md-token"))
                self.assertEqual(consumer.entitlement_errors, int(response.status == 403))
                self.assertNotIn("private-account", "\n".join(logs.output))

    async def test_renewal_without_token_never_opens_http_session(self):
        with patch("aiohttp.ClientSession") as create_session:
            self.assertFalse(await TradovateAdapter(None).renew_access_token())
        create_session.assert_not_called()

    async def test_renewal_loop_renews_only_near_expiry_and_marks_failure(self):
        for expiry, should_renew in (
            (None, False),
            (datetime.now(timezone.utc) + timedelta(hours=1), False),
            (datetime.now(timezone.utc) + timedelta(minutes=5), True),
        ):
            with self.subTest(expiry=expiry):
                consumer = _Consumer()
                adapter = TradovateAdapter(consumer)
                adapter.expiration_time = expiry
                adapter.renew_access_token = AsyncMock(return_value=False)
                with patch("gex_terminal.adapters.tradovate.asyncio.sleep", new_callable=AsyncMock) as sleep:
                    sleep.side_effect = [None, asyncio.CancelledError]
                    with self.assertRaises(asyncio.CancelledError):
                        await adapter._token_renewal_loop()
                self.assertEqual(adapter.renew_access_token.await_count, int(should_renew))
                self.assertEqual("subscription_error" in consumer.transitions, should_renew)


class TradovateSocketLifecycleTests(unittest.IsolatedAsyncioTestCase):
    def _adapter(self, consumer, **kwargs):
        adapter = TradovateAdapter(consumer, reconnect_base_delay_seconds=0, **kwargs)
        adapter._apply_token_payload({"accessToken": "rest-only-token", "mdAccessToken": "market-only-token"})
        adapter.discover_option_contracts = AsyncMock(return_value=[{"id": 41001}])
        adapter.keep_alive = AsyncMock()
        adapter._token_renewal_loop = AsyncMock()
        return adapter

    async def test_reconnect_reauthorizes_and_resubscribes_then_unsubscribes_every_socket(self):
        consumer = _Consumer()
        adapter = self._adapter(consumer, max_reconnect_attempts=1)
        sockets = [_Socket(interrupt=True), _Socket()]
        with (
            patch("websockets.connect", side_effect=sockets) as connect,
            self.assertLogs("gex_terminal.adapters.tradovate", level="WARNING"),
        ):
            await adapter.stream_market_data()
        self.assertEqual(connect.call_count, 2)
        adapter.discover_option_contracts.assert_awaited_once()
        self.assertEqual(consumer.transitions.count("connected"), 1)
        self.assertEqual(consumer.transitions.count("reconnected"), 1)
        self.assertEqual(consumer.transitions.count(("subscribed", 2)), 2)
        for socket in sockets:
            self.assertTrue(socket.closed)
            self.assertIn("market-only-token", socket.sent[0])
            self.assertNotIn("rest-only-token", "\n".join(socket.sent))
            subscriptions = [json.loads(frame.split("\n\n", 1)[1])["symbol"]
                             for frame in socket.sent if frame.startswith("md/subscribeQuote\n")]
            removals = [json.loads(frame.split("\n\n", 1)[1])["symbol"]
                        for frame in socket.sent if frame.startswith("md/unsubscribeQuote\n")]
            self.assertEqual(subscriptions, ["ES", 41001])
            self.assertEqual(removals, subscriptions)
        self.assertEqual(adapter._active_subscriptions, [])
        self.assertEqual(consumer.transitions[-1], "disconnected")

    async def test_connection_retry_exhaustion_does_not_log_exception_text(self):
        consumer = _Consumer()
        adapter = self._adapter(consumer, max_reconnect_attempts=2)
        with (
            patch("websockets.connect", side_effect=OSError("private-provider-account")) as connect,
            patch("gex_terminal.adapters.tradovate.asyncio.sleep", new_callable=AsyncMock) as sleep,
            self.assertLogs("gex_terminal.adapters.tradovate", level="WARNING") as logs,
        ):
            await adapter.stream_market_data()
        self.assertEqual(connect.call_count, 3)
        self.assertEqual(sleep.await_count, 2)
        self.assertEqual(consumer.transitions.count("disconnected"), 3)
        self.assertNotIn("private-provider-account", "\n".join(logs.output))

    async def test_cancellation_awaits_both_owned_background_tasks_and_unsubscribes_all(self):
        consumer = _Consumer()
        adapter = self._adapter(consumer, max_reconnect_attempts=0)
        socket = _Socket(block=True)
        stopped = []

        async def background(name):
            try:
                await asyncio.Event().wait()
            finally:
                stopped.append(name)

        adapter.keep_alive = lambda _: background("heartbeat")
        adapter._token_renewal_loop = lambda: background("renewal")
        with patch("websockets.connect", return_value=socket):
            task = asyncio.create_task(adapter.stream_market_data())
            await asyncio.wait_for(socket.waiting.wait(), 1)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await asyncio.wait_for(task, 1)
        self.assertCountEqual(stopped, ["heartbeat", "renewal"])
        removals = [frame for frame in socket.sent if frame.startswith("md/unsubscribeQuote\n")]
        self.assertEqual(len(removals), 2)
        self.assertTrue(socket.closed)
        self.assertEqual(adapter._active_subscriptions, [])
        self.assertEqual(consumer.transitions[-1], "disconnected")

    async def test_failed_background_task_does_not_skip_other_task_and_socket_cleanup(self):
        consumer = _Consumer()
        adapter = self._adapter(consumer, max_reconnect_attempts=0)
        socket = _Socket(block=True)
        renewal_stopped = asyncio.Event()

        async def failing_heartbeat(_):
            await asyncio.sleep(0)
            raise OSError("private-background-provider-body")

        async def renewal():
            try:
                await asyncio.Event().wait()
            finally:
                renewal_stopped.set()

        adapter.keep_alive = failing_heartbeat
        adapter._token_renewal_loop = renewal
        task = asyncio.create_task(adapter._run_websocket_session(socket, ["ES", 41001]))
        await asyncio.wait_for(socket.waiting.wait(), 1)
        await asyncio.sleep(0)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await asyncio.wait_for(task, 1)
        self.assertTrue(renewal_stopped.is_set())
        self.assertTrue(socket.closed)
        self.assertEqual(adapter._active_subscriptions, [])
        self.assertEqual(len([frame for frame in socket.sent
                              if frame.startswith("md/unsubscribeQuote\n")]), 2)
        self.assertEqual(consumer.transitions[-1], "disconnected")

    async def test_background_failure_on_eof_is_safe_and_retryable_after_full_cleanup(self):
        consumer = _Consumer()
        adapter = self._adapter(consumer, max_reconnect_attempts=0)
        socket = _Socket()
        renewal_stopped = asyncio.Event()

        async def failing_heartbeat(_):
            raise OSError("private-background-provider-body")

        async def renewal():
            try:
                await asyncio.Event().wait()
            finally:
                renewal_stopped.set()

        adapter.keep_alive = failing_heartbeat
        adapter._token_renewal_loop = renewal
        with self.assertLogs("gex_terminal.adapters.tradovate", level="WARNING") as logs:
            with self.assertRaisesRegex(RuntimeError, "^Tradovate background task failed$"):
                await adapter._run_websocket_session(socket, ["ES", 41001])
        self.assertTrue(renewal_stopped.is_set())
        self.assertTrue(socket.closed)
        self.assertEqual(adapter._active_subscriptions, [])
        self.assertIn("subscription_error", consumer.transitions)
        self.assertNotIn("private-background-provider-body", "\n".join(logs.output))
        self.assertEqual(consumer.transitions[-1], "disconnected")

    async def test_handled_caller_exception_does_not_hide_new_background_failure(self):
        consumer = _Consumer()
        adapter = self._adapter(consumer, max_reconnect_attempts=0)
        socket = _Socket()

        async def failing_heartbeat(_):
            raise OSError("private-background-provider-body")

        adapter.keep_alive = failing_heartbeat
        try:
            raise ValueError("already handled caller failure")
        except ValueError:
            with self.assertLogs("gex_terminal.adapters.tradovate", level="WARNING"):
                with self.assertRaisesRegex(RuntimeError, "^Tradovate background task failed$"):
                    await adapter._run_websocket_session(socket, ["ES", 41001])
        self.assertTrue(socket.closed)
        self.assertEqual(adapter._active_subscriptions, [])
        self.assertIn("subscription_error", consumer.transitions)
        self.assertEqual(consumer.transitions[-1], "disconnected")


if __name__ == "__main__":
    unittest.main()
