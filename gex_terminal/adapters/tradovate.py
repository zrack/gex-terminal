"""Tradovate market-data adapter.

The adapter deliberately keeps its public status at ``scaffold`` until a
credentialed certification run proves authentication, contract discovery,
WebSocket authorization, subscription acknowledgements, and normalized ticks.
Provider tokens and account identifiers are never written to logs or reports.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from gex_terminal.market_data_adapter import (
    AdapterInfo,
    MarketDataAdapter,
    dumps_normalized_message,
)

LOGGER = logging.getLogger(__name__)

ADAPTER_INFO = AdapterInfo(
    name="tradovate",
    label="Tradovate",
    status="scaffold",
    notes=(
        "Protocol-hardened live adapter; remains scaffold until an explicit, "
        "credentialed certification report passes."
    ),
)

REQUIRED_TRADOVATE_ENV_VARS = (
    "TRADOVATE_NAME",
    "TRADOVATE_PASSWORD",
    "TRADOVATE_APP_ID",
    "TRADOVATE_APP_VERSION",
    "TRADOVATE_CID",
    "TRADOVATE_SEC",
)

_RETRYABLE_HTTP_STATUSES = {429, 500, 502, 503, 504}
_ENTITLEMENT_STATUSES = {401, 403}


def missing_tradovate_credentials() -> list[str]:
    return [name for name in REQUIRED_TRADOVATE_ENV_VARS if not os.getenv(name)]


def validate_tradovate_credentials() -> None:
    missing = missing_tradovate_credentials()
    if missing:
        raise ValueError(f"missing Tradovate credential(s): {', '.join(missing)}")


class TradovateAdapter(MarketDataAdapter):
    """Normalize the official Tradovate REST and market-data protocols."""

    def __init__(
        self,
        consumer,
        target_underlying: str = "ES",
        environment: str | None = None,
        max_option_contracts: int = 60,
        contract_multiplier: float = 50.0,
        default_iv: float = 0.15,
        *,
        request_timeout_seconds: float = 15.0,
        acknowledgement_timeout_seconds: float = 10.0,
        max_http_attempts: int = 3,
        max_reconnect_attempts: int = 3,
        reconnect_base_delay_seconds: float = 1.0,
    ):
        self.consumer = consumer
        self.target_underlying = target_underlying.upper()
        self.max_option_contracts = max(1, int(max_option_contracts))
        self.contract_multiplier = float(contract_multiplier)
        self.default_iv = float(default_iv)
        if self.contract_multiplier <= 0:
            raise ValueError("contract_multiplier must be positive")
        if self.default_iv <= 0:
            raise ValueError("default_iv must be positive")

        resolved_environment = (environment or os.getenv("TRADOVATE_ENV", "demo")).lower()
        if resolved_environment not in {"demo", "live"}:
            raise ValueError("Tradovate environment must be 'demo' or 'live'")
        self.environment = resolved_environment
        host = "live.tradovateapi.com" if resolved_environment == "live" else "demo.tradovateapi.com"
        self.rest_url = f"https://{host}/v1"
        # Tradovate uses the same market-data socket host for demo and live.
        self.ws_url = "wss://md.tradovateapi.com/v1/websocket"

        self.request_timeout_seconds = float(request_timeout_seconds)
        self.acknowledgement_timeout_seconds = float(acknowledgement_timeout_seconds)
        self.max_http_attempts = max(1, int(max_http_attempts))
        self.max_reconnect_attempts = max(0, int(max_reconnect_attempts))
        self.reconnect_base_delay_seconds = max(0.0, float(reconnect_base_delay_seconds))

        self.auth_payload = {
            "name": os.getenv("TRADOVATE_NAME"),
            "password": os.getenv("TRADOVATE_PASSWORD"),
            "appId": os.getenv("TRADOVATE_APP_ID"),
            "appVersion": os.getenv("TRADOVATE_APP_VERSION"),
            "cid": os.getenv("TRADOVATE_CID"),
            "sec": os.getenv("TRADOVATE_SEC"),
        }
        self.access_token: str | None = None
        self.md_access_token: str | None = None
        # ``token`` remains as a compatibility alias used by existing callers.
        self.token: str | None = None
        self.expiration_time: datetime | None = None
        self.auth_capabilities: dict[str, bool | None] = {}
        self.auth_failure_reason: str | None = None

        # Existing fixtures set this mapping directly by contract symbol. Live
        # discovery additionally registers string contract IDs.
        self.contract_metadata: dict[str, dict[str, Any]] = {}
        self.underlying_contract: dict[str, Any] | None = None
        self._connected_once = False
        self._active_subscriptions: list[str | int] = []
        self._request_id = 1
        self._iv_fallback_count = 0
        self._receipt_time_fallback_count = 0

    async def authenticate(self) -> bool:
        """Acquire REST and market-data access tokens with bounded retries."""
        validate_tradovate_credentials()
        try:
            import aiohttp
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                "aiohttp is required for Tradovate live mode. Install with: pip install -e ."
            ) from exc

        timeout = aiohttp.ClientTimeout(total=self.request_timeout_seconds)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for attempt in range(self.max_http_attempts):
                async with session.post(
                    f"{self.rest_url}/auth/accesstokenrequest",
                    json=self.auth_payload,
                ) as response:
                    if response.status == 200:
                        payload = await response.json()
                        access_token = payload.get("accessToken")
                        if not access_token:
                            self.auth_failure_reason = (
                                "challenge_required"
                                if payload.get("p-ticket")
                                else "no_access_token"
                            )
                            LOGGER.error("Tradovate authentication returned no access token.")
                            return False
                        self._apply_token_payload(payload)
                        LOGGER.info("Tradovate authentication succeeded.")
                        return True

                    if response.status in _RETRYABLE_HTTP_STATUSES and attempt + 1 < self.max_http_attempts:
                        await asyncio.sleep(self._retry_delay(response, attempt))
                        continue

                    # Do not log response bodies: they can contain identity or
                    # authentication diagnostics.
                    LOGGER.error("Tradovate authentication failed with HTTP %s.", response.status)
                    self.auth_failure_reason = f"http_{response.status}"
                    return False
        return False

    async def renew_access_token(self) -> bool:
        """Renew the current REST/market-data token pair."""
        if not self.access_token:
            return False
        try:
            import aiohttp
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                "aiohttp is required for Tradovate live mode. Install with: pip install -e ."
            ) from exc

        headers = {"Authorization": f"Bearer {self.access_token}"}
        timeout = aiohttp.ClientTimeout(total=self.request_timeout_seconds)
        async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
            payload = await self._get_json_with_retries(
                session,
                f"{self.rest_url}/auth/renewAccessToken",
            )
        if not isinstance(payload, Mapping) or not payload.get("accessToken"):
            LOGGER.warning("Tradovate access-token renewal failed.")
            return False
        self._apply_token_payload(payload)
        return True

    def _apply_token_payload(self, payload: Mapping[str, Any]) -> None:
        self.access_token = str(payload["accessToken"])
        self.md_access_token = str(payload.get("mdAccessToken") or self.access_token)
        self.token = self.access_token
        self.expiration_time = self._parse_datetime(payload.get("expirationTime"))
        self.auth_capabilities = {
            "has_live": self._optional_bool(payload.get("hasLive")),
            "has_market_data": self._optional_bool(payload.get("hasMarketData")),
        }
        self.auth_failure_reason = None

    async def discover_option_contracts(self) -> list[dict[str, Any]]:
        """Discover contracts through product/maturity dependencies and suggestions.

        ``contract/find`` is intentionally not used as a chain endpoint; it is
        an exact contract lookup in the official API.
        """
        if not self.access_token and not self.token:
            raise RuntimeError("Cannot discover contracts before authentication.")
        access_token = self.access_token or self.token

        try:
            import aiohttp
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                "aiohttp is required for Tradovate live mode. Install with: pip install -e ."
            ) from exc

        headers = {"Authorization": f"Bearer {access_token}"}
        timeout = aiohttp.ClientTimeout(total=self.request_timeout_seconds)
        candidates: list[dict[str, Any]] = []
        maturity_by_id: dict[str, dict[str, Any]] = {}
        product: dict[str, Any] | None = None

        async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
            product_payload = await self._get_json_with_retries(
                session,
                f"{self.rest_url}/product/find",
                params={"name": self.target_underlying},
            )
            product_rows = self._extract_contract_list(product_payload)
            if product_rows:
                product = product_rows[0]
                product_id = product.get("id")
                if product_id is not None:
                    maturity_payload = await self._get_json_with_retries(
                        session,
                        f"{self.rest_url}/contractMaturity/deps",
                        params={"masterid": product_id},
                    )
                    for maturity in self._extract_contract_list(maturity_payload):
                        maturity_id = maturity.get("id")
                        if maturity_id is None:
                            continue
                        maturity_by_id[str(maturity_id)] = maturity
                        contract_payload = await self._get_json_with_retries(
                            session,
                            f"{self.rest_url}/contract/deps",
                            params={"masterid": maturity_id},
                        )
                        for contract in self._extract_contract_list(contract_payload):
                            candidates.append(
                                self._enrich_discovered_contract(contract, maturity, product)
                            )

            # Suggestions provide a bounded fallback and can surface option
            # product symbols that differ from the future root.
            suggestion_payload = await self._get_json_with_retries(
                session,
                f"{self.rest_url}/contract/suggest",
                params={"t": self.target_underlying, "l": max(100, self.max_option_contracts * 3)},
            )
            for contract in self._extract_contract_list(suggestion_payload):
                maturity = maturity_by_id.get(str(contract.get("contractMaturityId")))
                candidates.append(self._enrich_discovered_contract(contract, maturity, product))

        candidates = self._deduplicate_contracts(candidates)
        non_options = [row for row in candidates if not self._looks_like_option_contract(row)]
        self.underlying_contract = self._select_underlying_contract(non_options)
        option_contracts = [
            row for row in candidates if self._looks_like_option_contract(row)
        ][: self.max_option_contracts]

        self.contract_metadata.clear()
        for contract in option_contracts:
            self._register_contract_metadata(contract)
        if self.underlying_contract:
            self._register_underlying_metadata(self.underlying_contract)

        LOGGER.info(
            "Discovered %s Tradovate option contract(s) for %s.",
            len(option_contracts),
            self.target_underlying,
        )
        return option_contracts

    async def _get_json_with_retries(
        self,
        session,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
    ) -> Any:
        for attempt in range(self.max_http_attempts):
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    return await response.json()
                if response.status in _RETRYABLE_HTTP_STATUSES and attempt + 1 < self.max_http_attempts:
                    await asyncio.sleep(self._retry_delay(response, attempt))
                    continue
                if response.status in _ENTITLEMENT_STATUSES:
                    self._record_consumer("record_entitlement_error")
                LOGGER.warning("Tradovate request failed with HTTP %s for %s.", response.status, url)
                return None
        return None

    def _retry_delay(self, response, attempt: int) -> float:
        headers = getattr(response, "headers", {}) or {}
        retry_after = headers.get("Retry-After")
        if retry_after not in (None, ""):
            try:
                return max(0.0, float(retry_after))
            except (TypeError, ValueError):
                pass
        return min(30.0, float(2**attempt))

    async def keep_alive(self, websocket) -> None:
        """Send Tradovate's required 2.5-second heartbeat frame."""
        try:
            while True:
                await asyncio.sleep(2.5)
                await websocket.send("[]")
        except asyncio.CancelledError:
            raise

    async def _token_renewal_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(60.0)
                if (
                    self.expiration_time is not None
                    and self.expiration_time - datetime.now(timezone.utc) <= timedelta(minutes=15)
                    and not await self.renew_access_token()
                ):
                    self._record_consumer("mark_subscription_error")
        except asyncio.CancelledError:
            raise

    async def stream_market_data(self) -> None:
        """Authorize, subscribe, and route quotes with bounded reconnects."""
        try:
            import websockets
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                "websockets is required for Tradovate live mode. Install with: pip install -e ."
            ) from exc

        if not self.md_access_token:
            if not await self.authenticate():
                return
        option_contracts = await self.discover_option_contracts()
        subscriptions = self._subscription_values(option_contracts)
        if not subscriptions:
            self._record_consumer("mark_subscription_error")
            raise RuntimeError("Tradovate discovery returned no subscribable contracts")

        for reconnect_attempt in range(self.max_reconnect_attempts + 1):
            try:
                async with websockets.connect(
                    self.ws_url,
                    open_timeout=self.request_timeout_seconds,
                    close_timeout=5.0,
                ) as websocket:
                    await self._run_websocket_session(websocket, subscriptions)
                    return
            except asyncio.CancelledError:
                self._record_consumer("mark_disconnected")
                raise
            except PermissionError:
                self._record_consumer("mark_disconnected")
                return
            except Exception as exc:
                self._record_consumer("mark_disconnected")
                if reconnect_attempt >= self.max_reconnect_attempts:
                    LOGGER.error(
                        "Tradovate market-data connection stopped after bounded retries: %s",
                        type(exc).__name__,
                    )
                    return
                LOGGER.warning("Tradovate market-data connection interrupted; retrying.")
                delay = min(30.0, self.reconnect_base_delay_seconds * (2**reconnect_attempt))
                await asyncio.sleep(delay)

    async def _run_websocket_session(self, websocket, subscriptions: list[str | int]) -> None:
        heartbeat_task = None
        renewal_task = None
        self._active_subscriptions = []
        try:
            await self._await_open(websocket)
            auth_request_id = self._next_request_id()
            # The authorization body is the raw market-data access token, not
            # a JSON object.
            await websocket.send(
                f"authorize\n{auth_request_id}\n\n{self.md_access_token}"
            )
            await self._await_ack(websocket, auth_request_id, operation="authorize")

            if self._connected_once:
                self._record_consumer("mark_reconnected")
            else:
                self._record_consumer("mark_connected")
                self._connected_once = True

            for subscription in subscriptions:
                request_id = self._next_request_id()
                await self._subscribe_quote(websocket, request_id, subscription)
                await self._await_ack(websocket, request_id, operation="subscribe")
                self._active_subscriptions.append(subscription)
            self._record_consumer("mark_subscribed", len(self._active_subscriptions))

            heartbeat_task = asyncio.create_task(self.keep_alive(websocket))
            renewal_task = asyncio.create_task(self._token_renewal_loop())
            async for message in websocket:
                if message in {"h", "o", "[]"}:
                    continue
                await self._parse_and_route(message)
        finally:
            for task in (heartbeat_task, renewal_task):
                if task:
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await task
            await self._cleanup_websocket(websocket)
            self._record_consumer("mark_disconnected")

    async def _await_open(self, websocket) -> None:
        while True:
            raw = await asyncio.wait_for(
                websocket.recv(),
                timeout=self.acknowledgement_timeout_seconds,
            )
            if raw == "o":
                return
            if raw in {"h", "[]"}:
                continue
            # A response before the opening frame is a protocol error. Do not
            # authorize until the provider has explicitly opened the session.
            raise RuntimeError("Tradovate WebSocket did not send an opening frame")

    async def _await_ack(self, websocket, request_id: int, *, operation: str) -> dict[str, Any]:
        while True:
            raw = await asyncio.wait_for(
                websocket.recv(),
                timeout=self.acknowledgement_timeout_seconds,
            )
            if raw in {"h", "o", "[]"}:
                continue
            payloads = self._decode_frame(raw)
            for event in payloads:
                if event.get("i") == request_id:
                    status = int(event.get("s", 0))
                    if status == 200:
                        return event
                    self._record_consumer("mark_subscription_error")
                    if status in _ENTITLEMENT_STATUSES:
                        self._record_consumer("record_entitlement_error")
                        raise PermissionError(
                            f"Tradovate {operation} was rejected with HTTP {status}"
                        )
                    raise RuntimeError(
                        f"Tradovate {operation} was rejected with HTTP {status}"
                    )
                if event.get("e") in {"error", "md/error"}:
                    self._record_consumer("mark_subscription_error")
                    self._record_consumer("record_entitlement_error")
                    raise PermissionError(f"Tradovate {operation} returned an error event")
                if event.get("e") == "md":
                    await self._route_market_data_event(event)

    async def _subscribe_quote(self, websocket, request_id: int, symbol: str | int) -> None:
        body = json.dumps({"symbol": symbol}, separators=(",", ":"))
        await websocket.send(f"md/subscribeQuote\n{request_id}\n\n{body}")

    async def _unsubscribe_quote(self, websocket, request_id: int, symbol: str | int) -> None:
        body = json.dumps({"symbol": symbol}, separators=(",", ":"))
        await websocket.send(f"md/unsubscribeQuote\n{request_id}\n\n{body}")

    async def _cleanup_websocket(self, websocket) -> None:
        for subscription in self._active_subscriptions:
            with contextlib.suppress(Exception):
                await self._unsubscribe_quote(websocket, self._next_request_id(), subscription)
        self._active_subscriptions = []
        close = getattr(websocket, "close", None)
        if callable(close):
            with contextlib.suppress(Exception):
                result = close()
                if result is not None:
                    await result

    async def _parse_and_route(self, raw_message: str) -> None:
        """Decode one provider frame and route each valid quote independently."""
        self._record_consumer("record_provider_frame")
        try:
            payloads = self._decode_frame(raw_message)
        except (json.JSONDecodeError, TypeError, ValueError):
            self._record_consumer("record_provider_parse_error")
            return
        for event in payloads:
            if event.get("e") in {"error", "md/error"}:
                self._record_consumer("record_entitlement_error")
                continue
            if event.get("e") == "md":
                await self._route_market_data_event(event)

    async def _route_market_data_event(self, event: Mapping[str, Any]) -> None:
        data = event.get("d")
        if not isinstance(data, Mapping):
            self._record_consumer("record_provider_parse_error")
            return
        quotes = data.get("quotes", ())
        if not isinstance(quotes, list):
            self._record_consumer("record_provider_parse_error")
            return
        for quote in quotes:
            if not isinstance(quote, dict):
                self._record_consumer("record_provider_parse_error")
                continue
            if "timestamp" not in quote and data.get("timestamp"):
                quote = {**quote, "timestamp": data["timestamp"]}
            await self._route_quote(quote)

    @staticmethod
    def _decode_frame(raw_message: str) -> list[dict[str, Any]]:
        if not isinstance(raw_message, str) or not raw_message:
            raise ValueError("empty Tradovate frame")
        if raw_message[0] not in {"a", "m"}:
            raise ValueError("unsupported Tradovate frame")
        payload = json.loads(raw_message[1:])
        if isinstance(payload, dict):
            payload = [payload]
        if not isinstance(payload, list):
            raise ValueError("Tradovate frame payload must be an array")
        return [event for event in payload if isinstance(event, dict)]

    async def _route_quote(self, quote: dict[str, Any]) -> None:
        try:
            underlying_message = self._normalize_underlying_quote(quote)
            if underlying_message:
                await self.consumer.update_market_state(
                    dumps_normalized_message(underlying_message)
                )
                return

            option_messages = self._normalize_option_messages(quote)
            if option_messages:
                for option_message in option_messages:
                    await self.consumer.update_market_state(
                        dumps_normalized_message(option_message)
                    )
                return

            self._record_consumer("record_dropped_message")
        except (TypeError, ValueError) as error:
            LOGGER.warning("Rejected malformed Tradovate quote: %s", error)
            self._record_consumer("record_provider_parse_error")

    def _normalize_option_messages(
        self, quote: dict[str, Any]
    ) -> list[dict[str, Any]]:
        if "entries" in quote or quote.get("contractId") is not None:
            return self._normalize_official_option_quotes(quote)
        option_message = self._normalize_option_quote(quote)
        return [option_message] if option_message else []

    def _record_consumer(self, method_name: str, *args) -> None:
        method = getattr(self.consumer, method_name, None)
        if method:
            method(*args)

    def _record_quality_note(self, note: str) -> None:
        method = getattr(self.consumer, "record_quality_note", None)
        if method:
            method(note)

    def _normalize_underlying_quote(self, quote: dict[str, Any]) -> dict[str, Any] | None:
        metadata = self._metadata_for_quote(quote)
        symbol = self._quote_symbol(quote) or str(metadata.get("contract_symbol") or "")
        contract_id = quote.get("contractId")
        is_underlying_id = bool(
            contract_id is not None
            and self.underlying_contract
            and str(contract_id) == str(self.underlying_contract.get("id"))
        )
        is_underlying_metadata = metadata.get("instrument_class") == "future"
        is_target_symbol = symbol.upper() == self.target_underlying
        if not (is_underlying_id or is_underlying_metadata or is_target_symbol):
            return None

        price = self._quote_price(quote)
        if price is None:
            return None

        if "entries" not in quote and contract_id is None:
            return {
                "type": "underlying_tick",
                "symbol": self.target_underlying,
                "price": price,
            }

        event_time, received_time = self._quote_times(quote)
        return {
            "schema_version": 2,
            "type": "underlying_tick",
            "provider": "tradovate",
            "symbol": self.target_underlying,
            "price": price,
            "event_time": event_time,
            "received_time": received_time,
        }

    def _normalize_option_quote(self, quote: dict[str, Any]) -> dict[str, Any] | None:
        if "entries" in quote or quote.get("contractId") is not None:
            return self._normalize_official_option_quote(quote)

        # Retain the synthetic/legacy flat mapping for recorded fixtures and
        # backwards compatibility. It remains schema v1 and incremental.
        symbol = self._quote_symbol(quote)
        metadata = self._metadata_for_quote(quote)
        if not metadata and symbol:
            metadata = self._option_metadata_from_symbol(symbol) or {}
        strike = quote.get("strikePrice", metadata.get("strike"))
        option_type = quote.get("callPut", metadata.get("option_type"))
        volume = quote.get("tradeVol", quote.get("volume", quote.get("totalVolume")))
        iv = quote.get("impliedVol", quote.get("iv", metadata.get("iv", self.default_iv)))
        if strike in (None, "") or option_type in (None, "") or volume in (None, ""):
            return None
        normalized = {
            "type": "options_volume_tick",
            "strike": float(strike),
            "option_type": str(option_type).upper()[0],
            "volume": int(volume),
            "iv": float(iv),
        }
        if normalized["option_type"] not in {"C", "P"}:
            raise ValueError(f"unsupported option type for {symbol}: {option_type}")
        return normalized

    def _normalize_official_option_quote(self, quote: dict[str, Any]) -> dict[str, Any] | None:
        """Return the preferred source for compatibility with single-row callers."""
        messages = self._normalize_official_option_quotes(quote)
        for message in messages:
            if message["position_source"] == "trade_volume" and message["volume"] > 0:
                return message
        for message in messages:
            if message["position_source"] == "open_interest":
                return message
        return messages[0] if messages else None

    def _normalize_official_option_quotes(
        self, quote: dict[str, Any]
    ) -> list[dict[str, Any]]:
        metadata = self._metadata_for_quote(quote)
        if metadata.get("instrument_class") == "future":
            return []
        contract_id = quote.get("contractId", metadata.get("contract_id"))
        strike = quote.get("strikePrice", metadata.get("strike"))
        option_type = quote.get(
            "callPut",
            quote.get("putCall", quote.get("optionType", metadata.get("option_type"))),
        )
        expiry = metadata.get("expiry") or metadata.get("expiry_timestamp")
        entries = quote.get("entries")
        if not isinstance(entries, Mapping):
            return []

        total_volume = self._entry_size(entries, "TotalTradeVolume")
        open_interest = self._entry_size(entries, "OpenInterest")
        positions = []
        if total_volume is not None:
            positions.append(("trade_volume", total_volume))
        if open_interest is not None:
            positions.append(("open_interest", open_interest))
        if not positions:
            return []

        if (
            contract_id in (None, "")
            or strike in (None, "")
            or option_type in (None, "")
            or expiry in (None, "")
        ):
            return []
        option_code = str(option_type).upper()[0]
        if option_code not in {"C", "P"}:
            raise ValueError(f"unsupported Tradovate option type: {option_type}")

        iv = quote.get("impliedVol", quote.get("iv", metadata.get("iv")))
        iv_source = "provider"
        if iv in (None, ""):
            iv = self.default_iv
            iv_source = "configured_default"
            self._iv_fallback_count += 1
            self._record_quality_note(
                "Tradovate quotes do not provide implied volatility; configured fallback IV is in use"
            )
        event_time, received_time = self._quote_times(quote)
        instrument_class = str(metadata.get("instrument_class") or "futures_option")
        multiplier = metadata.get("multiplier", metadata.get("contract_multiplier"))
        if multiplier in (None, ""):
            multiplier = self.contract_multiplier

        normalized: dict[str, Any] = {
            "schema_version": 2,
            "type": "options_volume_tick",
            "provider": "tradovate",
            "contract_id": str(contract_id),
            "contract_symbol": str(
                metadata.get("contract_symbol")
                or self._quote_symbol(quote)
                or contract_id
            ),
            "symbol": self.target_underlying,
            "strike": float(strike),
            "option_type": option_code,
            "volume_semantics": "cumulative",
            "iv": float(iv),
            "iv_source": iv_source,
            "expiry": str(expiry),
            "instrument_class": instrument_class,
            "pricing_model": "black_76" if instrument_class == "futures_option" else "black_scholes",
            "contract_multiplier": float(multiplier),
            "event_time": event_time,
            "received_time": received_time,
        }
        expiry_timestamp = metadata.get("expiry_timestamp")
        if expiry_timestamp not in (None, ""):
            normalized["expiry_timestamp"] = str(expiry_timestamp)
        sequence = quote.get("sequence", quote.get("seq"))
        if sequence not in (None, ""):
            normalized["sequence"] = int(sequence)
        return [
            {
                **normalized,
                "volume": int(volume),
                "position_source": position_source,
            }
            for position_source, volume in positions
        ]

    def _quote_times(self, quote: Mapping[str, Any]) -> tuple[str, str]:
        received = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        candidate = quote.get("timestamp") or quote.get("eventTime")
        parsed = self._parse_datetime(candidate)
        if parsed is None:
            self._receipt_time_fallback_count += 1
            self._record_quality_note(
                "Tradovate quote timestamp missing or timezone-naive; receipt time used"
            )
            return received, received
        return parsed.isoformat().replace("+00:00", "Z"), received

    def _metadata_for_quote(self, quote: Mapping[str, Any]) -> dict[str, Any]:
        contract_id = quote.get("contractId")
        if contract_id is not None:
            metadata = self.contract_metadata.get(str(contract_id))
            if metadata:
                return metadata
        symbol = self._quote_symbol(quote)
        if symbol:
            metadata = self.contract_metadata.get(symbol)
            if metadata:
                return metadata
        if contract_id is not None:
            for metadata in self.contract_metadata.values():
                if str(metadata.get("contract_id")) == str(contract_id):
                    return metadata
        return {}

    def _register_contract_metadata(self, contract: Mapping[str, Any]) -> None:
        metadata = self._option_metadata(dict(contract))
        symbol = self._contract_symbol(dict(contract))
        contract_id = contract.get("id", contract.get("contractId"))
        if symbol:
            metadata.setdefault("contract_symbol", symbol)
        metadata.setdefault("instrument_class", "futures_option")
        if symbol:
            self.contract_metadata[symbol] = metadata
        if contract_id is not None:
            self.contract_metadata[str(contract_id)] = metadata

    def _register_underlying_metadata(self, contract: Mapping[str, Any]) -> None:
        symbol = self._contract_symbol(dict(contract))
        contract_id = contract.get("id", contract.get("contractId"))
        metadata = {
            "contract_id": str(contract_id) if contract_id is not None else None,
            "contract_symbol": symbol,
            "instrument_class": "future",
        }
        if symbol:
            self.contract_metadata[symbol] = metadata
        if contract_id is not None:
            self.contract_metadata[str(contract_id)] = metadata

    def _subscription_values(self, option_contracts: list[dict[str, Any]]) -> list[str | int]:
        values: list[str | int] = []
        if self.underlying_contract:
            underlying = self._contract_symbol(self.underlying_contract)
            if underlying:
                values.append(underlying)
            elif self.underlying_contract.get("id") is not None:
                values.append(self.underlying_contract["id"])
        else:
            values.append(self.target_underlying)

        for contract in option_contracts:
            symbol = self._contract_symbol(contract)
            value: str | int | None = symbol
            if value is None:
                value = contract.get("id", contract.get("contractId"))
            if value is not None and value not in values:
                values.append(value)
        return values

    def _next_request_id(self) -> int:
        request_id = self._request_id
        self._request_id += 1
        return request_id

    @staticmethod
    def _extract_contract_list(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            for key in ("items", "contracts", "data"):
                value = payload.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
            return [payload]
        return []

    @staticmethod
    def _looks_like_option_contract(contract: dict[str, Any]) -> bool:
        searchable = " ".join(
            str(contract.get(key, ""))
            for key in (
                "name",
                "symbol",
                "description",
                "contractType",
                "productType",
                "secType",
                "optionType",
            )
        ).lower()
        return (
            "option" in searchable
            or contract.get("strikePrice") is not None
            or contract.get("callPut") is not None
            or contract.get("putCall") is not None
            or contract.get("optionType") is not None
        )

    @staticmethod
    def _contract_symbol(contract: dict[str, Any]) -> str | None:
        value = contract.get("name") or contract.get("symbol") or contract.get("contractName")
        return str(value) if value else None

    @staticmethod
    def _option_metadata(contract: dict[str, Any]) -> dict[str, Any]:
        option_type = contract.get(
            "callPut",
            contract.get("putCall", contract.get("optionType")),
        )
        if option_type:
            option_type = str(option_type).upper()[0]
        metadata: dict[str, Any] = {
            "strike": contract.get("strikePrice") or contract.get("strike"),
            "option_type": option_type,
        }
        optional_fields = {
            "contract_id": contract.get("id", contract.get("contractId")),
            "expiry": TradovateAdapter._contract_expiry(contract),
            "expiry_timestamp": TradovateAdapter._contract_expiry_timestamp(contract),
            "instrument_class": contract.get("instrument_class"),
            "multiplier": contract.get(
                "multiplier",
                contract.get("contractMultiplier", contract.get("valuePerPoint")),
            ),
            "iv": contract.get(
                "impliedVol",
                contract.get("impliedVolatility", contract.get("iv")),
            ),
        }
        for key, value in optional_fields.items():
            if value not in (None, ""):
                metadata[key] = value
        if metadata.get("contract_id") is not None:
            metadata["contract_id"] = str(metadata["contract_id"])
            symbol = TradovateAdapter._contract_symbol(contract)
            if symbol:
                metadata["contract_symbol"] = symbol
        return metadata

    @staticmethod
    def _option_metadata_from_symbol(symbol: str) -> dict[str, Any] | None:
        match = re.search(r"(?:^|\s)([CP])\s*(\d+(?:\.\d+)?)$", symbol.strip(), re.IGNORECASE)
        if not match:
            return None
        return {
            "strike": float(match.group(2)),
            "option_type": match.group(1).upper(),
            "iv": 0.15,
        }

    @staticmethod
    def _quote_symbol(quote: Mapping[str, Any]) -> str | None:
        value = quote.get("symbol") or quote.get("contractName") or quote.get("name")
        return str(value) if value else None

    @staticmethod
    def _entry(entries: Mapping[str, Any], name: str) -> Mapping[str, Any] | None:
        direct = entries.get(name)
        if isinstance(direct, Mapping):
            return direct
        wanted = name.lower()
        for key, value in entries.items():
            if str(key).lower() == wanted and isinstance(value, Mapping):
                return value
        return None

    @classmethod
    def _entry_size(cls, entries: Mapping[str, Any], name: str) -> int | None:
        entry = cls._entry(entries, name)
        if not entry or entry.get("size") in (None, ""):
            return None
        return int(entry["size"])

    @classmethod
    def _quote_price(cls, quote: dict[str, Any]) -> float | None:
        entries = quote.get("entries")
        if isinstance(entries, Mapping):
            trade = cls._entry(entries, "Trade")
            if trade and trade.get("price") not in (None, ""):
                return float(trade["price"])
            bid_entry = cls._entry(entries, "Bid")
            offer_entry = cls._entry(entries, "Offer")
            if (
                bid_entry
                and offer_entry
                and bid_entry.get("price") not in (None, "")
                and offer_entry.get("price") not in (None, "")
            ):
                return (float(bid_entry["price"]) + float(offer_entry["price"])) / 2

        for field in ("lastPrice", "tradePrice", "price", "closePrice"):
            value = quote.get(field)
            if value not in (None, ""):
                return float(value)
        bid = quote.get("bidPrice")
        ask = quote.get("offerPrice", quote.get("askPrice"))
        if bid not in (None, "") and ask not in (None, ""):
            return (float(bid) + float(ask)) / 2
        return None

    @staticmethod
    def _contract_expiry(contract: Mapping[str, Any]) -> str | None:
        value = (
            contract.get("expiry")
            or contract.get("expirationDate")
            or contract.get("lastTradingDate")
            or contract.get("maturityDate")
        )
        return str(value) if value not in (None, "") else None

    @classmethod
    def _contract_expiry_timestamp(cls, contract: Mapping[str, Any]) -> str | None:
        for field in ("expiryTimestamp", "expirationTime", "lastTradingTime"):
            parsed = cls._parse_datetime(contract.get(field))
            if parsed is not None:
                return parsed.isoformat().replace("+00:00", "Z")
        expiry = contract.get("expirationDate") or contract.get("lastTradingDate")
        if isinstance(expiry, str) and "T" in expiry:
            parsed = cls._parse_datetime(expiry)
            if parsed is not None:
                return parsed.isoformat().replace("+00:00", "Z")
        return None

    @classmethod
    def _enrich_discovered_contract(
        cls,
        contract: Mapping[str, Any],
        maturity: Mapping[str, Any] | None,
        product: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        enriched = dict(contract)
        if maturity:
            for target, sources in {
                "expirationDate": ("expirationDate", "lastTradingDate", "maturityDate"),
                "lastTradingTime": ("lastTradingTime",),
            }.items():
                if enriched.get(target) in (None, ""):
                    for source in sources:
                        if maturity.get(source) not in (None, ""):
                            enriched[target] = maturity[source]
                            break
        if product and enriched.get("valuePerPoint") in (None, ""):
            if product.get("valuePerPoint") not in (None, ""):
                enriched["valuePerPoint"] = product["valuePerPoint"]
        return enriched

    @classmethod
    def _deduplicate_contracts(cls, contracts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        for contract in contracts:
            key_value = contract.get("id", contract.get("contractId"))
            if key_value is None:
                key_value = cls._contract_symbol(contract)
            if key_value is None:
                continue
            key = str(key_value)
            if key in seen:
                continue
            seen.add(key)
            result.append(contract)
        return result

    def _select_underlying_contract(
        self, contracts: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        if not contracts:
            return None
        exact = [
            row for row in contracts
            if (self._contract_symbol(row) or "").upper() == self.target_underlying
        ]
        if exact:
            return exact[0]
        prefixed = [
            row for row in contracts
            if (self._contract_symbol(row) or "").upper().startswith(self.target_underlying)
        ]
        return prefixed[0] if prefixed else contracts[0]

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if isinstance(value, datetime):
            parsed = value
        elif isinstance(value, str) and value.strip():
            text = value.strip()
            if text.endswith("Z"):
                text = f"{text[:-1]}+00:00"
            try:
                parsed = datetime.fromisoformat(text)
            except ValueError:
                return None
        else:
            return None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _optional_bool(value: Any) -> bool | None:
        if value is None:
            return None
        return bool(value)
