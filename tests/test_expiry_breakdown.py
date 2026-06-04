import asyncio
import json
import unittest

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


if __name__ == "__main__":
    unittest.main()
