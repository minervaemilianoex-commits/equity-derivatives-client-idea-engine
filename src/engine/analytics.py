from __future__ import annotations

from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

from src.engine.config import MARKET_CONFIG, MarketConfig


def compute_log_returns(spot_df: pd.DataFrame) -> pd.DataFrame:
    """
    Add log returns to the spot history.

    Formula:
        r_t = ln(S_t / S_{t-1})
    """
    df = spot_df.copy()
    df["log_return"] = np.log(df["close"] / df["close"].shift(1))
    return df


def add_realized_vol_columns(
    spot_df: pd.DataFrame,
    market_config: MarketConfig = MARKET_CONFIG,
) -> pd.DataFrame:
    """
    Add rolling realized volatility columns.

    Formula:
        RV_window = std(log_returns over window) * sqrt(252)
    """
    df = compute_log_returns(spot_df)

    short_window = market_config.rv_window_short
    long_window = market_config.rv_window_long

    df[f"rv_{short_window}d"] = (
        df["log_return"].rolling(short_window).std() * np.sqrt(market_config.trading_days_per_year)
    )
    df[f"rv_{long_window}d"] = (
        df["log_return"].rolling(long_window).std() * np.sqrt(market_config.trading_days_per_year)
    )

    return df


def add_momentum_columns(
    spot_df: pd.DataFrame,
    market_config: MarketConfig = MARKET_CONFIG,
) -> pd.DataFrame:
    """
    Add simple momentum columns.

    Formula:
        momentum_k = S_t / S_{t-k} - 1
    """
    df = spot_df.copy()

    short_window = market_config.momentum_window_short
    long_window = market_config.momentum_window_long

    df[f"mom_{short_window}d"] = df["close"].pct_change(short_window)
    df[f"mom_{long_window}d"] = df["close"].pct_change(long_window)

    return df


def add_drawdown_column(
    spot_df: pd.DataFrame,
    market_config: MarketConfig = MARKET_CONFIG,
) -> pd.DataFrame:
    """
    Add rolling drawdown column.

    Formula:
        drawdown_t = S_t / rolling_max_t - 1
    """
    df = spot_df.copy()

    lookback = market_config.drawdown_lookback
    rolling_peak = df["close"].rolling(window=lookback, min_periods=1).max()

    df["rolling_peak"] = rolling_peak
    df["drawdown"] = df["close"] / df["rolling_peak"] - 1.0

    return df


def enrich_spot_history(
    spot_df: pd.DataFrame,
    market_config: MarketConfig = MARKET_CONFIG,
) -> pd.DataFrame:
    """
    Build a feature-enriched spot history table.
    """
    df = add_realized_vol_columns(spot_df, market_config=market_config)
    df = add_momentum_columns(df, market_config=market_config)
    df = add_drawdown_column(df, market_config=market_config)
    return df


def classify_vol_regime(
    atm_iv: float,
    market_config: MarketConfig = MARKET_CONFIG,
) -> str:
    """
    Classify the absolute level of implied volatility.
    """
    if atm_iv < market_config.low_vol_threshold:
        return "low"
    if atm_iv > market_config.high_vol_threshold:
        return "high"
    return "normal"


def classify_vrp(
    vrp: float,
    market_config: MarketConfig = MARKET_CONFIG,
) -> str:
    """
    Classify IV versus RV.

    VRP = ATM IV - RV
    """
    if vrp > market_config.vrp_rich_threshold:
        return "IV_rich"
    if vrp < market_config.vrp_cheap_threshold:
        return "IV_cheap"
    return "IV_fair"


def classify_skew(
    skew_metric: float,
    market_config: MarketConfig = MARKET_CONFIG,
) -> str:
    """
    Classify skew.

    We define:
        skew_metric = IV(95% put proxy) - IV(105% call proxy)

    Interpretation:
    - positive => put skew
    - negative => call skew
    """
    if skew_metric >= market_config.skew_extreme_threshold:
        return "put_skew_extreme"
    if skew_metric >= market_config.skew_put_threshold:
        return "put_skew"
    if skew_metric <= -market_config.skew_extreme_threshold:
        return "call_skew_extreme"
    if skew_metric <= market_config.skew_call_threshold:
        return "call_skew"
    return "neutral"


def classify_trend(momentum_short: float, momentum_long: float) -> str:
    """
    Classify trend from short and long momentum.
    """
    if pd.isna(momentum_short) or pd.isna(momentum_long):
        return "unknown"

    if momentum_short > 0 and momentum_long > 0:
        return "positive"
    if momentum_short < 0 and momentum_long < 0:
        return "negative"
    return "mixed"


def classify_drawdown(drawdown: float) -> str:
    """
    Simple drawdown classification.
    """
    if pd.isna(drawdown):
        return "unknown"
    if drawdown <= -0.15:
        return "deep_drawdown"
    if drawdown <= -0.05:
        return "moderate_drawdown"
    return "contained_drawdown"


def _pick_nearest_iv(
    surface_df: pd.DataFrame,
    target_strike: float,
    option_type: Optional[str] = None,
) -> Dict[str, float]:
    """
    Pick the IV corresponding to the strike closest to target_strike.
    """
    df = surface_df.copy()

    if option_type is not None:
        filtered = df[df["option_type"] == option_type].copy()
        if not filtered.empty:
            df = filtered

    if df.empty:
        raise ValueError("No rows available to extract IV.")

    idx = (df["strike"] - target_strike).abs().idxmin()
    row = df.loc[idx]

    return {
        "strike": float(row["strike"]),
        "iv": float(row["iv"]),
    }


def extract_iv_metrics(
    iv_df: pd.DataFrame,
    spot: float,
    target_tenor_days: int = 30,
) -> Dict[str, Any]:
    """
    Extract a simplified IV snapshot:
    - ATM IV
    - 95% put proxy IV
    - 105% call proxy IV
    - skew metric
    """
    latest_date = pd.to_datetime(iv_df["date"]).max()
    latest_df = iv_df[pd.to_datetime(iv_df["date"]) == latest_date].copy()

    if latest_df.empty:
        raise ValueError("IV dataframe is empty after filtering latest date.")

    available_tenors = latest_df["tenor_days"].unique()
    selected_tenor = min(available_tenors, key=lambda x: abs(x - target_tenor_days))

    surface = latest_df[latest_df["tenor_days"] == selected_tenor].copy()

    atm_info = _pick_nearest_iv(surface, target_strike=spot)
    put_95_info = _pick_nearest_iv(surface, target_strike=spot * 0.95, option_type="put")
    call_105_info = _pick_nearest_iv(surface, target_strike=spot * 1.05, option_type="call")

    atm_iv = atm_info["iv"]
    put_95_iv = put_95_info["iv"]
    call_105_iv = call_105_info["iv"]

    skew_metric = put_95_iv - call_105_iv
    downside_skew_vs_atm = put_95_iv - atm_iv

    return {
        "iv_date": latest_date,
        "tenor_days": int(selected_tenor),
        "atm_strike": atm_info["strike"],
        "atm_iv": atm_iv,
        "put_95_strike": put_95_info["strike"],
        "put_95_iv": put_95_iv,
        "call_105_strike": call_105_info["strike"],
        "call_105_iv": call_105_iv,
        "skew_metric": skew_metric,
        "downside_skew_vs_atm": downside_skew_vs_atm,
    }


def detect_nearest_catalyst(
    events_df: pd.DataFrame,
    valuation_date: pd.Timestamp,
    market_config: MarketConfig = MARKET_CONFIG,
) -> Dict[str, Any]:
    """
    Find the nearest forward-looking event and classify whether it is near enough
    to matter for the current idea-generation process.
    """
    df = events_df.copy()
    df["event_date"] = pd.to_datetime(df["event_date"])

    future_events = df[df["event_date"] >= valuation_date].sort_values("event_date")

    if future_events.empty:
        return {
            "has_catalyst": False,
            "days_to_next_event": None,
            "next_event_type": None,
            "next_event_description": None,
        }

    next_event = future_events.iloc[0]
    days_to_next_event = int((next_event["event_date"] - valuation_date).days)

    return {
        "has_catalyst": days_to_next_event <= market_config.catalyst_window_days,
        "days_to_next_event": days_to_next_event,
        "next_event_type": next_event["event_type"],
        "next_event_description": next_event["description"],
    }


def build_market_snapshot(
    spot_df: pd.DataFrame,
    iv_df: pd.DataFrame,
    events_df: pd.DataFrame,
    market_config: MarketConfig = MARKET_CONFIG,
) -> Dict[str, Any]:
    """
    Build a single summary dictionary containing the latest market state.
    """
    enriched_spot = enrich_spot_history(spot_df, market_config=market_config)
    latest_row = enriched_spot.iloc[-1]

    spot = float(latest_row["close"])
    valuation_date = pd.to_datetime(latest_row["date"])

    rv_short_col = f"rv_{market_config.rv_window_short}d"
    rv_long_col = f"rv_{market_config.rv_window_long}d"
    mom_short_col = f"mom_{market_config.momentum_window_short}d"
    mom_long_col = f"mom_{market_config.momentum_window_long}d"

    rv_20d = float(latest_row[rv_short_col]) if pd.notna(latest_row[rv_short_col]) else np.nan
    rv_60d = float(latest_row[rv_long_col]) if pd.notna(latest_row[rv_long_col]) else np.nan
    mom_20d = float(latest_row[mom_short_col]) if pd.notna(latest_row[mom_short_col]) else np.nan
    mom_60d = float(latest_row[mom_long_col]) if pd.notna(latest_row[mom_long_col]) else np.nan
    drawdown = float(latest_row["drawdown"]) if pd.notna(latest_row["drawdown"]) else np.nan

    iv_metrics = extract_iv_metrics(iv_df=iv_df, spot=spot, target_tenor_days=30)
    catalyst_info = detect_nearest_catalyst(
        events_df=events_df,
        valuation_date=valuation_date,
        market_config=market_config,
    )

    atm_iv = float(iv_metrics["atm_iv"])
    vrp_20d = atm_iv - rv_20d if not np.isnan(rv_20d) else np.nan

    snapshot = {
        "valuation_date": valuation_date,
        "spot": spot,
        "rv_20d": rv_20d,
        "rv_60d": rv_60d,
        "atm_iv_30d": atm_iv,
        "put_95_iv": float(iv_metrics["put_95_iv"]),
        "call_105_iv": float(iv_metrics["call_105_iv"]),
        "skew_metric": float(iv_metrics["skew_metric"]),
        "downside_skew_vs_atm": float(iv_metrics["downside_skew_vs_atm"]),
        "vrp_20d": vrp_20d,
        "momentum_20d": mom_20d,
        "momentum_60d": mom_60d,
        "drawdown": drawdown,
        "vol_regime": classify_vol_regime(atm_iv, market_config=market_config),
        "vrp_regime": classify_vrp(vrp_20d, market_config=market_config),
        "skew_regime": classify_skew(float(iv_metrics["skew_metric"]), market_config=market_config),
        "trend_regime": classify_trend(mom_20d, mom_60d),
        "drawdown_regime": classify_drawdown(drawdown),
        "has_catalyst": catalyst_info["has_catalyst"],
        "days_to_next_event": catalyst_info["days_to_next_event"],
        "next_event_type": catalyst_info["next_event_type"],
        "next_event_description": catalyst_info["next_event_description"],
    }

    return snapshot


def snapshot_to_dataframe(snapshot: Dict[str, Any]) -> pd.DataFrame:
    """
    Convert the market snapshot dictionary into a 2-column dataframe
    for easier printing or reporting.
    """
    df = pd.DataFrame(
        {
            "metric": list(snapshot.keys()),
            "value": list(snapshot.values()),
        }
    )
    return df