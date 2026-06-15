"""Concentration banner — shown at the top of every trajectory run.

The tool must never let the user forget the book is a concentrated single-factor
wager being *monitored*, not diversified away. We compute, from a realized (here:
sample) monthly return panel of the AI/tech/semi risk sleeve:

- AI/tech/semi exposure as a fraction of ``net_worth_total`` (correction #1 denom),
- the value-weighted average pairwise correlation of the risk sleeve,
- effective independent bets via Meucci's PCA entropy ``exp(-Σ pᵢ ln pᵢ)`` over the
  normalized eigenvalues of the correlation matrix.

These are computed, not asserted — change the series and the numbers move.
"""

from __future__ import annotations

import numpy as np

from app.config import AppConfig
from app.data.contracts import ConcentrationBanner, Holding
from app.data.market_data import MarketData, make_market_data
from app.money import ZERO, msum, pct_of


def _risk_sleeve_tickers(holdings: list[Holding], cfg: AppConfig) -> list[tuple[str, float]]:
    """Return (ticker, market_value) for AI/tech/semi holdings, de-duplicated by ticker."""
    weights: dict[str, float] = {}
    for h in holdings:
        key = (h.underlying or h.ticker) if h.asset_type.value == "option" else h.ticker
        if not cfg.is_ai_tech_semi(key):
            continue
        mv = float(h.market_value) if h.market_value is not None else 0.0
        weights[key] = weights.get(key, 0.0) + abs(mv)
    return [(t, w) for t, w in weights.items() if w > 0]


def weighted_avg_pairwise_correlation(corr: np.ndarray, weights: np.ndarray) -> float:
    n = corr.shape[0]
    if n < 2:
        return 1.0
    num = 0.0
    den = 0.0
    for i in range(n):
        for j in range(i + 1, n):
            w = weights[i] * weights[j]
            num += w * corr[i, j]
            den += w
    return float(num / den) if den > 0 else 0.0


def effective_independent_bets(corr: np.ndarray) -> float:
    """Meucci effective number of bets: exp(entropy of normalized eigenvalues)."""
    n = corr.shape[0]
    if n < 2:
        return float(n)
    eig = np.linalg.eigvalsh(corr)
    eig = np.clip(eig, 1e-12, None)
    p = eig / eig.sum()
    entropy = -float(np.sum(p * np.log(p)))
    return float(np.exp(entropy))


def compute_concentration(
    holdings: list[Holding],
    cfg: AppConfig,
    seed: int | None = None,
    market: MarketData | None = None,
) -> ConcentrationBanner:
    market = market or make_market_data(cfg, seed=seed)
    net_worth = cfg.risk_budget.net_worth_total
    ai_value = msum(
        h.market_value
        for h in holdings
        if h.market_value is not None
        and cfg.is_ai_tech_semi(
            (h.underlying or h.ticker) if h.asset_type.value == "option" else h.ticker
        )
    )
    ai_pct = pct_of(ai_value if ai_value != ZERO else ZERO, net_worth)

    sleeve = _risk_sleeve_tickers(holdings, cfg)
    threshold = cfg.risk_budget.ai_concentration_flag_pct
    if len(sleeve) < 2:
        return ConcentrationBanner(
            ai_tech_semi_pct=ai_pct,
            weighted_avg_correlation=1.0 if sleeve else 0.0,
            effective_independent_bets=float(len(sleeve)),
            flagged=ai_pct > threshold,
            flag_threshold_pct=threshold,
        )

    tickers = [t for t, _ in sleeve]
    weights = np.array([w for _, w in sleeve], dtype=float)
    weights = weights / weights.sum()
    panel = market.monthly_returns(tickers, months=26)
    matrix = np.vstack([panel[t.upper()] for t in tickers])
    corr = np.corrcoef(matrix)

    return ConcentrationBanner(
        ai_tech_semi_pct=ai_pct,
        weighted_avg_correlation=weighted_avg_pairwise_correlation(corr, weights),
        effective_independent_bets=effective_independent_bets(corr),
        flagged=ai_pct > threshold,
        flag_threshold_pct=threshold,
    )
