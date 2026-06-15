"""Integration: run_trajectory end-to-end on fixtures, and both drag modes differ."""

from __future__ import annotations

from decimal import Decimal

from app.config import AppConfig, load_config
from app.data.loader import load_portfolio
from app.goal.trajectory import run_trajectory


def _fast_cfg() -> AppConfig:
    cfg = load_config()
    cfg.trajectory.n_paths = 1500
    cfg.trajectory.horizon_months = 180
    return cfg


def test_run_trajectory_produces_valid_result() -> None:
    cfg = _fast_cfg()
    pf = load_portfolio(cfg)
    res = run_trajectory(cfg, pf.holdings)
    assert (
        cfg.trajectory.threshold_min
        <= res.solved_drawdown_threshold
        <= cfg.trajectory.threshold_max
    )
    assert 0.0 <= res.ruin_probability <= 1.0
    assert res.concentration.flagged is True
    assert isinstance(res.median_terminal_wealth, Decimal)
    assert res.p10_terminal <= res.p50_terminal <= res.p90_terminal
    assert res.assumptions and any(a.load_bearing for a in res.assumptions)
    assert res.seed == cfg.trajectory.seed


def test_both_drag_modes_differ_via_trajectory() -> None:
    cfg = _fast_cfg()
    pf = load_portfolio(cfg)
    cfg.trajectory.drag_anchor_mode = "baseline_cagr"
    base = run_trajectory(cfg, pf.holdings)
    cfg.trajectory.drag_anchor_mode = "required_cagr"
    req = run_trajectory(cfg, pf.holdings)
    assert base.drag_anchor_mode != req.drag_anchor_mode
    assert base.withdrawal_cagr != req.withdrawal_cagr
