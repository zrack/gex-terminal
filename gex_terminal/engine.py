import numpy as np


class IntradayGexEngine:
    def __init__(self, multiplier: int = 100):
        """
        Initializes the engine.
        multiplier: 100 for standard equity/SPY options, 50 for E-mini ES options.
        """
        if not np.isfinite(float(multiplier)) or float(multiplier) <= 0:
            raise ValueError("multiplier must be finite and positive")
        self.multiplier = multiplier

    def calculate_d1(
        self,
        S: float,
        K: np.ndarray,
        t: np.ndarray,
        r: float,
        sigma: np.ndarray,
        *,
        pricing_model: str | np.ndarray = "black_scholes",
        carry_rate: float | np.ndarray = 0.0,
    ) -> np.ndarray:
        """Calculate d1 for Black-Scholes spot or Black-76 futures options."""
        strikes = np.asarray(K, dtype=float)
        times = np.asarray(t, dtype=float)
        vols = np.asarray(sigma, dtype=float)
        self._validate_gamma_inputs(S, strikes, times, r, vols)
        models = self._pricing_models(pricing_model, strikes.shape)
        carries = self._aligned_values(carry_rate, strikes.shape, "carry_rate")
        drift = np.where(models == "black_76", 0.0, r - carries)
        return (
            np.log(float(S) / strikes) + (drift + 0.5 * vols**2) * times
        ) / (vols * np.sqrt(times))

    def calculate_gamma(
        self,
        S: float,
        K: np.ndarray,
        t: np.ndarray,
        r: float,
        sigma: np.ndarray,
        *,
        pricing_model: str | np.ndarray = "black_scholes",
        carry_rate: float | np.ndarray = 0.0,
    ) -> np.ndarray:
        """Calculate theoretical gamma under an explicit pricing convention."""
        strikes = np.asarray(K, dtype=float)
        times = np.asarray(t, dtype=float)
        vols = np.asarray(sigma, dtype=float)
        self._validate_gamma_inputs(S, strikes, times, r, vols)
        models = self._pricing_models(pricing_model, strikes.shape)
        carries = self._aligned_values(carry_rate, strikes.shape, "carry_rate")
        d1 = self.calculate_d1(
            S,
            strikes,
            times,
            r,
            vols,
            pricing_model=models,
            carry_rate=carries,
        )
        n_prime_d1 = (1.0 / np.sqrt(2.0 * np.pi)) * np.exp(-0.5 * d1**2)
        base_gamma = n_prime_d1 / (float(S) * vols * np.sqrt(times))
        discount = np.where(
            models == "black_76",
            np.exp(-r * times),
            np.exp(-carries * times),
        )
        return base_gamma * discount

    def compute_intraday_gex_matrix(
        self, 
        spot_price: float, 
        strikes: np.ndarray, 
        days_to_expiry: float | np.ndarray,
        risk_free_rate: float, 
        implied_vols: np.ndarray,
        accumulated_call_vol: np.ndarray,
        accumulated_put_vol: np.ndarray,
        *,
        pricing_model: str | np.ndarray = "black_scholes",
        carry_rate: float | np.ndarray = 0.0,
        contract_multipliers: float | np.ndarray | None = None,
    ) -> dict:
        """
        Vectorized computation of the intraday Gamma Exposure profile using volume as an OI proxy.
        All array inputs must align perfectly in shape with the 'strikes' array.
        """
        strikes = np.asarray(strikes, dtype=float)
        implied_vols = np.asarray(implied_vols, dtype=float)
        accumulated_call_vol = np.asarray(accumulated_call_vol, dtype=float)
        accumulated_put_vol = np.asarray(accumulated_put_vol, dtype=float)
        arrays = (
            strikes,
            implied_vols,
            accumulated_call_vol,
            accumulated_put_vol,
        )
        if any(values.ndim != 1 for values in arrays):
            raise ValueError("Contract arrays must be one-dimensional")
        if len(strikes) == 0:
            raise ValueError("At least one option contract is required to compute GEX")
        if not (
            strikes.shape
            == implied_vols.shape
            == accumulated_call_vol.shape
            == accumulated_put_vol.shape
        ):
            raise ValueError("Contract arrays must have identical shapes")

        day_values = self._days_array(days_to_expiry, strikes.shape)
        if not np.all(np.isfinite(day_values)) or np.any(day_values <= 0):
            raise ValueError("days_to_expiry must be positive")
        if float(spot_price) <= 0 or not np.isfinite(float(spot_price)):
            raise ValueError("spot_price must be positive")
        if not np.isfinite(float(risk_free_rate)):
            raise ValueError("risk_free_rate must be finite")
        if np.any(strikes <= 0) or not np.all(np.isfinite(strikes)):
            raise ValueError("strikes must be positive")
        if np.any(implied_vols <= 0) or not np.all(np.isfinite(implied_vols)):
            raise ValueError("implied_vols must be positive")
        if (
            np.any(accumulated_call_vol < 0)
            or np.any(accumulated_put_vol < 0)
            or not np.all(np.isfinite(accumulated_call_vol))
            or not np.all(np.isfinite(accumulated_put_vol))
        ):
            raise ValueError("accumulated volumes must be finite and non-negative")

        models = self._pricing_models(pricing_model, strikes.shape)
        carries = self._aligned_values(carry_rate, strikes.shape, "carry_rate")
        multiplier_values = self._aligned_values(
            self.multiplier if contract_multipliers is None else contract_multipliers,
            strikes.shape,
            "contract_multipliers",
        )
        if np.any(multiplier_values <= 0):
            raise ValueError("contract_multipliers must be positive")

        # Convert days to expiry into fractions of a 365-day year.
        t = day_values / 365.0
        r = risk_free_rate
        
        # 1. Calculate theoretical gamma per contract row.
        contract_gammas = self.calculate_gamma(
            spot_price,
            strikes,
            t,
            r,
            implied_vols,
            pricing_model=models,
            carry_rate=carries,
        )
        
        # 2. Scale Gamma to Dollar GEX per 1% move
        # Formula: Vol * Gamma * Spot * (1% of Spot) * Contract Multiplier
        gex_scaling_factor = (
            contract_gammas
            * spot_price
            * (spot_price * 0.01)
            * multiplier_values
        )
        
        contract_call_gex = accumulated_call_vol * gex_scaling_factor
        contract_put_gex = accumulated_put_vol * gex_scaling_factor * -1.0

        # Multiple expiries and providers can share a strike. Aggregate contract
        # rows before deriving structural levels so the matrix remains one row per
        # strike while preserving contract-specific DTE and pricing inputs.
        unique_strikes, inverse = np.unique(strikes, return_inverse=True)
        call_gex_dollars = np.zeros_like(unique_strikes, dtype=float)
        put_gex_dollars = np.zeros_like(unique_strikes, dtype=float)
        call_volume = np.zeros_like(unique_strikes, dtype=float)
        put_volume = np.zeros_like(unique_strikes, dtype=float)
        gamma_weighted = np.zeros_like(unique_strikes, dtype=float)
        gamma_weights = np.zeros_like(unique_strikes, dtype=float)
        np.add.at(call_gex_dollars, inverse, contract_call_gex)
        np.add.at(put_gex_dollars, inverse, contract_put_gex)
        np.add.at(call_volume, inverse, accumulated_call_vol)
        np.add.at(put_volume, inverse, accumulated_put_vol)
        row_weights = accumulated_call_vol + accumulated_put_vol
        np.add.at(gamma_weighted, inverse, contract_gammas * row_weights)
        np.add.at(gamma_weights, inverse, row_weights)
        gammas = np.divide(
            gamma_weighted,
            gamma_weights,
            out=np.zeros_like(gamma_weighted),
            where=gamma_weights > 0,
        )
        strikes = unique_strikes
        net_gex_dollars = call_gex_dollars + put_gex_dollars
        
        # 3. Locate structural boundaries
        total_net_gex = np.sum(net_gex_dollars)
        abs_net = np.abs(net_gex_dollars)
        gamma_wall_index = np.argmax(abs_net)
        gamma_wall_strike = strikes[gamma_wall_index]

        # Call wall: strike with the most positive (call-side) dollar gamma.
        # Put wall: strike with the most negative (put-side) dollar gamma.
        call_wall_strike = strikes[np.argmax(call_gex_dollars)]
        put_wall_strike = strikes[np.argmax(np.abs(put_gex_dollars))]

        # Concentration: how tightly net gamma is clustered. concentration_ratio is
        # the single largest strike's share of total |net| gamma; concentration_band
        # is the strike range covering the smallest set of strikes that together hold
        # at least 70% of total |net| gamma.
        total_abs = float(np.sum(abs_net))
        concentration_ratio = float(np.max(abs_net) / total_abs) if total_abs else 0.0
        band_low, band_high = self.concentration_band(strikes, abs_net, threshold=0.70)

        strike_profile_flip = self.strike_profile_flip(strikes, net_gex_dollars)
        nearest_neutral_strike = float(strikes[np.argmin(np.abs(net_gex_dollars))])
        zero_gamma_strike = (
            strike_profile_flip
            if strike_profile_flip is not None
            else nearest_neutral_strike
        )
        nearest_zero_idx = np.argmin(np.abs(strikes - zero_gamma_strike))
        nearest_zero_strike = strikes[nearest_zero_idx]

        return {
            "strikes": strikes.tolist(),
            "gammas": gammas.tolist(),
            "call_gex": call_gex_dollars.tolist(),
            "put_gex": put_gex_dollars.tolist(),
            "net_gex": net_gex_dollars.tolist(),
            "total_net_gex": total_net_gex,
            "gamma_wall_strike": gamma_wall_strike,
            "call_wall_strike": call_wall_strike,
            "put_wall_strike": put_wall_strike,
            "concentration_ratio": concentration_ratio,
            "concentration_band_low": band_low,
            "concentration_band_high": band_high,
            "zero_gamma_strike": zero_gamma_strike,
            "nearest_zero_strike": nearest_zero_strike,
            "strike_profile_flip": strike_profile_flip,
            "nearest_neutral_strike": nearest_neutral_strike,
            "contract_count": int(len(inverse)),
            "pricing_models": sorted(set(models.tolist())),
            "zero_gamma_method": (
                "strike_profile_linear_interpolation"
                if strike_profile_flip is not None
                else "nearest_strike_bucket_fallback"
            ),
            "zero_gamma_semantics": "legacy_strike_profile",
            "gamma_aggregation": "quantity_weighted_mean",
            "call_volume": call_volume.tolist(),
            "put_volume": put_volume.tolist(),
            "units": "USD gamma exposure per 1% underlying move",
            "day_count_convention": "ACT/365",
        }

    def compute_directionalized_gex_matrix(
        self,
        spot_price: float,
        strikes: np.ndarray,
        days_to_expiry: float | np.ndarray,
        risk_free_rate: float,
        implied_vols: np.ndarray,
        buy_aggressor_vol: np.ndarray,
        sell_aggressor_vol: np.ndarray,
        unknown_aggressor_vol: np.ndarray,
        *,
        pricing_model: str | np.ndarray = "black_scholes",
        carry_rate: float | np.ndarray = 0.0,
        contract_multipliers: float | np.ndarray | None = None,
    ) -> dict:
        """Compute an aggressor-directionalized dealer-gamma proxy.

        The model assumes an aggressor buy leaves the passive counterparty short
        one option's gamma and an aggressor sell leaves it long gamma. Participant
        identity and opening/closing state remain unobserved, so this is emitted
        beside—not in place of—the default call-positive/put-negative proxy.
        """
        strikes = np.asarray(strikes, dtype=float)
        implied_vols = np.asarray(implied_vols, dtype=float)
        buy_volume = np.asarray(buy_aggressor_vol, dtype=float)
        sell_volume = np.asarray(sell_aggressor_vol, dtype=float)
        unknown_volume = np.asarray(unknown_aggressor_vol, dtype=float)
        arrays = (strikes, implied_vols, buy_volume, sell_volume, unknown_volume)
        if any(values.ndim != 1 for values in arrays):
            raise ValueError("Directionalized contract arrays must be one-dimensional")
        if len(strikes) == 0:
            raise ValueError("At least one option contract is required to compute GEX")
        if any(values.shape != strikes.shape for values in arrays[1:]):
            raise ValueError("Directionalized contract arrays must have identical shapes")
        if any(
            np.any(values < 0) or not np.all(np.isfinite(values))
            for values in (buy_volume, sell_volume, unknown_volume)
        ):
            raise ValueError("Directionalized volumes must be finite and non-negative")

        day_values = self._days_array(days_to_expiry, strikes.shape)
        models = self._pricing_models(pricing_model, strikes.shape)
        carries = self._aligned_values(carry_rate, strikes.shape, "carry_rate")
        multiplier_values = self._aligned_values(
            self.multiplier if contract_multipliers is None else contract_multipliers,
            strikes.shape,
            "contract_multipliers",
        )
        self._validate_gamma_inputs(
            float(spot_price),
            strikes,
            day_values / 365.0,
            float(risk_free_rate),
            implied_vols,
        )
        if np.any(multiplier_values <= 0):
            raise ValueError("contract_multipliers must be positive")

        contract_gammas = self.calculate_gamma(
            float(spot_price),
            strikes,
            day_values / 365.0,
            float(risk_free_rate),
            implied_vols,
            pricing_model=models,
            carry_rate=carries,
        )
        scaling = (
            contract_gammas
            * float(spot_price)
            * (float(spot_price) * 0.01)
            * multiplier_values
        )
        buy_gex = buy_volume * scaling * -1.0
        sell_gex = sell_volume * scaling

        unique_strikes, inverse = np.unique(strikes, return_inverse=True)
        buy_gex_by_strike = np.zeros_like(unique_strikes, dtype=float)
        sell_gex_by_strike = np.zeros_like(unique_strikes, dtype=float)
        buy_by_strike = np.zeros_like(unique_strikes, dtype=float)
        sell_by_strike = np.zeros_like(unique_strikes, dtype=float)
        unknown_by_strike = np.zeros_like(unique_strikes, dtype=float)
        gamma_weighted = np.zeros_like(unique_strikes, dtype=float)
        gamma_weights = np.zeros_like(unique_strikes, dtype=float)
        np.add.at(buy_gex_by_strike, inverse, buy_gex)
        np.add.at(sell_gex_by_strike, inverse, sell_gex)
        np.add.at(buy_by_strike, inverse, buy_volume)
        np.add.at(sell_by_strike, inverse, sell_volume)
        np.add.at(unknown_by_strike, inverse, unknown_volume)
        row_weights = buy_volume + sell_volume + unknown_volume
        np.add.at(gamma_weighted, inverse, contract_gammas * row_weights)
        np.add.at(gamma_weights, inverse, row_weights)
        gammas = np.divide(
            gamma_weighted,
            gamma_weights,
            out=np.zeros_like(gamma_weighted),
            where=gamma_weights > 0,
        )

        net_gex = buy_gex_by_strike + sell_gex_by_strike
        total_abs = float(np.sum(np.abs(net_gex)))
        gamma_wall = float(unique_strikes[int(np.argmax(np.abs(net_gex)))])
        flip = self.strike_profile_flip(unique_strikes, net_gex)
        nearest_neutral = float(unique_strikes[int(np.argmin(np.abs(net_gex)))])
        zero_gamma = flip if flip is not None else nearest_neutral
        band_low, band_high = self.concentration_band(
            unique_strikes,
            np.abs(net_gex),
            threshold=0.70,
        )
        known_volume = float(np.sum(buy_volume + sell_volume))
        unknown_total = float(np.sum(unknown_volume))
        all_volume = known_volume + unknown_total

        return {
            "model": "aggressor_directionalized_volume",
            "model_version": "gex-terminal.aggressor-directionalized.v1",
            "status": "available" if known_volume > 0 else "insufficient_directional_coverage",
            "strikes": unique_strikes.tolist(),
            "gammas": gammas.tolist(),
            "buy_aggressor_volume": buy_by_strike.tolist(),
            "sell_aggressor_volume": sell_by_strike.tolist(),
            "unknown_aggressor_volume": unknown_by_strike.tolist(),
            "buy_aggressor_gex": buy_gex_by_strike.tolist(),
            "sell_aggressor_gex": sell_gex_by_strike.tolist(),
            "net_gex": net_gex.tolist(),
            "total_net_gex": float(np.sum(net_gex)),
            "gamma_wall_strike": gamma_wall,
            "zero_gamma_strike": float(zero_gamma),
            "strike_profile_flip": float(flip) if flip is not None else None,
            "nearest_neutral_strike": nearest_neutral,
            "concentration_ratio": (
                float(np.max(np.abs(net_gex)) / total_abs) if total_abs else 0.0
            ),
            "concentration_band_low": float(band_low),
            "concentration_band_high": float(band_high),
            "known_direction_volume": known_volume,
            "unknown_direction_volume": unknown_total,
            "total_trade_volume": all_volume,
            "directional_coverage": known_volume / all_volume if all_volume else 0.0,
            "contract_count": int(len(strikes)),
            "pricing_models": sorted(set(models.tolist())),
            "units": "USD gamma exposure per 1% underlying move",
            "day_count_convention": "ACT/365",
            "directional_assumption": (
                "aggressor_buy_passive_counterparty_short_gamma; "
                "aggressor_sell_passive_counterparty_long_gamma"
            ),
            "participant_classification": "unobserved",
            "opening_closing_classification": "unobserved",
            "predictive_validity": "unmeasured",
        }

    @staticmethod
    def _validate_gamma_inputs(
        spot: float,
        strikes: np.ndarray,
        times: np.ndarray,
        risk_free_rate: float,
        vols: np.ndarray,
    ) -> None:
        arrays = (strikes, times, vols)
        if any(values.ndim != 1 for values in arrays):
            raise ValueError("Gamma contract arrays must be one-dimensional")
        if not (strikes.shape == times.shape == vols.shape):
            raise ValueError("Gamma contract arrays must have identical shapes")
        if len(strikes) == 0:
            raise ValueError("At least one option contract is required")
        if not np.isfinite(float(spot)) or float(spot) <= 0:
            raise ValueError("spot must be finite and positive")
        if not np.isfinite(float(risk_free_rate)):
            raise ValueError("risk_free_rate must be finite")
        if not np.all(np.isfinite(strikes)) or np.any(strikes <= 0):
            raise ValueError("strikes must be finite and positive")
        if not np.all(np.isfinite(times)) or np.any(times <= 0):
            raise ValueError("time to expiry must be finite and positive")
        if not np.all(np.isfinite(vols)) or np.any(vols <= 0):
            raise ValueError("volatility must be finite and positive")

    @staticmethod
    def _days_array(days_to_expiry: float | np.ndarray, shape: tuple[int, ...]) -> np.ndarray:
        if np.isscalar(days_to_expiry):
            return np.full(shape, float(days_to_expiry), dtype=float)
        values = np.asarray(days_to_expiry, dtype=float)
        if values.shape != shape:
            raise ValueError("days_to_expiry array must align with contract rows")
        return values

    @staticmethod
    def _pricing_models(
        pricing_model: str | np.ndarray,
        shape: tuple[int, ...],
    ) -> np.ndarray:
        if isinstance(pricing_model, str):
            models = np.full(shape, pricing_model.lower(), dtype=object)
        else:
            models = np.asarray(pricing_model, dtype=object)
            if models.shape != shape:
                raise ValueError("pricing_model array must align with contract rows")
            models = np.char.lower(models.astype(str)).astype(object)
        supported = {"black_scholes", "black_76"}
        invalid = sorted(set(models.tolist()) - supported)
        if invalid:
            raise ValueError(f"Unsupported pricing model(s): {', '.join(invalid)}")
        return models

    @staticmethod
    def _aligned_values(
        value: float | np.ndarray,
        shape: tuple[int, ...],
        name: str,
    ) -> np.ndarray:
        if np.isscalar(value):
            values = np.full(shape, float(value), dtype=float)
        else:
            values = np.asarray(value, dtype=float)
            if values.shape != shape:
                raise ValueError(f"{name} array must align with contract rows")
        if not np.all(np.isfinite(values)):
            raise ValueError(f"{name} must be finite")
        return values

    @staticmethod
    def concentration_band(strikes: np.ndarray, abs_net: np.ndarray, threshold: float = 0.70) -> tuple:
        """Return (low, high) strikes for the smallest set of strikes whose absolute
        net gamma sums to at least `threshold` of the total. Falls back to the full
        strike range when there is no exposure."""
        if len(strikes) == 0:
            return 0.0, 0.0
        total = float(np.sum(abs_net))
        if total <= 0:
            return float(np.min(strikes)), float(np.max(strikes))
        order = np.argsort(abs_net)[::-1]
        cumulative = 0.0
        chosen = []
        for idx in order:
            chosen.append(float(strikes[idx]))
            cumulative += float(abs_net[idx])
            if cumulative >= threshold * total:
                break
        return min(chosen), max(chosen)

    @staticmethod
    def interpolate_zero_gamma_strike(strikes: np.ndarray, net_gex_dollars: np.ndarray) -> float:
        """
        Estimate the zero-gamma boundary between strikes with linear interpolation.

        If no sign change exists in the current strike slice, fall back to the strike
        with the smallest absolute net GEX.
        """
        if len(strikes) == 0:
            return 0.0

        crossing = IntradayGexEngine.strike_profile_flip(strikes, net_gex_dollars)
        if crossing is not None:
            return crossing
        return float(strikes[np.argmin(np.abs(net_gex_dollars))])

    @staticmethod
    def strike_profile_flip(
        strikes: np.ndarray,
        net_gex_dollars: np.ndarray,
    ) -> float | None:
        """Return an adjacent-strike exposure crossing without a fallback.

        This is a crossing of the strike-bucket profile, not the underlying spot
        where aggregate portfolio gamma reprices to zero.
        """
        if len(strikes) == 0:
            return None

        signs = np.sign(net_gex_dollars)
        exact_zero = np.where(signs == 0)[0]
        if len(exact_zero):
            return float(strikes[exact_zero[0]])

        sign_changes = np.where(signs[:-1] * signs[1:] < 0)[0]
        if len(sign_changes):
            candidates = []
            for idx in sign_changes:
                x0, x1 = strikes[idx], strikes[idx + 1]
                y0, y1 = net_gex_dollars[idx], net_gex_dollars[idx + 1]
                if y1 == y0:
                    candidates.append(float(x0))
                else:
                    candidates.append(float(x0 - y0 * (x1 - x0) / (y1 - y0)))

            spot_center = float(strikes[np.argmin(np.abs(net_gex_dollars))])
            return min(candidates, key=lambda value: abs(value - spot_center))

        return None

# --- Quick Verification Block ---
if __name__ == "__main__":
    engine = IntradayGexEngine(multiplier=50) # ES Multiplier
    
    # Mocking a subset of an ES options chain around a 5000 spot price
    mock_strikes = np.array([4980, 4990, 5000, 5010, 5020])
    mock_ivs = np.array([0.14, 0.13, 0.12, 0.13, 0.14]) # Skew curve
    mock_call_vol = np.array([100, 450, 1200, 800, 300])
    mock_put_vol = np.array([1400, 950, 600, 200, 50])
    
    matrix = engine.compute_intraday_gex_matrix(
        spot_price=5000.0,
        strikes=mock_strikes,
        days_to_expiry=0.05, # ~1.2 hours to expiration (0-DTE environment)
        risk_free_rate=0.045,
        implied_vols=mock_ivs,
        accumulated_call_vol=mock_call_vol,
        accumulated_put_vol=mock_put_vol
    )
    
    print(f"System Check complete.")
    print(f"Calculated Gamma Wall: {matrix['gamma_wall_strike']}")
    print(f"Calculated Volatility Flip Node: {matrix['zero_gamma_strike']}")
