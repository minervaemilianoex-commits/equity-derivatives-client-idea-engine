from __future__ import annotations

from typing import Any, Dict

import numpy as np
import pandas as pd
from scipy.stats import norm

from src.engine.config import PRICING_CONFIG, PricingConfig
from src.engine.strategy_templates import StrategyIdea, StrategyLeg


def year_fraction(maturity_days: int) -> float:
    """
    Convert maturity in days into a simple ACT/365 year fraction.
    """
    return maturity_days / 365.0


def option_intrinsic_value(option_type: str, spot: float, strike: float) -> float:
    """
    Intrinsic value of a European option at expiry.
    """
    if option_type == "call":
        return max(spot - strike, 0.0)
    if option_type == "put":
        return max(strike - spot, 0.0)
    raise ValueError("option_type must be either 'call' or 'put'.")


def _bs_d1_d2(
    spot: float,
    strike: float,
    maturity_years: float,
    risk_free_rate: float,
    dividend_yield: float,
    sigma: float,
) -> tuple[float, float]:
    """
    Compute Black-Scholes d1 and d2.
    """
    sigma = max(sigma, 1e-8)
    maturity_years = max(maturity_years, 1e-12)

    numerator = (
        np.log(spot / strike)
        + (risk_free_rate - dividend_yield + 0.5 * sigma**2) * maturity_years
    )
    denominator = sigma * np.sqrt(maturity_years)

    d1 = numerator / denominator
    d2 = d1 - sigma * np.sqrt(maturity_years)

    return d1, d2


def bs_option_price(
    option_type: str,
    spot: float,
    strike: float,
    maturity_years: float,
    risk_free_rate: float,
    dividend_yield: float,
    sigma: float,
) -> float:
    """
    Black-Scholes price for a European call or put with continuous dividend yield.
    """
    if maturity_years <= 0:
        return option_intrinsic_value(option_type, spot, strike)

    d1, d2 = _bs_d1_d2(
        spot=spot,
        strike=strike,
        maturity_years=maturity_years,
        risk_free_rate=risk_free_rate,
        dividend_yield=dividend_yield,
        sigma=sigma,
    )

    discounted_spot = spot * np.exp(-dividend_yield * maturity_years)
    discounted_strike = strike * np.exp(-risk_free_rate * maturity_years)

    if option_type == "call":
        return discounted_spot * norm.cdf(d1) - discounted_strike * norm.cdf(d2)

    if option_type == "put":
        return discounted_strike * norm.cdf(-d2) - discounted_spot * norm.cdf(-d1)

    raise ValueError("option_type must be either 'call' or 'put'.")


def bs_option_greeks(
    option_type: str,
    spot: float,
    strike: float,
    maturity_years: float,
    risk_free_rate: float,
    dividend_yield: float,
    sigma: float,
) -> Dict[str, float]:
    """
    Black-Scholes Greeks.

    Returned conventions:
    - delta: standard
    - gamma: standard
    - vega_1vol: price change for +1 vol point (= +0.01 absolute vol)
    - theta_1day: price change per 1 calendar day
    - rho_1pct: price change for +1% rate shift (= +0.01 in rate)
    """
    if maturity_years <= 0:
        return {
            "delta": 0.0,
            "gamma": 0.0,
            "vega_1vol": 0.0,
            "theta_1day": 0.0,
            "rho_1pct": 0.0,
        }

    sigma = max(sigma, 1e-8)
    d1, d2 = _bs_d1_d2(
        spot=spot,
        strike=strike,
        maturity_years=maturity_years,
        risk_free_rate=risk_free_rate,
        dividend_yield=dividend_yield,
        sigma=sigma,
    )

    pdf_d1 = norm.pdf(d1)
    discount_q = np.exp(-dividend_yield * maturity_years)
    discount_r = np.exp(-risk_free_rate * maturity_years)
    sqrt_t = np.sqrt(maturity_years)

    if option_type == "call":
        delta = discount_q * norm.cdf(d1)
        theta_year = (
            -(spot * discount_q * pdf_d1 * sigma) / (2 * sqrt_t)
            - risk_free_rate * strike * discount_r * norm.cdf(d2)
            + dividend_yield * spot * discount_q * norm.cdf(d1)
        )
        rho = strike * maturity_years * discount_r * norm.cdf(d2)

    elif option_type == "put":
        delta = discount_q * (norm.cdf(d1) - 1.0)
        theta_year = (
            -(spot * discount_q * pdf_d1 * sigma) / (2 * sqrt_t)
            + risk_free_rate * strike * discount_r * norm.cdf(-d2)
            - dividend_yield * spot * discount_q * norm.cdf(-d1)
        )
        rho = -strike * maturity_years * discount_r * norm.cdf(-d2)

    else:
        raise ValueError("option_type must be either 'call' or 'put'.")

    gamma = (discount_q * pdf_d1) / (spot * sigma * sqrt_t)
    raw_vega = spot * discount_q * pdf_d1 * sqrt_t

    return {
        "delta": delta,
        "gamma": gamma,
        "vega_1vol": raw_vega * 0.01,
        "theta_1day": theta_year / 365.0,
        "rho_1pct": rho * 0.01,
    }


def leg_current_value(
    leg: StrategyLeg,
    spot: float,
    risk_free_rate: float,
    dividend_yield: float,
    vol_shift: float = 0.0,
) -> float:
    """
    Mark-to-market value of a single leg.

    For options:
        signed_quantity * Black-Scholes price
    For stock:
        signed_quantity * spot
    """
    signed_qty = leg.signed_quantity

    if leg.instrument == "stock":
        return signed_qty * spot

    sigma = max((leg.iv or 0.0) + vol_shift, 1e-6)
    maturity_years = year_fraction(leg.maturity_days or 0)

    option_price = bs_option_price(
        option_type=leg.instrument,
        spot=spot,
        strike=leg.strike or 0.0,
        maturity_years=maturity_years,
        risk_free_rate=risk_free_rate,
        dividend_yield=dividend_yield,
        sigma=sigma,
    )

    return signed_qty * option_price


def leg_greeks(
    leg: StrategyLeg,
    spot: float,
    risk_free_rate: float,
    dividend_yield: float,
    vol_shift: float = 0.0,
) -> Dict[str, float]:
    """
    Greeks of a single leg, already signed by long/short direction.
    """
    signed_qty = leg.signed_quantity

    if leg.instrument == "stock":
        return {
            "delta": signed_qty,
            "gamma": 0.0,
            "vega_1vol": 0.0,
            "theta_1day": 0.0,
            "rho_1pct": 0.0,
        }

    sigma = max((leg.iv or 0.0) + vol_shift, 1e-6)
    maturity_years = year_fraction(leg.maturity_days or 0)

    greeks = bs_option_greeks(
        option_type=leg.instrument,
        spot=spot,
        strike=leg.strike or 0.0,
        maturity_years=maturity_years,
        risk_free_rate=risk_free_rate,
        dividend_yield=dividend_yield,
        sigma=sigma,
    )

    return {key: signed_qty * value for key, value in greeks.items()}


def strategy_current_value(
    strategy: StrategyIdea,
    spot: float,
    risk_free_rate: float = PRICING_CONFIG.risk_free_rate,
    dividend_yield: float = PRICING_CONFIG.dividend_yield,
    vol_shift: float = 0.0,
) -> float:
    """
    Aggregate current value of the whole strategy.
    """
    return sum(
        leg_current_value(
            leg=leg,
            spot=spot,
            risk_free_rate=risk_free_rate,
            dividend_yield=dividend_yield,
            vol_shift=vol_shift,
        )
        for leg in strategy.legs
    )


def strategy_greeks(
    strategy: StrategyIdea,
    spot: float,
    risk_free_rate: float = PRICING_CONFIG.risk_free_rate,
    dividend_yield: float = PRICING_CONFIG.dividend_yield,
    vol_shift: float = 0.0,
) -> Dict[str, float]:
    """
    Aggregate Greeks across all legs.
    """
    total = {
        "delta": 0.0,
        "gamma": 0.0,
        "vega_1vol": 0.0,
        "theta_1day": 0.0,
        "rho_1pct": 0.0,
    }

    for leg in strategy.legs:
        leg_metrics = leg_greeks(
            leg=leg,
            spot=spot,
            risk_free_rate=risk_free_rate,
            dividend_yield=dividend_yield,
            vol_shift=vol_shift,
        )
        for key in total:
            total[key] += leg_metrics[key]

    return total


def leg_expiry_value(leg: StrategyLeg, spot_expiry: float) -> float:
    """
    Terminal value of a single leg at expiry.
    """
    signed_qty = leg.signed_quantity

    if leg.instrument == "stock":
        return signed_qty * spot_expiry

    intrinsic = option_intrinsic_value(
        option_type=leg.instrument,
        spot=spot_expiry,
        strike=leg.strike or 0.0,
    )
    return signed_qty * intrinsic


def strategy_expiry_value(strategy: StrategyIdea, spot_expiry: float) -> float:
    """
    Aggregate terminal value of the strategy at expiry.
    """
    return sum(leg_expiry_value(leg, spot_expiry) for leg in strategy.legs)


def strategy_expiry_pnl(
    strategy: StrategyIdea,
    spot_today: float,
    spot_expiry: float,
    risk_free_rate: float = PRICING_CONFIG.risk_free_rate,
    dividend_yield: float = PRICING_CONFIG.dividend_yield,
) -> float:
    """
    Expiry P&L = terminal value - initial mark-to-market value.
    """
    initial_value = strategy_current_value(
        strategy=strategy,
        spot=spot_today,
        risk_free_rate=risk_free_rate,
        dividend_yield=dividend_yield,
    )
    final_value = strategy_expiry_value(strategy=strategy, spot_expiry=spot_expiry)

    return final_value - initial_value


def build_payoff_grid(
    strategy: StrategyIdea,
    spot_today: float,
    pricing_config: PricingConfig = PRICING_CONFIG,
    risk_free_rate: float = PRICING_CONFIG.risk_free_rate,
    dividend_yield: float = PRICING_CONFIG.dividend_yield,
) -> pd.DataFrame:
    """
    Build a payoff / expiry P&L grid over a range of expiry spot prices.
    """
    min_spot = spot_today * pricing_config.payoff_grid_min_pct
    max_spot = spot_today * pricing_config.payoff_grid_max_pct

    spot_grid = np.linspace(
        min_spot,
        max_spot,
        pricing_config.payoff_grid_points,
    )

    rows = []
    for spot_expiry in spot_grid:
        terminal_value = strategy_expiry_value(strategy, spot_expiry)
        pnl = strategy_expiry_pnl(
            strategy=strategy,
            spot_today=spot_today,
            spot_expiry=spot_expiry,
            risk_free_rate=risk_free_rate,
            dividend_yield=dividend_yield,
        )
        rows.append(
            {
                "spot_expiry": spot_expiry,
                "terminal_value": terminal_value,
                "expiry_pnl": pnl,
            }
        )

    return pd.DataFrame(rows)


def build_expiry_scenario_table(
    strategy: StrategyIdea,
    spot_today: float,
    pricing_config: PricingConfig = PRICING_CONFIG,
    risk_free_rate: float = PRICING_CONFIG.risk_free_rate,
    dividend_yield: float = PRICING_CONFIG.dividend_yield,
) -> pd.DataFrame:
    """
    Build a simple expiry P&L table for discrete spot shocks.
    """
    rows = []

    for shock in pricing_config.spot_shocks_pct:
        scenario_spot = spot_today * (1.0 + shock)
        terminal_value = strategy_expiry_value(strategy, scenario_spot)
        expiry_pnl = strategy_expiry_pnl(
            strategy=strategy,
            spot_today=spot_today,
            spot_expiry=scenario_spot,
            risk_free_rate=risk_free_rate,
            dividend_yield=dividend_yield,
        )

        rows.append(
            {
                "spot_shock_pct": shock,
                "spot_expiry": scenario_spot,
                "terminal_value": terminal_value,
                "expiry_pnl": expiry_pnl,
            }
        )

    return pd.DataFrame(rows)


def build_mtm_scenario_table(
    strategy: StrategyIdea,
    spot_today: float,
    pricing_config: PricingConfig = PRICING_CONFIG,
    risk_free_rate: float = PRICING_CONFIG.risk_free_rate,
    dividend_yield: float = PRICING_CONFIG.dividend_yield,
) -> pd.DataFrame:
    """
    Build a mark-to-market scenario table under spot and parallel IV shocks.

    Interpretation:
    - Spot is shocked immediately
    - Each option leg IV is shifted by the same absolute amount
    - Maturity is kept unchanged
    """
    initial_value = strategy_current_value(
        strategy=strategy,
        spot=spot_today,
        risk_free_rate=risk_free_rate,
        dividend_yield=dividend_yield,
        vol_shift=0.0,
    )

    rows = []

    for spot_shock in pricing_config.spot_shocks_pct:
        shocked_spot = spot_today * (1.0 + spot_shock)

        for vol_shock in pricing_config.vol_shocks_abs:
            scenario_value = strategy_current_value(
                strategy=strategy,
                spot=shocked_spot,
                risk_free_rate=risk_free_rate,
                dividend_yield=dividend_yield,
                vol_shift=vol_shock,
            )

            scenario_pnl = scenario_value - initial_value

            rows.append(
                {
                    "spot_shock_pct": spot_shock,
                    "vol_shock_abs": vol_shock,
                    "scenario_spot": shocked_spot,
                    "scenario_value": scenario_value,
                    "scenario_pnl": scenario_pnl,
                }
            )

    return pd.DataFrame(rows)


def strategy_valuation_summary(
    strategy: StrategyIdea,
    spot: float,
    risk_free_rate: float = PRICING_CONFIG.risk_free_rate,
    dividend_yield: float = PRICING_CONFIG.dividend_yield,
) -> Dict[str, float]:
    """
    Convenience summary combining current value and aggregate Greeks.
    """
    current_value = strategy_current_value(
        strategy=strategy,
        spot=spot,
        risk_free_rate=risk_free_rate,
        dividend_yield=dividend_yield,
    )

    greeks = strategy_greeks(
        strategy=strategy,
        spot=spot,
        risk_free_rate=risk_free_rate,
        dividend_yield=dividend_yield,
    )

    summary = {"current_value": current_value}
    summary.update(greeks)
    return summary

def estimate_breakeven_from_payoff_grid(payoff_df: pd.DataFrame) -> float | None:
    """
    Approximate breakeven from the expiry P&L grid using sign changes.
    """
    df = payoff_df.copy().sort_values("spot_expiry").reset_index(drop=True)

    pnl = df["expiry_pnl"].values
    spot = df["spot_expiry"].values

    for i in range(1, len(df)):
        if pnl[i - 1] == 0:
            return float(spot[i - 1])

        if pnl[i - 1] * pnl[i] < 0:
            # Linear interpolation
            x1, x2 = spot[i - 1], spot[i]
            y1, y2 = pnl[i - 1], pnl[i]

            breakeven = x1 - y1 * (x2 - x1) / (y2 - y1)
            return float(breakeven)

    return None

def payoff_profile_summary(payoff_df: pd.DataFrame) -> Dict[str, float | None]:
    """
    Extract simple payoff summary statistics from an expiry payoff grid.

    Important:
    these are grid-based summary metrics, not necessarily closed-form theoretical
    maxima/minima for all structures.
    """
    grid_max_profit = float(payoff_df["expiry_pnl"].max())
    grid_max_loss = float(payoff_df["expiry_pnl"].min())
    grid_breakeven = estimate_breakeven_from_payoff_grid(payoff_df)

    return {
        "grid_max_profit": grid_max_profit,
        "grid_max_loss": grid_max_loss,
        "grid_breakeven": grid_breakeven,
    }

def payoff_profile_summary(payoff_df: pd.DataFrame) -> Dict[str, float | None]:
    """
    Extract simple payoff summary statistics from an expiry payoff grid.

    Important:
    these are grid-based summary metrics, not necessarily closed-form theoretical
    maxima/minima for all structures.
    """
    grid_max_profit = float(payoff_df["expiry_pnl"].max())
    grid_max_loss = float(payoff_df["expiry_pnl"].min())
    grid_breakeven = estimate_breakeven_from_payoff_grid(payoff_df)

    return {
        "grid_max_profit": grid_max_profit,
        "grid_max_loss": grid_max_loss,
        "grid_breakeven": grid_breakeven,
    }

def extract_client_structure_levels(strategy: StrategyIdea) -> Dict[str, Any]:
    """
    Client-friendly structure levels, derived from strategy metadata.

    These are not pricing outputs, but simple commercial levels that make
    the structure easier to explain to a client.
    """
    name = strategy.name
    md = strategy.metadata

    if name == "call_spread":
        return {
            "upside_participation_starts_above": md.get("lower_strike"),
            "upside_capped_above": md.get("upper_strike"),
        }

    if name == "put_spread_collar":
        return {
            "protection_starts_at": md.get("long_put_strike"),
            "protection_flattens_below": md.get("short_put_strike"),
            "upside_capped_above": md.get("short_call_strike"),
            "stock_position_included": md.get("include_stock_leg"),
        }

    if name == "short_put_spread":
        return {
            "premium_kept_above": md.get("short_put_strike"),
            "max_loss_zone_below": md.get("long_put_strike"),
        }

    if name == "risk_reversal":
        return {
            "downside_exposure_below": md.get("put_strike"),
            "upside_participation_above": md.get("call_strike"),
        }

    return {}