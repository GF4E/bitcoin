"""Monte-Carlo trajectory: reproducibility, ruin/guard constraints, VA offset,
income-sleeve compounding, and median-terminal-wealth maximization."""

from __future__ import annotations

from dataclasses import replace

import numpy as np

from app.goal.monte_carlo import SimInputs, simulate
from app.goal.objective import Guard, evaluate_threshold, solve_threshold

NET_WORTH = 3_190_000.0


def _inp(**kw: object) -> SimInputs:
    base: dict[str, object] = dict(
        start_wealth=NET_WORTH,
        horizon_months=180,
        core_mu=0.10,
        core_vol=0.22,
        income_mu=0.085,
        income_vol=0.16,
        income_fraction=0.10,
        correlation=0.59,
        safe_annual=0.045,
        defensive_exposure=0.35,
        monthly_expenses=12000.0,
        va_floor=4158.0,
        discretionary=2000.0,
        milestone=5_000_000.0,
        n_paths=2000,
        seed=12345,
    )
    base.update(kw)
    return SimInputs(**base)  # type: ignore[arg-type]


def test_mc_reproducible_under_fixed_seed() -> None:
    a = simulate(_inp(), 0.25)
    b = simulate(_inp(), 0.25)
    assert np.array_equal(a.terminal, b.terminal)
    assert a.ruin_probability == b.ruin_probability


def test_randomize_changes_draws() -> None:
    a = simulate(_inp(randomize=True), 0.25)
    b = simulate(_inp(randomize=True), 0.25)
    assert not np.array_equal(a.terminal, b.terminal)


def test_ruin_constraint_enforced_when_feasible() -> None:
    sol = solve_threshold(
        _inp(),
        ruin_cap=0.075,
        guard=Guard("p25_floor", NET_WORTH, 0.10),
        t_min=0.05,
        t_max=0.40,
        tol=0.0025,
        n_grid=9,
    )
    if sol.feasible:
        assert sol.selected.ruin <= 0.075 + 1e-9
        assert sol.selected.guard_passed


def test_downside_guard_binds_in_stress_reports_infeasible() -> None:
    # Low return + high vol: the p25 floor cannot be met at any threshold.
    stressed = _inp(core_mu=0.05, core_vol=0.34, n_paths=3000, horizon_months=240)
    sol = solve_threshold(
        stressed,
        ruin_cap=0.075,
        guard=Guard("p25_floor", NET_WORTH, 0.10),
        t_min=0.05,
        t_max=0.40,
        tol=0.0025,
        n_grid=9,
    )
    assert sol.feasible is False
    # the reported tradeoff is still the least-bad (lowest ruin) candidate
    assert sol.selected.threshold in [e.threshold for e in sol.sweep]


def test_cvar_guard_mode_available() -> None:
    e = evaluate_threshold(_inp(), 0.25, 0.075, Guard("cvar", NET_WORTH, 0.10))
    assert e.guard_metric.startswith("cvar_worst_10pct")


def test_median_terminal_wealth_maximization() -> None:
    sol = solve_threshold(
        _inp(),
        ruin_cap=0.075,
        guard=Guard("p25_floor", NET_WORTH, 0.10),
        t_min=0.05,
        t_max=0.40,
        tol=0.0025,
        n_grid=9,
    )
    feasible = [e for e in sol.sweep if e.feasible]
    if feasible:
        best = max(e.median_terminal for e in feasible)
        assert sol.selected.median_terminal >= best - 1e-6


def test_va_offset_reduces_ruin_and_lifts_terminal() -> None:
    # A higher VA floor shrinks the portfolio-funded gap -> safer.
    low_va = _inp(core_mu=0.06, core_vol=0.26, va_floor=4158.0, n_paths=4000, horizon_months=240)
    high_va = replace(low_va, va_floor=6158.0)
    r_low, r_high = simulate(low_va, 0.20), simulate(high_va, 0.20)
    assert r_high.gap < r_low.gap
    assert r_high.ruin_probability <= r_low.ruin_probability
    assert np.median(r_high.terminal) > np.median(r_low.terminal)


def test_income_sleeve_compounding_affects_results() -> None:
    base = _inp(n_paths=4000)
    richer = replace(base, income_mu=0.16)
    assert np.median(simulate(richer, 0.25).terminal) != np.median(simulate(base, 0.25).terminal)
    # and the income sleeve must actually be present to matter
    no_sleeve = replace(base, income_fraction=0.0)
    assert np.median(simulate(no_sleeve, 0.25).terminal) != np.median(simulate(base, 0.25).terminal)
