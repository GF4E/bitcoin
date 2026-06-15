"""Orchestrate a full run into a single run folder (deterministic from fixtures).

Saves raw normalized inputs, configs used, all reports/CSVs, trade memos, the
decision log, data-quality warnings, run metadata, and assumptions_used.yaml.
"""

from __future__ import annotations

from pathlib import Path

from app.config import AppConfig
from app.data.contracts import Holding
from app.data.loader import load_portfolio
from app.decision_engine import DecisionBundle, run_decision_engine
from app.goal.concentration import compute_concentration
from app.goal.income_sleeve import build_income_comparison
from app.goal.trajectory import run_trajectory, sensitivity_grid
from app.momentum.engine import compute_signals
from app.portfolio.replacement_engine import compare_replacement
from app.reports import tables
from app.reports.exposure_report import render_exposure_report
from app.reports.goal_report import (
    render_goal_trajectory_report,
    render_income_sleeve_comparison,
)
from app.reports.memos import build_covered_call_memo, build_leaps_memo, render_memo
from app.reports.writer import RunFolder


def _holdings_rows(holdings: list[Holding]) -> tuple[list[str], list[dict[str, object]]]:
    cols = [
        "account_id",
        "masked_account_id",
        "ticker",
        "name",
        "asset_type",
        "sleeve",
        "role",
        "momentum_tag",
        "quantity",
        "price",
        "market_value",
        "cost_basis",
        "unrealized_gain_loss",
        "is_schwab_managed",
        "data_source",
        "data_quality_flags",
    ]
    rows = [
        {c: getattr(h, c) for c in cols if c != "data_quality_flags"}
        | {"data_quality_flags": ";".join(h.data_quality_flags)}
        for h in holdings
    ]
    return cols, rows


def _replacements(cfg: AppConfig, bundle: DecisionBundle, holdings: list[Holding]) -> list:
    ai_holdings = [
        h
        for h in holdings
        if cfg.is_ai_tech_semi(h.ticker) and h.asset_type.value in ("equity", "fund")
    ]
    if not ai_holdings:
        return []
    sigs = {s.ticker: s for s in compute_signals(cfg, sorted({h.ticker for h in ai_holdings}))}
    incumbent = min(
        ai_holdings, key=lambda h: sigs[h.ticker].blended_momentum if h.ticker in sigs else 0.0
    )
    adds = [o for o in bundle.opportunities if o.candidate_action.value == "add"][:3]
    return [compare_replacement(cfg, incumbent, o.ticker) for o in adds]


def _write_memos(cfg: AppConfig, run: RunFolder, bundle: DecisionBundle) -> dict[str, str]:
    memo_paths: dict[str, str] = {}
    leaders = [lc for lc in bundle.leaps if lc.candidate_action.value == "open_leap"][:3]
    calls = [cc for cc in bundle.covered_calls if cc.candidate_action.value == "write_call"][:3]
    for lc in leaders:
        name = f"trade_memos/leaps_{lc.underlying}_{lc.strike}.md"
        run.write_text(name, render_memo(build_leaps_memo(cfg, lc)))
        memo_paths[f"{lc.underlying} {lc.expiration} C{lc.strike}"] = name
    for cc in calls:
        name = f"trade_memos/covered_call_{cc.ticker}_{cc.strike}.md"
        run.write_text(name, render_memo(build_covered_call_memo(cfg, cc)))
        memo_paths[f"{cc.ticker} {cc.expiration} C{cc.strike}"] = name
    return memo_paths


def run_all(cfg: AppConfig, run_id: str | None = None, base: Path | None = None) -> Path:
    pf = load_portfolio(cfg)
    run = RunFolder(cfg, run_id=run_id, base=base)
    ts = run.started_at
    cmode = cfg.settings.compliance_mode

    bundle = run_decision_engine(cfg, pf.accounts, pf.holdings, run.run_id, ts)
    banner = compute_concentration(pf.holdings, cfg, seed=cfg.trajectory.seed)
    trajectory = run_trajectory(cfg, pf.holdings, concentration=banner)
    cells = sensitivity_grid(cfg)
    income = build_income_comparison(cfg)
    replacements = _replacements(cfg, bundle, pf.holdings)

    # trade memos first, so the decision log can reference memo paths
    memo_paths = _write_memos(cfg, run, bundle)
    for e in bundle.decision_log:
        if e.ticker in memo_paths:
            e.memo_path = memo_paths[e.ticker]

    # markdown reports
    run.write_text(
        "portfolio_exposure_report.md",
        render_exposure_report(cfg, bundle.exposure, bundle.reconciliation, bundle.throttle),
    )
    run.write_text(
        "goal_trajectory_report.md", render_goal_trajectory_report(cfg, trajectory, cells)
    )
    run.write_text("income_sleeve_comparison.md", render_income_sleeve_comparison(cfg, income))

    # CSV report set
    run.write_csv("current_holdings_decisions.csv", *tables.holdings_table(bundle, cmode))
    run.write_csv("opportunities_ranked.csv", *tables.opportunities_table(bundle, cmode))
    run.write_csv("replacement_candidates.csv", *tables.replacement_table(replacements))
    run.write_csv("leaps_candidates.csv", *tables.leaps_table(bundle, cmode))
    run.write_csv("covered_call_candidates.csv", *tables.covered_call_table(bundle, cmode))
    run.write_csv("momentum_signals.csv", *tables.momentum_table(bundle))
    run.write_csv("execution_flags.csv", *tables.execution_table(bundle))
    run.write_csv("decision_log.csv", *tables.decision_log_table(bundle.decision_log, cmode))

    # raw normalized inputs + data-quality warnings
    run.write_csv("normalized_holdings.csv", *_holdings_rows(pf.holdings))
    all_warnings = [
        *pf.ledger.warnings,
        *trajectory.warnings,
        *income.warnings,
        *bundle.recon_warnings,
    ]
    run.write_csv(
        "data_quality_warnings.csv",
        ["code", "severity", "message", "ticker", "field", "label"],
        [
            {
                "code": w.code,
                "severity": w.severity.value,
                "message": w.message,
                "ticker": w.ticker or "",
                "field": w.field or "",
                "label": w.label.value if w.label else "",
            }
            for w in all_warnings
        ],
    )

    # configs used + assumptions + metadata
    run.write_yaml(
        "configs_used.yaml",
        {
            "settings": cfg.settings.model_dump(mode="json"),
            "risk_budget": cfg.risk_budget.model_dump(mode="json"),
            "goal_plan": cfg.goal_plan.model_dump(mode="json"),
            "trajectory": cfg.trajectory.model_dump(mode="json"),
        },
    )
    run.write_assumptions([*trajectory.assumptions, *income.assumptions])
    run.finalize(cfg.settings.mode, trajectory.seed, notes="run-all")
    return run.path
