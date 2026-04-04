from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.engine.config import STRATEGY_CONFIG, StrategyConfig


@dataclass
class StrategyLeg:
    """
    Generic leg used in a structured trade idea.

    instrument:
        - "call"
        - "put"
        - "stock"
    side:
        - "long"
        - "short"
    quantity:
        positive size in number of units / contracts
    strike:
        only used for options
    maturity_days:
        only used for options
    iv:
        implied volatility assigned to the leg (used later by the pricer)
    """

    instrument: str
    side: str
    quantity: float
    strike: Optional[float] = None
    maturity_days: Optional[int] = None
    iv: Optional[float] = None

    def __post_init__(self) -> None:
        valid_instruments = {"call", "put", "stock"}
        valid_sides = {"long", "short"}

        if self.instrument not in valid_instruments:
            raise ValueError(f"Invalid instrument '{self.instrument}'. Must be one of {valid_instruments}.")

        if self.side not in valid_sides:
            raise ValueError(f"Invalid side '{self.side}'. Must be one of {valid_sides}.")

        if self.quantity <= 0:
            raise ValueError("Quantity must be strictly positive.")

        if self.instrument in {"call", "put"}:
            if self.strike is None or self.strike <= 0:
                raise ValueError("Option legs must have a strictly positive strike.")
            if self.maturity_days is None or self.maturity_days <= 0:
                raise ValueError("Option legs must have a strictly positive maturity_days.")
            if self.iv is None or self.iv <= 0:
                raise ValueError("Option legs must have a strictly positive implied volatility.")

        if self.instrument == "stock":
            if self.strike is not None:
                raise ValueError("Stock legs must not have a strike.")
            if self.maturity_days is not None:
                raise ValueError("Stock legs must not have a maturity_days.")
            if self.iv is not None:
                raise ValueError("Stock legs must not have an implied volatility.")

    @property
    def signed_quantity(self) -> float:
        """
        Positive for long legs, negative for short legs.
        """
        return self.quantity if self.side == "long" else -self.quantity


@dataclass
class StrategyIdea:
    """
    Container for a structured trade idea.
    """

    name: str
    description: str
    rationale: str
    market_view: str
    tags: List[str] = field(default_factory=list)
    legs: List[StrategyLeg] = field(default_factory=list)
    is_defined_risk: bool = True
    has_short_put_exposure: bool = False
    short_put_exposure_style: str = "none"
    upfront_style: str = "debit"
    explainability_level: int = 8
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_leg(self, leg: StrategyLeg) -> None:
        self.legs.append(leg)

    def option_legs(self) -> List[StrategyLeg]:
        return [leg for leg in self.legs if leg.instrument in {"call", "put"}]

    def stock_legs(self) -> List[StrategyLeg]:
        return [leg for leg in self.legs if leg.instrument == "stock"]

    def summary(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "market_view": self.market_view,
            "num_legs": len(self.legs),
            "tags": self.tags,
            "metadata": self.metadata,
        }


def _round_strike(value: float) -> float:
    return round(value, 2)


def _resolve_tenor(
    tenor_days: Optional[int],
    strategy_config: StrategyConfig = STRATEGY_CONFIG,
) -> int:
    """
    Use an explicit tenor if provided, otherwise the project default tenor.
    """
    if tenor_days is not None:
        return tenor_days
    return strategy_config.standard_tenor_days


def _estimate_iv_for_leg(
    snapshot: Dict[str, Any],
    moneyness: float,
    instrument: str,
) -> float:
    """
    Estimate a leg-level IV from a sparse market snapshot.

    Available in snapshot:
    - atm_iv_30d
    - put_95_iv
    - call_105_iv

    We use simple interpolation / extrapolation rules.
    This is intentionally lightweight and explainable for an MVP.
    """
    atm_iv = float(snapshot["atm_iv_30d"])
    put_95_iv = float(snapshot["put_95_iv"])
    call_105_iv = float(snapshot["call_105_iv"])

    if instrument == "put":
        if abs(moneyness - 0.95) < 1e-9:
            return put_95_iv

        if moneyness < 0.95:
            # Extrapolate richer downside put IV
            extra_skew = max(put_95_iv - atm_iv, 0.01)
            slope = extra_skew / 0.05
            iv = put_95_iv + slope * (0.95 - moneyness)
            return round(max(iv, 0.01), 4)

        # Interpolate between ATM and 95% put
        weight = (1.00 - moneyness) / 0.05
        iv = atm_iv + weight * (put_95_iv - atm_iv)
        return round(max(iv, 0.01), 4)

    if instrument == "call":
        if abs(moneyness - 1.05) < 1e-9:
            return call_105_iv

        if moneyness > 1.05:
            # Extrapolate flatter / slightly cheaper upside call IV
            upside_slope = max(atm_iv - call_105_iv, 0.005) / 0.05
            iv = call_105_iv - upside_slope * (moneyness - 1.05)
            return round(max(iv, 0.01), 4)

        # Interpolate between ATM and 105% call
        weight = (moneyness - 1.00) / 0.05
        iv = atm_iv + weight * (call_105_iv - atm_iv)
        return round(max(iv, 0.01), 4)

    raise ValueError("instrument must be either 'call' or 'put'.")


def build_call_spread(
    snapshot: Dict[str, Any],
    quantity: float = 1.0,
    tenor_days: Optional[int] = None,
    strategy_config: StrategyConfig = STRATEGY_CONFIG,
) -> StrategyIdea:
    """
    Long call spread:
    - long lower strike call
    - short higher strike call

    Best suited for:
    - moderately bullish view
    - controlled premium outlay
    """
    spot = float(snapshot["spot"])
    tenor = _resolve_tenor(tenor_days, strategy_config)

    lower_moneyness = strategy_config.bullish_lower_strike_pct
    upper_moneyness = strategy_config.bullish_upper_strike_pct

    lower_strike = _round_strike(spot * lower_moneyness)
    upper_strike = _round_strike(spot * upper_moneyness)

    long_call_iv = _estimate_iv_for_leg(snapshot, lower_moneyness, "call")
    short_call_iv = _estimate_iv_for_leg(snapshot, upper_moneyness, "call")

    idea = StrategyIdea(
        name="call_spread",
        description="Bullish defined-risk upside participation via a long call spread.",
        rationale=(
            "Useful when the client expects moderate upside and wants to reduce premium "
            "versus an outright long call."
        ),
        market_view="moderately_bullish",
        tags=["bullish", "defined-risk", "moderate-upside", "client-friendly"],
        is_defined_risk=True,
        has_short_put_exposure=False,
        short_put_exposure_style="none",
        upfront_style="debit",
        explainability_level=9,
        metadata={
            "tenor_days": tenor,
            "lower_strike": lower_strike,
            "upper_strike": upper_strike,
        },
    )

    idea.add_leg(
        StrategyLeg(
            instrument="call",
            side="long",
            quantity=quantity,
            strike=lower_strike,
            maturity_days=tenor,
            iv=long_call_iv,
        )
    )
    idea.add_leg(
        StrategyLeg(
            instrument="call",
            side="short",
            quantity=quantity,
            strike=upper_strike,
            maturity_days=tenor,
            iv=short_call_iv,
        )
    )

    return idea


def build_put_spread_collar(
    snapshot: Dict[str, Any],
    quantity: float = 1.0,
    tenor_days: Optional[int] = None,
    include_stock_leg: bool = True,
    strategy_config: StrategyConfig = STRATEGY_CONFIG,
) -> StrategyIdea:
    """
    Put spread collar:
    - optional long stock leg
    - long protective put
    - short lower strike put
    - short covered call

    Best suited for:
    - investor already long the stock
    - wants partial protection at reduced cost
    """
    spot = float(snapshot["spot"])
    tenor = _resolve_tenor(tenor_days, strategy_config)

    long_put_moneyness = strategy_config.protection_put_strike_pct
    short_put_moneyness = strategy_config.protection_short_put_strike_pct
    short_call_moneyness = strategy_config.covered_call_strike_pct

    long_put_strike = _round_strike(spot * long_put_moneyness)
    short_put_strike = _round_strike(spot * short_put_moneyness)
    short_call_strike = _round_strike(spot * short_call_moneyness)

    long_put_iv = _estimate_iv_for_leg(snapshot, long_put_moneyness, "put")
    short_put_iv = _estimate_iv_for_leg(snapshot, short_put_moneyness, "put")
    short_call_iv = _estimate_iv_for_leg(snapshot, short_call_moneyness, "call")

    idea = StrategyIdea(
        name="put_spread_collar",
        description="Partial downside protection financed by short downside and upside optionality.",
        rationale=(
            "Useful for a client already long the stock who wants to protect part of the downside "
            "without paying for a full standalone put hedge."
        ),
        market_view="protective_bullish",
        tags=["hedging", "income-financed", "defined-risk-band", "client-friendly"],
        is_defined_risk=True,
        has_short_put_exposure=True,
        short_put_exposure_style="hedge_overlay",
        upfront_style="low_cost_overlay",
        explainability_level=8,
        metadata={
            "tenor_days": tenor,
            "long_put_strike": long_put_strike,
            "short_put_strike": short_put_strike,
            "short_call_strike": short_call_strike,
            "include_stock_leg": include_stock_leg,
        },
    )

    if include_stock_leg:
        idea.add_leg(
            StrategyLeg(
                instrument="stock",
                side="long",
                quantity=quantity,
            )
        )

    idea.add_leg(
        StrategyLeg(
            instrument="put",
            side="long",
            quantity=quantity,
            strike=long_put_strike,
            maturity_days=tenor,
            iv=long_put_iv,
        )
    )
    idea.add_leg(
        StrategyLeg(
            instrument="put",
            side="short",
            quantity=quantity,
            strike=short_put_strike,
            maturity_days=tenor,
            iv=short_put_iv,
        )
    )
    idea.add_leg(
        StrategyLeg(
            instrument="call",
            side="short",
            quantity=quantity,
            strike=short_call_strike,
            maturity_days=tenor,
            iv=short_call_iv,
        )
    )

    return idea


def build_short_put_spread(
    snapshot: Dict[str, Any],
    quantity: float = 1.0,
    tenor_days: Optional[int] = None,
    strategy_config: StrategyConfig = STRATEGY_CONFIG,
) -> StrategyIdea:
    """
    Short put spread:
    - short higher strike put
    - long lower strike put

    Best suited for:
    - mildly bullish / neutral view
    - desire to monetize rich downside skew or elevated IV
    - defined downside risk
    """
    spot = float(snapshot["spot"])
    tenor = _resolve_tenor(tenor_days, strategy_config)

    short_put_moneyness = strategy_config.short_put_spread_upper_strike_pct
    long_put_moneyness = strategy_config.short_put_spread_lower_strike_pct

    short_put_strike = _round_strike(spot * short_put_moneyness)
    long_put_strike = _round_strike(spot * long_put_moneyness)

    short_put_iv = _estimate_iv_for_leg(snapshot, short_put_moneyness, "put")
    long_put_iv = _estimate_iv_for_leg(snapshot, long_put_moneyness, "put")

    idea = StrategyIdea(
        name="short_put_spread",
        description="Defined-risk short downside volatility expression via a put credit spread.",
        rationale=(
            "Useful when downside implied volatility looks rich relative to realized volatility "
            "and the client is comfortable taking limited downside risk."
        ),
        market_view="neutral_to_mildly_bullish",
        tags=["short-vol", "defined-risk", "income", "downside-skew"],
        is_defined_risk=True,
        has_short_put_exposure=True,
        short_put_exposure_style="directional_short_put",
        upfront_style="credit",
        explainability_level=7,
        metadata={
            "tenor_days": tenor,
            "short_put_strike": short_put_strike,
            "long_put_strike": long_put_strike,
        },
    )

    idea.add_leg(
        StrategyLeg(
            instrument="put",
            side="short",
            quantity=quantity,
            strike=short_put_strike,
            maturity_days=tenor,
            iv=short_put_iv,
        )
    )
    idea.add_leg(
        StrategyLeg(
            instrument="put",
            side="long",
            quantity=quantity,
            strike=long_put_strike,
            maturity_days=tenor,
            iv=long_put_iv,
        )
    )

    return idea


def build_risk_reversal(
    snapshot: Dict[str, Any],
    quantity: float = 1.0,
    tenor_days: Optional[int] = None,
    strategy_config: StrategyConfig = STRATEGY_CONFIG,
) -> StrategyIdea:
    """
    Bullish risk reversal:
    - short OTM put
    - long OTM call

    Best suited for:
    - directional bullish view
    - desire to exploit downside skew
    - more sophisticated client profile
    """
    spot = float(snapshot["spot"])
    tenor = _resolve_tenor(tenor_days, strategy_config)

    put_moneyness = strategy_config.rr_put_strike_pct
    call_moneyness = strategy_config.rr_call_strike_pct

    put_strike = _round_strike(spot * put_moneyness)
    call_strike = _round_strike(spot * call_moneyness)

    put_iv = _estimate_iv_for_leg(snapshot, put_moneyness, "put")
    call_iv = _estimate_iv_for_leg(snapshot, call_moneyness, "call")

    idea = StrategyIdea(
        name="risk_reversal",
        description="Bullish skew-driven structure: sell downside skew to finance upside exposure.",
        rationale=(
            "Useful for a client with a constructive view who is willing to absorb downside risk "
            "in exchange for cheaper upside participation."
        ),
        market_view="bullish_skew_trade",
        tags=["bullish", "skew-trade", "client-selective", "less-plain-vanilla"],
        is_defined_risk=False,
        has_short_put_exposure=True,
        short_put_exposure_style="directional_short_put",
        upfront_style="zero_or_low_cost",
        explainability_level=6,
        metadata={
            "tenor_days": tenor,
            "put_strike": put_strike,
            "call_strike": call_strike,
        },
    )

    idea.add_leg(
        StrategyLeg(
            instrument="put",
            side="short",
            quantity=quantity,
            strike=put_strike,
            maturity_days=tenor,
            iv=put_iv,
        )
    )
    idea.add_leg(
        StrategyLeg(
            instrument="call",
            side="long",
            quantity=quantity,
            strike=call_strike,
            maturity_days=tenor,
            iv=call_iv,
        )
    )

    return idea


def build_strategy_library(
    snapshot: Dict[str, Any],
    quantity: float = 1.0,
    tenor_days: Optional[int] = None,
    strategy_config: StrategyConfig = STRATEGY_CONFIG,
) -> Dict[str, StrategyIdea]:
    """
    Build all base strategy templates from a given market snapshot.
    """
    strategies = {
        "call_spread": build_call_spread(
            snapshot=snapshot,
            quantity=quantity,
            tenor_days=tenor_days,
            strategy_config=strategy_config,
        ),
        "put_spread_collar": build_put_spread_collar(
            snapshot=snapshot,
            quantity=quantity,
            tenor_days=tenor_days,
            include_stock_leg=True,
            strategy_config=strategy_config,
        ),
        "short_put_spread": build_short_put_spread(
            snapshot=snapshot,
            quantity=quantity,
            tenor_days=tenor_days,
            strategy_config=strategy_config,
        ),
        "risk_reversal": build_risk_reversal(
            snapshot=snapshot,
            quantity=quantity,
            tenor_days=tenor_days,
            strategy_config=strategy_config,
        ),
    }

    return strategies