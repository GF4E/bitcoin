"""Goal-trajectory engine — orchestration.

Builds the simulation inputs from config + holdings, computes the live
concentration banner, runs the sensitivity sweep (the report headline), solves the
drawdown threshold under the two-constraint objective, and assembles a
``TrajectoryResult``. All money is reconstructed as ``Decimal`` here, at emit time;
the simulation itself was pure ``float``.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date

import numpy as np

from app.config import AppConfig
from app.data.contracts import (
    Assumption,
    ConcentrationBanner,
    DataLabel,
    DataQualityWarning,
    Holding,
    Severity,
    TrajectoryResult,
)
from app.goal.concentration import compute_concentration
from app.goal.monte_carlo import SimInputs, simulate
from app.goal.objective import (
    Guard,
    ThresholdSolution,
    cagr,
    deterministic_end_wealth,
    drag_ceiling_withdrawal,
    solve_threshold,
)
from app.money import round_money, to_money


def target_years(cfg: AppConfig, today: date | None = None) -> float:
    today = today or date(2026, 6, 15)
    days = (cfg.goal_plan.target_date - today).days
    return max(days / 365.25, 0.25)


def build_inputs(
    cfg: AppConfig,
    *,
    return_mult: float = 1.0,
    vol_mult: float = 1.0,
) -> SimInputs:
    gp = cfg.goal_plan
    t = cfg.trajectory
    return SimInputs(
        start_wealth=float(gp.net_worth_total),
        horizon_months=t.horizon_months,
        core_mu=gp.expected_return_annual * return_mult,
        core_vol=gp.volatility_annual * vol_mult,
        income_mu=t.income_sleeve_expected_return,
        income_vol=t.income_sleeve_volatility,
        income_fraction=t.income_fraction,
        correlation=gp.income_sleeve_correlation,
        safe_annual=t.safe_annual,
        defensive_exposure=t.defensive_exposure,
        monthly_expenses=float(gp.monthly_expenses),
        va_floor=float(gp.va_monthly_floor),
        discretionary=float(gp.discretionary_cuttable),
        milestone=float(gp.milestone_wealth),
        n_paths=t.n_paths,
        seed=t.seed,
        randomize=t.randomize_seed,
    )


def _guard(cfg: AppConfig) -> Guard:
    return Guard(
        mode=cfg.trajectory.downside_guard_mode,
        floor=float(cfg.risk_budget.net_worth_total),
        cvar_alpha=cfg.trajectory.cvar_alpha,
    )


def _solve(cfg: AppConfig, inp: SimInputs, n_grid: int | None = None) -> ThresholdSolution:
    t = cfg.trajectory
    return solve_threshold(
        inp,
        ruin_cap=t.ruin_probability_max,
        guard=_guard(cfg),
        t_min=t.threshold_min,
        t_max=t.threshold_max,
        tol=t.threshold_tolerance,
        n_grid=n_grid or t.n_grid,
    )


@dataclass(frozen=True)
class SensitivityCell:
    return_mult: float
    vol_mult: float
    median_terminal: float
    ruin: float
    threshold: float
    feasible: bool


def sensitivity_grid(cfg: AppConfig) -> list[SensitivityCell]:
    """Sweep -20/-10/0/+10/+20% on expected_return AND volatility (the headline)."""
    pcts = [0.0, *cfg.trajectory.sensitivity_pcts]
    levels = sorted({round(1.0 + p, 4) for p in pcts})
    cells: list[SensitivityCell] = []
    for rm in levels:
        for vm in levels:
            inp = build_inputs(cfg, return_mult=rm, vol_mult=vm)
            # reduced paths/grid keep the 5x5 headline grid fast; the point estimate
            # (run_trajectory) uses full n_paths.
            inp = replace(inp, n_paths=cfg.trajectory.sensitivity_n_paths)
            sol = _solve(cfg, inp, n_grid=cfg.trajectory.sensitivity_n_grid)
            cells.append(
                SensitivityCell(
                    return_mult=rm,
                    vol_mult=vm,
                    median_terminal=sol.selected.median_terminal,
                    ruin=sol.selected.ruin,
                    threshold=sol.threshold,
                    feasible=sol.feasible,
                )
            )
    return cells


def milestone_crossing_distribution(inp: SimInputs, threshold: float) -> dict[str, float]:
    res = simulate(inp, threshold)
    crossed = res.crossing_month[res.crossing_month >= 0]
    if crossed.size == 0:
        return {}
    months = crossed.astype(float)
    return {
        "p10_months": float(np.percentile(months, 10)),
        "p50_months": float(np.percentile(months, 50)),
        "p90_months": float(np.percentile(months, 90)),
        "share_crossing": float((res.crossing_month >= 0).mean()),
    }


def run_trajectory(
    cfg: AppConfig, holdings: list[Holding], concentration: ConcentrationBanner | None = None
) -> TrajectoryResult:
    gp = cfg.goal_plan
    t = cfg.trajectory
    inp = build_inputs(cfg)
    sol = _solve(cfg, inp)
    sel = sol.selected
    banner = concentration or compute_concentration(holdings, cfg, seed=t.seed)

    drag = drag_ceiling_withdrawal(
        start=float(gp.net_worth_total),
        expected_return=gp.expected_return_annual,
        horizon_months=t.horizon_months,
        drag_ceiling_bps=t.drag_ceiling_bps,
        mode=t.drag_anchor_mode,
        milestone=float(gp.milestone_wealth),
        target_years=target_years(cfg),
    )
    baseline_cagr = cagr(
        float(gp.net_worth_total),
        deterministic_end_wealth(
            float(gp.net_worth_total), gp.expected_return_annual, t.horizon_months, 0.0
        ),
        t.horizon_months,
    )

    warnings: list[DataQualityWarning] = []
    if not sol.feasible:
        warnings.append(
            DataQualityWarning(
                code="no_feasible_threshold",
                message=(
                    "No drawdown threshold satisfies both ruin<=%.1f%% and the downside guard; "
                    "reporting the least-bad tradeoff." % (t.ruin_probability_max * 100)
                ),
                severity=Severity.CRITICAL,
            )
        )
    expected_gap = float(gp.monthly_expenses - gp.va_monthly_floor)
    if abs(expected_gap - float(gp.monthly_gap)) > 1.0:
        warnings.append(
            DataQualityWarning(
                code="gap_inconsistent",
                message=f"monthly_gap {gp.monthly_gap} != expenses-VA {expected_gap:.0f}",
                severity=Severity.WARN,
            )
        )

    assumptions = [
        Assumption(
            name="expected_return_annual",
            value=f"{gp.expected_return_annual:.3f}",
            label=DataLabel.ESTIMATED,
            load_bearing=True,
            rationale="Least-sourceable, most load-bearing; swept in the headline grid.",
        ),
        Assumption(
            name="volatility_annual",
            value=f"{gp.volatility_annual:.3f}",
            label=DataLabel.ESTIMATED,
            load_bearing=True,
            rationale="Least-sourceable, most load-bearing; swept in the headline grid.",
        ),
        Assumption(
            name="income_sleeve_correlation",
            value=f"{gp.income_sleeve_correlation:.2f}",
            label=DataLabel.ESTIMATED,
            load_bearing=True,
            rationale="Estimated from price history.",
        ),
        Assumption(
            name="seed_fixed",
            value=str(t.seed),
            label=DataLabel.ASSUMED,
            rationale="A single fixed-seed run is not the full probability picture.",
        ),
        Assumption(
            name="net_worth_total",
            value=str(gp.net_worth_total),
            label=DataLabel.VERIFIED,
            load_bearing=True,
            rationale="Denominator for all risk/withdrawal/goal math.",
        ),
    ]

    return TrajectoryResult(
        solved_drawdown_threshold=sol.threshold,
        ruin_probability=sel.ruin,
        downside_guard_passed=sel.guard_passed,
        downside_guard_metric=sel.guard_metric,
        downside_guard_value=round_money(to_money(sel.guard_value)),
        feasible=sol.feasible,
        median_terminal_wealth=round_money(to_money(sel.p50)),
        p10_terminal=round_money(to_money(sel.p10)),
        p25_terminal=round_money(to_money(sel.p25)),
        p50_terminal=round_money(to_money(sel.p50)),
        p90_terminal=round_money(to_money(sel.p90)),
        prob_reach_milestone=simulate(inp, sol.threshold).prob_reach_milestone,
        milestone_crossing_months=milestone_crossing_distribution(inp, sol.threshold),
        drag_anchor_mode=drag.mode,
        baseline_cagr=baseline_cagr,
        withdrawal_cagr=drag.withdrawal_cagr,
        n_paths=t.n_paths,
        seed=None if t.randomize_seed else t.seed,
        concentration=banner,
        assumptions=assumptions,
        warnings=warnings,
    )
