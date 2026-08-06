import json
import os
import unittest
from unittest.mock import patch

from gex_terminal.adapters.databento import DatabentoAdapter
from gex_terminal.consumer import StatefulGexConsumer
from gex_terminal.engine import IntradayGexEngine
from gex_terminal.implied_volatility import black_76_option_price
from gex_terminal.market_data_adapter import validate_normalized_message


class _FakeLiveClient:
    def __init__(self, records, **kwargs):
        self.records = list(records)
        self.kwargs = kwargs
        self.subscriptions = []
        self.stopped = False

    def subscribe(self, **kwargs):
        self.subscriptions.append(kwargs)
        return len(self.subscriptions)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self.records:
            raise StopAsyncIteration
        return self.records.pop(0)

    def stop(self):
        self.stopped = True


class DatabentoLiveAdapterTests(unittest.IsolatedAsyncioTestCase):
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
        ])
        self.assertEqual(client.subscriptions[0]["symbols"], ("ES.OPT", "ES.FUT"))
        self.assertEqual(client.subscriptions[1]["symbols"], "ES.v.0")
        self.assertTrue(client.stopped)
        self.assertEqual(adapter._definition_count, 1)
        self.assertEqual(adapter._underlying_quote_count, 1)
        self.assertEqual(adapter._option_trade_count, 1)
        self.assertEqual(adapter._inverted_iv_count, 1)
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


if __name__ == "__main__":
    unittest.main()
