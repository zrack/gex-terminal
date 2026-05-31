import asyncio
import json
import logging
import os
import aiohttp
import websockets

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

class TradovateAdapter:
    def __init__(self, consumer, target_underlying="ES", environment: str | None = None):
        self.consumer = consumer
        self.target_underlying = target_underlying
        
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
        if not self.token:
            if not await self.authenticate():
                return

        async for websocket in websockets.connect(self.ws_url):
            logging.info("Connected to Tradovate Market Data WebSocket.")
            self.consumer.mark_connected()
            
            # Start the background heartbeat
            heartbeat_task = asyncio.create_task(self.keep_alive(websocket))
            
            try:
                # 1. Authorize the WebSocket
                auth_frame = f'authorize\n1\n\n{{"token":"{self.token}"}}'
                await websocket.send(auth_frame)

                # 2. Subscribe to MD (Market Data)
                # Note: In a full production app, you would dynamically map the active ES/NQ options symbols here.
                # This is a representative subscription payload for the target underlying.
                sub_frame = f'md/subscribeQuote\n2\n\n{{"symbol":"{self.target_underlying}"}}'
                await websocket.send(sub_frame)

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
                            # Assume we mapped the quote's symbol ID back to its option parameters
                            # (Strike, Type, Vol) earlier in the system map.
                            
                            # Normalization step: formatting for our engine
                            standardized_msg = {
                                "type": "options_volume_tick",
                                "strike": quote.get("strikePrice", 0), 
                                "option_type": quote.get("callPut", "C"), 
                                "volume": quote.get("tradeVol", 0),
                                "iv": quote.get("impliedVol", 0.15)
                            }
                            
                            # Fire it into the pipeline
                            await self.consumer.update_market_state(json.dumps(standardized_msg))
                            
        except json.JSONDecodeError:
            pass # Ignore malformed frames or acks
