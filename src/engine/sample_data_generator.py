from __future__ import annotations

import numpy as np
import pandas as pd
from pandas.tseries.offsets import BDay

from src.engine.config import EVENTS_FILE, IV_SURFACE_FILE, SPOT_HISTORY_FILE


def generate_spot_history(
    start_date: str = "2024-01-02",
    periods: int = 140,
    initial_spot: float = 100.0,
    seed: int = 42,
) -> pd.DataFrame:
    """
    Generate a synthetic but plausible spot price history.

    The path is split into 3 regimes:
    1) mild uptrend + low vol
    2) selloff + high vol
    3) rebound + medium vol

    This is useful because it creates:
    - momentum changes
    - drawdown
    - more realistic realized volatility patterns
    """
    if periods < 80:
        raise ValueError("Use at least 80 business days to get meaningful rolling features.")

    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(start=start_date, periods=periods)

    # periods prices => periods - 1 returns
    total_returns = periods - 1

    # Split the return history into 3 market regimes
    seg1 = 50
    seg2 = 35
    seg3 = total_returns - seg1 - seg2

    # Regime 1: positive drift, low vol
    r1 = rng.normal(loc=0.0006, scale=0.008, size=seg1)

    # Regime 2: negative drift, higher vol (selloff / stress phase)
    r2 = rng.normal(loc=-0.0012, scale=0.020, size=seg2)

    # Regime 3: rebound, still somewhat volatile
    r3 = rng.normal(loc=0.0010, scale=0.012, size=seg3)

    log_returns = np.concatenate([r1, r2, r3])

    prices = [initial_spot]
    for r in log_returns:
        next_price = prices[-1] * np.exp(r)
        prices.append(next_price)

    df = pd.DataFrame(
        {
            "date": dates,
            "close": np.round(prices, 2),
        }
    )

    return df


def generate_iv_surface(latest_spot: float, valuation_date: pd.Timestamp) -> pd.DataFrame:
    """
    Generate a simplified implied volatility surface snapshot.

    We use 2 maturities and 5 moneyness buckets.
    The smile is designed to show a typical equity put skew:
    downside puts richer than upside calls.
    """
    surface_map = {
        30: {
            0.90: 0.31,
            0.95: 0.28,
            1.00: 0.25,
            1.05: 0.24,
            1.10: 0.23,
        },
        90: {
            0.90: 0.29,
            0.95: 0.27,
            1.00: 0.24,
            1.05: 0.23,
            1.10: 0.22,
        },
    }

    rows = []

    for tenor_days, smile in surface_map.items():
        for moneyness, iv in smile.items():
            strike = round(latest_spot * moneyness, 2)

            # For simplicity:
            # downside strikes are labeled as puts,
            # upside strikes as calls,
            # ATM as call (just to keep the schema simple).
            if moneyness < 1.0:
                option_type = "put"
            else:
                option_type = "call"

            rows.append(
                {
                    "date": valuation_date,
                    "tenor_days": tenor_days,
                    "strike": strike,
                    "option_type": option_type,
                    "iv": iv,
                }
            )

    return pd.DataFrame(rows)


def generate_events(valuation_date: pd.Timestamp) -> pd.DataFrame:
    """
    Generate a small forward-looking event calendar.
    """
    events = [
        {
            "event_date": valuation_date + BDay(7),
            "event_type": "earnings",
            "description": "Quarterly earnings release",
        },
        {
            "event_date": valuation_date + BDay(18),
            "event_type": "macro",
            "description": "Central bank decision",
        },
    ]

    return pd.DataFrame(events)


def save_sample_data() -> None:
    """
    Generate and save all sample datasets to the project's data folder.
    """
    spot_df = generate_spot_history()
    valuation_date = pd.to_datetime(spot_df["date"].iloc[-1])
    latest_spot = float(spot_df["close"].iloc[-1])

    iv_df = generate_iv_surface(latest_spot=latest_spot, valuation_date=valuation_date)
    events_df = generate_events(valuation_date=valuation_date)

    spot_df.to_csv(SPOT_HISTORY_FILE, index=False)
    iv_df.to_csv(IV_SURFACE_FILE, index=False)
    events_df.to_csv(EVENTS_FILE, index=False)

    print("=== SAMPLE DATA GENERATED ===")
    print(f"Spot history saved to: {SPOT_HISTORY_FILE}")
    print(f"IV surface saved to:   {IV_SURFACE_FILE}")
    print(f"Events saved to:       {EVENTS_FILE}")
    print(f"\nLatest spot: {latest_spot:.2f}")
    print(f"Valuation date: {valuation_date.date()}")


if __name__ == "__main__":
    save_sample_data()