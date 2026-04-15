# Equity Derivatives Client Idea Engine

A client-personalized equity derivatives idea engine that ranks option structures using market regime, client objective, and suitability constraints.

This project is not just an options pricer. It is a rule-based structuring workflow designed to answer a more commercial question:

**Given the current market setup and a specific client mandate, which option structures are most suitable, and why?**

The engine combines market diagnostics, template-based strategy generation, pricing and Greeks, and a transparent ranking framework to produce explainable trade ideas.

---

## Project objective

The engine is built to support a simplified structuring / solutions-style process.

It starts from three questions:

1. **What does the market look like?**  
   Volatility level, skew, volatility risk premium, momentum, drawdown, and nearby catalysts.

2. **What is the client trying to achieve?**  
   For example:
   - `hedge_existing_long`
   - `directional_upside`
   - `yield_enhancement`
   - `sophisticated_skew_trade`

3. **What kind of client is this?**  
   The same objective does not imply the same recommendation.  
   A conservative client and an aggressive client can face the same market but still receive different rankings.

The result is a ranked list of trade ideas with:
- market context,
- score breakdown,
- client-facing structure levels,
- valuation summary,
- payoff summary,
- why-now rationale,
- key risks,
- client-profile notes,
- exportable run reports.

---

## Why this project is different

Many student derivatives projects stop at pricing.

This one instead focuses on **idea generation and suitability**:
- it links market regime to structure selection,
- it incorporates client objective,
- it incorporates client profile constraints,
- it separates hard exclusions from soft penalties,
- it produces output that is explainable to both technical and commercial readers.

This makes it closer to a **structuring / solutions workflow** than to a standalone pricing notebook.

---

## Core workflow

The engine runs through five layers.

### 1. Market snapshot
The engine builds a compact market state from spot history, synthetic IV surface data, and event data.

Main metrics include:
- spot
- realized volatility (`rv_20d`, `rv_60d`)
- ATM implied volatility
- downside skew proxies
- volatility risk premium
- short and long momentum
- drawdown
- nearest catalyst

These metrics are then mapped into qualitative regimes such as:
- `low`, `normal`, `high` volatility
- `IV_rich`, `IV_fair`, `IV_cheap`
- `put_skew`, `neutral`, `call_skew`
- `positive`, `negative`, `mixed` trend
- `contained_drawdown`, `moderate_drawdown`, `deep_drawdown`

### 2. Strategy library
The engine builds a small strategy library of explainable equity derivatives structures, including:

- `call_spread`
- `put_spread_collar`
- `short_put_spread`
- `risk_reversal`

These are intentionally simple enough to remain commercially interpretable.

### 3. Valuation and risk
Each structure is priced with a simplified options framework and summarized through:
- current value
- delta
- gamma
- vega
- theta
- rho

The engine also builds a payoff grid at expiry to extract:
- max profit
- max loss
- breakeven

### 4. Ranking logic
Each strategy is evaluated across four pillars:

- **market_fit**  
  Alignment between the current regime and the strategy’s intended use case.

- **payoff_efficiency**  
  A heuristic assessment of payoff attractiveness, cost or credit, and grid-based reward/risk shape.

- **client_explainability**  
  How easy the structure is to explain, position, and commercialize.

- **risk_discipline**  
  How controlled and suitable the downside profile is.

The total score is a weighted combination of these four components.

### 5. Client profile overlay
The engine supports predefined client profiles backed by explicit parameters.

Examples:
- `conservative`
- `balanced`
- `yield_seeking`
- `aggressive`

Profiles affect the output through two mechanisms:

#### Hard filters
Some strategies may be excluded entirely if they violate explicit suitability constraints.

Example:
- directional short put exposure not allowed for a conservative profile.

#### Soft adjustments
Some strategies remain eligible but are penalized or rewarded depending on profile preferences.

Examples:
- reward low upfront cost,
- penalize weak explainability,
- penalize undefined risk,
- penalize excessive downside.

This distinction is important:  
the engine does not just score strategies; it also applies a basic suitability layer.

---

## Current data setup

The project currently uses lightweight synthetic / local data files:

- `spot_history.csv`
- `iv_surface_synthetic.csv`
- `events.csv`

This keeps the project:
- easy to run,
- reproducible,
- free of paid data dependencies.

The setup is intentionally simple, but the architecture is designed so richer data can be added later.

---

## Repository structure

```text
equity-idea-engine/
│
├─ data/
│  ├─ spot_history.csv
│  ├─ iv_surface_synthetic.csv
│  └─ events.csv
│
├─ outputs/
│  └─ ...
│
├─ src/
│  └─ engine/
│     ├─ analytics.py
│     ├─ config.py
│     ├─ data_loader.py
│     ├─ idea_engine.py
│     ├─ payoff_charts.py
│     ├─ pricer.py
│     ├─ reporting.py
│     └─ strategy_templates.py
│
├─ main.py
├─ requirements.txt
└─ README.md