"""Concentration banner computes from a series and flags above threshold."""

from __future__ import annotations

import numpy as np

from app.config import AppConfig
from app.data.loader import load_portfolio
from app.goal.concentration import (
    compute_concentration,
    effective_independent_bets,
    weighted_avg_pairwise_correlation,
)


def test_banner_flags_concentrated_book(cfg: AppConfig) -> None:
    pf = load_portfolio(cfg)
    b = compute_concentration(pf.holdings, cfg, seed=cfg.trajectory.seed)
    assert b.ai_tech_semi_pct > 0.40
    assert b.flagged is True
    assert 0.0 < b.weighted_avg_correlation < 1.0
    assert 1.0 < b.effective_independent_bets < 9.0  # concentrated: far fewer than the name count


def test_enb_decreases_with_correlation() -> None:
    # higher uniform correlation -> fewer effective bets
    n = 6
    lo = 0.2 * np.ones((n, n)) + 0.8 * np.eye(n)
    hi = 0.8 * np.ones((n, n)) + 0.2 * np.eye(n)
    assert effective_independent_bets(hi) < effective_independent_bets(lo)


def test_weighted_avg_pairwise_correlation_equicorrelation() -> None:
    n = 4
    rho = 0.5
    corr = rho * np.ones((n, n)) + (1 - rho) * np.eye(n)
    w = np.full(n, 1.0 / n)
    assert abs(weighted_avg_pairwise_correlation(corr, w) - rho) < 1e-9
