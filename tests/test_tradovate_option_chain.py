"""Constructed Tradovate scenarios test software behavior, not observed payloads."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlparse

from gex_terminal.adapters.tradovate import TradovateAdapter
from gex_terminal.consumer import StatefulGexConsumer
from gex_terminal.engine import IntradayGexEngine
from gex_terminal.package_data import provider_fixture_path


FIXTURE_NAME = "tradovate_option_chain_synthetic.json"
FORBIDDEN_KEYS = {
    "accountid", "account_id", "token", "accesstoken", "mdaccesstoken",
    "credential", "credentials", "password", "secret", "apikey", "api_key",
}


def _assert_no_secret_keys(value, path="fixture"):
    """Guard known secret-bearing fields; this is not a general PII sanitizer."""
    if isinstance(value, dict):
        for key, nested in value.items():
            if key.casefold() in FORBIDDEN_KEYS:
                raise AssertionError(f"Forbidden field at {path}.{key}")
            _assert_no_secret_keys(nested, f"{path}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _assert_no_secret_keys(nested, f"{path}[{index}]")


def _scenarios():
    return json.loads(provider_fixture_path(FIXTURE_NAME).read_text(encoding="utf-8"))


class _Response:
    status = 200

    def __init__(self, payload):
        self.payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def json(self):
        return deepcopy(self.payload)


class _DiscoverySession:
    """Record actual REST requests while replacing only the HTTP boundary."""

    def __init__(self, scenario, *, product_present=True, suggestions=None, wrapper=None):
        self.scenario = scenario
        self.product_present = product_present
        self.suggestions = suggestions
        self.wrapper = wrapper
        self.requests = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def get(self, url, *, params):
        path = urlparse(url).path
        self.requests.append((path, dict(params)))
        if path == "/v1/product/find":
            rows = [self.scenario["product"]] if self.product_present else []
        elif path == "/v1/contractMaturity/deps":
            rows = self.scenario["maturities"]
        elif path == "/v1/contract/deps":
            rows = self.scenario["contracts_by_maturity"][str(params["masterid"])]
        elif path == "/v1/contract/suggest":
            rows = self.scenario["suggestions"] if self.suggestions is None else self.suggestions
        else:
            raise AssertionError(f"Unexpected discovery route {path}")
        return _Response({self.wrapper: rows} if self.wrapper else rows)


class _RecordingConsumer(StatefulGexConsumer):
    def __init__(self, scenario):
        super().__init__(
            IntradayGexEngine(multiplier=scenario["contract_multiplier"]),
            target_underlying=scenario["symbol"], data_mode="live",
        )
        self.normalized = []

    async def update_market_state(self, raw_message):
        self.normalized.append(json.loads(raw_message))
        return await super().update_market_state(raw_message)


class TradovateSyntheticFixtureTests(unittest.TestCase):
    def test_fixture_provenance_and_package_location_are_explicit(self):
        previous = Path.cwd()
        with tempfile.TemporaryDirectory() as directory:
            try:
                os.chdir(directory)
                payload = _scenarios()
            finally:
                os.chdir(previous)
        self.assertEqual(payload["schema"], "gex-terminal.synthetic-tradovate-chain-scenarios.v1")
        self.assertEqual(payload["provenance"]["origin"], "constructed")
        self.assertIs(payload["provenance"]["observed_provider_payload"], False)
        self.assertEqual({case["symbol"] for case in payload["cases"]}, {"ES", "NQ"})
        _assert_no_secret_keys(payload)

    def test_secret_key_guard_rejects_injected_nested_fields_without_matching_prose(self):
        _assert_no_secret_keys({"source": "No credentials, password, or secret data."})
        for key in sorted(FORBIDDEN_KEYS):
            with self.subTest(key=key), self.assertRaisesRegex(AssertionError, "Forbidden field"):
                _assert_no_secret_keys({"rows": [{"nested": {key.upper(): "injected"}}]})


class TradovateSyntheticChainTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _adapter(scenario, *, max_option_contracts=60):
        consumer = _RecordingConsumer(scenario)
        adapter = TradovateAdapter(
            consumer, target_underlying=scenario["symbol"],
            contract_multiplier=scenario["contract_multiplier"],
            max_option_contracts=max_option_contracts,
        )
        adapter.access_token = "synthetic-discovery-token"
        return adapter, consumer

    async def _discover(self, scenario, *, max_option_contracts=60, **session_options):
        adapter, consumer = self._adapter(scenario, max_option_contracts=max_option_contracts)
        session = _DiscoverySession(scenario, **session_options)
        with patch("aiohttp.ClientSession", return_value=session):
            contracts = await adapter.discover_option_contracts()
        return adapter, consumer, session, contracts

    async def test_discovery_requests_join_deduplicate_and_register_each_identity(self):
        for scenario in _scenarios()["cases"]:
            with self.subTest(symbol=scenario["symbol"]):
                adapter, _, session, contracts = await self._discover(scenario)
                self.assertEqual(len(contracts), 5)
                self.assertEqual(len({row["id"] for row in contracts}), 5)
                self.assertEqual(session.requests, [
                    ("/v1/product/find", {"name": scenario["symbol"]}),
                    ("/v1/contractMaturity/deps", {"masterid": scenario["product"]["id"]}),
                    *[("/v1/contract/deps", {"masterid": row["id"]}) for row in scenario["maturities"]],
                    ("/v1/contract/suggest", {"t": scenario["symbol"], "l": 180}),
                ])
                expiries = set()
                for contract in contracts:
                    metadata = adapter.contract_metadata[str(contract["id"])]
                    self.assertIs(metadata, adapter.contract_metadata[contract["name"]])
                    self.assertEqual(metadata["multiplier"], scenario["contract_multiplier"])
                    self.assertEqual(metadata["instrument_class"], "futures_option")
                    self.assertIn(metadata["option_type"], ("C", "P"))
                    self.assertTrue(metadata["expiry_timestamp"].endswith("20:00:00Z"))
                    expiries.add(metadata["expiry"])
                self.assertEqual(expiries, {"2026-09-18", "2026-12-18"})
                future = adapter.underlying_contract
                self.assertIsNotNone(future)
                self.assertEqual(adapter.contract_metadata[str(future["id"])]["instrument_class"], "future")

    async def test_discovery_caps_options_after_deduplication_and_accepts_list_wrappers(self):
        for scenario in _scenarios()["cases"]:
            scenario = deepcopy(scenario)
            first_maturity = str(scenario["maturities"][0]["id"])
            rows = scenario["contracts_by_maturity"][first_maturity]
            rows.insert(2, deepcopy(rows[1]))
            for wrapper in (None, "items", "contracts", "data"):
                with self.subTest(symbol=scenario["symbol"], wrapper=wrapper):
                    adapter, _, session, contracts = await self._discover(
                        scenario, max_option_contracts=2, wrapper=wrapper,
                    )
                    self.assertEqual(len(contracts), 2)
                    self.assertEqual(len({row["id"] for row in contracts}), 2)
                    option_ids = {
                        value["contract_id"] for value in adapter.contract_metadata.values()
                        if value["instrument_class"] == "futures_option"
                    }
                    self.assertEqual(option_ids, {str(row["id"]) for row in contracts})
                    self.assertEqual(session.requests[-1][1]["l"], 100)

    async def test_discovery_uses_complete_suggestions_when_product_lookup_is_empty(self):
        for scenario in _scenarios()["cases"]:
            suggestion = deepcopy(scenario["suggestions"][-1])
            suggestion.update(expirationDate="2026-12-18", expirationTime="2026-12-18T20:00:00Z")
            with self.subTest(symbol=scenario["symbol"]):
                adapter, _, session, contracts = await self._discover(
                    scenario, product_present=False, suggestions=[suggestion],
                )
                self.assertEqual(contracts, [suggestion])
                self.assertEqual([path for path, _ in session.requests], ["/v1/product/find", "/v1/contract/suggest"])
                metadata = adapter.contract_metadata[str(suggestion["id"])]
                self.assertEqual(metadata["expiry"], "2026-12-18")
                self.assertEqual(metadata["expiry_timestamp"], "2026-12-18T20:00:00Z")

    async def test_discovery_requires_authentication_before_creating_http_session(self):
        adapter, _ = self._adapter(_scenarios()["cases"][0])
        adapter.access_token = None
        with patch("aiohttp.ClientSession") as session, self.assertRaisesRegex(RuntimeError, "before authentication"):
            await adapter.discover_option_contracts()
        session.assert_not_called()

    async def test_discovered_chains_drive_v2_consumer_engine_without_double_counting(self):
        for scenario in _scenarios()["cases"]:
            with self.subTest(symbol=scenario["symbol"]):
                adapter, consumer, _, contracts = await self._discover(scenario)
                consumer.mark_connected()
                consumer.mark_subscribed(len(contracts) + 1)
                frame = "a" + json.dumps(scenario["quote_events"])
                await adapter._parse_and_route(frame)
                await adapter._parse_and_route(frame)
                expected_spot = scenario["quote_events"][0]["d"]["quotes"][0]["entries"]["Trade"]["price"]
                self.assertEqual(consumer.current_spot, expected_spot)
                self.assertEqual(len(consumer.contract_state), 10)
                for index, contract in enumerate(contracts, 1):
                    for source, quantity in (("trade_volume", index * 10), ("open_interest", index * 100)):
                        state = consumer.contract_state[("tradovate", str(contract["id"]), source)]
                        self.assertEqual(state["accumulated_volume"], quantity)
                        self.assertEqual(state["contract_multiplier"], scenario["contract_multiplier"])
                        self.assertEqual(state["pricing_model"], "black_76")
                        expected_iv = contract.get("impliedVol", adapter.default_iv)
                        self.assertEqual(state["iv"], expected_iv)
                        self.assertEqual(state["strike"], contract["strikePrice"])
                options = [message for message in consumer.normalized if message["type"] == "options_volume_tick"]
                self.assertEqual({message["schema_version"] for message in options}, {2})
                self.assertEqual({message["volume_semantics"] for message in options}, {"cumulative"})
                self.assertEqual({message["position_source"] for message in options}, {"trade_volume", "open_interest"})
                self.assertEqual({message["option_type"] for message in options}, {"C", "P"})
                fallback = [message for message in options if message["iv_source"] == "configured_default"]
                self.assertEqual(len(fallback), 4)
                self.assertTrue(all(message["iv"] == adapter.default_iv for message in fallback))
                self.assertEqual(adapter._iv_fallback_count, 2)
                snapshot = await consumer.process_latest_snapshot(
                    days_to_expiry=30,
                    as_of=datetime(2026, 8, 4, 20, 0, 2, tzinfo=timezone.utc),
                )
                self.assertNotIn("error", snapshot)
                self.assertEqual(snapshot["normalized_schema_versions"], [2])
                self.assertEqual(snapshot["position_sources"], ["trade_volume"])
                self.assertEqual(snapshot["selected_contract_count"], 5)
                self.assertEqual(snapshot["available_expiries"], ["2026-09-18", "2026-12-18"])
                self.assertEqual(sum(snapshot["call_volume"]) + sum(snapshot["put_volume"]), 150)
                self.assertIn("gamma_wall_strike", snapshot)
                quality = consumer.feed_quality_snapshot()
                self.assertEqual(quality["health"], "degraded")
                self.assertEqual(quality["fallback_iv_tick_count"], 4)

                increased = deepcopy(scenario["quote_events"][0]["d"]["quotes"][1])
                increased["timestamp"] = "2026-08-04T20:00:03Z"
                increased["entries"]["TotalTradeVolume"]["size"] = 15
                await adapter._parse_and_route("a" + json.dumps([{"e": "md", "d": {"quotes": [increased]}}]))
                state_key = ("tradovate", str(contracts[0]["id"]))
                self.assertEqual(consumer.contract_state[(*state_key, "trade_volume")]["accumulated_volume"], 15)
                self.assertEqual(consumer.contract_state[(*state_key, "open_interest")]["accumulated_volume"], 100)

    async def test_missing_identity_or_expiry_is_dropped_without_blocking_valid_quote(self):
        for scenario in _scenarios()["cases"]:
            for invalid_kind in ("unknown_id", "missing_id", "missing_expiry"):
                with self.subTest(symbol=scenario["symbol"], invalid=invalid_kind):
                    adapter, consumer, _, contracts = await self._discover(scenario)
                    quotes = deepcopy(scenario["quote_events"][0]["d"]["quotes"][1:3])
                    if invalid_kind == "unknown_id":
                        quotes[0]["contractId"] = -1
                    elif invalid_kind == "missing_id":
                        quotes[0].pop("contractId")
                    else:
                        metadata = adapter.contract_metadata[str(contracts[0]["id"])]
                        metadata.pop("expiry")
                        metadata.pop("expiry_timestamp")
                    await adapter._parse_and_route("a" + json.dumps([{"e": "md", "d": {"quotes": quotes}}]))
                    self.assertEqual(len(consumer.contract_state), 2)
                    self.assertEqual(consumer.dropped_message_count, 1)
                    self.assertEqual({key[1] for key in consumer.contract_state}, {str(contracts[1]["id"])})

    async def test_malformed_quote_and_non_quote_rows_are_quarantined(self):
        for scenario in _scenarios()["cases"]:
            for invalid in (None, [], "invalid", {"contractId": "missing", "entries": []}):
                with self.subTest(symbol=scenario["symbol"], invalid=invalid):
                    adapter, consumer, _, contracts = await self._discover(scenario)
                    valid = deepcopy(scenario["quote_events"][0]["d"]["quotes"][1])
                    await adapter._parse_and_route("a" + json.dumps([{"e": "md", "d": {"quotes": [invalid, valid]}}]))
                    self.assertEqual(len(consumer.contract_state), 2)
                    self.assertEqual({key[1] for key in consumer.contract_state}, {str(contracts[0]["id"])})
                    self.assertEqual(consumer.provider_parse_error_count + consumer.dropped_message_count, 1)


if __name__ == "__main__":
    unittest.main()
