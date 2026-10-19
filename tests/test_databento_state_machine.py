"""Seeded multi-contract event histories checked against a dictionary oracle.

The oracle models the externally promised OI rule: the latest reference session
wins, and publication time breaks ties within one session. It uses no consumer
helpers, normalized contracts, or provider normalization functions.
"""

import random
import unittest
from datetime import date, datetime, timedelta, timezone

from tests.databento_test_cases import (
    PRODUCTS, adapter_for, definition, feed, quote, statistics, trade,
)


STATE_MACHINE_SEEDS = (35, 2035, 6502, 99035)
EVENTS_PER_SEED = 1500
GENERATED_EVENTS = len(STATE_MACHINE_SEEDS) * EVENTS_PER_SEED
CONTRACTS_PER_SEED = 12
PRECONDITION_EVENTS_PER_SEED = 64
PRECONDITION_EVENTS = len(STATE_MACHINE_SEEDS) * PRECONDITION_EVENTS_PER_SEED


class SessionOracle:
    """Latest-session OI ledger, independent of the application's state shape."""

    def __init__(self):
        self.rows = {}
        self.accepted_adds = 0
        self.accepted_deletes = 0

    def observe(self, instrument, session, published, action, quantity):
        if action == "add" and (
            quantity is None or isinstance(quantity, bool) or not isinstance(quantity, int)
            or quantity < 0 or quantity >= 9223372036854775807
        ):
            return
        stamp = (session, published)
        prior = self.rows.get(instrument)
        if prior is not None and stamp <= prior["stamp"]:
            return
        self.rows[instrument] = {
            "stamp": stamp, "contracts": quantity if action == "add" else 0,
            "deleted": action == "delete",
        }
        if action == "delete":
            self.accepted_deletes += 1
        else:
            self.accepted_adds += 1


class DatabentoStateMachineTests(unittest.IsolatedAsyncioTestCase):
    async def test_seeded_histories_match_independent_session_oracle_after_every_event(self):
        generated = 0
        precondition_events = 0
        for seed_index, seed in enumerate(STATE_MACHINE_SEEDS):
            rng = random.Random(seed)
            root = "ES" if seed_index % 2 == 0 else "NQ"
            adapter, consumer = adapter_for(root)
            instruments = list(range(1001, 1001 + CONTRACTS_PER_SEED))
            oracle = SessionOracle()
            # Arbitrary arrivals before definitions have no usable identity.
            for _ in range(PRECONDITION_EVENTS_PER_SEED // 2):
                instrument = rng.choice(instruments)
                early = (
                    statistics(instrument_id=instrument, quantity=rng.randrange(3000))
                    if rng.choice((True, False)) else
                    trade(instrument_id=instrument, size=rng.randrange(1, 20))
                )
                await feed(adapter, early)
                self.assertFalse(consumer.contract_state)
                precondition_events += 1
            for offset, instrument in enumerate(instruments):
                await feed(adapter, definition(
                    root, PRODUCTS[root][offset], "C" if offset % 2 == 0 else "P",
                    instrument_id=instrument, expiration="2027-03-19T20:00:00Z",
                ))
            # Definitions alone still cannot establish the correct forward price.
            for _ in range(PRECONDITION_EVENTS_PER_SEED // 2):
                await feed(adapter, statistics(instrument_id=rng.choice(instruments)))
                self.assertFalse(consumer.contract_state)
                precondition_events += 1
            self.assertEqual(adapter._open_interest_count, 0)
            self.assertEqual(adapter._dropped_before_underlying_count, PRECONDITION_EVENTS_PER_SEED // 2)
            await feed(adapter, quote(root))
            for instrument in instruments:
                await feed(adapter, trade(instrument_id=instrument, sequence=1))
            trade_state = {
                key: dict(value) for key, value in consumer.contract_state.items()
                if key[2] == "trade_volume"
            }
            history = []
            for event_index in range(EVENTS_PER_SEED):
                mode = rng.choice(("add", "add", "zero", "delete", "duplicate", "old_session", "new_session", "invalid"))
                instrument = rng.choice(instruments)
                prior = oracle.rows.get(instrument)
                if mode == "duplicate" and history:
                    instrument, session, published, action, quantity, sequence = rng.choice(history)
                else:
                    day = rng.randrange(20)
                    if mode == "old_session" and prior is not None:
                        session = prior["stamp"][0] - timedelta(days=1)
                    elif mode == "new_session" and prior is not None:
                        session = prior["stamp"][0] + timedelta(days=1)
                    else:
                        session = date(2026, 8, 1) + timedelta(days=day)
                    # Publication delay varies independently from reference date.
                    published = datetime.combine(session, datetime.min.time(), timezone.utc)
                    published += timedelta(days=rng.randrange(3), seconds=rng.randrange(86400))
                    action = "delete" if mode == "delete" else "add"
                    quantity = 0 if mode == "zero" else rng.randrange(1, 4000)
                    if mode == "invalid":
                        quantity = rng.choice((None, -1, 9223372036854775807))
                    if action == "delete":
                        quantity = rng.choice((None, -1, 9223372036854775807, quantity))
                    # Sequence may restart every reference session; it is not the
                    # OI session/revision ordering authority.
                    sequence = rng.choice((0, 1, rng.randrange(2, 500)))
                oracle.observe(instrument, session, published, action, quantity)
                publication = published.isoformat().replace("+00:00", "Z")
                await feed(adapter, statistics(
                    instrument_id=instrument, quantity=quantity,
                    update_action=1 if action == "add" else 2,
                    ts_ref=session.isoformat(), ts_event=publication, sequence=sequence,
                ))
                history.append((instrument, session, published, action, quantity, sequence))
                with self.subTest(seed=seed, event=event_index, mode=mode):
                    actual_oi = {
                        int(key[1]): {
                            "stamp": (
                                date.fromisoformat(state["open_interest_reference_date"]),
                                datetime.fromisoformat(state["event_time"].replace("Z", "+00:00")),
                            ),
                            "contracts": state["accumulated_volume"],
                            "deleted": state["open_interest_invalidated"],
                        }
                        for key, state in consumer.contract_state.items()
                        if key[2] == "open_interest"
                    }
                    self.assertEqual(actual_oi, oracle.rows)
                    self.assertEqual({
                        key: value for key, value in consumer.contract_state.items()
                        if key[2] == "trade_volume"
                    }, trade_state)
                    self.assertEqual(adapter._open_interest_count, oracle.accepted_adds)
                    self.assertEqual(adapter._open_interest_delete_count, oracle.accepted_deletes)
                    if oracle.rows:
                        expected_status = "observed" if any(
                            not value["deleted"] for value in oracle.rows.values()
                        ) else "invalidated"
                        self.assertEqual(adapter.diagnostics()["open_interest"]["status"], expected_status)
                generated += 1
        self.assertEqual(generated, GENERATED_EVENTS)
        self.assertEqual(precondition_events, PRECONDITION_EVENTS)


if __name__ == "__main__":
    unittest.main()
