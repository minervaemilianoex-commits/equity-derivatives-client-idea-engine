from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from src.engine.config import RANKING_CONFIG, RankingConfig
from src.engine.pricer import (
    build_payoff_grid,
    extract_client_structure_levels,
    payoff_profile_summary,
    strategy_valuation_summary,
)
from src.engine.strategy_templates import StrategyIdea, build_strategy_library


@dataclass
class RankedIdea:
    strategy: StrategyIdea
    total_score: float
    component_scores: Dict[str, float]
    strategy_family: str
    client_objective: str
    why_now_points: List[str] = field(default_factory=list)
    risk_points: List[str] = field(default_factory=list)
    client_type: str = ""
    client_angle: str = ""
    valuation_summary: Dict[str, float] = field(default_factory=dict)
    payoff_summary: Dict[str, Optional[float]] = field(default_factory=dict)
    client_structure_levels: Dict[str, Any] = field(default_factory=dict)

    def to_record(self, rank: int) -> Dict[str, Any]:
        return {
            "rank": rank,
            "strategy_name": self.strategy.name,
            "strategy_family": self.strategy_family,
            "client_objective": self.client_objective,
            "total_score": round(self.total_score, 4),
            "market_fit": round(self.component_scores["market_fit"], 4),
            "payoff_efficiency": round(self.component_scores["payoff_efficiency"], 4),
            "client_explainability": round(self.component_scores["client_explainability"], 4),
            "risk_discipline": round(self.component_scores["risk_discipline"], 4),
            "market_view": self.strategy.market_view,
            "client_type": self.client_type,
            "tenor_days": self.strategy.metadata.get("tenor_days"),
            "key_parameters": summarize_strategy_parameters(self.strategy),
        }


def clamp_score(value: float, lower: float = 0.0, upper: float = 10.0) -> float:
    return max(lower, min(value, upper))


def soft_cap_market_fit(value: float) -> float:
    return min(clamp_score(value), 9.5)


def strategy_family(strategy_name: str) -> str:
    mapping = {
        "call_spread": "directional_upside",
        "put_spread_collar": "protection_overlay",
        "short_put_spread": "yield_short_vol",
        "risk_reversal": "skew_trade",
    }
    return mapping.get(strategy_name, "other")


def primary_client_objective(strategy_name: str) -> str:
    mapping = {
        "call_spread": "directional_upside",
        "put_spread_collar": "hedge_existing_long",
        "short_put_spread": "yield_enhancement",
        "risk_reversal": "sophisticated_skew_trade",
    }
    return mapping.get(strategy_name, "not_specified")


def summarize_strategy_parameters(strategy: StrategyIdea) -> str:
    strike_items = []

    for key, value in strategy.metadata.items():
        if "strike" in key:
            strike_items.append(f"{key}={value}")

    tenor = strategy.metadata.get("tenor_days")
    if tenor is not None:
        strike_items.append(f"tenor_days={tenor}")

    include_stock_leg = strategy.metadata.get("include_stock_leg")
    if include_stock_leg is not None:
        strike_items.append(f"include_stock_leg={include_stock_leg}")

    return ", ".join(strike_items)


def _objective_alignment_adjustment(
    strategy_name: str,
    client_objective: Optional[str],
) -> Tuple[float, Optional[str]]:
    if client_objective is None:
        return 0.0, None

    primary = primary_client_objective(strategy_name)

    secondary_matches = {
        "risk_reversal": {"directional_upside"},
    }

    if client_objective == primary:
        return 2.0, f"Structure is directly aligned with client objective '{client_objective}'."

    if client_objective in secondary_matches.get(strategy_name, set()):
        return 0.75, f"Structure is partially aligned with client objective '{client_objective}'."

    return -1.25, f"Structure is less aligned with client objective '{client_objective}'."


def _base_explainability_score(
    strategy_name: str,
    ranking_config: RankingConfig = RANKING_CONFIG,
) -> Tuple[float, List[str]]:
    base_score = float(ranking_config.explainability_scores.get(strategy_name, 5.0))

    explanation_map = {
        "call_spread": (
            "Two-leg capped-upside structure: easy to explain and very intuitive for a directional client."
        ),
        "put_spread_collar": (
            "Classic protection overlay for an existing long position: simple floor/cap narrative."
        ),
        "short_put_spread": (
            "Still explainable, but premium-selling and downside risk require a more careful conversation."
        ),
        "risk_reversal": (
            "Less plain-vanilla: financing upside by selling downside skew is powerful but less intuitive."
        ),
    }

    explanation = explanation_map.get(
        strategy_name,
        "Structure can be explained to a client, but may need more contextualization."
    )

    return clamp_score(base_score), [explanation]


def _risk_discipline_score(
    strategy_name: str,
    snapshot: Dict[str, Any],
) -> Tuple[float, List[str]]:
    drawdown_regime = snapshot["drawdown_regime"]
    has_catalyst = bool(snapshot["has_catalyst"])

    if strategy_name == "call_spread":
        score = 9.0
        risks = [
            "Upside is capped above the short call strike.",
            "The full premium can be lost if the stock fails to rally enough by expiry.",
        ]
        return clamp_score(score), risks

    if strategy_name == "put_spread_collar":
        score = 8.5
        if drawdown_regime in {"moderate_drawdown", "deep_drawdown"}:
            score += 0.3
        risks = [
            "Protection is only partial: below the short put strike, downside protection stops improving.",
            "Upside is capped by the short call.",
        ]
        return clamp_score(score), risks

    if strategy_name == "short_put_spread":
        score = 7.5
        if has_catalyst:
            score -= 0.5
        if drawdown_regime == "deep_drawdown":
            score -= 0.5
        risks = [
            "Premium received is capped, while downside losses can still be meaningful within the spread width.",
            "Gap risk around events matters when selling downside optionality.",
        ]
        return clamp_score(score), risks

    if strategy_name == "risk_reversal":
        score = 4.8
        if has_catalyst:
            score -= 0.5
        if drawdown_regime == "deep_drawdown":
            score -= 0.8
        risks = [
            "Downside is materially exposed because the short put finances the upside call.",
            "This is more suitable for sophisticated clients who understand the short downside exposure.",
        ]
        return clamp_score(score), risks

    return 5.0, ["Risk profile not explicitly classified."]


def _market_fit_call_spread(snapshot: Dict[str, Any]) -> Tuple[float, List[str]]:
    score = 4.0
    reasons = []

    trend_regime = snapshot["trend_regime"]
    vrp_regime = snapshot["vrp_regime"]
    vol_regime = snapshot["vol_regime"]
    has_catalyst = bool(snapshot["has_catalyst"])
    momentum_20d = float(snapshot["momentum_20d"])
    drawdown_regime = snapshot["drawdown_regime"]

    if trend_regime == "positive":
        score += 2.0
        reasons.append("Trend is positive, which supports a directional upside structure.")
    elif trend_regime == "mixed" and momentum_20d > 0:
        score += 1.25
        reasons.append("Short-term momentum is positive even though the broader trend is mixed.")

    if vrp_regime == "IV_cheap":
        score += 2.0
        reasons.append("Implied volatility does not look expensive versus realized volatility.")
    elif vrp_regime == "IV_fair":
        score += 1.5
        reasons.append("Implied volatility looks broadly fair, which is acceptable for buying upside.")
    elif vrp_regime == "IV_rich":
        score += 0.25
        reasons.append("Implied volatility is rich, but the spread still partially mitigates premium cost.")

    if vol_regime in {"low", "normal"}:
        score += 1.25
        reasons.append("Absolute volatility is not excessively high, so long optionality is more acceptable.")
    else:
        score -= 0.75
        reasons.append("Very high absolute volatility makes outright upside optionality more expensive.")

    if has_catalyst:
        score += 1.00
        reasons.append("A nearby catalyst can justify owning defined-risk upside rather than pure delta.")

    if drawdown_regime == "deep_drawdown":
        score -= 1.25
        reasons.append("A deep recent drawdown argues for more caution on directional upside structures.")
    elif drawdown_regime == "moderate_drawdown":
        score -= 0.50
        reasons.append("Recent weakness suggests being selective on outright bullish structures.")

    return clamp_score(score), reasons


def _market_fit_put_spread_collar(snapshot: Dict[str, Any]) -> Tuple[float, List[str]]:
    score = 4.0
    reasons = []

    drawdown_regime = snapshot["drawdown_regime"]
    skew_regime = snapshot["skew_regime"]
    vrp_regime = snapshot["vrp_regime"]
    vol_regime = snapshot["vol_regime"]
    trend_regime = snapshot["trend_regime"]
    has_catalyst = bool(snapshot["has_catalyst"])

    if drawdown_regime in {"moderate_drawdown", "deep_drawdown"}:
        score += 2.25
        reasons.append("Recent drawdown makes partial protection more relevant for an existing long investor.")

    if skew_regime in {"put_skew", "put_skew_extreme"}:
        score += 1.75
        reasons.append("Downside skew is pronounced, which supports structures built around downside protection and financing legs.")

    if vrp_regime == "IV_rich":
        score += 1.75
        reasons.append("Standalone puts look relatively expensive, so a cost-reducing collar is more attractive.")
    elif vrp_regime == "IV_fair":
        score += 1.0
        reasons.append("Implied volatility is not cheap enough to strongly favor a naked hedge, so a financed hedge remains sensible.")

    if vol_regime in {"normal", "high"}:
        score += 0.5
        reasons.append("A non-low volatility regime makes protection more commercially relevant.")

    if trend_regime in {"mixed", "negative"}:
        score += 0.75
        reasons.append("The trend backdrop is not cleanly bullish, which increases the appeal of partial downside defense.")

    if has_catalyst:
        score += 1.25
        reasons.append("A nearby event supports having some downside protection ahead of potential gap risk.")

    return clamp_score(score), reasons


def _market_fit_short_put_spread(snapshot: Dict[str, Any]) -> Tuple[float, List[str]]:
    score = 3.5
    reasons = []

    drawdown_regime = snapshot["drawdown_regime"]
    skew_regime = snapshot["skew_regime"]
    vrp_regime = snapshot["vrp_regime"]
    vol_regime = snapshot["vol_regime"]
    trend_regime = snapshot["trend_regime"]
    has_catalyst = bool(snapshot["has_catalyst"])
    momentum_20d = float(snapshot["momentum_20d"])

    if vrp_regime == "IV_rich":
        score += 2.5
        reasons.append("Implied volatility is rich versus realized volatility, which supports selective premium selling.")
    elif vrp_regime == "IV_fair":
        score += 1.0
        reasons.append("Implied volatility is not obviously cheap, so a cautious premium-selling structure can still be discussed.")

    if skew_regime in {"put_skew", "put_skew_extreme"}:
        score += 2.0
        reasons.append("Downside skew is pronounced, which makes selling downside vol more attractive in relative terms.")

    if vol_regime == "normal":
        score += 0.75
        reasons.append("Normal volatility is often a cleaner environment than stressed volatility for controlled short-vol structures.")
    elif vol_regime == "high":
        score += 0.25
        reasons.append("High volatility increases premium intake, but also raises downside risk, so the positive impact is limited.")
    elif vol_regime == "low":
        score -= 0.5
        reasons.append("Low volatility reduces the appeal of selling premium.")

    if trend_regime == "positive":
        score += 1.0
        reasons.append("A positive trend supports a neutral-to-mildly bullish short put spread.")
    elif trend_regime == "mixed" and momentum_20d > 0:
        score += 0.5
        reasons.append("Short-term recovery helps, even though the broader trend is mixed.")

    if drawdown_regime == "deep_drawdown":
        score -= 1.5
        reasons.append("A deep drawdown is a warning sign when monetizing downside optionality.")
    elif drawdown_regime == "moderate_drawdown":
        score -= 0.5
        reasons.append("Recent weakness means downside premium may be rich for a reason.")

    if has_catalyst:
        score -= 0.75
        reasons.append("Selling downside optionality into a nearby event deserves extra caution.")

    return clamp_score(score), reasons


def _market_fit_risk_reversal(snapshot: Dict[str, Any]) -> Tuple[float, List[str]]:
    score = 3.5
    reasons = []

    drawdown_regime = snapshot["drawdown_regime"]
    skew_regime = snapshot["skew_regime"]
    vrp_regime = snapshot["vrp_regime"]
    vol_regime = snapshot["vol_regime"]
    trend_regime = snapshot["trend_regime"]
    has_catalyst = bool(snapshot["has_catalyst"])
    momentum_20d = float(snapshot["momentum_20d"])

    if skew_regime in {"put_skew", "put_skew_extreme"}:
        score += 2.5
        reasons.append("Pronounced downside skew makes financing upside via short downside skew more attractive.")

    if trend_regime == "positive":
        score += 2.0
        reasons.append("A positive directional backdrop supports a bullish skew trade.")
    elif trend_regime == "mixed" and momentum_20d > 0:
        score += 1.0
        reasons.append("Short-term upside stabilization helps justify a selective bullish structure.")

    if vrp_regime == "IV_rich":
        score += 1.0
        reasons.append("Rich implied volatility can make the sold downside leg more valuable as a financing source.")
    elif vrp_regime == "IV_cheap":
        score -= 0.5
        reasons.append("Cheap implied volatility reduces the advantage of financing the call via a short put.")

    if has_catalyst:
        score += 0.5
        reasons.append("A catalyst can justify owning upside convexity, though the short downside must be handled carefully.")

    if drawdown_regime == "deep_drawdown":
        score -= 2.0
        reasons.append("Deep drawdown materially weakens the case for a short-put-financed structure.")
    elif drawdown_regime == "moderate_drawdown":
        score -= 0.75
        reasons.append("Recent weakness reduces the comfort level with open downside exposure.")

    if vol_regime == "high":
        score -= 1.0
        reasons.append("Very high volatility makes short downside exposure harder to justify commercially.")

    return clamp_score(score), reasons


def _market_fit_score(
    strategy_name: str,
    snapshot: Dict[str, Any],
) -> Tuple[float, List[str]]:
    if strategy_name == "call_spread":
        return _market_fit_call_spread(snapshot)
    if strategy_name == "put_spread_collar":
        return _market_fit_put_spread_collar(snapshot)
    if strategy_name == "short_put_spread":
        return _market_fit_short_put_spread(snapshot)
    if strategy_name == "risk_reversal":
        return _market_fit_risk_reversal(snapshot)

    return 5.0, ["No dedicated market-fit logic available for this structure."]


def _payoff_efficiency_score(
    strategy: StrategyIdea,
    spot: float,
) -> Tuple[float, Dict[str, Optional[float]], Dict[str, float], List[str]]:
    valuation_summary = strategy_valuation_summary(strategy=strategy, spot=spot)
    payoff_grid = build_payoff_grid(strategy=strategy, spot_today=spot)
    payoff_summary = payoff_profile_summary(payoff_grid)

    current_value = float(valuation_summary["current_value"])
    grid_max_profit = (
        float(payoff_summary["grid_max_profit"])
        if payoff_summary["grid_max_profit"] is not None else 0.0
    )
    grid_max_loss = (
        float(payoff_summary["grid_max_loss"])
        if payoff_summary["grid_max_loss"] is not None else 0.0
    )

    reasons = []
    has_stock_leg = len(strategy.stock_legs()) > 0

    if has_stock_leg:
        loss_abs_pct_of_spot = abs(min(grid_max_loss, 0.0)) / spot
        profit_pct_of_spot = max(grid_max_profit, 0.0) / spot

        score = 6.0

        if loss_abs_pct_of_spot <= 0.05:
            score += 2.0
            reasons.append("The structure compresses downside meaningfully over the analysis range.")
        elif loss_abs_pct_of_spot <= 0.10:
            score += 1.0
            reasons.append("The structure provides noticeable downside compression, though not a full hedge.")

        if profit_pct_of_spot >= 0.05:
            score += 1.0
            reasons.append("The client still retains meaningful upside before the cap becomes binding.")

        if "defined-risk-band" in strategy.tags or "hedging" in strategy.tags:
            score += 1.0
            reasons.append("The payoff band is commercially appealing because protection and monetization are both visible.")

    else:
        loss_abs = abs(min(grid_max_loss, 0.0))
        reward_risk = (grid_max_profit / loss_abs) if loss_abs > 1e-8 else 3.0
        premium_pct_of_spot = abs(current_value) / spot

        score = 4.0

        if reward_risk >= 2.0:
            score += 3.0
            reasons.append(
                f"The payoff offers roughly {reward_risk:.1f}x upside versus maximum premium-at-risk on the analysis grid."
            )
        elif reward_risk >= 1.0:
            score += 2.0
            reasons.append(
                f"The reward-to-risk profile is acceptable at roughly {reward_risk:.1f}x on the analysis grid."
            )
        elif reward_risk >= 0.5:
            score += 1.0
            reasons.append(
                f"The payoff ratio is positive, though not especially asymmetric at roughly {reward_risk:.1f}x on the analysis grid."
            )

        if premium_pct_of_spot <= 0.03:
            score += 2.0
            reasons.append("Upfront capital outlay is contained relative to spot.")
        elif premium_pct_of_spot <= 0.06:
            score += 1.0
            reasons.append("Premium outlay remains manageable relative to spot.")

        if "defined-risk" in strategy.tags:
            score += 1.0
            reasons.append("Maximum downside is defined, which improves implementation quality.")

        if strategy.name == "risk_reversal":
            score -= 0.5
            reasons.append("The profile is efficient on financing terms, but less balanced on downside convexity.")

    return (
        clamp_score(score),
        payoff_summary,
        valuation_summary,
        reasons,
    )


def _build_client_structure_levels(
    strategy: StrategyIdea,
    valuation_summary: Dict[str, float],
    spot: float,
) -> Dict[str, Any]:
    levels = extract_client_structure_levels(strategy)
    current_value = float(valuation_summary["current_value"])

    if strategy.name == "call_spread":
        levels["net_upfront_cost"] = round(current_value, 4)

    elif strategy.name == "put_spread_collar":
        levels["overlay_net_value_vs_stock"] = round(current_value - spot, 4)

    elif strategy.name == "short_put_spread":
        levels["net_upfront_credit"] = round(-current_value, 4)

    elif strategy.name == "risk_reversal":
        levels["net_upfront_cost_or_credit"] = round(current_value, 4)

    return levels


def _suggest_client_type(strategy_name: str) -> str:
    mapping = {
        "call_spread": "Directional institutional / HNWI client seeking defined-risk upside",
        "put_spread_collar": "Existing long holder / HNWI / protection-seeking investor",
        "short_put_spread": "Yield-oriented sophisticated client comfortable with limited downside risk",
        "risk_reversal": "More sophisticated institutional / advanced HNWI client",
    }
    return mapping.get(strategy_name, "General client profile")


def _client_angle(strategy_name: str) -> str:
    mapping = {
        "call_spread": (
            "Simple way to express moderate upside while reducing premium versus an outright call."
        ),
        "put_spread_collar": (
            "Good hedge overlay for an existing long position: protection is improved while keeping cost contained."
        ),
        "short_put_spread": (
            "Defined-risk way to monetize rich downside premium without selling naked puts."
        ),
        "risk_reversal": (
            "More sophisticated skew trade that can cheapen upside participation by monetizing downside skew."
        ),
    }
    return mapping.get(strategy_name, "Client angle not specified.")


def _weighted_total_score(
    component_scores: Dict[str, float],
    ranking_config: RankingConfig = RANKING_CONFIG,
) -> float:
    weights = ranking_config.weights

    total = 0.0
    for key, weight in weights.items():
        total += weight * component_scores[key]

    return clamp_score(total)


def evaluate_strategy(
    strategy: StrategyIdea,
    snapshot: Dict[str, Any],
    client_objective: Optional[str] = None,
    ranking_config: RankingConfig = RANKING_CONFIG,
) -> RankedIdea:
    spot = float(snapshot["spot"])

    market_fit_score, market_fit_reasons = _market_fit_score(strategy.name, snapshot)

    objective_adjustment, objective_reason = _objective_alignment_adjustment(
        strategy_name=strategy.name,
        client_objective=client_objective,
    )

    market_fit_score = soft_cap_market_fit(market_fit_score + objective_adjustment)

    if objective_reason is not None:
        market_fit_reasons = [objective_reason] + market_fit_reasons

    payoff_efficiency_score, payoff_summary, valuation_summary, payoff_reasons = _payoff_efficiency_score(
        strategy=strategy,
        spot=spot,
    )

    client_explainability_score, explainability_reasons = _base_explainability_score(
        strategy_name=strategy.name,
        ranking_config=ranking_config,
    )

    risk_discipline_score, risk_points = _risk_discipline_score(
        strategy_name=strategy.name,
        snapshot=snapshot,
    )

    component_scores = {
        "market_fit": market_fit_score,
        "payoff_efficiency": payoff_efficiency_score,
        "client_explainability": client_explainability_score,
        "risk_discipline": risk_discipline_score,
    }

    total_score = _weighted_total_score(
        component_scores=component_scores,
        ranking_config=ranking_config,
    )

    why_now_points = []
    why_now_points.extend(market_fit_reasons[:5])
    why_now_points.extend(payoff_reasons[:2])
    why_now_points.extend(explainability_reasons[:1])

    seen = set()
    why_now_points = [x for x in why_now_points if not (x in seen or seen.add(x))]

    client_structure_levels = _build_client_structure_levels(
        strategy=strategy,
        valuation_summary=valuation_summary,
        spot=spot,
    )

    return RankedIdea(
        strategy=strategy,
        total_score=total_score,
        component_scores=component_scores,
        strategy_family=strategy_family(strategy.name),
        client_objective=client_objective or "cross_client_ranking",
        why_now_points=why_now_points,
        risk_points=risk_points,
        client_type=_suggest_client_type(strategy.name),
        client_angle=_client_angle(strategy.name),
        valuation_summary=valuation_summary,
        payoff_summary=payoff_summary,
        client_structure_levels=client_structure_levels,
    )


def rank_trade_ideas(
    snapshot: Dict[str, Any],
    quantity: float = 1.0,
    tenor_days: Optional[int] = None,
    top_n: Optional[int] = None,
    client_objective: Optional[str] = None,
    ranking_config: RankingConfig = RANKING_CONFIG,
) -> List[RankedIdea]:
    strategy_library = build_strategy_library(
        snapshot=snapshot,
        quantity=quantity,
        tenor_days=tenor_days,
    )

    evaluated = [
        evaluate_strategy(
            strategy=strategy,
            snapshot=snapshot,
            client_objective=client_objective,
            ranking_config=ranking_config,
        )
        for strategy in strategy_library.values()
    ]

    ranked = sorted(evaluated, key=lambda x: x.total_score, reverse=True)

    if top_n is not None:
        ranked = ranked[:top_n]

    return ranked


def ranked_ideas_to_dataframe(ranked_ideas: List[RankedIdea]) -> pd.DataFrame:
    records = []
    for i, ranked_idea in enumerate(ranked_ideas, start=1):
        records.append(ranked_idea.to_record(rank=i))

    return pd.DataFrame(records)


def detailed_ranked_idea_to_dataframe(ranked_idea: RankedIdea) -> pd.DataFrame:
    rows = [
        {"metric": "strategy_name", "value": ranked_idea.strategy.name},
        {"metric": "strategy_family", "value": ranked_idea.strategy_family},
        {"metric": "client_objective", "value": ranked_idea.client_objective},
        {"metric": "description", "value": ranked_idea.strategy.description},
        {"metric": "market_view", "value": ranked_idea.strategy.market_view},
        {"metric": "client_type", "value": ranked_idea.client_type},
        {"metric": "client_angle", "value": ranked_idea.client_angle},
        {"metric": "total_score", "value": round(ranked_idea.total_score, 4)},
        {"metric": "market_fit", "value": round(ranked_idea.component_scores["market_fit"], 4)},
        {"metric": "payoff_efficiency", "value": round(ranked_idea.component_scores["payoff_efficiency"], 4)},
        {"metric": "client_explainability", "value": round(ranked_idea.component_scores["client_explainability"], 4)},
        {"metric": "risk_discipline", "value": round(ranked_idea.component_scores["risk_discipline"], 4)},
        {"metric": "current_value", "value": round(ranked_idea.valuation_summary["current_value"], 4)},
        {"metric": "delta", "value": round(ranked_idea.valuation_summary["delta"], 4)},
        {"metric": "gamma", "value": round(ranked_idea.valuation_summary["gamma"], 4)},
        {"metric": "vega_1vol", "value": round(ranked_idea.valuation_summary["vega_1vol"], 4)},
        {"metric": "theta_1day", "value": round(ranked_idea.valuation_summary["theta_1day"], 4)},
        {"metric": "rho_1pct", "value": round(ranked_idea.valuation_summary["rho_1pct"], 4)},
        {
            "metric": "grid_max_profit",
            "value": None if ranked_idea.payoff_summary["grid_max_profit"] is None
            else round(float(ranked_idea.payoff_summary["grid_max_profit"]), 4)
        },
        {
            "metric": "grid_max_loss",
            "value": None if ranked_idea.payoff_summary["grid_max_loss"] is None
            else round(float(ranked_idea.payoff_summary["grid_max_loss"]), 4)
        },
        {
            "metric": "grid_breakeven",
            "value": None if ranked_idea.payoff_summary["grid_breakeven"] is None
            else round(float(ranked_idea.payoff_summary["grid_breakeven"]), 4)
        },
        {"metric": "key_parameters", "value": summarize_strategy_parameters(ranked_idea.strategy)},
    ]

    for key, value in ranked_idea.client_structure_levels.items():
        rows.append({"metric": key, "value": value})

    return pd.DataFrame(rows)