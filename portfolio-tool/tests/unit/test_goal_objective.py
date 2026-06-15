"""Objective math: required-CAGR, drag-in-bps, both drag modes differ, bisection."""

from __future__ import annotations

import math

from app.goal.objective import (
    bisect_boundary,
    cagr,
    deterministic_end_wealth,
    drag_ceiling_withdrawal,
    required_cagr,
    solve_max_withdrawal,
)

START = 3_190_000.0
MILESTONE = 5_000_000.0


def test_required_cagr_formula() -> None:
    r = required_cagr(START, MILESTONE, 2.0)
    assert math.isclose(r, (MILESTONE / START) ** 0.5 - 1.0, rel_tol=1e-12)


def test_zero_withdrawal_cagr_equals_return() -> None:
    end = deterministic_end_wealth(START, 0.10, 120, 0.0)
    assert math.isclose(cagr(START, end, 120), 0.10, rel_tol=1e-9)


def test_more_withdrawal_lowers_cagr() -> None:
    e0 = deterministic_end_wealth(START, 0.10, 120, 0.0)
    e1 = deterministic_end_wealth(START, 0.10, 120, 5000.0)
    assert cagr(START, e1, 120) < cagr(START, e0, 120)


def test_drag_in_bps_monotone() -> None:
    # A bigger drag ceiling tolerates a bigger withdrawal.
    tight = drag_ceiling_withdrawal(
        start=START,
        expected_return=0.10,
        horizon_months=240,
        drag_ceiling_bps=10,
        mode="baseline_cagr",
        milestone=MILESTONE,
        target_years=2.0,
    )
    loose = drag_ceiling_withdrawal(
        start=START,
        expected_return=0.10,
        horizon_months=240,
        drag_ceiling_bps=100,
        mode="baseline_cagr",
        milestone=MILESTONE,
        target_years=2.0,
    )
    assert loose.max_monthly_withdrawal > tight.max_monthly_withdrawal > 0


def test_both_drag_modes_differ_on_identical_inputs() -> None:
    kw = dict(
        start=START,
        expected_return=0.10,
        horizon_months=240,
        drag_ceiling_bps=50,
        milestone=MILESTONE,
        target_years=2.0,
    )
    baseline = drag_ceiling_withdrawal(mode="baseline_cagr", **kw)
    required = drag_ceiling_withdrawal(mode="required_cagr", **kw)
    assert baseline.floor_cagr != required.floor_cagr
    assert baseline.max_monthly_withdrawal != required.max_monthly_withdrawal


def test_bisect_boundary_converges_monotone() -> None:
    root = bisect_boundary(lambda x: x <= 0.3, 0.0, 1.0, tol=1e-4)
    assert abs(root - 0.3) < 1e-3
    # predicate true on whole range -> returns hi; false at lo -> returns lo
    assert bisect_boundary(lambda x: True, 0.0, 1.0, 1e-4) == 1.0
    assert bisect_boundary(lambda x: False, 0.0, 1.0, 1e-4) == 0.0


def test_solve_max_withdrawal_respects_floor() -> None:
    w = solve_max_withdrawal(START, 0.10, 240, 0.095)
    end = deterministic_end_wealth(START, 0.10, 240, w)
    assert cagr(START, end, 240) >= 0.095 - 1e-6
