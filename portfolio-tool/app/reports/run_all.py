"""Orchestrate a full run into a single run folder.

P2 scope: portfolio load, concentration banner, goal-trajectory report, and the
income-sleeve comparison (the two headline deliverables) plus data-quality
warnings. P3 extends this with holdings decisions, opportunities, LEAPS,
covered-calls, momentum, execution flags, the decision log, and trade memos.
"""

from __future__ import annotations

from pathlib import Path

from app.config import AppConfig
from app.data.loader import load_portfolio
from app.goal.concentration import compute_concentration
from app.goal.income_sleeve import build_income_comparison
from app.goal.trajectory import run_trajectory, sensitivity_grid
from app.reports.goal_report import (
    render_goal_trajectory_report,
    render_income_sleeve_comparison,
)
from app.reports.writer import RunFolder


def _warning_rows(*warning_lists: list) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for wl in warning_lists:
        for w in wl:
            rows.append(
                {
                    "code": w.code,
                    "severity": w.severity.value,
                    "message": w.message,
                    "ticker": w.ticker or "",
                    "field": w.field or "",
                    "label": w.label.value if w.label else "",
                }
            )
    return rows


def run_all(cfg: AppConfig, run_id: str | None = None, base: Path | None = None) -> Path:
    pf = load_portfolio(cfg)
    run = RunFolder(cfg, run_id=run_id, base=base)

    banner = compute_concentration(pf.holdings, cfg, seed=cfg.trajectory.seed)
    trajectory = run_trajectory(cfg, pf.holdings, concentration=banner)
    cells = sensitivity_grid(cfg)
    income = build_income_comparison(cfg)

    run.write_text(
        "goal_trajectory_report.md", render_goal_trajectory_report(cfg, trajectory, cells)
    )
    run.write_text("income_sleeve_comparison.md", render_income_sleeve_comparison(cfg, income))

    run.write_csv(
        "data_quality_warnings.csv",
        ["code", "severity", "message", "ticker", "field", "label"],
        _warning_rows(pf.ledger.warnings, trajectory.warnings, income.warnings),
    )
    run.write_assumptions([*trajectory.assumptions, *income.assumptions])
    run.finalize(cfg.settings.mode, trajectory.seed, notes="run-all")
    return run.path
