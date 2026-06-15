"""Deterministic sample series generators (feed momentum/VWAP in P3)."""

from __future__ import annotations

import numpy as np

from app.data.fixtures import (
    anchor_price,
    daily_closes,
    intraday_session,
    monthly_price_bars,
    monthly_return_panel,
)


def test_monthly_price_bars_anchor_to_current_price() -> None:
    bars = monthly_price_bars("NVDA", months=14, seed=7)
    assert len(bars) == 14
    assert abs(float(bars[-1]["close"]) - anchor_price("NVDA")) < 1e-6
    # deterministic
    assert monthly_price_bars("NVDA", months=14, seed=7) == bars


def test_daily_closes_length_and_anchor() -> None:
    closes = daily_closes("SMH", days=220, seed=7)
    assert closes.shape == (220,)
    assert abs(float(closes[-1]) - anchor_price("SMH")) < 1e-6


def test_intraday_session_shapes() -> None:
    session = intraday_session("NVDA", n=40, seed=7)
    assert len(session) == 40
    assert all(len(x) == 2 for x in session)


def test_panel_is_correlated_for_ai_names() -> None:
    panel = monthly_return_panel(["NVDA", "AVGO", "SMH"], months=26, seed=12345)
    m = np.vstack([panel["NVDA"], panel["AVGO"], panel["SMH"]])
    corr = np.corrcoef(m)
    # AI names share the dominant factor -> positive off-diagonal correlation
    assert corr[0, 1] > 0.3 and corr[0, 2] > 0.3
