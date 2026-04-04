from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


# Root del progetto:
# config.py -> engine -> src -> project_root
PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "outputs"

SPOT_HISTORY_FILE = DATA_DIR / "spot_history.csv"
IV_SURFACE_FILE = DATA_DIR / "iv_surface_synthetic.csv"
EVENTS_FILE = DATA_DIR / "events.csv"


@dataclass
class MarketConfig:
    """
    Configurazioni per feature engineering e classificazione del contesto di mercato.
    """

    trading_days_per_year: int = 252

    # Realized volatility windows
    rv_window_short: int = 20
    rv_window_long: int = 60

    # Momentum windows
    momentum_window_short: int = 20
    momentum_window_long: int = 60

    # Drawdown lookback
    drawdown_lookback: int = 252

    # Volatility regime thresholds
    low_vol_threshold: float = 0.20
    high_vol_threshold: float = 0.35

    # VRP thresholds: IV - RV
    vrp_rich_threshold: float = 0.03
    vrp_cheap_threshold: float = -0.03

    # Skew thresholds
    skew_put_threshold: float = 0.02
    skew_call_threshold: float = -0.02
    skew_extreme_threshold: float = 0.05

    # Event proximity
    catalyst_window_days: int = 10


@dataclass
class PricingConfig:
    """
    Configurazioni per pricing, scenario analysis e payoff grid.
    """

    risk_free_rate: float = 0.02
    dividend_yield: float = 0.00

    # Shock di spot per scenari discreti
    spot_shocks_pct: List[float] = field(
        default_factory=lambda: [-0.10, -0.05, 0.00, 0.05, 0.10]
    )

    # Shock di volatilità in punti assoluti
    vol_shocks_abs: List[float] = field(
        default_factory=lambda: [-0.05, 0.00, 0.05]
    )

    # Range del payoff chart
    payoff_grid_min_pct: float = 0.70
    payoff_grid_max_pct: float = 1.30
    payoff_grid_points: int = 200


@dataclass
class StrategyConfig:
    """
    Convenzioni standard per le strutture opzionali dell'MVP.
    """

    standard_tenor_days: int = 30

    # Call spread
    bullish_lower_strike_pct: float = 1.00
    bullish_upper_strike_pct: float = 1.10

    # Put spread collar
    protection_put_strike_pct: float = 0.95
    protection_short_put_strike_pct: float = 0.90
    covered_call_strike_pct: float = 1.05

    # Short put spread
    short_put_spread_upper_strike_pct: float = 0.95
    short_put_spread_lower_strike_pct: float = 0.90

    # Risk reversal
    rr_put_strike_pct: float = 0.95
    rr_call_strike_pct: float = 1.05


@dataclass
class RankingConfig:
    """
    Pesi del ranking finale delle trade ideas.
    """

    weights: Dict[str, float] = field(
        default_factory=lambda: {
            "market_fit": 0.40,
            "payoff_efficiency": 0.25,
            "client_explainability": 0.20,
            "risk_discipline": 0.15,
        }
    )

    explainability_scores: Dict[str, int] = field(
        default_factory=lambda: {
            "call_spread": 9,
            "put_spread_collar": 8,
            "short_put_spread": 7,
            "risk_reversal": 6,
        }
    )


MARKET_CONFIG = MarketConfig()
PRICING_CONFIG = PricingConfig()
STRATEGY_CONFIG = StrategyConfig()
RANKING_CONFIG = RankingConfig()

# =========================
# Client profile layer
# =========================

@dataclass(frozen=True)
class ClientProfileConfig:
    profile_id: str
    allow_short_put_exposure: bool
    prefer_defined_risk: bool
    prefer_low_upfront_cost: bool
    min_explainability_score: float
    max_grid_loss_pct_of_spot: float
    ranking_weights_override: Optional[Dict[str, float]] = None


CLIENT_PROFILES: Dict[str, ClientProfileConfig] = {
    "conservative": ClientProfileConfig(
        profile_id="conservative",
        allow_short_put_exposure=False,
        prefer_defined_risk=True,
        prefer_low_upfront_cost=True,
        min_explainability_score=8.0,
        max_grid_loss_pct_of_spot=0.08,
        ranking_weights_override={
            "market_fit": 0.32,
            "payoff_efficiency": 0.18,
            "client_explainability": 0.22,
            "risk_discipline": 0.28,
        },
    ),
    "balanced": ClientProfileConfig(
        profile_id="balanced",
        allow_short_put_exposure=False,
        prefer_defined_risk=True,
        prefer_low_upfront_cost=False,
        min_explainability_score=7.0,
        max_grid_loss_pct_of_spot=0.15,
        ranking_weights_override={
            "market_fit": 0.38,
            "payoff_efficiency": 0.24,
            "client_explainability": 0.18,
            "risk_discipline": 0.20,
        },
    ),
    "yield_seeking": ClientProfileConfig(
        profile_id="yield_seeking",
        allow_short_put_exposure=True,
        prefer_defined_risk=True,
        prefer_low_upfront_cost=True,
        min_explainability_score=6.0,
        max_grid_loss_pct_of_spot=0.18,
        ranking_weights_override={
            "market_fit": 0.34,
            "payoff_efficiency": 0.32,
            "client_explainability": 0.14,
            "risk_discipline": 0.20,
        },
    ),
    "aggressive": ClientProfileConfig(
        profile_id="aggressive",
        allow_short_put_exposure=True,
        prefer_defined_risk=False,
        prefer_low_upfront_cost=False,
        min_explainability_score=5.5,
        max_grid_loss_pct_of_spot=0.30,
        ranking_weights_override={
            "market_fit": 0.42,
            "payoff_efficiency": 0.30,
            "client_explainability": 0.10,
            "risk_discipline": 0.18,
        },
    ),
}


def get_client_profile(profile_id: str) -> ClientProfileConfig:
    """
    Restituisce la configurazione di un profilo cliente predefinito.
    Solleva ValueError se il profilo non esiste.
    """
    normalized = profile_id.strip().lower()

    if normalized not in CLIENT_PROFILES:
        available = ", ".join(CLIENT_PROFILES.keys())
        raise ValueError(
            f"Unknown client profile '{profile_id}'. Available profiles: {available}"
        )

    return CLIENT_PROFILES[normalized]