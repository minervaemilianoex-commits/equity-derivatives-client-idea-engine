=== MARKET SNAPSHOT ===
                metric                      value
        valuation_date        2024-07-15 00:00:00
                  spot                      90.39
                rv_20d                     0.1914
                rv_60d                     0.1738
            atm_iv_30d                       0.25
             put_95_iv                       0.28
           call_105_iv                       0.24
           skew_metric                       0.04
  downside_skew_vs_atm                       0.03
               vrp_20d                     0.0586
          momentum_20d                     0.0166
          momentum_60d                     -0.085
              drawdown                    -0.1677
            vol_regime                     normal
            vrp_regime                    IV_rich
           skew_regime                   put_skew
          trend_regime                      mixed
       drawdown_regime              deep_drawdown
          has_catalyst                       True
    days_to_next_event                          9
       next_event_type                   earnings
next_event_description Quarterly earnings release

=== CLIENT OBJECTIVE ===
hedge_existing_long

=== RANKED TRADE IDEAS ===
 rank     strategy_name    strategy_family    client_objective  total_score  market_fit  payoff_efficiency  client_explainability  risk_discipline       
    1 put_spread_collar protection_overlay hedge_existing_long        8.720        9.50                8.0                    8.0              8.8       
    2       call_spread directional_upside hedge_existing_long        7.750        5.25               10.0                    9.0              9.0       
    3  short_put_spread    yield_short_vol hedge_existing_long        6.425        5.75                7.0                    7.0              6.5       
    4     risk_reversal         skew_trade hedge_existing_long        5.700        5.25                7.5                    6.0              3.5       

=== TOP IDEAS - DETAIL VIEW ===

--- IDEA #1: put_spread_collar ---
Strategy family: protection_overlay
Client objective used: hedge_existing_long
Description: Partial downside protection financed by short downside and upside optionality.
Client type: Existing long holder / HNWI / protection-seeking investor
Client angle: Good hedge overlay for an existing long position: protection is improved while keeping cost contained.
Total score: 8.7200

Score breakdown:
              market_fit: 9.5000
       payoff_efficiency: 8.0000
   client_explainability: 8.0000
         risk_discipline: 8.8000

Key parameters:
              tenor_days: 30
         long_put_strike: 85.87
        short_put_strike: 81.35
       short_call_strike: 94.91
       include_stock_leg: True

Client-friendly structure levels:
    protection_starts_at: 85.87
  protection_flattens_below: 81.35
     upside_capped_above: 94.91
  stock_position_included: True
  overlay_net_value_vs_stock: -0.2755

Valuation summary:
           current_value: 90.1145
                   delta: 0.6063
                   gamma: -0.0316
               vega_1vol: -0.0501
              theta_1day: 0.0221
                rho_1pct: -0.0290

Payoff summary:
         grid_max_profit: 4.7955
           grid_max_loss: -22.3215
          grid_breakeven: 90.1145

Why now:
  - Structure is directly aligned with client objective 'hedge_existing_long'.
  - Recent drawdown makes partial protection more relevant for an existing long investor.
  - Downside skew is pronounced, which supports structures built around downside protection and financing legs.
  - Standalone puts look relatively expensive, so a cost-reducing collar is more attractive.
  - A non-low volatility regime makes protection more commercially relevant.
  - The client still retains meaningful upside before the cap becomes binding.
  - The payoff band is commercially appealing because protection and monetization are both visible.
  - Classic protection overlay for an existing long position: simple floor/cap narrative.

Key risks:
  - Protection is only partial: below the short put strike, downside protection stops improving.
  - Upside is capped by the short call.

--- IDEA #2: call_spread ---
Strategy family: directional_upside
Client objective used: hedge_existing_long
Description: Bullish defined-risk upside participation via a long call spread.
Client type: Directional institutional / HNWI client seeking defined-risk upside
Client angle: Simple way to express moderate upside while reducing premium versus an outright call.
Total score: 7.7500

Score breakdown:
              market_fit: 5.2500
       payoff_efficiency: 10.0000
   client_explainability: 9.0000
         risk_discipline: 9.0000

Key parameters:
              tenor_days: 30
            lower_strike: 90.39
            upper_strike: 99.43

Client-friendly structure levels:
  upside_participation_starts_above: 90.39
     upside_capped_above: 99.43
        net_upfront_cost: 2.4381

Valuation summary:
           current_value: 2.4381
                   delta: 0.4408
                   gamma: 0.0359
               vega_1vol: 0.0637
              theta_1day: -0.0299
                rho_1pct: 0.0307

Payoff summary:
         grid_max_profit: 6.6019
           grid_max_loss: -2.4381
          grid_breakeven: 92.8281

Why now:
  - Structure is less aligned with client objective 'hedge_existing_long'.
  - Short-term momentum is positive even though the broader trend is mixed.
  - Implied volatility is rich, but the spread still partially mitigates premium cost.
  - Absolute volatility is not excessively high, so long optionality is more acceptable.
  - A nearby catalyst can justify owning defined-risk upside rather than pure delta.
  - The payoff offers roughly 2.7x upside versus maximum premium-at-risk on the analysis grid.
  - Upfront capital outlay is contained relative to spot.
  - Two-leg capped-upside structure: easy to explain and very intuitive for a directional client.

Key risks:
  - Upside is capped above the short call strike.
  - The full premium can be lost if the stock fails to rally enough by expiry.

--- IDEA #3: short_put_spread ---
Strategy family: yield_short_vol
Client objective used: hedge_existing_long
Description: Defined-risk short downside volatility expression via a put credit spread.
Client type: Yield-oriented sophisticated client comfortable with limited downside risk
Client angle: Defined-risk way to monetize rich downside premium without selling naked puts.
Total score: 6.4250

Score breakdown:
              market_fit: 5.7500
       payoff_efficiency: 7.0000
   client_explainability: 7.0000
         risk_discipline: 6.5000

Key parameters:
              tenor_days: 30
        short_put_strike: 85.87
         long_put_strike: 81.35

Client-friendly structure levels:
      premium_kept_above: 85.87
     max_loss_zone_below: 81.35
      net_upfront_credit: 0.6569

Valuation summary:
           current_value: -0.6569
                   delta: 0.1362
                   gamma: -0.0203
               vega_1vol: -0.0335
              theta_1day: 0.0126
                rho_1pct: 0.0107

Payoff summary:
         grid_max_profit: 0.6569
           grid_max_loss: -3.8631
          grid_breakeven: 85.2131

Why now:
  - Structure is less aligned with client objective 'hedge_existing_long'.
  - Implied volatility is rich versus realized volatility, which supports selective premium selling.
  - Downside skew is pronounced, which makes selling downside vol more attractive in relative terms.
  - Normal volatility is often a cleaner environment than stressed volatility for controlled short-vol structures.
  - Short-term recovery helps, even though the broader trend is mixed.
  - Upfront capital outlay is contained relative to spot.
  - Maximum downside is defined, which improves implementation quality.
  - Still explainable, but premium-selling and downside risk require a more careful conversation.

Key risks:
  - Premium received is capped, while downside losses can still be meaningful within the spread width.
  - Gap risk around events matters when selling downside optionality.

=== REPORTING OUTPUT ===
Reports exported to: C:\Users\emili\OneDrive\Desktop\equity-idea-engine\outputs\20260330_202113_hedge_existing_long