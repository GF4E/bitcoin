"""Headline report writers: goal_trajectory_report.md and income_sleeve_comparison.md.

goal_trajectory_report.md leads with the sensitivity sweep (the honest result is the
spread, not a single triumphant number), then the live concentration banner, the
solved threshold + ruin + guard, terminal-wealth percentiles, the 5M-crossing date
distribution, and labeled assumptions — exactly the spec's ordering.
"""

from __future__ import annotations

from app.config import AppConfig
from app.data.contracts import ConcentrationBanner, IncomeSleeveComparison, TrajectoryResult
from app.goal.trajectory import SensitivityCell
from app.reports.markdown import (
    assumptions_table,
    fmt_money,
    fmt_money_m,
    fmt_pct,
    footer,
    grid_table,
)


def _concentration_block(b: ConcentrationBanner) -> str:
    flag = " **⚠ FLAGGED**" if b.flagged else ""
    return (
        "## 2. Concentration banner (every run)\n\n"
        f"- AI/tech/semi exposure: **{fmt_pct(b.ai_tech_semi_pct)}** of net worth "
        f"(flag threshold {fmt_pct(b.flag_threshold_pct)}){flag}\n"
        f"- Weighted-average pairwise correlation of the risk sleeve: **{b.weighted_avg_correlation:.2f}**\n"
        f"- Effective independent bets (Meucci entropy): **{b.effective_independent_bets:.1f}**\n\n"
        "_This book is a concentrated single-factor wager being monitored, not "
        "diversified away._\n"
    )


def render_goal_trajectory_report(
    cfg: AppConfig, result: TrajectoryResult, cells: list[SensitivityCell]
) -> str:
    rows = sorted({c.return_mult for c in cells})
    cols = sorted({c.vol_mult for c in cells})
    by_key = {(c.return_mult, c.vol_mult): c for c in cells}

    def med(r: float, c: float) -> str:
        return fmt_money_m(by_key[(r, c)].median_terminal)

    def ruin(r: float, c: float) -> str:
        cell = by_key[(r, c)]
        return fmt_pct(cell.ruin) + ("" if cell.feasible else " (infeas)")

    def thr(r: float, c: float) -> str:
        return f"{by_key[(r, c)].threshold:.2f}"

    parts: list[str] = []
    parts.append("# Goal-Trajectory Report\n")
    parts.append(
        "**Read the spread, not the point estimate.** The point estimate below is only "
        "as good as the expected-return and volatility assumptions — the two least-sourceable, "
        "most load-bearing inputs. The sensitivity sweep is the honest result.\n"
    )

    parts.append("## 1. Sensitivity sweep (headline)\n")
    parts.append(
        "Each cell re-solves the full objective at a perturbed expected_return (rows) and "
        "volatility (cols). Base case is the centre cell (x1.00 / x1.00).\n"
    )
    parts.append("\n### Median terminal wealth\n")
    parts.append(grid_table(rows, cols, med))
    parts.append("\n### Ruin probability\n")
    parts.append(grid_table(rows, cols, ruin))
    parts.append("\n### Solved drawdown threshold\n")
    parts.append(grid_table(rows, cols, thr))

    parts.append("\n" + _concentration_block(result.concentration))

    feas = "feasible" if result.feasible else "**NO feasible threshold — least-bad tradeoff shown**"
    parts.append(
        "\n## 3. Solved drawdown threshold + ruin + downside guard\n\n"
        f"- Solved drawdown threshold (the OUTPUT, not an input): **{result.solved_drawdown_threshold:.3f}** ({feas})\n"
        f"- Ruin probability: **{fmt_pct(result.ruin_probability)}** (cap {fmt_pct(cfg.trajectory.ruin_probability_max)})\n"
        f"- Downside-dispersion guard ({result.downside_guard_metric}): "
        f"{fmt_money(result.downside_guard_value)} — **{'PASS' if result.downside_guard_passed else 'FAIL'}** "
        f"(floor = net_worth_total {fmt_money(cfg.risk_budget.net_worth_total)})\n"
        f"- Drag-anchor mode: {result.drag_anchor_mode}; baseline CAGR {fmt_pct(result.baseline_cagr)}, "
        f"withdrawal CAGR {fmt_pct(result.withdrawal_cagr)}\n"
    )

    parts.append(
        "\n## 4. Terminal wealth distribution\n\n"
        f"- Median (p50): **{fmt_money(result.p50_terminal)}**\n"
        f"- p10 / p25 / p90: {fmt_money(result.p10_terminal)} / {fmt_money(result.p25_terminal)} "
        f"/ {fmt_money(result.p90_terminal)}\n"
        f"- Monte-Carlo paths: {result.n_paths:,}; seed: {result.seed} "
        f"(a single fixed-seed run is not the full probability picture)\n"
    )

    cross = result.milestone_crossing_months
    parts.append(
        f"\n## 5. {fmt_money(cfg.goal_plan.milestone_wealth)} milestone-crossing distribution\n\n"
        f"- P(reach milestone within horizon): **{fmt_pct(result.prob_reach_milestone)}**\n"
    )
    if cross:
        parts.append(
            f"- Months to cross — p10 {cross.get('p10_months', float('nan')):.0f}, "
            f"p50 {cross.get('p50_months', float('nan')):.0f}, "
            f"p90 {cross.get('p90_months', float('nan')):.0f} "
            f"(milestone is a reported crossing, NOT the optimization target)\n"
        )
    else:
        parts.append("- Milestone not crossed on any modeled path within the horizon.\n")

    parts.append("\n## 6. Assumptions (labeled)\n")
    parts.append(assumptions_table(result.assumptions))
    if result.warnings:
        parts.append("\n### Data-quality warnings\n")
        for w in result.warnings:
            parts.append(f"- [{w.severity.value}] {w.code}: {w.message}")

    parts.append(footer(cfg.settings.compliance_mode))
    return "\n".join(parts)


def render_income_sleeve_comparison(cfg: AppConfig, cmp: IncomeSleeveComparison) -> str:
    parts: list[str] = []
    parts.append("# Income-Sleeve Comparison (A vs B)\n")
    parts.append(
        "The income approach is an open question re-tested every run. Capture ratios are "
        "**derived empirically** from a realized monthly total-return series — never hardcoded. "
        "The tool reports the delta and the regime dependence; the user arbitrates.\n"
    )
    parts.append(
        "## Approaches\n\n"
        f"- **A ({cmp.a_label})**: QQQI-style capped covered-call income; distributions "
        "reinvest-until-drawn.\n"
        f"- **B ({cmp.b_label})**: QQQM-equivalent full upside + a {cmp.buffer_months}-month "
        "T-bill/SGOV buffer sized to the gap, selling index for the gap.\n"
    )
    parts.append(
        "## Terminal-wealth delta (A minus B)\n\n"
        f"- p10: **{fmt_money(cmp.delta_terminal_p10)}**\n"
        f"- p50: **{fmt_money(cmp.delta_terminal_p50)}**\n"
        f"- p90: **{fmt_money(cmp.delta_terminal_p90)}**\n\n"
        "_Negative => Approach B (full upside) finishes ahead in the modeled regime._\n"
    )
    parts.append(
        "## Empirically-derived capture\n\n"
        f"- Up-capture: **{cmp.up_capture:.3f}**, down-capture: **{cmp.down_capture:.3f}**\n"
        f"- Source: {cmp.capture_source} ({cmp.capture_date_range})\n"
        f"- Peer substitution used: **{cmp.peer_substituted}** "
        "(longest-record peer for the capped bound when the fund history is <3yr)\n"
    )
    parts.append(
        "## ROC regime flag\n\n"
        f"- Trailing windows with non-negative index return (constructive ROC): "
        f"**{fmt_pct(cmp.roc_constructive_share)}**\n"
        f"- {cmp.regime_note}\n"
    )
    parts.append("\n## Assumptions (labeled)\n")
    parts.append(assumptions_table(cmp.assumptions))
    if cmp.warnings:
        parts.append("\n### Data-quality warnings\n")
        for w in cmp.warnings:
            parts.append(f"- [{w.severity.value}] {w.code}: {w.message}")
    parts.append(footer(cfg.settings.compliance_mode))
    return "\n".join(parts)
