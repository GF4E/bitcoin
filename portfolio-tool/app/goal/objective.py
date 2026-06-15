"""Objective function and solvers for the goal-trajectory engine.

Objective: among drawdown thresholds satisfying BOTH (a) ruin <= cap and (b) the
downside-dispersion guard, select the one with the highest median terminal wealth.
Higher T stays risk-on through deeper drawdowns (higher median terminal wealth in
most regimes) while ruin rises and the lower tail thins. The optimizer sweeps the
threshold across a deterministic grid and selects the feasible candidate with the
highest median terminal wealth. ``bisect_boundary`` is a separate, monotone
root-finder (tested independently) for locating constraint boundaries. If no
threshold is feasible, return the least-bad tradeoff, flagged.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from app.goal.monte_carlo import SimInputs, cvar_lower, percentile, simulate


@dataclass(frozen=True)
class Guard:
    mode: str  # "p25_floor" | "cvar"
    floor: float  # net_worth_total (book must not shrink in the guarded tail)
    cvar_alpha: float  # worst-fraction for the CVaR variant


@dataclass(frozen=True)
class ThresholdEval:
    threshold: float
    median_terminal: float
    p10: float
    p25: float
    p50: float
    p90: float
    ruin: float
    guard_metric: str
    guard_value: float
    guard_passed: bool
    feasible: bool


def evaluate_threshold(
    inp: SimInputs, threshold: float, ruin_cap: float, guard: Guard
) -> ThresholdEval:
    res = simulate(inp, threshold)
    term = res.terminal
    p10, p25, p50, p90 = (percentile(term, q) for q in (10, 25, 50, 90))
    if guard.mode == "cvar":
        gval = cvar_lower(term, res.ruined, guard.cvar_alpha)
        gmetric = f"cvar_worst_{int(guard.cvar_alpha * 100)}pct_nonruined"
    else:
        gval = p25
        gmetric = "p25_terminal"
    guard_passed = gval >= guard.floor
    feasible = (res.ruin_probability <= ruin_cap) and guard_passed
    return ThresholdEval(
        threshold=threshold,
        median_terminal=p50,
        p10=p10,
        p25=p25,
        p50=p50,
        p90=p90,
        ruin=res.ruin_probability,
        guard_metric=gmetric,
        guard_value=gval,
        guard_passed=guard_passed,
        feasible=feasible,
    )


def bisect_boundary(predicate: Callable[[float], bool], lo: float, hi: float, tol: float) -> float:
    """Largest x in [lo, hi] with predicate(x) True, assuming predicate is monotone
    (True near lo, flips False toward hi). Deterministic given a deterministic predicate."""
    if not predicate(lo):
        return lo
    if predicate(hi):
        return hi
    while hi - lo > tol:
        mid = 0.5 * (lo + hi)
        if predicate(mid):
            lo = mid
        else:
            hi = mid
    return lo


@dataclass(frozen=True)
class ThresholdSolution:
    threshold: float
    feasible: bool
    selected: ThresholdEval
    sweep: list[ThresholdEval]


def solve_threshold(
    inp: SimInputs,
    *,
    ruin_cap: float,
    guard: Guard,
    t_min: float,
    t_max: float,
    tol: float,
    n_grid: int = 13,
) -> ThresholdSolution:
    grid = [t_min + (t_max - t_min) * i / (n_grid - 1) for i in range(n_grid)]
    sweep = [evaluate_threshold(inp, t, ruin_cap, guard) for t in grid]
    feasible = [e for e in sweep if e.feasible]

    if not feasible:
        # No threshold satisfies both constraints: report the least-bad tradeoff.
        best = min(sweep, key=lambda e: (e.ruin, -e.guard_value))
        return ThresholdSolution(
            threshold=best.threshold, feasible=False, selected=best, sweep=sweep
        )

    # The spec's selection rule: among feasible thresholds, the highest median
    # terminal wealth. Median is not strictly monotone in T (at low vol the spending
    # response dominates, at high vol the de-risk response does), so we take the grid
    # argmax directly rather than the feasibility boundary. ``tol`` is unused here;
    # ``bisect_boundary`` is the separately-tested monotone root-finder.
    _ = tol
    selected = max(feasible, key=lambda e: e.median_terminal)
    return ThresholdSolution(
        threshold=selected.threshold, feasible=True, selected=selected, sweep=sweep
    )


# --------------------------------------------------------------------------- #
# Drag-ceiling / required-CAGR math (deterministic, no Monte-Carlo)
# --------------------------------------------------------------------------- #
def deterministic_end_wealth(
    start: float, annual_return: float, horizon_months: int, monthly_withdrawal: float
) -> float:
    g = (1.0 + annual_return) ** (1.0 / 12.0) - 1.0
    w = start
    for _ in range(horizon_months):
        w = w * (1.0 + g) - monthly_withdrawal
    return w


def cagr(start: float, end: float, horizon_months: int) -> float:
    if end <= 0 or start <= 0:
        return -1.0
    return (end / start) ** (12.0 / horizon_months) - 1.0


def required_cagr(start: float, milestone: float, years: float) -> float:
    """CAGR required to reach the milestone in ``years`` (a milestone, not the target)."""
    if start <= 0 or years <= 0:
        return 0.0
    return (milestone / start) ** (1.0 / years) - 1.0


def solve_max_withdrawal(
    start: float, annual_return: float, horizon_months: int, min_cagr: float
) -> float:
    """Largest constant monthly withdrawal keeping CAGR >= min_cagr (monotone -> bisection)."""
    if (
        cagr(
            start,
            deterministic_end_wealth(start, annual_return, horizon_months, 0.0),
            horizon_months,
        )
        < min_cagr
    ):
        return 0.0
    lo, hi = 0.0, start / horizon_months
    for _ in range(64):
        mid = 0.5 * (lo + hi)
        end = deterministic_end_wealth(start, annual_return, horizon_months, mid)
        if cagr(start, end, horizon_months) >= min_cagr:
            lo = mid
        else:
            hi = mid
    return lo


@dataclass(frozen=True)
class DragResult:
    mode: str
    baseline_cagr: float
    floor_cagr: float
    max_monthly_withdrawal: float
    withdrawal_cagr: float


def drag_ceiling_withdrawal(
    *,
    start: float,
    expected_return: float,
    horizon_months: int,
    drag_ceiling_bps: float,
    mode: str,
    milestone: float,
    target_years: float,
) -> DragResult:
    drag = drag_ceiling_bps / 10_000.0
    baseline = cagr(
        start, deterministic_end_wealth(start, expected_return, horizon_months, 0.0), horizon_months
    )
    if mode == "required_cagr":
        floor = required_cagr(start, milestone, target_years) - drag
    else:
        floor = baseline - drag
    w = solve_max_withdrawal(start, expected_return, horizon_months, floor)
    wc = cagr(
        start, deterministic_end_wealth(start, expected_return, horizon_months, w), horizon_months
    )
    return DragResult(
        mode=mode,
        baseline_cagr=baseline,
        floor_cagr=floor,
        max_monthly_withdrawal=w,
        withdrawal_cagr=wc,
    )
