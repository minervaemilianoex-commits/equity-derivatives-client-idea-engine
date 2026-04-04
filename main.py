import pandas as pd

from src.engine.analytics import build_market_snapshot, snapshot_to_dataframe
from src.engine.data_loader import load_all_data
from src.engine.idea_engine import (
    rank_trade_ideas,
    ranked_ideas_to_dataframe,
    explain_profile_filtering,
)
from src.engine.reporting import export_run_bundle


# Cambia questi valori per cambiare il tipo di cliente / profilo
# Client objective options:
# - "directional_upside"
# - "hedge_existing_long"
# - "yield_enhancement"
# - "sophisticated_skew_trade"
# - None
CLIENT_OBJECTIVE = "hedge_existing_long"

# Client profile options:
# - "conservative"
# - "balanced"
# - "yield_seeking"
# - "aggressive"
CLIENT_PROFILE_ID = "conservative"


def format_snapshot(snapshot_df: pd.DataFrame) -> pd.DataFrame:
    df = snapshot_df.copy()

    def _fmt_value(row):
        value = row["value"]
        if isinstance(value, float):
            return round(value, 4)
        return value

    df["value"] = df.apply(_fmt_value, axis=1)
    return df


def format_ranking_table(ranking_df: pd.DataFrame) -> pd.DataFrame:
    df = ranking_df.copy()

    float_cols = [
        "total_score",
        "market_fit",
        "payoff_efficiency",
        "client_explainability",
        "risk_discipline",
    ]
    for col in float_cols:
        if col in df.columns:
            df[col] = df[col].round(3)

    display_cols = [
        "rank",
        "strategy_name",
        "strategy_family",
        "client_objective",
        "total_score",
        "market_fit",
        "payoff_efficiency",
        "client_explainability",
        "risk_discipline",
    ]

    existing_cols = [col for col in display_cols if col in df.columns]
    return df[existing_cols]


def main() -> None:
    spot_df, iv_df, events_df = load_all_data()

    snapshot = build_market_snapshot(
        spot_df=spot_df,
        iv_df=iv_df,
        events_df=events_df,
    )

    print("=== MARKET SNAPSHOT ===")
    print(format_snapshot(snapshot_to_dataframe(snapshot)).to_string(index=False))

    print("\n=== CLIENT SETTINGS ===")
    print(f"Client objective: {CLIENT_OBJECTIVE}")
    print(f"Client profile: {CLIENT_PROFILE_ID}")

    profile_exclusions = explain_profile_filtering(
        snapshot=snapshot,
        client_profile_id=CLIENT_PROFILE_ID,
    )

    if profile_exclusions:
        print("\nStrategies excluded by client profile:")
        for strategy_name, reason in profile_exclusions.items():
            print(f" - {strategy_name}: {reason}")
    else:
        print("\nNo strategies excluded by client profile.")

    ranked_ideas = rank_trade_ideas(
        snapshot=snapshot,
        quantity=1.0,
        top_n=4,
        client_objective=CLIENT_OBJECTIVE,
        client_profile_id=CLIENT_PROFILE_ID,
    )

    ranking_df = ranked_ideas_to_dataframe(ranked_ideas)

    print("\n=== RANKED TRADE IDEAS ===")
    print(format_ranking_table(ranking_df).to_string(index=False))

    print("\n=== TOP IDEAS - DETAIL VIEW ===")
    for i, ranked_idea in enumerate(ranked_ideas[:3], start=1):
        print(f"\n--- IDEA #{i}: {ranked_idea.strategy.name} ---")
        print(f"Strategy family: {ranked_idea.strategy_family}")
        print(f"Client objective used: {ranked_idea.client_objective}")
        print(f"Description: {ranked_idea.strategy.description}")
        print(f"Client type: {ranked_idea.client_type}")
        print(f"Client angle: {ranked_idea.client_angle}")
        print(f"Total score: {ranked_idea.total_score:.4f}")

        print("\nScore breakdown:")
        for key, value in ranked_idea.component_scores.items():
            print(f"  {key:>22}: {value:.4f}")

        print("\nKey parameters:")
        for key, value in ranked_idea.strategy.metadata.items():
            print(f"  {key:>22}: {value}")

        print("\nClient-friendly structure levels:")
        for key, value in ranked_idea.client_structure_levels.items():
            print(f"  {key:>22}: {value}")

        print("\nValuation summary:")
        for key, value in ranked_idea.valuation_summary.items():
            print(f"  {key:>22}: {value:.4f}")

        print("\nPayoff summary:")
        for key, value in ranked_idea.payoff_summary.items():
            if value is None:
                print(f"  {key:>22}: None")
            else:
                print(f"  {key:>22}: {float(value):.4f}")

        print("\nWhy now:")
        for point in ranked_idea.why_now_points:
            print(f"  - {point}")
        
        print("\nProfile notes:")
        if ranked_idea.profile_notes:
            for point in ranked_idea.profile_notes:
                print(f"  - {point}")
        else:
            print("  - None")

        print("\nKey risks:")
        for point in ranked_idea.risk_points:
            print(f"  - {point}")

    run_dir = export_run_bundle(
        snapshot=snapshot,
        ranked_ideas=ranked_ideas,
        top_n=3,
    )

    print("\n=== REPORTING OUTPUT ===")
    print(f"Reports exported to: {run_dir}")


if __name__ == "__main__":
    main()


