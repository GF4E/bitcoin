"""Command-line interface (``python -m app.cli`` / ``portfolio-tool``).

v1 is READ-ONLY: no order placement, no execution endpoints. ``--mock`` runs with
zero credentials from the packaged sample fixtures.
"""

from __future__ import annotations

import typer

from app.config import AppConfig, load_config
from app.data.loader import load_portfolio
from app.reports.markdown import fmt_money, fmt_money_m, fmt_pct
from app.reports.writer import RunFolder

app = typer.Typer(
    add_completion=False, help="Local, read-only Schwab portfolio + trade-decision support tool."
)


def _cfg(mock: bool) -> AppConfig:
    cfg = load_config()
    if mock:
        cfg.settings.mode = "mock"
    return cfg


@app.command("load-portfolio")
def load_portfolio_cmd(
    mock: bool = typer.Option(True, help="Use packaged fixtures, zero credentials."),
) -> None:
    """Load + normalize the portfolio and print a summary."""
    cfg = _cfg(mock)
    pf = load_portfolio(cfg)
    schwab = sum((h.market_value or 0) for h in pf.schwab_holdings)
    manual = sum((h.market_value or 0) for h in pf.manual_holdings)
    typer.echo(f"Accounts: {len(pf.accounts)}  Holdings: {len(pf.holdings)}")
    typer.echo(f"Schwab-managed value (concentration/reconciliation denom): {fmt_money(schwab)}")
    typer.echo(f"External/manual sleeve (excluded from Schwab reconciliation): {fmt_money(manual)}")
    typer.echo(
        f"net_worth_total (risk/withdrawal/goal denom): {fmt_money(cfg.risk_budget.net_worth_total)}"
    )
    if pf.ledger.warnings:
        typer.echo(
            f"Data-quality warnings: {len(pf.ledger.warnings)} ({', '.join(sorted(set(pf.ledger.codes())))})"
        )


@app.command("project-goal")
def project_goal_cmd(
    mock: bool = typer.Option(True),
    write: bool = typer.Option(True, help="Write goal_trajectory_report.md to a run folder."),
) -> None:
    """Run the goal-trajectory engine standalone (both drag modes, solve threshold,
    sensitivity grid + concentration banner)."""
    from app.goal.concentration import compute_concentration
    from app.goal.trajectory import run_trajectory, sensitivity_grid
    from app.reports.goal_report import render_goal_trajectory_report

    cfg = _cfg(mock)
    pf = load_portfolio(cfg)
    banner = compute_concentration(pf.holdings, cfg, seed=cfg.trajectory.seed)
    typer.echo(
        f"Concentration: AI/tech/semi {fmt_pct(banner.ai_tech_semi_pct)}"
        f"{' [FLAGGED]' if banner.flagged else ''}, corr {banner.weighted_avg_correlation:.2f}, "
        f"effective bets {banner.effective_independent_bets:.1f}"
    )
    result = run_trajectory(cfg, pf.holdings, concentration=banner)
    typer.echo(
        f"Solved threshold {result.solved_drawdown_threshold:.3f} "
        f"({'feasible' if result.feasible else 'INFEASIBLE'}); ruin {fmt_pct(result.ruin_probability)}; "
        f"guard {'PASS' if result.downside_guard_passed else 'FAIL'}; "
        f"median terminal {fmt_money_m(result.median_terminal_wealth)}; "
        f"P(reach {fmt_money(cfg.goal_plan.milestone_wealth)}) {fmt_pct(result.prob_reach_milestone)}"
    )
    if write:
        cells = sensitivity_grid(cfg)
        run = RunFolder(cfg)
        run.write_text(
            "goal_trajectory_report.md", render_goal_trajectory_report(cfg, result, cells)
        )
        run.write_assumptions(result.assumptions)
        run.finalize(cfg.settings.mode, result.seed, notes="project-goal")
        typer.echo(f"Wrote {run.path / 'goal_trajectory_report.md'}")


@app.command("compare-income-sleeve")
def compare_income_sleeve_cmd(
    mock: bool = typer.Option(True),
    write: bool = typer.Option(True),
) -> None:
    """Run the income-sleeve A-vs-B comparison standalone (empirical capture, ROC flag)."""
    from app.goal.income_sleeve import build_income_comparison
    from app.reports.goal_report import render_income_sleeve_comparison

    cfg = _cfg(mock)
    cmp = build_income_comparison(cfg)
    typer.echo(
        f"Capture up={cmp.up_capture:.3f} down={cmp.down_capture:.3f} "
        f"(peer_substituted={cmp.peer_substituted}); A-B p50 delta {fmt_money(cmp.delta_terminal_p50)}; "
        f"ROC constructive {fmt_pct(cmp.roc_constructive_share)}"
    )
    if write:
        run = RunFolder(cfg)
        run.write_text("income_sleeve_comparison.md", render_income_sleeve_comparison(cfg, cmp))
        run.write_assumptions(cmp.assumptions)
        run.finalize(cfg.settings.mode, cfg.trajectory.seed, notes="compare-income-sleeve")
        typer.echo(f"Wrote {run.path / 'income_sleeve_comparison.md'}")


@app.command("run-all")
def run_all_cmd(
    mock: bool = typer.Option(False, "--mock", help="Run from fixtures, zero credentials."),
    live_readonly: bool = typer.Option(
        False, "--live-readonly", help="Read-only live pull (needs credentials)."
    ),
) -> None:
    """Generate the full report set into a single run folder (deterministic from fixtures)."""
    from app.reports.run_all import run_all

    if not mock and not live_readonly:
        mock = True
    cfg = load_config()
    cfg.settings.mode = "live_readonly" if live_readonly else "mock"
    path = run_all(cfg)
    typer.echo(f"Run complete: {path}")
    typer.echo("Inspect first: goal_trajectory_report.md, income_sleeve_comparison.md")


if __name__ == "__main__":
    app()
