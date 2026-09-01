import asyncio
import json
import os
import unittest
from unittest.mock import patch

from gex_terminal.adapters.databento import DatabentoAdapter, underlying_timing_status
from gex_terminal.consumer import StatefulGexConsumer
from gex_terminal.engine import IntradayGexEngine
from gex_terminal.implied_volatility import black_76_option_price
from gex_terminal.market_data_adapter import validate_normalized_message


class _FakeLiveClient:
    def __init__(
        self,
        records,
        *,
        subscription_errors=None,
        wait_forever=False,
        close_wait_forever=False,
        **kwargs,
    ):
        self.records = list(records)
        self.kwargs = kwargs
        self.subscription_errors = dict(subscription_errors or {})
        self.wait_forever = wait_forever
        self.close_wait_forever = close_wait_forever
        self.subscriptions = []
        self.stopped = False
        self.iteration_started = asyncio.Event()
        self.reconnect_callback = None
        self.reconnect_exception_callback = None

    def add_reconnect_callback(self, callback, exception_callback=None):
        self.reconnect_callback = callback
        self.reconnect_exception_callback = exception_callback

    def subscribe(self, **kwargs):
        self.subscriptions.append(kwargs)
        error = self.subscription_errors.get(kwargs["schema"])
        if error is not None:
            raise error
        return len(self.subscriptions)

    def __aiter__(self):
        return self

    async def __anext__(self):
        self.iteration_started.set()
        if not self.records:
            if self.wait_forever:
                await asyncio.Event().wait()
            raise StopAsyncIteration
        item = self.records.pop(0)
        if item == "__reconnect__":
            self.reconnect_callback("last-event", "reconnect-start")
            return await self.__anext__()
        if isinstance(item, BaseException):
            raise item
        return item

    def stop(self):
        self.stopped = True

    async def wait_for_close(self, timeout=None):
        if self.close_wait_forever:
            await asyncio.Event().wait()


class DatabentoLiveAdapterTests(unittest.IsolatedAsyncioTestCase):
    def test_underlying_timing_status_is_fail_closed(self):
        aligned = underlying_timing_status(
            option_event_time="2026-08-06T16:00:01Z",
            underlying_event_time="2026-08-06T16:00:00Z",
            maximum_age_seconds=2.0,
        )
        stale = underlying_timing_status(
            option_event_time="2026-08-06T16:00:03Z",
            underlying_event_time="2026-08-06T16:00:00Z",
            maximum_age_seconds=2.0,
        )
        future = underlying_timing_status(
            option_event_time="2026-08-06T15:59:59Z",
            underlying_event_time="2026-08-06T16:00:00Z",
            maximum_age_seconds=2.0,
        )
        self.assertEqual(aligned["status"], "aligned")
        self.assertEqual(aligned["age_ms"], 1000.0)
        self.assertEqual(stale["status"], "stale_underlying_price")
        self.assertEqual(future["status"], "future_underlying_price")

    async def test_mixed_live_records_invert_iv_and_reach_consumer(self):
        event_time = "2026-08-06T16:00:00Z"
        expiry = "2026-08-20T20:00:00Z"
        option_price = black_76_option_price(
            futures_price=6000.0,
            strike=6050.0,
            time_to_expiry_years=14.1666666667 / 365.0,
            risk_free_rate=0.045,
            volatility=0.22,
            option_type="C",
        )
        records = [
            {
                "record_type": "definition",
                "instrument_id": 101,
                "raw_symbol": "ESQ6 C6050",
                "asset": "ES",
                "underlying": "ES",
                "underlying_id": 202,
                "strike_price": 6050.0,
                "instrument_class": "C",
                "expiration": expiry,
                "contract_multiplier": 50,
            },
            {
                "record_type": "mbp-1",
                "instrument_id": 202,
                "bid_px_00": 5999.75,
                "ask_px_00": 6000.25,
                "ts_event": event_time,
            },
            {
                "record_type": "trades",
                "instrument_id": 101,
                "price": option_price,
                "size": 7,
                "side": "B",
                "sequence": 11,
                "ts_event": event_time,
            },
        ]
        client = _FakeLiveClient(records)
        consumer = StatefulGexConsumer(
            IntradayGexEngine(multiplier=50),
            target_underlying="ES",
            data_mode="live",
        )
        adapter = DatabentoAdapter(
            consumer,
            target_underlying="ES",
            risk_free_rate=0.045,
            live_client_factory=lambda **kwargs: client,
        )

        with patch.dict(os.environ, {"DATABENTO_API_KEY": "db-test-key"}, clear=False):
            adapter.api_key = os.environ["DATABENTO_API_KEY"]
            await adapter.stream_market_data()

        self.assertEqual([row["schema"] for row in client.subscriptions], [
            "definition",
            "mbp-1",
            "trades",
            "statistics",
        ])
        self.assertEqual(client.subscriptions[0]["symbols"], ("ES.OPT", "ES.FUT"))
        self.assertEqual(client.subscriptions[1]["symbols"], "ES.v.0")
        self.assertNotIn("snapshot", client.subscriptions[1])
        self.assertTrue(client.stopped)
        self.assertEqual(adapter._definition_count, 1)
        self.assertEqual(adapter._underlying_quote_count, 1)
        self.assertEqual(adapter._option_trade_count, 1)
        self.assertEqual(adapter._inverted_iv_count, 1)
        diagnostics = adapter.diagnostics()
        self.assertEqual(diagnostics["open_interest"]["status"], "unavailable")
        self.assertEqual(diagnostics["model_inputs"]["iv_inversion_attempts"], 1)
        self.assertEqual(diagnostics["model_inputs"]["iv_inversion_failures"], 0)
        self.assertEqual(diagnostics["model_inputs"]["underlying_age_observations"], 1)
        self.assertEqual(diagnostics["model_inputs"]["underlying_age_ms_mean"], 0.0)
        self.assertTrue(diagnostics["lifecycle"]["clean_stop"])
        self.assertTrue(
            diagnostics["lifecycle"]["reconnect_callback_registered"]
        )
        self.assertFalse(diagnostics["lifecycle"]["reconnect_observed"])
        self.assertNotIn("db-test-key", json.dumps(diagnostics))
        state = consumer.contract_state[("databento", "101", "trade_volume")]
        self.assertEqual(state["iv_source"], "black_76_inverted")
        self.assertAlmostEqual(state["iv"], 0.22, places=6)
        self.assertEqual(state["iv_provenance"]["option_price_source"], "databento_trade")
        self.assertEqual(consumer.fallback_iv_tick_count, 0)
        snapshot = await consumer.process_latest_snapshot(days_to_expiry=14.0)
        self.assertEqual(snapshot["iv_source_counts"], {"black_76_inverted": 1})
        self.assertEqual(snapshot["iv_inversion_methods"], ["black_76_bisection"])

    async def test_drops_option_for_a_different_futures_underlying(self):
        client = _FakeLiveClient([
            {
                "record_type": "definition",
                "instrument_id": 101,
                "raw_symbol": "ESZ6 C6050",
                "asset": "ES",
                "underlying_id": 303,
                "strike_price": 6050.0,
                "instrument_class": "C",
                "expiration": "2026-12-18T20:00:00Z",
            },
            {
                "record_type": "mbp-1",
                "instrument_id": 202,
                "bid_px_00": 5999.75,
                "ask_px_00": 6000.25,
                "ts_event": "2026-08-06T16:00:00Z",
            },
            {
                "record_type": "trades",
                "instrument_id": 101,
                "price": 100.0,
                "size": 2,
                "side": "B",
                "ts_event": "2026-08-06T16:00:01Z",
            },
        ])
        consumer = StatefulGexConsumer(
            IntradayGexEngine(multiplier=50),
            target_underlying="ES",
            data_mode="live",
        )
        adapter = DatabentoAdapter(
            consumer,
            target_underlying="ES",
            live_client_factory=lambda **kwargs: client,
        )
        adapter.api_key = "db-test-key"

        await adapter.stream_market_data()

        self.assertEqual(adapter._dropped_underlying_mismatch_count, 1)
        self.assertEqual(adapter._option_trade_count, 0)
        self.assertEqual(consumer.contract_state, {})

    def test_inverted_message_provenance_validates(self):
        message = DatabentoAdapter._normalize_option_trade_record(
            {
                "instrument_id": 101,
                "price": 100.0,
                "size": 1,
                "side": "A",
                "ts_event": "2026-08-06T16:00:00Z",
            },
            {
                101: {
                    "instrument_id": 101,
                    "raw_symbol": "NQQ6 P19000",
                    "underlying": "NQ",
                    "strike": 19000.0,
                    "option_type": "P",
                    "expiry": "2026-08-20",
                    "expiry_timestamp": "2026-08-20T20:00:00Z",
                }
            },
            underlying_price=19500.0,
            underlying_event_time="2026-08-06T15:59:59Z",
            risk_free_rate=0.045,
        )

        validate_normalized_message(message)
        self.assertIn(message["iv_source"], {"black_76_inverted", "configured_default"})
        self.assertNotIn("api", json.dumps(message).lower())

    async def test_statistics_open_interest_is_observed_separately_from_trades(self):
        client = _FakeLiveClient([
            {
                "record_type": "definition",
                "instrument_id": 101,
                "raw_symbol": "ESZ6 C6050",
                "asset": "ES",
                "strike_price": 6050.0,
                "instrument_class": "C",
                "expiration": "2026-12-18T20:00:00Z",
            },
            {
                "record_type": "statistics",
                "instrument_id": 101,
                "stat_type": 9,
                "quantity": 1200,
                "ts_event": "2026-08-06T16:00:00Z",
                "sequence": 50,
            },
        ])
        consumer = StatefulGexConsumer(
            IntradayGexEngine(multiplier=50),
            target_underlying="ES",
            data_mode="live",
        )
        adapter = DatabentoAdapter(
            consumer,
            target_underlying="ES",
            live_client_factory=lambda **kwargs: client,
        )
        adapter.api_key = "db-test-key"

        await adapter.stream_market_data()

        diagnostics = adapter.diagnostics()
        self.assertEqual(diagnostics["open_interest"]["status"], "observed")
        self.assertEqual(diagnostics["open_interest"]["provider_observations"], 1)
        self.assertEqual(diagnostics["open_interest"]["observations"], 1)
        self.assertIn(("databento", "101", "open_interest"), consumer.contract_state)
        self.assertNotIn(("databento", "101", "trade_volume"), consumer.contract_state)

    async def test_native_provider_iv_is_not_counted_as_fallback(self):
        client = _FakeLiveClient([
            {
                "record_type": "definition",
                "instrument_id": 101,
                "raw_symbol": "ESZ6 C6050",
                "asset": "ES",
                "strike_price": 6050.0,
                "instrument_class": "C",
                "expiration": "2026-12-18T20:00:00Z",
                "iv": 0.24,
            },
            {
                "record_type": "trades",
                "instrument_id": 101,
                "price": 100.0,
                "size": 1,
                "side": "B",
                "sequence": 1,
                "ts_event": "2026-08-06T16:00:00Z",
            },
        ])
        consumer = StatefulGexConsumer(
            IntradayGexEngine(multiplier=50),
            target_underlying="ES",
            data_mode="live",
        )
        adapter = DatabentoAdapter(
            consumer,
            target_underlying="ES",
            live_client_factory=lambda **kwargs: client,
        )
        adapter.api_key = "db-test-key"

        await adapter.stream_market_data()

        diagnostics = adapter.diagnostics()["model_inputs"]
        self.assertEqual(adapter._provider_iv_count, 1)
        self.assertEqual(adapter._inverted_iv_count, 0)
        self.assertEqual(adapter._iv_fallback_count, 0)
        self.assertEqual(diagnostics["provider_iv_ticks"], 1)
        self.assertEqual(diagnostics["fallback_iv_ticks"], 0)

    async def test_statistics_entitlement_rejection_degrades_oi_without_stopping_core(self):
        client = _FakeLiveClient(
            [],
            subscription_errors={
                "statistics": PermissionError("statistics entitlement denied")
            },
        )
        consumer = StatefulGexConsumer(
            IntradayGexEngine(multiplier=50),
            target_underlying="ES",
            data_mode="live",
        )
        adapter = DatabentoAdapter(
            consumer,
            target_underlying="ES",
            live_client_factory=lambda **kwargs: client,
        )
        adapter.api_key = "db-test-key"

        await adapter.stream_market_data()

        diagnostics = adapter.diagnostics()
        self.assertEqual(
            diagnostics["open_interest"]["status"], "entitlement_denied"
        )
        self.assertEqual(diagnostics["subscriptions"]["failed_schemas"], ["statistics"])
        self.assertEqual(diagnostics["subscriptions"]["ids_observed"], 3)
        self.assertEqual(consumer.entitlement_error_count, 1)
        self.assertEqual(consumer.subscription_status, "subscribed")
        self.assertTrue(diagnostics["lifecycle"]["stream_completed"])

    async def test_required_subscription_failure_is_reported_and_stopped(self):
        client = _FakeLiveClient(
            [], subscription_errors={"trades": RuntimeError("subscription failed")}
        )
        consumer = StatefulGexConsumer(
            IntradayGexEngine(multiplier=50),
            target_underlying="ES",
            data_mode="live",
        )
        adapter = DatabentoAdapter(
            consumer,
            target_underlying="ES",
            live_client_factory=lambda **kwargs: client,
        )
        adapter.api_key = "db-test-key"

        with self.assertRaisesRegex(RuntimeError, "subscription failed"):
            await adapter.stream_market_data()

        diagnostics = adapter.diagnostics()
        self.assertEqual(diagnostics["lifecycle"]["state"], "subscription_error")
        self.assertEqual(diagnostics["lifecycle"]["subscription_error_count"], 1)
        self.assertEqual(diagnostics["lifecycle"]["provider_error_count"], 0)
        self.assertEqual(diagnostics["subscriptions"]["failed_schemas"], ["trades"])
        self.assertEqual(consumer.subscription_status, "error")
        self.assertTrue(client.stopped)

    async def test_malformed_frame_is_counted_before_provider_error_and_clean_stop(self):
        class MalformedRecord:
            @property
            def instrument_id(self):
                raise ValueError("malformed instrument id")

        client = _FakeLiveClient([
            MalformedRecord(),
            {"record_type": "error", "message": "provider rejected request"},
        ])
        consumer = StatefulGexConsumer(
            IntradayGexEngine(multiplier=50),
            target_underlying="ES",
            data_mode="live",
        )
        adapter = DatabentoAdapter(
            consumer,
            target_underlying="ES",
            live_client_factory=lambda **kwargs: client,
        )
        adapter.api_key = "db-test-key"

        with self.assertRaisesRegex(RuntimeError, "gateway returned an error"):
            await adapter.stream_market_data()

        diagnostics = adapter.diagnostics()
        self.assertEqual(consumer.provider_parse_error_count, 1)
        self.assertEqual(diagnostics["lifecycle"]["provider_error_count"], 1)
        self.assertEqual(diagnostics["lifecycle"]["subscription_error_count"], 0)
        self.assertTrue(diagnostics["lifecycle"]["clean_stop"])

    async def test_nonfinite_provider_numeric_is_counted_as_malformed_not_transport(self):
        client = _FakeLiveClient([
            {
                "record_type": "definition",
                "instrument_id": float("inf"),
                "raw_symbol": "ESZ6 C6050",
                "strike_price": 6050.0,
                "instrument_class": "C",
                "expiration": "2026-12-18T20:00:00Z",
            },
        ])
        consumer = StatefulGexConsumer(
            IntradayGexEngine(multiplier=50),
            target_underlying="ES",
            data_mode="live",
        )
        adapter = DatabentoAdapter(
            consumer,
            target_underlying="ES",
            live_client_factory=lambda **kwargs: client,
        )
        adapter.api_key = "db-test-key"

        await adapter.stream_market_data()

        lifecycle = adapter.diagnostics()["lifecycle"]
        self.assertEqual(consumer.provider_parse_error_count, 1)
        self.assertEqual(lifecycle["provider_error_count"], 0)
        self.assertTrue(lifecycle["clean_stop"])

    async def test_cancellation_stops_and_disconnects_without_reconnect_claim(self):
        client = _FakeLiveClient([], wait_forever=True)
        consumer = StatefulGexConsumer(
            IntradayGexEngine(multiplier=50),
            target_underlying="ES",
            data_mode="live",
        )
        adapter = DatabentoAdapter(
            consumer,
            target_underlying="ES",
            live_client_factory=lambda **kwargs: client,
        )
        adapter.api_key = "db-test-key"
        task = asyncio.create_task(adapter.stream_market_data())
        await client.iteration_started.wait()

        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task

        diagnostics = adapter.diagnostics()
        self.assertTrue(diagnostics["lifecycle"]["cancelled"])
        self.assertEqual(diagnostics["lifecycle"]["state"], "cancelled")
        self.assertTrue(diagnostics["lifecycle"]["clean_stop"])
        self.assertEqual(diagnostics["lifecycle"]["disconnect_count"], 0)
        self.assertFalse(diagnostics["lifecycle"]["reconnect_observed"])
        self.assertEqual(consumer.connection_state, "DISCONNECTED")

    async def test_provider_disconnect_is_recorded_without_reconnect_claim(self):
        client = _FakeLiveClient([ConnectionError("provider disconnected")])
        consumer = StatefulGexConsumer(
            IntradayGexEngine(multiplier=50),
            target_underlying="ES",
            data_mode="live",
        )
        adapter = DatabentoAdapter(
            consumer,
            target_underlying="ES",
            live_client_factory=lambda **kwargs: client,
        )
        adapter.api_key = "db-test-key"

        with self.assertRaisesRegex(ConnectionError, "provider disconnected"):
            await adapter.stream_market_data()

        diagnostics = adapter.diagnostics()["lifecycle"]
        self.assertEqual(diagnostics["disconnect_count"], 1)
        self.assertEqual(diagnostics["provider_error_count"], 1)
        self.assertEqual(diagnostics["last_provider_error_category"], "transport")
        self.assertFalse(diagnostics["reconnect_observed"])
        self.assertTrue(diagnostics["clean_stop"])

    async def test_sequence_integrity_and_iv_failure_are_observable(self):
        records = [
            {
                "record_type": "definition",
                "instrument_id": 101,
                "raw_symbol": "ESZ6 C6050",
                "asset": "ES",
                "underlying_id": 202,
                "strike_price": 6050.0,
                "instrument_class": "C",
                "expiration": "2026-12-18T20:00:00Z",
            },
            {
                "record_type": "mbp-1",
                "instrument_id": 202,
                "bid_px_00": 5999.75,
                "ask_px_00": 6000.25,
                "ts_event": "2026-08-06T16:00:00Z",
            },
        ]
        for sequence in (10, 12, 12, 11):
            records.append({
                "record_type": "trades",
                "instrument_id": 101,
                "price": 99999.0,
                "size": 1,
                "side": "B",
                "sequence": sequence,
                "ts_event": "2026-08-06T16:00:01Z",
            })
        client = _FakeLiveClient(records)
        consumer = StatefulGexConsumer(
            IntradayGexEngine(multiplier=50),
            target_underlying="ES",
            data_mode="live",
        )
        adapter = DatabentoAdapter(
            consumer,
            target_underlying="ES",
            live_client_factory=lambda **kwargs: client,
        )
        adapter.api_key = "db-test-key"

        await adapter.stream_market_data()

        diagnostics = adapter.diagnostics()
        self.assertEqual(
            diagnostics["sequence_integrity"],
            {
                "observed": 4,
                "venue_sequence_discontinuities": 1,
                "venue_sequence_skipped_values": 1,
                "maybe_bad_book_flags": 0,
                "duplicates": 1,
                "out_of_order": 1,
            },
        )
        self.assertEqual(diagnostics["model_inputs"]["iv_inversion_attempts"], 4)
        self.assertEqual(diagnostics["model_inputs"]["iv_inversion_failures"], 4)
        self.assertEqual(
            diagnostics["model_inputs"]["iv_inversion_status_counts"],
            {"outside_no_arbitrage_bounds": 4},
        )

    async def test_open_interest_statuses_cover_not_requested_and_unsupported(self):
        for request_open_interest, error, expected in (
            (False, None, "not_requested"),
            (True, ValueError("unknown schema statistics"), "unsupported"),
        ):
            with self.subTest(expected=expected):
                errors = {"statistics": error} if error is not None else None
                client = _FakeLiveClient([], subscription_errors=errors)
                consumer = StatefulGexConsumer(
                    IntradayGexEngine(multiplier=50),
                    target_underlying="ES",
                    data_mode="live",
                )
                adapter = DatabentoAdapter(
                    consumer,
                    target_underlying="ES",
                    request_open_interest=request_open_interest,
                    live_client_factory=lambda **kwargs: client,
                )
                adapter.api_key = "db-test-key"

                await adapter.stream_market_data()

                self.assertEqual(
                    adapter.diagnostics()["open_interest"]["status"], expected
                )

    async def test_reconnect_callback_and_post_reconnect_data_are_observable(self):
        client = _FakeLiveClient([
            "__reconnect__",
            {"record_type": "control"},
        ])
        consumer = StatefulGexConsumer(
            IntradayGexEngine(multiplier=50),
            target_underlying="ES",
            data_mode="live",
        )
        adapter = DatabentoAdapter(
            consumer,
            target_underlying="ES",
            live_client_factory=lambda **kwargs: client,
        )
        adapter.api_key = "db-test-key"

        await adapter.stream_market_data()

        lifecycle = adapter.diagnostics()["lifecycle"]
        self.assertTrue(lifecycle["reconnect_callback_registered"])
        self.assertEqual(lifecycle["reconnect_events_observed"], 1)
        self.assertEqual(lifecycle["reconnect_boundaries_observed"], 1)
        self.assertEqual(lifecycle["post_reconnect_frames"], 1)
        self.assertTrue(lifecycle["reconnect_observed"])
        self.assertTrue(lifecycle["resubscription_observed"])
        self.assertEqual(consumer.reconnect_count, 1)

    async def test_bad_book_flag_is_distinct_from_trade_sequence_discontinuity(self):
        client = _FakeLiveClient([
            {
                "record_type": "trades",
                "instrument_id": 101,
                "sequence": 10,
                "flags": 0,
            },
            {
                "record_type": "trades",
                "instrument_id": 101,
                "sequence": 12,
                "flags": 4,
            },
        ])
        consumer = StatefulGexConsumer(
            IntradayGexEngine(multiplier=50),
            target_underlying="ES",
            data_mode="live",
        )
        adapter = DatabentoAdapter(
            consumer,
            target_underlying="ES",
            live_client_factory=lambda **kwargs: client,
        )
        adapter.api_key = "db-test-key"

        await adapter.stream_market_data()

        sequence = adapter.diagnostics()["sequence_integrity"]
        self.assertEqual(sequence["venue_sequence_discontinuities"], 1)
        self.assertEqual(sequence["maybe_bad_book_flags"], 1)

    async def test_generic_provider_error_does_not_claim_oi_specific_denial(self):
        client = _FakeLiveClient([
            {"record_type": "error", "message": "entitlement denied"},
        ])
        consumer = StatefulGexConsumer(
            IntradayGexEngine(multiplier=50),
            target_underlying="ES",
            data_mode="live",
        )
        adapter = DatabentoAdapter(
            consumer,
            target_underlying="ES",
            live_client_factory=lambda **kwargs: client,
        )
        adapter.api_key = "db-test-key"

        with self.assertRaisesRegex(RuntimeError, "gateway returned an error"):
            await adapter.stream_market_data()

        self.assertEqual(
            adapter.diagnostics()["open_interest"]["status"],
            "unavailable",
        )

    async def test_close_wait_timeout_fails_clean_stop_closed(self):
        client = _FakeLiveClient([], close_wait_forever=True)
        consumer = StatefulGexConsumer(
            IntradayGexEngine(multiplier=50),
            target_underlying="ES",
            data_mode="live",
        )
        adapter = DatabentoAdapter(
            consumer,
            target_underlying="ES",
            live_client_factory=lambda **kwargs: client,
        )
        adapter.api_key = "db-test-key"

        with patch(
            "gex_terminal.adapters.databento.DEFAULT_DATABENTO_STOP_TIMEOUT_SECONDS",
            0.01,
        ):
            await adapter.stream_market_data()

        lifecycle = adapter.diagnostics()["lifecycle"]
        self.assertFalse(lifecycle["clean_stop"])
        self.assertEqual(lifecycle["stop_error_count"], 1)


if __name__ == "__main__":
    unittest.main()
