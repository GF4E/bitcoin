"""Momentum engine — direction/selection.

Generalized and vol-targeted: 12-1 time-series momentum (skip the most recent
month), a blended-horizon option to reduce single-parameter fragility, an
absolute-momentum trend filter (the crash protection), inverse-vol position sizing
scaled to a portfolio vol target, and cross-sectional ranking to get *paid* for
concentration. No ticker logic lives here — the universe comes from config.
"""

from __future__ import annotations

import numpy as np

from app.config import AppConfig, MomentumConfig
from app.data.contracts import MomentumSignal, MomentumTag
from app.data.market_data import MarketData, make_market_data


def time_series_momentum(closes: np.ndarray, lookback: int, skip: int) -> float:
    """12-1 style: return from t-lookback to t-skip (excludes the most recent month)."""
    if len(closes) <= lookback:
        return 0.0
    end = closes[-1 - skip] if skip > 0 else closes[-1]
    start = closes[-1 - lookback]
    return float(end / start - 1.0)


def blended_momentum(closes: np.ndarray, horizons: list[int], skip: int) -> float:
    vals = [time_series_momentum(closes, h, skip) for h in horizons if len(closes) > h]
    return float(np.mean(vals)) if vals else 0.0


def realized_vol(closes: np.ndarray) -> float:
    if len(closes) < 3:
        return 0.0
    rets = np.diff(closes) / closes[:-1]
    return float(np.std(rets, ddof=1) * np.sqrt(12.0))


def trend_filter_on(closes: np.ndarray, daily: np.ndarray, mom_cfg: MomentumConfig) -> bool:
    """Absolute-momentum trend filter: 12m excess return over T-bills AND price>200DMA."""
    excess = time_series_momentum(closes, mom_cfg.lookback_months, 0) - mom_cfg.tbill_annual
    above_sma = True
    if len(daily) >= mom_cfg.trend_filter_sma_days:
        sma = float(np.mean(daily[-mom_cfg.trend_filter_sma_days :]))
        above_sma = float(daily[-1]) >= sma
    use_excess = excess > 0 if mom_cfg.trend_filter_use_tbill_excess else True
    return bool(use_excess and above_sma)


def vol_target_weight(rvol: float, vol_target: float, max_weight: float = 1.5) -> float:
    """Inverse-to-realized-vol sizing scaled to the portfolio vol target."""
    if rvol <= 1e-6:
        return max_weight
    return float(min(vol_target / rvol, max_weight))


def run_momentum(cfg: AppConfig) -> list[MomentumSignal]:
    universe = cfg.watchlists.get("momentum_universe", []) or _default_universe(cfg)
    return compute_signals(cfg, universe)


def compute_signals(
    cfg: AppConfig, universe: list[str], market: MarketData | None = None
) -> list[MomentumSignal]:
    """Momentum signals + leader/ballast tags for an arbitrary ticker list."""
    mom = cfg.momentum
    if not universe:
        return []
    market = market or make_market_data(cfg)

    raw: dict[str, dict[str, float]] = {}
    for ticker in universe:
        closes = market.monthly_closes(ticker, months=26)
        daily = market.daily_closes(ticker, days=max(mom.trend_filter_sma_days + 20, 220))
        ts = time_series_momentum(closes, mom.lookback_months, mom.skip_months)
        ts_prev = time_series_momentum(closes[:-1], mom.lookback_months, mom.skip_months)
        raw[ticker] = {
            "ts": ts,
            "blended": blended_momentum(closes, mom.blend_horizons, mom.skip_months)
            if mom.use_blended
            else ts,
            "rvol": realized_vol(closes),
            "trend": float(trend_filter_on(closes, daily, mom)),
            "persistent": float(ts > mom_threshold(cfg) and ts_prev > mom_threshold(cfg)),
        }

    # cross-sectional ranking (1 = strongest blended momentum)
    order = sorted(raw, key=lambda t: raw[t]["blended"], reverse=True)
    ranks = {t: i + 1 for i, t in enumerate(order)}

    lead_thr = float(cfg.decision_thresholds.get("momentum", {}).get("leader_threshold", 0.15))
    ball_thr = float(cfg.decision_thresholds.get("momentum", {}).get("ballast_threshold", 0.05))
    signals: list[MomentumSignal] = []
    for ticker in universe:
        r = raw[ticker]
        tag = _tag(r, lead_thr, ball_thr)
        signals.append(
            MomentumSignal(
                ticker=ticker,
                ts_momentum_12_1=r["ts"],
                blended_momentum=r["blended"],
                cross_sectional_rank=ranks[ticker],
                trend_filter_on=bool(r["trend"]),
                realized_vol=r["rvol"],
                target_weight=vol_target_weight(r["rvol"], mom.vol_target_annual),
                momentum_tag=tag,
                persistent_breach=bool(r["persistent"]),
            )
        )
    return signals


def mom_threshold(cfg: AppConfig) -> float:
    return float(cfg.decision_thresholds.get("momentum", {}).get("breach_threshold", 0.0))


def _tag(r: dict[str, float], leader_threshold: float, ballast_threshold: float) -> MomentumTag:
    """Absolute leader/ballast tag (drives covered-call protection): a leader is a
    clear winner (strong positive momentum + positive trend) you let run; ballast is
    flat/weak or trend-off — the kind you would accept being called away."""
    if r["trend"] and r["ts"] > leader_threshold:
        return MomentumTag.LEADER
    if (not r["trend"]) or r["ts"] <= ballast_threshold:
        return MomentumTag.BALLAST
    return MomentumTag.NEUTRAL


def _default_universe(cfg: AppConfig) -> list[str]:
    return sorted(cfg.sleeve_classifications.keys())


def tag_map(signals: list[MomentumSignal]) -> dict[str, MomentumTag]:
    return {s.ticker: s.momentum_tag for s in signals}
