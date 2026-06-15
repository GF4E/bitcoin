"""Config loads with the right types and the user-context defaults."""

from __future__ import annotations

from decimal import Decimal

from app.config import AppConfig


def test_money_fields_are_decimal(cfg: AppConfig) -> None:
    assert isinstance(cfg.goal_plan.monthly_gap, Decimal)
    assert cfg.goal_plan.va_monthly_floor == Decimal("4158")
    assert cfg.goal_plan.monthly_gap == Decimal("7842")
    assert cfg.goal_plan.milestone_wealth == Decimal("5000000")


def test_trajectory_defaults(cfg: AppConfig) -> None:
    t = cfg.trajectory
    assert t.n_paths == 10000
    assert t.ruin_probability_max == 0.075
    assert t.drag_anchor_mode == "baseline_cagr"
    assert t.downside_guard_mode == "p25_floor"
    assert t.sensitivity_pcts == [-0.20, -0.10, 0.10, 0.20]


def test_leaps_budget_math(cfg: AppConfig) -> None:
    assert cfg.risk_budget.leaps_budget == Decimal("160000")
    assert cfg.risk_budget.remaining_leaps_budget == Decimal("98000")


def test_safety_order_execution_disabled(cfg: AppConfig) -> None:
    assert cfg.settings.order_execution_enabled is False
