from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import matplotlib.pyplot as plt
import pandas as pd

from src.engine.analytics import snapshot_to_dataframe
from src.engine.config import OUTPUT_DIR
from src.engine.idea_engine import (
    RankedIdea,
    detailed_ranked_idea_to_dataframe,
    ranked_ideas_to_dataframe,
)
from src.engine.pricer import build_mtm_scenario_table, build_payoff_grid


def _sanitize_filename(value: str) -> str:
    allowed = []
    for ch in value.lower():
        if ch.isalnum() or ch in {"_", "-"}:
            allowed.append(ch)
        elif ch in {" ", "/"}:
            allowed.append("_")
    return "".join(allowed).strip("_")


def _fmt_num(value: Any, digits: int = 4) -> str:
    if value is None:
        return "None"
    if isinstance(value, (float, int)):
        return f"{value:.{digits}f}"
    return str(value)


def _fmt_pct_from_decimal(value: Optional[float], digits: int = 1) -> str:
    if value is None:
        return "None"
    return f"{100 * value:.{digits}f}%"


def _run_folder_name(client_objective: Optional[str]) -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    objective = _sanitize_filename(client_objective or "cross_client_ranking")
    return f"{timestamp}_{objective}"


def ensure_run_output_dir(client_objective: Optional[str] = None) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    run_dir = OUTPUT_DIR / _run_folder_name(client_objective)
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def plot_payoff_chart(
    ranked_idea: RankedIdea,
    spot_today: float,
    output_path: Path,
) -> None:
    payoff_df = build_payoff_grid(
        strategy=ranked_idea.strategy,
        spot_today=spot_today,
    )

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(payoff_df["spot_expiry"], payoff_df["expiry_pnl"], linewidth=2)

    ax.axhline(0, linestyle="--")
    ax.axvline(spot_today, linestyle="--")

    breakeven = ranked_idea.payoff_summary.get("grid_breakeven")
    if breakeven is not None:
        ax.axvline(float(breakeven), linestyle=":")

    ax.set_title(f"Expiry P&L - {ranked_idea.strategy.name}")
    ax.set_xlabel("Underlying price at expiry")
    ax.set_ylabel("P&L at expiry")
    ax.grid(True, alpha=0.3)

    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_mtm_heatmap(
    ranked_idea: RankedIdea,
    spot_today: float,
    output_path: Path,
) -> None:
    mtm_df = build_mtm_scenario_table(
        strategy=ranked_idea.strategy,
        spot_today=spot_today,
    )

    pivot = mtm_df.pivot(
        index="spot_shock_pct",
        columns="vol_shock_abs",
        values="scenario_pnl",
    ).sort_index()

    fig, ax = plt.subplots(figsize=(8, 5))
    im = ax.imshow(pivot.values, aspect="auto")

    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels([f"{100 * x:.1f} vol pts" for x in pivot.columns])

    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels([f"{100 * x:.1f}%" for x in pivot.index])

    ax.set_title(f"MTM Scenario P&L - {ranked_idea.strategy.name}")
    ax.set_xlabel("Parallel IV shock")
    ax.set_ylabel("Spot shock")

    for i in range(pivot.shape[0]):
        for j in range(pivot.shape[1]):
            ax.text(
                j,
                i,
                f"{pivot.iloc[i, j]:.2f}",
                ha="center",
                va="center",
                fontsize=9,
            )

    fig.colorbar(im, ax=ax)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def _market_context_sentence(snapshot: Dict[str, Any]) -> str:
    base = (
        f"Vol regime is {snapshot['vol_regime']}, IV vs RV looks {snapshot['vrp_regime']}, "
        f"skew is {snapshot['skew_regime']}, trend is {snapshot['trend_regime']} "
        f"and drawdown regime is {snapshot['drawdown_regime']}."
    )

    if snapshot.get("has_catalyst"):
        base += (
            f" There is also a nearby catalyst in {snapshot['days_to_next_event']} days "
            f"({snapshot['next_event_type']}: {snapshot['next_event_description']})."
        )

    return base


def _client_levels_sentence(ranked_idea: RankedIdea) -> str:
    levels = ranked_idea.client_structure_levels
    if not levels:
        return ""

    parts = []
    for key, value in levels.items():
        parts.append(f"{key}={value}")

    return "Key structure levels: " + ", ".join(parts) + "."


def build_client_note(
    ranked_idea: RankedIdea,
    snapshot: Dict[str, Any],
) -> str:
    """
    Client-facing note in a more bank-style compact format.
    """
    lines: List[str] = []

    lines.append(f"Trade idea: {ranked_idea.strategy.name}")
    lines.append(f"Client angle: {ranked_idea.client_angle}")
    lines.append("")
    lines.append("Market context")
    lines.append(_market_context_sentence(snapshot))
    lines.append("")
    lines.append("Why this idea now")
    for point in ranked_idea.why_now_points[:4]:
        lines.append(f"- {point}")
    lines.append("")
    lines.append("Structure")
    lines.append(_client_levels_sentence(ranked_idea) or "Standard structure parameters available in the detailed report.")
    lines.append("")
    lines.append("Risk considerations")
    for point in ranked_idea.risk_points[:2]:
        lines.append(f"- {point}")

    if ranked_idea.payoff_summary.get("grid_breakeven") is not None:
        lines.append("")
        lines.append(
            f"On the analysis grid, breakeven is around {ranked_idea.payoff_summary['grid_breakeven']:.2f}."
        )

    return "\n".join(lines)


def build_internal_markdown_report(
    ranked_idea: RankedIdea,
    snapshot: Dict[str, Any],
) -> str:
    lines: List[str] = []

    lines.append(f"# {ranked_idea.strategy.name}")
    lines.append("")
    lines.append(f"**Strategy family:** {ranked_idea.strategy_family}")
    lines.append(f"**Client objective:** {ranked_idea.client_objective}")
    lines.append(f"**Client type:** {ranked_idea.client_type}")
    lines.append(f"**Client angle:** {ranked_idea.client_angle}")
    lines.append(f"**Total score:** {ranked_idea.total_score:.4f}")
    lines.append("")

    lines.append("## Market snapshot")
    lines.append(
        f"- Spot: {_fmt_num(snapshot['spot'])}\n"
        f"- RV20: {_fmt_num(snapshot['rv_20d'])}\n"
        f"- ATM IV 30d: {_fmt_num(snapshot['atm_iv_30d'])}\n"
        f"- VRP regime: {snapshot['vrp_regime']}\n"
        f"- Skew regime: {snapshot['skew_regime']}\n"
        f"- Trend regime: {snapshot['trend_regime']}\n"
        f"- Drawdown regime: {snapshot['drawdown_regime']}\n"
        f"- Catalyst: {snapshot['has_catalyst']}"
    )
    lines.append("")

    lines.append("## Score breakdown")
    for key, value in ranked_idea.component_scores.items():
        lines.append(f"- **{key}**: {value:.4f}")
    lines.append("")

    lines.append("## Key parameters")
    for key, value in ranked_idea.strategy.metadata.items():
        lines.append(f"- **{key}**: {value}")
    lines.append("")

    if ranked_idea.client_structure_levels:
        lines.append("## Client-friendly structure levels")
        for key, value in ranked_idea.client_structure_levels.items():
            lines.append(f"- **{key}**: {value}")
        lines.append("")

    lines.append("## Valuation summary")
    for key, value in ranked_idea.valuation_summary.items():
        lines.append(f"- **{key}**: {value:.4f}")
    lines.append("")

    lines.append("## Payoff summary")
    for key, value in ranked_idea.payoff_summary.items():
        if value is None:
            lines.append(f"- **{key}**: None")
        else:
            lines.append(f"- **{key}**: {float(value):.4f}")
    lines.append("")

    lines.append("## Why now")
    for point in ranked_idea.why_now_points:
        lines.append(f"- {point}")
    lines.append("")

    lines.append("## Key risks")
    for point in ranked_idea.risk_points:
        lines.append(f"- {point}")

    return "\n".join(lines)


def build_run_summary_markdown(
    snapshot: Dict[str, Any],
    ranked_ideas: List[RankedIdea],
) -> str:
    """
    One top-level summary file for the whole run.
    """
    lines: List[str] = []

    if not ranked_ideas:
        return "# Run summary\n\nNo ranked ideas available."

    top = ranked_ideas[0]
    client_objective = top.client_objective

    lines.append("# Run summary")
    lines.append("")
    lines.append(f"**Client objective:** {client_objective}")
    lines.append(f"**Valuation date:** {snapshot['valuation_date']}")
    lines.append(f"**Spot:** {_fmt_num(snapshot['spot'])}")
    lines.append("")
    lines.append("## Market context")
    lines.append(_market_context_sentence(snapshot))
    lines.append("")
    lines.append("## Top recommendation")
    lines.append(f"**{top.strategy.name}** — total score {top.total_score:.4f}")
    lines.append(f"- Strategy family: {top.strategy_family}")
    lines.append(f"- Client angle: {top.client_angle}")
    lines.append(f"- Why now: {top.why_now_points[0] if top.why_now_points else top.client_angle}")
    lines.append("")

    lines.append("## Ranking overview")
    for i, idea in enumerate(ranked_ideas, start=1):
        lines.append(
            f"{i}. **{idea.strategy.name}** "
            f"(score={idea.total_score:.4f}, family={idea.strategy_family}, "
            f"market_fit={idea.component_scores['market_fit']:.2f})"
        )
    lines.append("")

    lines.append("## Practical read-across")
    lines.append(
        "The ranking should be interpreted within the chosen client objective. "
        "A protection overlay, a directional upside trade and a short-vol income structure "
        "are not interchangeable across all client situations."
    )

    return "\n".join(lines)


def export_run_bundle(
    snapshot: Dict[str, Any],
    ranked_ideas: List[RankedIdea],
    top_n: int = 3,
) -> Path:
    client_objective = ranked_ideas[0].client_objective if ranked_ideas else None
    run_dir = ensure_run_output_dir(client_objective=client_objective)

    snapshot_df = snapshot_to_dataframe(snapshot)
    snapshot_df.to_csv(run_dir / "snapshot.csv", index=False)

    ranking_df = ranked_ideas_to_dataframe(ranked_ideas)
    ranking_df.to_csv(run_dir / "ranking.csv", index=False)

    run_summary = build_run_summary_markdown(snapshot, ranked_ideas)
    (run_dir / "run_summary.md").write_text(run_summary, encoding="utf-8")

    spot_today = float(snapshot["spot"])

    for i, ranked_idea in enumerate(ranked_ideas[:top_n], start=1):
        idea_folder = run_dir / f"{i:02d}_{_sanitize_filename(ranked_idea.strategy.name)}"
        idea_folder.mkdir(parents=True, exist_ok=True)

        details_df = detailed_ranked_idea_to_dataframe(ranked_idea)
        details_df.to_csv(idea_folder / "details.csv", index=False)

        client_note = build_client_note(ranked_idea, snapshot)
        (idea_folder / "client_note.txt").write_text(client_note, encoding="utf-8")

        internal_report = build_internal_markdown_report(ranked_idea, snapshot)
        (idea_folder / "internal_report.md").write_text(internal_report, encoding="utf-8")

        plot_payoff_chart(
            ranked_idea=ranked_idea,
            spot_today=spot_today,
            output_path=idea_folder / "payoff_chart.png",
        )

        plot_mtm_heatmap(
            ranked_idea=ranked_idea,
            spot_today=spot_today,
            output_path=idea_folder / "mtm_heatmap.png",
        )

    return run_dir