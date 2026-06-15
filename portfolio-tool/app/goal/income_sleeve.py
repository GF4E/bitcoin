"""Income-sleeve comparison (Approach A capped-income vs Approach B uncapped+buffer).

The income approach is an OPEN QUESTION re-tested every run, not a baked-in
conclusion. Capture ratios are DERIVED empirically by regressing a realized
monthly total-return series (here a labeled sample fixture; live mode pulls real
NAV+distributions) on the underlying index — never hardcoded. If the capped
fund's history is too short (QQQI <3yr), we widen to the longest-record peer
(QYLD) for the capped bound and say so.

Approach A: a QQQI-style covered-call income sleeve; distributions reinvest-until-
drawn (modeled as a capped total return). Approach B: a QQQM-equivalent full-upside
core plus a 12-24 month T-bill/SGOV buffer sized to the gap, selling index for the
gap. Both run under IDENTICAL index paths; the user arbitrates — the tool reports
the dollar terminal-wealth delta and the regime dependence.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.config import AppConfig
from app.data.contracts import (
    Assumption,
    DataLabel,
    DataQualityWarning,
    IncomeSleeveComparison,
    Severity,
)
from app.data.market_data import MarketData, make_market_data
from app.money import round_money, to_money


@dataclass(frozen=True)
class CaptureEstimate:
    up_capture: float
    down_capture: float
    n_months: int
    source: str
    date_range: str
    peer_substituted: bool
    fund_short_sample: dict[str, float] | None = None


def derive_capture(fund: np.ndarray, index: np.ndarray) -> tuple[float, float]:
    """Up/down capture as the ratio of cumulative fund-to-index return in up/down
    index months. Reproducible from the series — no constant baked in."""
    up = index >= 0
    dn = ~up
    up_cap = float(fund[up].sum() / index[up].sum()) if index[up].sum() != 0 else 1.0
    dn_cap = float(fund[dn].sum() / index[dn].sum()) if index[dn].sum() != 0 else 1.0
    return up_cap, dn_cap


def estimate_capture(cfg: AppConfig, market: MarketData | None = None) -> CaptureEstimate:
    market = market or make_market_data(cfg)
    cols, date_range = market.income_return_series()
    isc = cfg.income_sleeve
    index = np.array(cols[isc.underlying_index], dtype=float)
    n = len(index)
    fund_short = None
    if isc.capped_fund in cols:
        fu, fd = derive_capture(np.array(cols[isc.capped_fund], dtype=float), index)
        fund_short = {"up": fu, "down": fd}

    if n < isc.min_series_months_for_direct and isc.peer_fallback_fund in cols:
        series = np.array(cols[isc.peer_fallback_fund], dtype=float)
        source = isc.peer_fallback_fund
        peer = True
    else:
        series = np.array(cols[isc.capped_fund], dtype=float)
        source = isc.capped_fund
        peer = False
    up_cap, dn_cap = derive_capture(series, index)
    return CaptureEstimate(
        up_capture=up_cap,
        down_capture=dn_cap,
        n_months=n,
        source=source,
        date_range=date_range,
        peer_substituted=peer,
        fund_short_sample=fund_short if peer else None,
    )


@dataclass(frozen=True)
class IncomeSimResult:
    delta: np.ndarray  # Approach A minus Approach B, per path
    a_terminal: np.ndarray
    b_terminal: np.ndarray
    roc_constructive_share: float
    a_win_share: float


def compare_approaches(
    *,
    start_wealth: float,
    horizon_months: int,
    index_mu: float,
    index_vol: float,
    up_capture: float,
    down_capture: float,
    monthly_gap: float,
    buffer_months: int,
    safe_annual: float,
    roc_window: int,
    n_paths: int,
    seed: int,
    randomize: bool = False,
) -> IncomeSimResult:
    rng = np.random.default_rng(None if randomize else seed)
    h, n = horizon_months, n_paths
    mu = index_mu / 12.0 - 0.5 * index_vol**2 / 12.0
    sd = index_vol / np.sqrt(12.0)
    r_idx = mu + sd * rng.standard_normal((h, n))

    # Approach A: capped total return; distributions reinvest-until-drawn.
    r_a = np.where(r_idx >= 0, up_capture * r_idx, down_capture * r_idx)
    wa = np.full(n, start_wealth, dtype=float)

    # Approach B: full-upside equity + a T-bill buffer sized to the gap.
    safe_m = safe_annual / 12.0
    buffer0 = float(buffer_months) * monthly_gap
    w_eq = np.full(n, start_wealth - buffer0, dtype=float)
    w_buf = np.full(n, buffer0, dtype=float)

    for t in range(h):
        wa = wa * (1.0 + r_a[t]) - monthly_gap
        w_buf = w_buf * (1.0 + safe_m)
        w_eq = w_eq * (1.0 + r_idx[t])
        from_buf = np.minimum(np.maximum(w_buf, 0.0), monthly_gap)
        w_buf = w_buf - from_buf
        w_eq = w_eq - (monthly_gap - from_buf)
    wb = w_eq + w_buf

    # ROC regime flag: share of (path, month) windows where the trailing index
    # return is non-negative (constructive) vs negative (distributions eroding NAV).
    if h > roc_window:
        cum = np.cumprod(1.0 + r_idx, axis=0)
        trailing = cum[roc_window:] / cum[:-roc_window] - 1.0
        roc_share = float((trailing >= 0).mean())
    else:
        roc_share = float((r_idx >= 0).mean())

    delta = wa - wb
    return IncomeSimResult(
        delta=delta,
        a_terminal=wa,
        b_terminal=wb,
        roc_constructive_share=roc_share,
        a_win_share=float((delta > 0).mean()),
    )


def build_income_comparison(
    cfg: AppConfig, market: MarketData | None = None
) -> IncomeSleeveComparison:
    cap = estimate_capture(cfg, market)
    gp = cfg.goal_plan
    t = cfg.trajectory
    isc = cfg.income_sleeve
    sim = compare_approaches(
        start_wealth=float(gp.net_worth_total),
        horizon_months=t.horizon_months,
        index_mu=gp.expected_return_annual,
        index_vol=gp.volatility_annual,
        up_capture=cap.up_capture,
        down_capture=cap.down_capture,
        monthly_gap=float(gp.monthly_gap),
        buffer_months=isc.buffer_months,
        safe_annual=t.safe_annual,
        roc_window=isc.roc_trailing_window_months,
        n_paths=t.n_paths,
        seed=t.seed,
        randomize=t.randomize_seed,
    )

    constructive = sim.roc_constructive_share >= 0.5
    regime_note = (
        f"Approach A (capped income) wins in flat/choppy/bear Nasdaq; Approach B "
        f"(uncapped + buffer) wins in sustained bull. In this sample's modeled paths, "
        f"A finishes ahead on {sim.a_win_share:.0%} of paths. ROC is "
        f"{'mostly CONSTRUCTIVE' if constructive else 'frequently DESTRUCTIVE'} "
        f"({sim.roc_constructive_share:.0%} of trailing windows non-negative): the QQQI "
        f"tax advantage is conditional on the bull case."
    )

    warnings: list[DataQualityWarning] = []
    if cap.peer_substituted:
        warnings.append(
            DataQualityWarning(
                code="capture_peer_substituted",
                message=(
                    f"{isc.capped_fund} history is {cap.n_months}mo (<"
                    f"{isc.min_series_months_for_direct}); capture derived from peer "
                    f"{isc.peer_fallback_fund} as the capped bound."
                ),
                severity=Severity.WARN,
                label=DataLabel.ESTIMATED,
            )
        )

    assumptions = [
        Assumption(
            name="up_down_capture",
            value=f"up={cap.up_capture:.3f} down={cap.down_capture:.3f}",
            label=DataLabel.ESTIMATED,
            load_bearing=True,
            rationale=f"Regressed from realized {cap.source} vs {isc.underlying_index} returns "
            f"({cap.date_range}); never hardcoded.",
        ),
        Assumption(
            name="buffer_months",
            value=str(isc.buffer_months),
            label=DataLabel.ASSUMED,
            rationale="Approach B T-bill/SGOV buffer sized against the monthly gap.",
        ),
    ]

    return IncomeSleeveComparison(
        delta_terminal_p10=round_money(to_money(float(np.percentile(sim.delta, 10)))),
        delta_terminal_p50=round_money(to_money(float(np.percentile(sim.delta, 50)))),
        delta_terminal_p90=round_money(to_money(float(np.percentile(sim.delta, 90)))),
        up_capture=cap.up_capture,
        down_capture=cap.down_capture,
        capture_source=f"realized monthly total returns: {cap.source} vs {isc.underlying_index}",
        capture_date_range=cap.date_range,
        peer_substituted=cap.peer_substituted,
        buffer_months=isc.buffer_months,
        roc_constructive_share=sim.roc_constructive_share,
        regime_note=regime_note,
        assumptions=assumptions,
        warnings=warnings,
    )
