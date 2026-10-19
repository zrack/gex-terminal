"""Constructed parameter boundaries, never observed provider-payload evidence."""

import copy
import json
import unittest
from unittest.mock import AsyncMock

from gex_terminal.adapters.tradovate import TradovateAdapter
from gex_terminal.adapters.tradovate import _backoff_delay
from tests.test_tradovate_protocol import RecordingConsumer, _option_contract


def frame(*quotes):
    return "a" + json.dumps([{"e": "md", "d": {"quotes": list(quotes)}}])


def option_quote():
    return {"contractId": 41001, "timestamp": "2026-08-04T20:00:00Z",
            "entries": {"TotalTradeVolume": {"size": 25}}}


def adapter_and_consumer():
    consumer = RecordingConsumer()
    adapter = TradovateAdapter(consumer)
    adapter.contract_metadata = {"41001": _option_contract()}
    return adapter, consumer


class TradovateParameterTests(unittest.TestCase):
    def test_nonboolean_auth_capabilities_are_not_reported_as_granted(self):
        for value in ("false", "true", 0, 1, {}, [], None):
            with self.subTest(value=value):
                adapter = TradovateAdapter(None)
                adapter._apply_token_payload({"accessToken": "synthetic", "hasLive": value,
                                              "hasMarketData": value})
                self.assertEqual(adapter.auth_capabilities, {"has_live": None, "has_market_data": None})
        for value in (True, False):
            adapter._apply_token_payload({"accessToken": "synthetic", "hasLive": value,
                                          "hasMarketData": value})
            self.assertEqual(adapter.auth_capabilities, {"has_live": value, "has_market_data": value})

    def test_constructor_rejects_invalid_finite_numeric_limits(self):
        for field in ("contract_multiplier", "default_iv", "request_timeout_seconds",
                      "acknowledgement_timeout_seconds"):
            for value in (True, False, 0, -1, float("nan"), float("inf"), "bad"):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    TradovateAdapter(None, **{field: value})
        for value in (True, -1, float("nan"), float("inf")):
            with self.subTest(delay=value), self.assertRaises(ValueError):
                TradovateAdapter(None, reconnect_base_delay_seconds=value)

    def test_constructor_requires_integral_counts_and_preserves_zero_reconnects(self):
        for field in ("max_option_contracts", "max_http_attempts", "max_reconnect_attempts"):
            invalid = [True, -1, 1.5, "1.5", float("nan"), float("inf")]
            if field != "max_reconnect_attempts":
                invalid.append(0)
            for value in invalid:
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    TradovateAdapter(None, **{field: value})
        adapter = TradovateAdapter(None, max_option_contracts="2", max_http_attempts=2.0,
                                   max_reconnect_attempts=0, reconnect_base_delay_seconds=0)
        self.assertEqual(adapter.max_option_contracts, 2)
        self.assertEqual(adapter.max_http_attempts, 2)
        self.assertEqual(adapter.max_reconnect_attempts, 0)
        self.assertEqual(adapter.reconnect_base_delay_seconds, 0)

    def test_retry_after_cannot_make_retry_delay_unbounded(self):
        class Response:
            def __init__(self, value):
                self.headers = {"Retry-After": value}

        adapter = TradovateAdapter(None)
        for value, expected in (("2", 2), ("999999", 30), ("inf", 4),
                                ("nan", 4), ("-1", 4), ("bad", 4)):
            with self.subTest(value=value):
                self.assertEqual(adapter._retry_delay(Response(value), 2), expected)
        self.assertEqual(adapter._retry_delay(Response("bad"), 10_000), 30)
        self.assertEqual(_backoff_delay(0, 10_000), 0)
        self.assertEqual(_backoff_delay(1e-4, 10_000), 30)
        self.assertAlmostEqual(_backoff_delay(0.25, 3), 2)


class TradovateQuoteParameterTests(unittest.IsolatedAsyncioTestCase):
    async def test_boolean_response_id_cannot_satisfy_an_integer_request(self):
        adapter, consumer = adapter_and_consumer()
        socket = type("Socket", (), {})()
        socket.recv = AsyncMock(side_effect=[
            'a[{"i":true,"s":200}]', 'a[{"i":1,"s":200}]',
        ])
        result = await adapter._await_ack(socket, 1, operation="authorize")
        self.assertIs(type(result["i"]), int)
        self.assertEqual(socket.recv.await_count, 2)

    async def test_boolean_fractional_and_infinite_ack_statuses_never_succeed(self):
        for status in (True, 200.5, "200.5", float("nan"), float("inf")):
            with self.subTest(status=status):
                adapter, consumer = adapter_and_consumer()
                socket = type("Socket", (), {})()
                socket.recv = AsyncMock(return_value="a" + json.dumps([{"i": 1, "s": status}]))
                with self.assertRaisesRegex(RuntimeError, "invalid status"):
                    await adapter._await_ack(socket, 1, operation="authorize")
                self.assertEqual(consumer.subscription_error_count, 1)

    async def test_nonintegral_and_nonfinite_quantities_are_quarantined_not_truncated(self):
        for field in ("TotalTradeVolume", "OpenInterest"):
            for value in (True, -1, 1.5, "1.5", float("nan"), float("inf"), "bad"):
                with self.subTest(field=field, value=value):
                    adapter, consumer = adapter_and_consumer()
                    bad = option_quote()
                    bad["entries"] = {field: {"size": value}}
                    await adapter._parse_and_route(frame(bad, option_quote()))
                    self.assertEqual(len(consumer.messages), 1)
                    self.assertEqual(consumer.messages[0]["volume"], 25)
                    self.assertEqual(consumer.provider_parse_error_count, 1)

    async def test_invalid_strike_iv_multiplier_and_sequence_cannot_enter_state(self):
        cases = []
        for key in ("strikePrice", "iv"):
            cases.extend((key, value) for value in (True, 0, -1, float("nan"), float("inf")))
        cases.extend(("sequence", value) for value in (True, -1, 1.5, "1.5", float("inf")))
        for key, value in cases:
            with self.subTest(field=key, value=value):
                adapter, consumer = adapter_and_consumer()
                bad = option_quote()
                bad[key] = value
                await adapter._parse_and_route(frame(bad, option_quote()))
                self.assertEqual(len(consumer.messages), 1)
                self.assertEqual(consumer.provider_parse_error_count, 1)
        for value in (True, 0, -1, float("nan"), float("inf")):
            with self.subTest(multiplier=value):
                adapter, consumer = adapter_and_consumer()
                adapter.contract_metadata["41001"]["contract_multiplier"] = value
                await adapter._parse_and_route(frame(option_quote()))
                self.assertEqual(consumer.messages, [])
                self.assertEqual(consumer.provider_parse_error_count, 1)

    async def test_invalid_underlying_prices_leave_later_valid_quote_available(self):
        for value in (True, 0, -1, float("nan"), float("inf")):
            with self.subTest(value=value):
                adapter, consumer = adapter_and_consumer()
                bad = {"symbol": "ES", "entries": {"Trade": {"price": value}},
                       "timestamp": "2026-08-04T20:00:00Z"}
                await adapter._parse_and_route(frame(bad, option_quote()))
                self.assertEqual(len(consumer.messages), 1)
                self.assertEqual(consumer.messages[0]["type"], "options_volume_tick")
                self.assertEqual(consumer.provider_parse_error_count, 1)

    async def test_zero_cumulative_values_and_integral_numeric_strings_are_valid(self):
        adapter, consumer = adapter_and_consumer()
        quote = option_quote()
        quote.update({"sequence": "0", "iv": "0.2"})
        quote["entries"] = {"TotalTradeVolume": {"size": "0"},
                            "OpenInterest": {"size": 100.0}}
        await adapter._parse_and_route(frame(quote))
        self.assertEqual(consumer.provider_parse_error_count, 0)
        self.assertEqual({item["position_source"]: item["volume"] for item in consumer.messages},
                         {"trade_volume": 0, "open_interest": 100})
        self.assertTrue(all(item["sequence"] == 0 for item in consumer.messages))

    async def test_missing_or_naive_clock_remains_explicit_receipt_fallback(self):
        for timestamp in (None, "bad", "2026-08-04T20:00:00"):
            with self.subTest(timestamp=timestamp):
                adapter, consumer = adapter_and_consumer()
                quote = option_quote()
                quote["timestamp"] = timestamp
                await adapter._parse_and_route(frame(quote))
                self.assertEqual(adapter._receipt_time_fallback_count, 1)
                self.assertEqual(consumer.messages[0]["event_time"], consumer.messages[0]["received_time"])

    async def test_rejected_quote_does_not_log_untrusted_provider_values(self):
        adapter, consumer = adapter_and_consumer()
        quote = option_quote()
        private_value = "unstructured-private-provider-sentinel"
        quote["entries"]["TotalTradeVolume"]["size"] = private_value
        original = copy.deepcopy(quote)
        with self.assertLogs("gex_terminal.adapters.tradovate", "WARNING") as recorded:
            await adapter._parse_and_route(frame(quote, option_quote()))
        self.assertNotIn(private_value, "\n".join(recorded.output))
        self.assertEqual(quote, original)
        self.assertEqual(len(consumer.messages), 1)


if __name__ == "__main__":
    unittest.main()
