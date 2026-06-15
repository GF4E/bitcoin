"""Income-sleeve A-vs-B: empirical capture, identical-seed delta, ROC flag, regime flip."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from app.config import AppConfig
from app.goal.income_sleeve import (
    build_income_comparison,
    compare_approaches,
    derive_capture,
    estimate_capture,
)

APP_DIR = Path(__file__).resolve().parent.parent.parent / "app"


def test_capture_derived_from_series_not_hardcoded() -> None:
    index = np.array([0.05, -0.04, 0.03, -0.02, 0.06, -0.01])
    fund_capped = np.where(index >= 0, 0.6 * index, 0.95 * index)
    up, dn = derive_capture(fund_capped, index)
    assert abs(up - 0.6) < 1e-9
    assert abs(dn - 0.95) < 1e-9
    # a different series yields a different capture (nothing is constant)
    up2, _ = derive_capture(np.where(index >= 0, 0.4 * index, index), index)
    assert up2 != up


def test_no_hardcoded_capture_ratio_in_engine() -> None:
    """Guard: the income-sleeve engine must not contain a literal capture ratio."""
    src = (APP_DIR / "goal" / "income_sleeve.py").read_text("utf-8")
    # capture must come from derive_capture(); the only floats are clamps/labels.
    assert "derive_capture" in src
    for forbidden in ("up_capture = 0.", "down_capture = 0.", "0.74 *", "0.49 *"):
        assert forbidden not in src


def test_peer_substitution_flows_through(cfg: AppConfig) -> None:
    cap = estimate_capture(cfg)
    # QQQI sample history is <36 months -> peer (QYLD) used for the capped bound.
    assert cap.peer_substituted is True
    assert cap.source == cfg.income_sleeve.peer_fallback_fund
    assert (
        cap.fund_short_sample is not None
    )  # QQQI's own short-sample estimate retained for context


def test_identical_seed_delta_reproducible() -> None:
    kw = dict(
        start_wealth=3_190_000.0,
        horizon_months=120,
        index_mu=0.10,
        index_vol=0.20,
        up_capture=0.7,
        down_capture=0.9,
        monthly_gap=7842.0,
        buffer_months=18,
        safe_annual=0.045,
        roc_window=12,
        n_paths=3000,
        seed=12345,
    )
    a = compare_approaches(**kw)
    b = compare_approaches(**kw)
    assert np.array_equal(a.delta, b.delta)


def test_buffer_sizing_matches_gap() -> None:
    cfg_buffer_months = 18
    gap = 7842.0
    # Approach B holds buffer_months*gap in the buffer; verify via a 1-month, zero-return run.
    res = compare_approaches(
        start_wealth=1_000_000.0,
        horizon_months=1,
        index_mu=0.0,
        index_vol=0.0,
        up_capture=1.0,
        down_capture=1.0,
        monthly_gap=gap,
        buffer_months=cfg_buffer_months,
        safe_annual=0.0,
        roc_window=12,
        n_paths=10,
        seed=1,
    )
    # B terminal = start - gap (one month's draw from the buffer); A terminal = start - gap too.
    assert np.allclose(res.b_terminal, 1_000_000.0 - gap)


def test_roc_flag_and_regime_flip() -> None:
    # As modeled return falls, A improves relative to B (delta increases) and ROC
    # becomes less constructive; A overtakes B with downside-protective capture in a bear.
    deltas = []
    roc = []
    for mu in (0.16, 0.08, 0.0, -0.10):
        s = compare_approaches(
            start_wealth=3_190_000.0,
            horizon_months=120,
            index_mu=mu,
            index_vol=0.18,
            up_capture=0.74,
            down_capture=0.85,
            monthly_gap=7842.0,
            buffer_months=18,
            safe_annual=0.045,
            roc_window=12,
            n_paths=4000,
            seed=12345,
        )
        deltas.append(float(np.median(s.delta)))
        roc.append(s.roc_constructive_share)
    assert deltas[0] < deltas[1] < deltas[2] < deltas[3]  # A relatively better as return falls
    assert roc[0] > roc[-1]  # ROC more destructive in the bear
    assert deltas[-1] > 0  # A overtakes B in the bear


def test_build_comparison_emits_decimal_money(cfg: AppConfig) -> None:
    cfg.trajectory.n_paths = 2000
    cmp = build_income_comparison(cfg)
    from decimal import Decimal

    assert isinstance(cmp.delta_terminal_p50, Decimal)
    assert cmp.up_capture > 0 and cmp.down_capture > 0
