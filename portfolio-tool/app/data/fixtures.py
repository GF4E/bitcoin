"""Deterministic sample market data for mock mode.

Everything here is labeled ``sample_fixture`` and is analogous to the income-
returns CSV: offline, reproducible stand-ins for data that a live read-only
Schwab pull would provide. Engines never hardcode decision-driving figures — they
compute momentum, correlation, and capture *from these series*. Swap in live
pulls and the same math runs on real numbers.

The AI/tech/semi names share a common factor, so their pairwise correlations come
out high (~0.6) and the concentration banner's "effective independent bets" is a
real eigenvalue computation, not a constant.
"""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import date, datetime
from functools import cache
from pathlib import Path

import numpy as np

SAMPLE_DIR = Path(__file__).resolve().parent / "sample_fixtures"

# Sample per-ticker drift/vol (annual) and factor loadings. data_source: sample_fixture.
# AI names load on the shared AI factor (high mutual correlation); ballast does not.
_DEFAULT = {"ret": 0.08, "vol": 0.20, "ai_beta": 0.0, "mkt_beta": 0.6}
_PARAMS: dict[str, dict[str, float]] = {
    "NVDA": {"ret": 0.34, "vol": 0.45, "ai_beta": 1.25, "mkt_beta": 0.5},
    "AVGO": {"ret": 0.30, "vol": 0.40, "ai_beta": 1.15, "mkt_beta": 0.5},
    "SMH": {"ret": 0.28, "vol": 0.35, "ai_beta": 1.20, "mkt_beta": 0.5},
    "SOXX": {"ret": 0.26, "vol": 0.34, "ai_beta": 1.15, "mkt_beta": 0.5},
    "MSFT": {"ret": 0.20, "vol": 0.26, "ai_beta": 0.85, "mkt_beta": 0.6},
    "GOOGL": {"ret": 0.18, "vol": 0.28, "ai_beta": 0.80, "mkt_beta": 0.6},
    "META": {"ret": 0.22, "vol": 0.32, "ai_beta": 0.85, "mkt_beta": 0.6},
    "AMZN": {"ret": 0.17, "vol": 0.30, "ai_beta": 0.70, "mkt_beta": 0.7},
    "TSM": {"ret": 0.24, "vol": 0.33, "ai_beta": 1.05, "mkt_beta": 0.5},
    "ASML": {"ret": 0.21, "vol": 0.34, "ai_beta": 1.00, "mkt_beta": 0.5},
    "MU": {"ret": 0.23, "vol": 0.42, "ai_beta": 1.10, "mkt_beta": 0.5},
    "ANET": {"ret": 0.25, "vol": 0.38, "ai_beta": 1.05, "mkt_beta": 0.5},
    "VRT": {"ret": 0.33, "vol": 0.50, "ai_beta": 1.20, "mkt_beta": 0.5},
    "VST": {"ret": 0.31, "vol": 0.44, "ai_beta": 1.00, "mkt_beta": 0.6},
    "PLTR": {"ret": 0.30, "vol": 0.55, "ai_beta": 1.10, "mkt_beta": 0.6},
    "ARM": {"ret": 0.20, "vol": 0.50, "ai_beta": 1.05, "mkt_beta": 0.5},
    "QQQ": {"ret": 0.14, "vol": 0.20, "ai_beta": 0.55, "mkt_beta": 0.8},
    "QQQM": {"ret": 0.14, "vol": 0.20, "ai_beta": 0.55, "mkt_beta": 0.8},
    "QQQI": {"ret": 0.10, "vol": 0.15, "ai_beta": 0.45, "mkt_beta": 0.7},
    "KO": {"ret": 0.05, "vol": 0.14, "ai_beta": 0.0, "mkt_beta": 0.4},
    "GLD": {"ret": 0.06, "vol": 0.13, "ai_beta": 0.0, "mkt_beta": 0.1},
    "SGOV": {"ret": 0.045, "vol": 0.01, "ai_beta": 0.0, "mkt_beta": 0.0},
    "VOO": {"ret": 0.09, "vol": 0.16, "ai_beta": 0.10, "mkt_beta": 1.0},
}

_ANCHOR_PRICE: dict[str, float] = {
    "NVDA": 180.0,
    "AVGO": 280.0,
    "SMH": 270.0,
    "SOXX": 255.0,
    "MSFT": 460.0,
    "GOOGL": 185.0,
    "META": 720.0,
    "AMZN": 215.0,
    "TSM": 205.0,
    "ASML": 920.0,
    "MU": 130.0,
    "ANET": 110.0,
    "VRT": 115.0,
    "VST": 165.0,
    "PLTR": 145.0,
    "ARM": 175.0,
    "QQQ": 520.0,
    "QQQM": 205.0,
    "QQQI": 52.0,
    "KO": 62.0,
    "GLD": 215.0,
    "SGOV": 100.0,
    "VOO": 500.0,
}


def _seed_for(ticker: str, salt: int) -> int:
    h = hashlib.sha1(f"{ticker}:{salt}".encode()).digest()
    return int.from_bytes(h[:4], "big")


def params(ticker: str) -> dict[str, float]:
    return _PARAMS.get(ticker.upper(), _DEFAULT)


def anchor_price(ticker: str) -> float:
    return _ANCHOR_PRICE.get(ticker.upper(), 100.0)


def monthly_return_panel(
    tickers: list[str], months: int = 26, seed: int = 7
) -> dict[str, np.ndarray]:
    """Correlated monthly total-return series via a 2-factor model (AI + market).

    Deterministic for a given seed. Returns ticker -> array of length ``months``.
    """
    rng = np.random.default_rng(seed)
    ai_factor = rng.normal(0.020, 0.060, months)  # shared AI capex factor (dominant)
    mkt_factor = rng.normal(0.008, 0.030, months)  # broad market factor
    out: dict[str, np.ndarray] = {}
    for t in tickers:
        p = params(t)
        idio_rng = np.random.default_rng(_seed_for(t, seed))
        # Modest idiosyncratic share => the AI names move together (high pairwise
        # correlation, few effective bets) — the concentrated single-factor wager.
        idio_sd = max(p["vol"] / np.sqrt(12.0) * 0.55, 1e-4)
        drift = p["ret"] / 12.0 - 0.5 * (p["vol"] ** 2) / 12.0
        r = (
            drift
            + p["ai_beta"] * (ai_factor - ai_factor.mean())
            + p["mkt_beta"] * (mkt_factor - mkt_factor.mean())
            + idio_rng.normal(0.0, idio_sd, months)
        )
        out[t.upper()] = r
    return out


def monthly_price_bars(ticker: str, months: int = 26, seed: int = 7) -> list[dict[str, object]]:
    """Monthly OHLC-ish bars anchored to the current price. Plain dicts (PriceBar built upstream)."""
    rets = monthly_return_panel([ticker], months=months, seed=seed)[ticker.upper()]
    closes = np.exp(np.cumsum(rets))
    closes = closes / closes[-1] * anchor_price(ticker)
    end = date(2026, 6, 15)
    bars: list[dict[str, object]] = []
    for i, c in enumerate(closes):
        bar_date = _add_months(end, -(len(closes) - 1 - i))
        prev = closes[i - 1] if i > 0 else c
        o = float(prev)
        bars.append(
            {
                "ticker": ticker.upper(),
                "bar_date": bar_date.isoformat(),
                "open": round(o, 4),
                "high": round(max(o, float(c)) * 1.01, 4),
                "low": round(min(o, float(c)) * 0.99, 4),
                "close": round(float(c), 4),
                "volume": 1_000_000,
            }
        )
    return bars


def daily_closes(ticker: str, days: int = 260, seed: int = 7) -> np.ndarray:
    """Deterministic daily close path anchored to the current price (for 200-DMA)."""
    p = params(ticker)
    rng = np.random.default_rng(_seed_for(ticker, seed + 1000))
    drift = p["ret"] / 252.0 - 0.5 * (p["vol"] ** 2) / 252.0
    sd = p["vol"] / np.sqrt(252.0)
    rets = rng.normal(drift, sd, days)
    closes = np.exp(np.cumsum(rets))
    return closes / closes[-1] * anchor_price(ticker)


def intraday_session(ticker: str, n: int = 78, seed: int = 7) -> list[tuple[float, float]]:
    """Intraday (price, volume) tuples for a session VWAP. Slope tracks momentum sign."""
    p = params(ticker)
    rng = np.random.default_rng(_seed_for(ticker, seed + 2000))
    base = anchor_price(ticker)
    trend = 0.0006 if p["ret"] >= 0.12 else -0.0004
    prices = base * (1.0 + np.cumsum(rng.normal(trend, 0.0015, n)))
    prices = prices / prices[-1] * base
    vols = rng.integers(5_000, 25_000, n).astype(float)
    return list(zip(prices.tolist(), vols.tolist(), strict=True))


def _add_months(d: date, delta: int) -> date:
    m = d.month - 1 + delta
    y = d.year + m // 12
    return date(y, m % 12 + 1, min(d.day, 28))


# --------------------------------------------------------------------------- #
# Sample-fixture loaders (JSON/CSV)
# --------------------------------------------------------------------------- #
@cache
def _load_json(name: str) -> dict[str, object]:
    with (SAMPLE_DIR / name).open("r", encoding="utf-8") as fh:
        return json.load(fh)


def load_sample_accounts() -> dict[str, object]:
    return _load_json("schwab_accounts.json")


def load_sample_manual() -> dict[str, object]:
    return _load_json("manual_holdings.json")


def load_sample_quotes() -> dict[str, object]:
    return _load_json("quotes.json")


def load_sample_option_chains() -> dict[str, object]:
    return _load_json("option_chains.json")


def load_income_returns() -> tuple[dict[str, list[float]], str]:
    """Return ({column: monthly returns}, date_range_str) from the sample CSV."""
    path = SAMPLE_DIR / "income_returns.csv"
    cols: dict[str, list[float]] = {}
    months: list[str] = []
    with path.open("r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        fields = [f for f in (reader.fieldnames or []) if f != "month"]
        for f in fields:
            cols[f] = []
        for row in reader:
            months.append(row["month"])
            for f in fields:
                cols[f].append(float(row[f]))
    date_range = f"{months[0]}..{months[-1]}" if months else "n/a"
    return cols, date_range


def now_as_of() -> datetime:
    return datetime(2026, 6, 15, 16, 0, 0)
