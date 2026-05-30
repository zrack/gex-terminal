import asyncio
import json
import logging
import numpy as np
from typing import Dict, Any
from gex_engine import IntradayGexEngine

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

class StatefulGexConsumer:
    def __init__(self, engine: IntradayGexEngine, target_underlying: str = "ES"):
        self.engine = engine
        self.target_underlying = target_underlying
        
        # State: { strike_price: { 'C': accumulated_volume, 'P': accumulated_volume, 'iv': implied_vol } }
        self.chain_state: Dict[float, Dict[str, Any]] = {}
        self.current_spot: float = 0.0
        
        # Lock to ensure thread-safe state mutations during high-frequency bursts
        self.state_lock = asyncio.Lock()

    async def update_market_state(self, raw_message: str):
        """
        Parses incoming WebSocket frames and safely increments volume data structures.
        Expects a normalized JSON structure from your data provider's broker API.
        """
        try:
            data = json.loads(raw_message)
            
            # 1. Update Underlying Spot Price
            if data.get("type") == "underlying_tick" and data.get("symbol") == self.target_underlying:
                async with self.state_lock:
                    self.current_spot = float(data["price"])
                return

            # 2. Update Options Traded Volume
            if data.get("type") == "options_volume_tick":
                strike = float(data["strike"])
                option_type = data["option_type"] # 'C' or 'P'
                volume = int(data["volume"])
                iv = float(data.get("iv", 0.15)) # Default or fallback IV

                async with self.state_lock:
                    if strike not in self.chain_state:
                        self.chain_state[strike] = {"C": 0, "P": 0, "iv": iv}
                    
                    self.chain_state[strike][option_type] += volume
                    self.chain_state[strike]["iv"] = iv # Update local IV skew dynamically

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logging.error(f"Failed parsing market data frame: {e}")

    async def process_latest_snapshot(self, days_to_expiry: float) -> dict:
        """
        Converts the live in-memory state map into aligned arrays 
        and computes the full mathematical GEX profile.
        """
        async with self.state_lock:
            if not self.chain_state or self.current_spot == 0.0:
                return {"error": "Insufficient data state to compute matrix."}
            
            # Sort strikes to maintain mathematical spatial alignment
            sorted_strikes = sorted(self.chain_state.keys())
            
            strikes_arr = np.array(sorted_strikes, dtype=float)
            iv_arr = np.array([self.chain_state[k]["iv"] for k in sorted_strikes], dtype=float)
            call_vol_arr = np.array([self.chain_state[k]["C"] for k in sorted_strikes], dtype=float)
            put_vol_arr = np.array([self.chain_state[k]["P"] for k in sorted_strikes], dtype=float)
            
            spot = self.current_spot

        # Pass the extracted, aligned state straight to the vectorized math module
        return self.engine.compute_intraday_gex_matrix(
            spot_price=spot,
            strikes=strikes_arr,
            days_to_expiry=days_to_expiry,
            risk_free_rate=0.045,
            implied_vols=iv_arr,
            accumulated_call_vol=call_vol_arr,
            accumulated_put_vol=put_vol_arr
        )

    async def continuous_calculation_loop(self, interval_seconds: float = 2.0):
        """Asynchronous worker loop that periodically calculates GEX from memory state."""
        logging.info("Starting calculation dispatcher...")
        while True:
            await asyncio.sleep(interval_seconds)
            results = await self.process_latest_snapshot(days_to_expiry=0.01)
            
            if "error" not in results:
                logging.info(
                    f"Spot: {self.current_spot:.2f} | "
                    f"Gamma Wall: {results['gamma_wall_strike']} | "
                    f"Zero GEX Node: {results['zero_gamma_strike']}"
                )