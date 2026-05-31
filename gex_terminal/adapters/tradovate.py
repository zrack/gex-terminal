import asyncio
import json
import logging
import os
from typing import Any

from gex_terminal.market_data_adapter import MarketDataAdapter, dumps_normalized_message

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

REQUIRED_TRADOVATE_ENV_VARS = (
    "TRADOVATE_NAME",
    "TRADOVATE_PASSWORD",
    "TRADOVATE_APP_ID",
    "TRADOVATE_APP_VERSION",
    "TRADOVATE_CID",
    "TRADOVATE_SEC",
)


def missing_tradovate_credentials() -> list[str]:
    return [name for name in REQUIRED_TRADOVATE_ENV_VARS if not os.getenv(name)]


def validate_tradovate_credentials() -> None:
    missing = missing_tradovate_credentials()
    if missing:
        raise ValueError(f"missing Tradovate credential(s): {', '.join(missing)}")


class TradovateAdapter(MarketDataAdapter):
    def __init__(
        self,
        consumer,
        target_underlying="ES",
        environment: str | None = None,
        max_option_contracts: int = 60,
    ):
        self.consumer = consumer
        self.target_underlying = target_underlying
        self.max_option_contracts = max_option_contracts
        self.contract_metadata: dict[str, dict[str, Any]] = {}
        
        # Load Config
        environment = environment or os.getenv("TRADOVATE_ENV", "demo")
        self.rest_url = "https://live.tradovateapi.com/v1" if environment == "live" else "https://demo.tradovateapi.com/v1"
        self.ws_url = "wss://md.tradovateapi.com/v1/websocket" if environment == "live" else "wss://md.tradovateapi.com/v1/websocket"
        
        self.auth_payload = {
            "name": os.getenv("TRADOVATE_NAME"),
            "password": os.getenv("TRADOVATE_PASSWORD"),
            "appId": os.getenv("TRADOVATE_APP_ID"),
            "appVersion": os.getenv("TRADOVATE_APP_VERSION"),
            "cid": os.getenv("TRADOVATE_CID"),
            "sec": os.getenv("TRADOVATE_SEC")
        }
        self.token = None

    async def authenticate(self) -> bool:
        """Retrieves a session token via REST API."""
        validate_tradovate_credentials()
        try:
            import aiohttp
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                "aiohttp is required for Tradovate live mode. Install with: pip install -e ."
            ) from exc

        logging.info("Authenticating with Tradovate REST API...")
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self.rest_url}/auth/accesstokenrequest", json=self.auth_payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self.token = data.get("accessToken")
                    logging.info("Successfully acquired Tradovate access token.")
                    return True
                else:
                    logging.error(f"Authentication failed: {await resp.text()}")
                    return False

    async def discover_option_contracts(self) -> list[dict[str, Any]]:
        """Discover option contracts for the target underlying through Tradovate REST."""
        if not self.token:
            raise RuntimeError("Cannot discover contracts before authentication.")

        try:
            import aiohttp
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                "aiohttp is required for Tradovate live mode. Install with: pip install -e ."
            ) from exc

        headers = {"Authorization": f"Bearer {self.token}"}
        params = {"name": self.target_underlying}
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(f"{self.rest_url}/contract/find", params=params) as resp:
                if resp.status != 200:
                    logging.warning("Contract discovery failed: %s", await resp.text())
                    return []
                payload = await resp.json()

        contracts = self._extract_contract_list(payload)
        option_contracts = [
            contract for contract in contracts
            if self._looks_like_option_contract(contract)
        ][:self.max_option_contracts]

        self.contract_metadata = {
            symbol: self._option_metadata(contract)
            for contract in option_contracts
            if (symbol := self._contract_symbol(contract))
        }
        logging.info(
            "Discovered %s option contract(s) for %s.",
            len(self.contract_metadata),
            self.target_underlying,
        )
        return option_contracts

    async def keep_alive(self, websocket):
        """Tradovate requires a heartbeat every 2.5 seconds to keep the socket alive."""
        try:
            while True:
                await asyncio.sleep(2.5)
                await websocket.send("[]") # Tradovate heartbeat frame
        except asyncio.CancelledError:
            pass

    async def stream_market_data(self):
        """Connects to WebSocket, authorizes, and streams options volume."""
        try:
            import websockets
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                "websockets is required for Tradovate live mode. Install with: pip install -e ."
            ) from exc

        if not self.token:
            if not await self.authenticate():
                return
        option_contracts = await self.discover_option_contracts()

        async for websocket in websockets.connect(self.ws_url):
            logging.info("Connected to Tradovate Market Data WebSocket.")
            self.consumer.mark_connected()
            
            # Start the background heartbeat
            heartbeat_task = asyncio.create_task(self.keep_alive(websocket))
            
            try:
                # 1. Authorize the WebSocket
                auth_frame = f'authorize\n1\n\n{{"token":"{self.token}"}}'
                await websocket.send(auth_frame)

                # 2. Subscribe to the underlying plus discovered option contracts.
                request_id = 2
                await self._subscribe_quote(websocket, request_id, self.target_underlying)
                request_id += 1
                for contract in option_contracts:
                    symbol = self._contract_symbol(contract)
                    if not symbol:
                        continue
                    await self._subscribe_quote(websocket, request_id, symbol)
                    request_id += 1

                # 3. Listen and Route
                async for message in websocket:
                    # Tradovate sends heartbeat acks as 'h' and data frames as 'a'
                    if message.startswith("a"): 
                        await self._parse_and_route(message)
                        
            except websockets.ConnectionClosed:
                logging.warning("Tradovate WebSocket disconnected. Reconnecting...")
                self.consumer.mark_disconnected()
                heartbeat_task.cancel()
                continue
            except Exception as e:
                logging.error(f"WebSocket Error: {e}")
                self.consumer.mark_disconnected()
                heartbeat_task.cancel()
                break

    async def _parse_and_route(self, raw_message: str):
        """
        Normalizes Tradovate's specific JSON schema into the standard format 
        required by the StatefulGexConsumer.
        """
        try:
            # Tradovate arrays look like: a[{"e":"md","d":{"quotes":[{...}]}}]
            payloads = json.loads(raw_message[1:]) 
            
            for event in payloads:
                if event.get("e") == "md": # Market Data Event
                    data = event.get("d", {})
                    
                    # Example parsing logic for Tradovate's quote schema
                    # Actual schema mapping depends on exactly how you query their options chain
                    if "quotes" in data:
                        for quote in data["quotes"]:
                            underlying_msg = self._normalize_underlying_quote(quote)
                            if underlying_msg:
                                await self.consumer.update_market_state(
                                    dumps_normalized_message(underlying_msg)
                                )
                                continue

                            option_msg = self._normalize_option_quote(quote)
                            if option_msg:
                                await self.consumer.update_market_state(
                                    dumps_normalized_message(option_msg)
                                )
                            
        except json.JSONDecodeError:
            pass # Ignore malformed frames or acks

    async def _subscribe_quote(self, websocket, request_id: int, symbol: str) -> None:
        sub_frame = f'md/subscribeQuote\n{request_id}\n\n{{"symbol":"{symbol}"}}'
        await websocket.send(sub_frame)

    def _normalize_underlying_quote(self, quote: dict[str, Any]) -> dict[str, Any] | None:
        symbol = self._quote_symbol(quote)
        if symbol != self.target_underlying:
            return None

        price = self._quote_price(quote)
        if price is None:
            return None

        return {
            "type": "underlying_tick",
            "symbol": self.target_underlying,
            "price": price,
        }

    def _normalize_option_quote(self, quote: dict[str, Any]) -> dict[str, Any] | None:
        symbol = self._quote_symbol(quote)
        metadata = self.contract_metadata.get(symbol or "", {})

        strike = quote.get("strikePrice", metadata.get("strike"))
        option_type = quote.get("callPut", metadata.get("option_type"))
        volume = quote.get("tradeVol", quote.get("volume", quote.get("totalVolume")))
        iv = quote.get("impliedVol", quote.get("iv", metadata.get("iv", 0.15)))

        if strike in (None, "") or option_type in (None, "") or volume in (None, ""):
            return None

        return {
            "type": "options_volume_tick",
            "strike": float(strike),
            "option_type": str(option_type).upper()[0],
            "volume": int(volume),
            "iv": float(iv),
        }

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
            for key in ("name", "symbol", "description", "contractType", "productType", "secType")
        ).lower()
        return (
            "option" in searchable
            or contract.get("strikePrice") is not None
            or contract.get("callPut") is not None
            or contract.get("putCall") is not None
        )

    @staticmethod
    def _contract_symbol(contract: dict[str, Any]) -> str | None:
        value = contract.get("name") or contract.get("symbol") or contract.get("contractName")
        return str(value) if value else None

    @staticmethod
    def _option_metadata(contract: dict[str, Any]) -> dict[str, Any]:
        option_type = contract.get("callPut", contract.get("putCall"))
        if option_type:
            option_type = str(option_type).upper()[0]
        return {
            "strike": contract.get("strikePrice") or contract.get("strike"),
            "option_type": option_type,
            "iv": contract.get("impliedVol", 0.15),
        }

    @staticmethod
    def _quote_symbol(quote: dict[str, Any]) -> str | None:
        value = quote.get("symbol") or quote.get("contractName") or quote.get("name")
        return str(value) if value else None

    @staticmethod
    def _quote_price(quote: dict[str, Any]) -> float | None:
        for field in ("lastPrice", "tradePrice", "price", "closePrice"):
            value = quote.get(field)
            if value not in (None, ""):
                return float(value)

        bid = quote.get("bidPrice")
        ask = quote.get("offerPrice", quote.get("askPrice"))
        if bid not in (None, "") and ask not in (None, ""):
            return (float(bid) + float(ask)) / 2

        return None
