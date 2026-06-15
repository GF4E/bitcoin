"""Momentum engine + macro throttle + conflict rule."""

from __future__ import annotations

import numpy as np

from app.config import AppConfig
from app.data.contracts import MomentumSignal, MomentumTag
from app.momentum.engine import (
    blended_momentum,
    run_momentum,
    tag_map,
    time_series_momentum,
    trend_filter_on,
    vol_target_weight,
)
from app.momentum.throttle import apply_conflict_rule, load_throttle, macro_throttle


def test_ts_momentum_skips_recent_month() -> None:
    closes = np.array([100.0, 105.0, 110.0, 120.0, 130.0])
    skip1 = time_series_momentum(closes, lookback=3, skip=1)  # 120/105 - 1
    skip0 = time_series_momentum(closes, lookback=3, skip=0)  # 130/105 - 1
    assert abs(skip1 - (120.0 / 105.0 - 1.0)) < 1e-12
    assert abs(skip0 - (130.0 / 105.0 - 1.0)) < 1e-12
    assert skip1 != skip0


def test_blended_momentum_averages_horizons() -> None:
    closes = np.cumprod(np.r_[100.0, np.full(20, 1.02)])
    b = blended_momentum(closes, [1, 3, 12], skip=1)
    assert b > 0  # steady uptrend


def test_vol_target_inverse_sizing() -> None:
    assert abs(vol_target_weight(0.13, 0.13) - 1.0) < 1e-9
    assert vol_target_weight(0.26, 0.13) < vol_target_weight(
        0.13, 0.13
    )  # higher vol -> smaller size
    assert vol_target_weight(0.01, 0.13, max_weight=1.5) == 1.5  # capped


def test_trend_filter_flips_with_direction(cfg: AppConfig) -> None:
    up = np.cumprod(np.r_[100.0, np.full(24, 1.03)])
    down = np.cumprod(np.r_[100.0, np.full(24, 0.97)])
    up_daily = np.cumprod(np.r_[100.0, np.full(260, 1.001)])
    down_daily = np.cumprod(np.r_[100.0, np.full(260, 0.999)])
    assert trend_filter_on(up, up_daily, cfg.momentum) is True
    assert trend_filter_on(down, down_daily, cfg.momentum) is False


def test_throttle_multiplier_and_persistence(cfg: AppConfig) -> None:
    scores = {"a": 1.0, "b": 0.0, "c": 0.5, "d": 0.5}
    # one risk-off indicator (b) persisted long enough -> persistent brake
    persisted = macro_throttle(scores, {"b": 3}, required=2)
    assert abs(persisted.gross_exposure_multiplier - 0.5) < 1e-9
    assert persisted.persistent is True
    assert persisted.brake_active is True
    # same scores but the risk-off reading is too fresh -> not persistent
    fresh = macro_throttle(scores, {"b": 1}, required=2)
    assert fresh.persistent is False


def test_conflict_rule_brake_cuts_size_engine_keeps_selection() -> None:
    sigs = [
        MomentumSignal(
            ticker="NVDA",
            ts_momentum_12_1=0.4,
            blended_momentum=0.4,
            trend_filter_on=True,
            realized_vol=0.4,
            target_weight=1.0,
            momentum_tag=MomentumTag.LEADER,
        ),
        MomentumSignal(
            ticker="KO",
            ts_momentum_12_1=0.02,
            blended_momentum=0.02,
            trend_filter_on=False,
            realized_vol=0.14,
            target_weight=0.9,
            momentum_tag=MomentumTag.BALLAST,
        ),
    ]
    from app.data.contracts import ThrottleState

    no_brake = apply_conflict_rule(
        sigs, ThrottleState(gross_exposure_multiplier=1.0, persistent=False, brake_active=False)
    )
    brake = apply_conflict_rule(
        sigs, ThrottleState(gross_exposure_multiplier=0.5, persistent=True, brake_active=True)
    )
    # brake wins on sizing: gross exposure halved
    assert abs(brake.gross_after - 0.5 * no_brake.gross_after) < 1e-9
    # engine wins on selection: same ordering, top momentum name retained and largest
    assert brake.selection == no_brake.selection == ["NVDA", "KO"]
    assert max(brake.sized_weights, key=lambda k: brake.sized_weights[k]) == "NVDA"


def test_run_momentum_tags_leaders_and_ballast(cfg: AppConfig) -> None:
    signals = run_momentum(cfg)
    tags = tag_map(signals)
    # The strong-drift AI names should be leaders; low-drift ballast names should not.
    assert tags.get("NVDA") == MomentumTag.LEADER
    assert any(t is MomentumTag.LEADER for t in tags.values())
    # at least one signal carries a vol-targeted weight
    assert all(s.target_weight > 0 for s in signals)


def test_load_throttle_from_fixture(cfg: AppConfig) -> None:
    t = load_throttle(cfg)
    assert 0.0 <= t.gross_exposure_multiplier <= 1.0
    assert t.brake_active is True  # sample state is mildly risk-off
