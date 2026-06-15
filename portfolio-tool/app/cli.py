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


@app.command("evaluate-holdings")
def evaluate_holdings_cmd(mock: bool = typer.Option(True)) -> None:
    """Score current holdings and emit the full decision envelope per holding."""
    from app.portfolio.holding_evaluator import evaluate_holdings

    cfg = _cfg(mock)
    pf = load_portfolio(cfg)
    for d in evaluate_holdings(cfg, pf.holdings):
        typer.echo(
            f"{d.ticker:8s} {d.candidate_action.value:16s} conf {d.confidence:.2f} "
            f"score {d.total_score:5.1f} [{d.triage.value}] {d.rationale}"
        )


@app.command("evaluate-opportunities")
def evaluate_opportunities_cmd(mock: bool = typer.Option(True)) -> None:
    """Rank the opportunity universe."""
    from app.opportunities.screener import screen_opportunities

    cfg = _cfg(mock)
    pf = load_portfolio(cfg)
    for o in screen_opportunities(cfg, pf.holdings):
        typer.echo(
            f"{o.ticker:6s} {o.candidate_action.value:8s} score {o.total_score:5.1f} "
            f"conf {o.confidence:.2f}  {o.thesis_bucket}"
        )


@app.command("screen-leaps")
def screen_leaps_cmd(mock: bool = typer.Option(True)) -> None:
    """Screen the LEAPS universe (stock-replacement leverage on momentum leaders)."""
    from app.options.leaps_screener import screen_leaps

    cfg = _cfg(mock)
    for c in screen_leaps(cfg)[:12]:
        typer.echo(
            f"{c.underlying:6s} {c.expiration} C{c.strike} d{c.delta:.2f} "
            f"cost {fmt_money(c.cost)} score {c.total_score:5.1f} {c.candidate_action.value} "
            f"| 2x@{c.px_2x} 3x@{c.px_3x} 5x@{c.px_5x}"
        )


@app.command("screen-covered-calls")
def screen_covered_calls_cmd(mock: bool = typer.Option(True)) -> None:
    """Screen covered-call / repair candidates (ballast only; leaders protected)."""
    from app.options.covered_call_engine import screen_covered_calls

    cfg = _cfg(mock)
    pf = load_portfolio(cfg)
    cands = screen_covered_calls(cfg, pf.holdings)
    if not cands:
        typer.echo(
            "No eligible ballast holdings (momentum leaders are protected from call-writing)."
        )
    for c in cands:
        typer.echo(
            f"{c.ticker:6s} {c.expiration} C{c.strike} d{c.delta:.2f} income {fmt_money(c.premium_income)} "
            f"[{c.classification}] {c.candidate_action.value} eff_exit {c.effective_exit_if_assigned}"
        )


@app.command("run-momentum")
def run_momentum_cmd(mock: bool = typer.Option(True)) -> None:
    """Run the momentum engine + macro throttle + conflict rule."""
    from app.momentum.engine import run_momentum
    from app.momentum.throttle import apply_conflict_rule, load_throttle

    cfg = _cfg(mock)
    sigs = run_momentum(cfg)
    throttle = load_throttle(cfg)
    res = apply_conflict_rule(sigs, throttle)
    typer.echo(
        f"Throttle gross multiplier {throttle.gross_exposure_multiplier:.0%} "
        f"(brake {'ON' if throttle.brake_active else 'off'}); conflict rule: brake sizes, engine selects."
    )
    for s in sorted(sigs, key=lambda x: x.blended_momentum, reverse=True):
        typer.echo(
            f"{s.ticker:6s} 12-1 {s.ts_momentum_12_1:+.3f} blended {s.blended_momentum:+.3f} "
            f"trend {'on' if s.trend_filter_on else 'off'} tag {s.momentum_tag.value:7s} "
            f"sized_w {res.sized_weights[s.ticker]:.2f}"
        )


@app.command("generate-reports")
def generate_reports_cmd(mock: bool = typer.Option(True)) -> None:
    """Alias for run-all: generate the full deterministic report set."""
    run_all_cmd(mock=mock, live_readonly=False)


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
