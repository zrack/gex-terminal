import numpy as np
from scipy.stats import norm

class IntradayGexEngine:
    def __init__(self, multiplier: int = 100):
        """
        Initializes the engine.
        multiplier: 100 for standard equity/SPY options, 50 for E-mini ES options.
        """
        self.multiplier = multiplier

    def calculate_d1(self, S: float, K: np.ndarray, t: np.ndarray, r: float, sigma: np.ndarray) -> np.ndarray:
        """Calculates d1 for an array of strikes, times to expiration, and IVs."""
        # Prevent division by zero if an option is exactly at expiration
        t = np.where(t == 0, 1e-5, t)
        return (np.log(S / K) + (r + 0.5 * sigma**2) * t) / (sigma * np.sqrt(t))

    def calculate_gamma(self, S: float, K: np.ndarray, t: np.ndarray, r: float, sigma: np.ndarray) -> np.ndarray:
        """Calculates theoretical Gamma for an array of strikes."""
        t = np.where(t == 0, 1e-5, t)
        d1 = self.calculate_d1(S, K, t, r, sigma)
        n_prime_d1 = (1.0 / np.sqrt(2.0 * np.pi)) * np.exp(-0.5 * d1**2)
        gamma = n_prime_d1 / (S * sigma * np.sqrt(t))
        return gamma

    def compute_intraday_gex_matrix(
        self, 
        spot_price: float, 
        strikes: np.ndarray, 
        days_to_expiry: float, 
        risk_free_rate: float, 
        implied_vols: np.ndarray,
        accumulated_call_vol: np.ndarray,
        accumulated_put_vol: np.ndarray
    ) -> dict:
        """
        Vectorized computation of the intraday Gamma Exposure profile using volume as an OI proxy.
        All array inputs must align perfectly in shape with the 'strikes' array.
        """
        # Convert days to expiry into fraction of a 365-day year
        t = np.full_like(strikes, days_to_expiry / 365.0, dtype=float)
        r = risk_free_rate
        
        # 1. Calculate theoretical Gamma per strike
        gammas = self.calculate_gamma(spot_price, strikes, t, r, implied_vols)
        
        # 2. Scale Gamma to Dollar GEX per 1% move
        # Formula: Vol * Gamma * Spot * (1% of Spot) * Contract Multiplier
        gex_scaling_factor = gammas * spot_price * (spot_price * 0.01) * self.multiplier
        
        call_gex_dollars = accumulated_call_vol * gex_scaling_factor
        put_gex_dollars = accumulated_put_vol * gex_scaling_factor * -1.0
        net_gex_dollars = call_gex_dollars + put_gex_dollars
        
        # 3. Locate structural boundaries
        total_net_gex = np.sum(net_gex_dollars)
        gamma_wall_index = np.argmax(np.abs(net_gex_dollars))
        gamma_wall_strike = strikes[gamma_wall_index]
        
        # Zero Gamma approximation: find the strike where the sign flips or approaches absolute zero
        zero_gamma_idx = np.argmin(np.abs(net_gex_dollars))
        zero_gamma_strike = strikes[zero_gamma_idx]

        return {
            "strikes": strikes.tolist(),
            "call_gex": call_gex_dollars.tolist(),
            "put_gex": put_gex_dollars.tolist(),
            "net_gex": net_gex_dollars.tolist(),
            "total_net_gex": total_net_gex,
            "gamma_wall_strike": gamma_wall_strike,
            "zero_gamma_strike": zero_gamma_strike
        }

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