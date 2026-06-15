"""VWAP overlay — execution timing ONLY, never conviction.

Per underlying: session VWAP, price-vs-VWAP, slope, above-VWAP time, distance
z-score, volume-vs-average, and anchored VWAPs. VWAP_STATUS defaults to
``no_signal`` when data is missing. Applied only after thesis/fit/math pass. No
option VWAP for illiquid contracts (we use bid/ask/OI/vol/mid/IV/delta instead).
"""

from __future__ import annotations

import numpy as np

from app.config import AppConfig
from app.data.contracts import ExecutionSignal, VWAPFeatures, VWAPStatus
from app.data.fixtures import intraday_session
from app.money import to_money


def _running_vwap(prices: np.ndarray, volumes: np.ndarray) -> np.ndarray:
    cum_pv = np.cumsum(prices * volumes)
    cum_v = np.cumsum(volumes)
    return cum_pv / np.maximum(cum_v, 1e-9)


def compute_vwap_features(ticker: str, session: list[tuple[float, float]]) -> VWAPFeatures:
    if len(session) < 3:
        return VWAPFeatures(ticker=ticker, status=VWAPStatus.NO_SIGNAL)
    prices = np.array([p for p, _ in session], dtype=float)
    volumes = np.array([v for _, v in session], dtype=float)
    running = _running_vwap(prices, volumes)
    session_vwap = float(running[-1])
    last = float(prices[-1])
    pvp = (last - session_vwap) / session_vwap
    slope = float(running[-1] - running[len(running) // 2])
    above_pct = float((prices > running).mean())
    zscore = float((last - session_vwap) / (np.std(prices) + 1e-9))
    vol_vs_avg = float(volumes[-1] / (volumes.mean() + 1e-9))
    # anchored VWAPs from a couple of reference points (swing low / session open).
    anchored = {
        "session_open": float(np.sum(prices * volumes) / np.sum(volumes)),
        "swing_low": float(
            np.sum(prices[int(np.argmin(prices)) :] * volumes[int(np.argmin(prices)) :])
            / np.maximum(np.sum(volumes[int(np.argmin(prices)) :]), 1e-9)
        ),
    }
    status = classify_status(pvp, slope, zscore, above_pct)
    return VWAPFeatures(
        ticker=ticker,
        session_vwap=to_money(round(session_vwap, 4)),
        price_vs_vwap_pct=pvp,
        slope=slope,
        above_vwap_minutes_pct=above_pct,
        distance_zscore=zscore,
        volume_vs_avg=vol_vs_avg,
        anchored_vwaps=anchored,
        status=status,
    )


def classify_status(pvp: float, slope: float, zscore: float, above_pct: float) -> VWAPStatus:
    if zscore > 1.5 and pvp > 0.01:
        return VWAPStatus.EXTENDED_DO_NOT_CHASE
    if pvp >= 0 and slope >= 0 and above_pct >= 0.5:
        return VWAPStatus.CLEAN_ENTRY if abs(pvp) < 0.005 else VWAPStatus.SELL_PREMIUM_WINDOW
    if -0.005 <= pvp < 0.005:
        return VWAPStatus.ACCEPTABLE_ENTRY
    if pvp < 0 and slope < 0:
        return VWAPStatus.BUYBACK_WINDOW
    return VWAPStatus.WEAK_WAIT


def vwap_signal(cfg: AppConfig, ticker: str) -> ExecutionSignal:
    feats = compute_vwap_features(ticker, intraday_session(ticker, seed=cfg.trajectory.seed))
    rationale = (
        f"price_vs_vwap {feats.price_vs_vwap_pct:.2%}, slope {feats.slope:+.3f}, "
        f"above-VWAP {feats.above_vwap_minutes_pct:.0%}"
        if feats.status is not VWAPStatus.NO_SIGNAL
        else "insufficient intraday data"
    )
    return ExecutionSignal(
        ticker=ticker, status=feats.status, rationale=rationale, timing_only=True
    )
