import asyncio
import json
import unittest
from datetime import datetime, timezone

from gex_terminal.consumer import StatefulGexConsumer
from gex_terminal.engine import IntradayGexEngine


def _consumer():
    engine = IntradayGexEngine(multiplier=50)
    consumer = StatefulGexConsumer(engine, target_underlying="ES", data_mode="demo")
    consumer.current_spot = 100.0
    return consumer


async def _tick(consumer, strike, option_type, volume, iv=0.2, expiry=None):
    payload = {
        "type": "options_volume_tick",
        "strike": strike,
        "option_type": option_type,
        "volume": volume,
        "iv": iv,
    }
    if expiry is not None:
        payload["expiry"] = expiry
    await consumer.update_market_state(json.dumps(payload))


async def _v2_tick(
    consumer,
    *,
    contract_id,
    expiry,
    expiry_timestamp,
    strike,
    option_type,
    volume,
    sequence,
):
    await consumer.update_market_state(json.dumps({
        "schema_version": 2,
        "type": "options_volume_tick",
        "provider": "test",
        "contract_id": contract_id,
        "symbol": "ES",
        "expiry": expiry,
        "expiry_timestamp": expiry_timestamp,
        "strike": strike,
        "option_type": option_type,
        "volume": volume,
        "iv": 0.2,
        "iv_source": "provider",
        "instrument_class": "futures_option",
        "volume_semantics": "incremental",
        "position_source": "trade_volume",
        "event_time": "2026-06-18T14:00:00Z",
        "sequence": sequence,
    }))


class ExpiryBreakdownTests(unittest.TestCase):
    def test_single_bucket_when_no_expiry_tags(self):
        async def run():
            consumer = _consumer()
            await _tick(consumer, 100.0, "C", 500)
            await _tick(consumer, 100.0, "P", 200)
            breakdown = await consumer.process_expiry_breakdown(days_to_expiry=0.25)
            return breakdown

        breakdown = asyncio.run(run())
        self.assertEqual(len(breakdown), 1)
        self.assertIn("0.25DTE", breakdown)

    def test_groups_by_expiry_tag(self):
        async def run():
            consumer = _consumer()
            await _tick(consumer, 100.0, "C", 500, expiry="2026-06-05")
            await _tick(consumer, 100.0, "P", 200, expiry="2026-06-05")
            await _tick(consumer, 100.0, "C", 300, expiry="2026-06-12")
            breakdown = await consumer.process_expiry_breakdown(days_to_expiry=0.25)
            return breakdown

        breakdown = asyncio.run(run())
        self.assertEqual(set(breakdown), {"2026-06-05", "2026-06-12"})
        # the call-only second expiry should be net positive
        self.assertGreater(breakdown["2026-06-12"], 0.0)

    def test_empty_state_returns_empty_breakdown(self):
        async def run():
            consumer = _consumer()
            consumer.current_spot = 0.0
            return await consumer.process_expiry_breakdown(days_to_expiry=0.25)

        self.assertEqual(asyncio.run(run()), {})

    def test_contract_aware_breakdown_prices_each_expiry_before_aggregation(self):
        async def run():
            consumer = _consumer()
            await _v2_tick(
                consumer,
                contract_id="near-C",
                expiry="2026-06-18",
                expiry_timestamp="2026-06-18T20:00:00Z",
                strike=100,
                option_type="C",
                volume=100,
                sequence=1,
            )
            await _v2_tick(
                consumer,
                contract_id="far-C",
                expiry="2026-07-18",
                expiry_timestamp="2026-07-18T20:00:00Z",
                strike=100,
                option_type="C",
                volume=100,
                sequence=2,
            )
            as_of = datetime(2026, 6, 18, 14, tzinfo=timezone.utc)
            all_data = await consumer.process_latest_snapshot(
                days_to_expiry=0.25,
                as_of=as_of,
            )
            near = await consumer.process_latest_snapshot(
                days_to_expiry=0.25,
                as_of=as_of,
                expiry_filter="0dte",
            )
            far = await consumer.process_latest_snapshot(
                days_to_expiry=0.25,
                as_of=as_of,
                expiry_filter="2026-07-18",
            )
            breakdown = await consumer.process_expiry_breakdown(days_to_expiry=0.25)
            return all_data, near, far, breakdown

        all_data, near, far, breakdown = asyncio.run(run())
        self.assertEqual(near["selected_contract_count"], 1)
        self.assertEqual(far["selected_contract_count"], 1)
        self.assertNotAlmostEqual(near["total_net_gex"], far["total_net_gex"])
        self.assertAlmostEqual(
            all_data["total_net_gex"],
            sum(breakdown.values()),
            places=6,
        )


if __name__ == "__main__":
    unittest.main()
