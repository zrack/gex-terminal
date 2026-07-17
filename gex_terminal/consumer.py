import asyncio
import json
import logging
import time
import numpy as np
from typing import Dict, Any
from gex_terminal.engine import IntradayGexEngine
from gex_terminal.feed_quality import build_feed_quality_snapshot

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

class StatefulGexConsumer:
    def __init__(
        self,
        engine: IntradayGexEngine,
        target_underlying: str = "ES",
        risk_free_rate: float = 0.045,
        data_mode: str = "live",
        stale_after_seconds: float = 10.0,
    ):
        self.engine = engine
        self.target_underlying = target_underlying
        self.risk_free_rate = risk_free_rate
        self.data_mode = data_mode.upper()
        self.stale_after_seconds = stale_after_seconds
        
        # State: { strike_price: { 'C': accumulated_volume, 'P': accumulated_volume, 'iv': implied_vol } }
        self.chain_state: Dict[float, Dict[str, Any]] = {}
        # Per-expiry volume state, only populated when ticks carry an "expiry" tag.
        # { expiry_label: { strike: { 'C', 'P', 'iv' } } }
        self.expiry_state: Dict[str, Dict[float, Dict[str, Any]]] = {}
        self.current_spot: float = 0.0
        self.session_open: float = 0.0
        self.last_message_at: float | None = None
        self.last_snapshot_at: float | None = None
        self.connection_state: str = "SIM" if self.data_mode == "DEMO" else "DISCONNECTED"
        self.message_count: int = 0
        self.malformed_message_count: int = 0
        self.dropped_message_count: int = 0
        self.entitlement_error_count: int = 0
        
        # Lock to ensure thread-safe state mutations during high-frequency bursts
        self.state_lock = asyncio.Lock()

    @property
    def runtime_status(self) -> str:
        if self.data_mode == "DEMO":
            return "SIM"
        if self.data_mode == "REPLAY":
            return "REPLAY" if self.current_spot and self.chain_state else "CONNECTED"
        if self.connection_state == "DISCONNECTED":
            return "DISCONNECTED"
        if self.last_message_at is None:
            return "CONNECTED"
        if time.monotonic() - self.last_message_at > self.stale_after_seconds:
            return "STALE"
        return "LIVE"

    def mark_connected(self) -> None:
        self.connection_state = "CONNECTED"

    def mark_disconnected(self) -> None:
        self.connection_state = "DISCONNECTED"

    def record_entitlement_error(self) -> None:
        self.entitlement_error_count += 1

    def feed_quality_snapshot(
        self,
        *,
        latency_ms: float = 0.0,
        p95_latency_ms: float = 0.0,
        now: float | None = None,
    ) -> dict:
        now = time.monotonic() if now is None else now
        last_message_age = None
        if self.last_message_at is not None:
            last_message_age = max(0.0, now - self.last_message_at)
        last_snapshot_age = None
        if self.last_snapshot_at is not None:
            last_snapshot_age = max(0.0, now - self.last_snapshot_at)

        return build_feed_quality_snapshot(
            status=self.runtime_status,
            data_mode=self.data_mode,
            connection_state=self.connection_state,
            message_count=self.message_count,
            malformed_count=self.malformed_message_count,
            dropped_count=self.dropped_message_count,
            entitlement_error_count=self.entitlement_error_count,
            last_message_age_seconds=last_message_age,
            last_snapshot_age_seconds=last_snapshot_age,
            stale_after_seconds=self.stale_after_seconds,
            latency_ms=latency_ms,
            p95_latency_ms=p95_latency_ms,
        ).to_dict()

    async def update_market_state(self, raw_message: str):
        """
        Parses incoming WebSocket frames and safely increments volume data structures.
        Expects a normalized JSON structure from your data provider's broker API.
        """
        try:
            data = json.loads(raw_message)
            
            # 1. Update Underlying Spot Price
            if data.get("type") == "underlying_tick":
                if data.get("symbol") != self.target_underlying:
                    self.dropped_message_count += 1
                    return
                async with self.state_lock:
                    self.current_spot = float(data["price"])
                    self.last_message_at = time.monotonic()
                    self.message_count += 1
                return

            # 2. Update Options Traded Volume
            if data.get("type") == "options_volume_tick":
                strike = float(data["strike"])
                option_type = data["option_type"] # 'C' or 'P'
                volume = int(data["volume"])
                iv = float(data.get("iv", 0.15)) # Default or fallback IV

                expiry = data.get("expiry")

                async with self.state_lock:
                    if strike not in self.chain_state:
                        self.chain_state[strike] = {"C": 0, "P": 0, "iv": iv}

                    self.chain_state[strike][option_type] += volume
                    self.chain_state[strike]["iv"] = iv # Update local IV skew dynamically
                    self.last_message_at = time.monotonic()
                    self.message_count += 1

                    # Optionally track the same flow grouped by expiry for breakdowns.
                    if expiry is not None:
                        label = str(expiry)
                        bucket = self.expiry_state.setdefault(label, {})
                        if strike not in bucket:
                            bucket[strike] = {"C": 0, "P": 0, "iv": iv}
                        bucket[strike][option_type] += volume
                        bucket[strike]["iv"] = iv
                return

            self.dropped_message_count += 1

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            self.malformed_message_count += 1
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
            self.last_snapshot_at = time.monotonic()

        # Pass the extracted, aligned state straight to the vectorized math module
        return self.engine.compute_intraday_gex_matrix(
            spot_price=spot,
            strikes=strikes_arr,
            days_to_expiry=days_to_expiry,
            risk_free_rate=self.risk_free_rate,
            implied_vols=iv_arr,
            accumulated_call_vol=call_vol_arr,
            accumulated_put_vol=put_vol_arr
        )

    async def process_expiry_breakdown(self, days_to_expiry: float, expiry_days: dict | None = None) -> dict:
        """Return total net GEX grouped by expiry.

        When ticks have carried an ``expiry`` tag, each expiry bucket is priced with
        its own days-to-expiry (from ``expiry_days``, falling back to ``days_to_expiry``).
        When no per-expiry data exists, returns a single session bucket computed from
        the aggregate chain state.
        """
        expiry_days = expiry_days or {}
        async with self.state_lock:
            if not self.chain_state or self.current_spot == 0.0:
                return {}
            spot = self.current_spot
            buckets = {
                label: {strike: dict(values) for strike, values in strikes.items()}
                for label, strikes in self.expiry_state.items()
            }
            aggregate = {strike: dict(values) for strike, values in self.chain_state.items()}

        if not buckets:
            label = f"{days_to_expiry:g}DTE"
            return {label: self._bucket_net_gex(aggregate, spot, days_to_expiry)}

        breakdown = {}
        for label, strikes in buckets.items():
            dte = expiry_days.get(label, days_to_expiry)
            breakdown[label] = self._bucket_net_gex(strikes, spot, dte)
        return breakdown

    def _bucket_net_gex(self, strikes_map: Dict[float, Dict[str, Any]], spot: float, days_to_expiry: float) -> float:
        """Compute total net dollar GEX for one strike->volume bucket."""
        if not strikes_map:
            return 0.0
        sorted_strikes = sorted(strikes_map.keys())
        strikes_arr = np.array(sorted_strikes, dtype=float)
        iv_arr = np.array([strikes_map[k]["iv"] for k in sorted_strikes], dtype=float)
        call_arr = np.array([strikes_map[k]["C"] for k in sorted_strikes], dtype=float)
        put_arr = np.array([strikes_map[k]["P"] for k in sorted_strikes], dtype=float)
        matrix = self.engine.compute_intraday_gex_matrix(
            spot_price=spot,
            strikes=strikes_arr,
            days_to_expiry=days_to_expiry,
            risk_free_rate=self.risk_free_rate,
            implied_vols=iv_arr,
            accumulated_call_vol=call_arr,
            accumulated_put_vol=put_arr,
        )
        return float(matrix["total_net_gex"])

    async def continuous_calculation_loop(
        self,
        interval_seconds: float = 2.0,
        days_to_expiry: float = 0.01,
    ):
        """Asynchronous worker loop that periodically calculates GEX from memory state."""
        logging.info("Starting calculation dispatcher...")
        while True:
            await asyncio.sleep(interval_seconds)
            results = await self.process_latest_snapshot(days_to_expiry=days_to_expiry)
            
            if "error" not in results:
                logging.info(
                    f"Spot: {self.current_spot:.2f} | "
                    f"Gamma Wall: {results['gamma_wall_strike']} | "
                    f"Zero GEX Node: {results['zero_gamma_strike']}"
                )
