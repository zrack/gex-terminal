"""Synthetic, independently enumerated cases for the offline Databento gates."""

from datetime import datetime, timezone

from gex_terminal.adapters.databento import DatabentoAdapter
from gex_terminal.consumer import StatefulGexConsumer
from gex_terminal.engine import IntradayGexEngine


EVENT = "2026-08-06T16:00:00Z"
EXPIRIES = (
    "2026-08-06T20:00:00Z",  # Same-day options retain the intraday expiry time.
    "2026-08-13T20:00:00Z",
    "2026-10-16T20:00:00Z",
)
# CME product families, enumerated independently of the adapter's own table.
PRODUCTS = {
    "ES": ("ES", "EW", "EW1", "EW2", "EW3", "EW4") + tuple(
        f"E{week}{day}" for week in range(1, 6) for day in "ABCD"
    ),
    "NQ": ("NQ", "QNE", "QN1", "QN2", "QN3", "QN4") + tuple(
        f"Q{week}{day}" for week in range(1, 6) for day in "ABCD"
    ),
}
MULTIPLIERS = {"ES": 50.0, "NQ": 20.0}
PRICES = {"ES": 6000.0, "NQ": 22000.0}


def as_datetime(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def nanos(value):
    return int(as_datetime(value).timestamp() * 1_000_000_000)


def adapter_for(root="ES", **kwargs):
    consumer = StatefulGexConsumer(
        IntradayGexEngine(multiplier=MULTIPLIERS[root]),
        target_underlying=root, data_mode="replay",
    )
    return DatabentoAdapter(consumer, target_underlying=root, **kwargs), consumer


def definition(root="ES", product=None, option_type="C", **overrides):
    return {
        "record_type": "definition", "instrument_id": 101,
        "raw_symbol": f"{product or root}Q6 {option_type}{int(PRICES[root])}",
        "asset": product or root, "underlying": f"{root}U6", "underlying_id": 202,
        "strike_price": PRICES[root], "instrument_class": option_type,
        "expiration": EXPIRIES[1], "contract_multiplier": 2147483647,
        "unit_of_measure": "USD", "unit_of_measure_qty": MULTIPLIERS[root],
        **overrides,
    }


def quote(root="ES", **overrides):
    return {
        "record_type": "mbp-1", "instrument_id": 202,
        "bid_px_00": PRICES[root] - 0.25, "ask_px_00": PRICES[root] + 0.25,
        "ts_event": EVENT, **overrides,
    }


def trade(**overrides):
    return {
        "record_type": "trades", "instrument_id": 101,
        "price": 100.0, "size": 7, "side": "B", "iv": 0.22,
        "ts_event": EVENT, **overrides,
    }


def statistics(**overrides):
    return {
        "record_type": "statistics", "instrument_id": 101,
        "stat_type": 9, "quantity": 1200, "update_action": 1,
        "ts_ref": "2026-08-05", "ts_event": EVENT, **overrides,
    }


async def feed(adapter, *records):
    for record in records:
        await adapter._handle_live_record(record)
