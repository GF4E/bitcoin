"""Market-data provider abstraction.

Engines read market data (quotes, option chains, monthly/daily/intraday price
series, income-fund returns) through a ``MarketData`` provider rather than calling
fixtures directly. ``MockMarketData`` reproduces the sample-fixture behavior exactly
(so mock output stays byte-identical and deterministic); ``LiveMarketData`` routes
the same calls through the read-only Schwab client + parsers.

Macro-throttle indicators (Brent, VIX, Hormuz, …) are NOT Schwab data and stay a
manual source (``app/momentum/throttle.py``), so they are not part of this provider.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

import numpy as np

from app.config import AppConfig
from app.data import fixtures
from app.money import Money, to_money

if TYPE_CHECKING:  # pragma: no cover
    from app.schwab_client.client import SchwabClient


@runtime_checkable
class MarketData(Protocol):
    def monthly_closes(self, ticker: str, months: int = 26) -> np.ndarray: ...
    def daily_closes(self, ticker: str, days: int = 260) -> np.ndarray: ...
    def intraday(self, ticker: str) -> list[tuple[float, float]]: ...
    def monthly_returns(self, tickers: list[str], months: int = 26) -> dict[str, np.ndarray]: ...
    def quote_last(self, ticker: str) -> Money | None: ...
    def raw_option_chain(self, underlyings: set[str] | None = None) -> dict[str, Any]: ...
    def income_return_series(self) -> tuple[dict[str, list[float]], str]: ...


class MockMarketData:
    """Sample-fixture provider — exact reproduction of prior direct-fixture behavior."""

    def __init__(self, cfg: AppConfig, seed: int | None = None) -> None:
        self.cfg = cfg
        self._seed = cfg.trajectory.seed if seed is None else seed

    def monthly_closes(self, ticker: str, months: int = 26) -> np.ndarray:
        bars = fixtures.monthly_price_bars(ticker, months=months, seed=self._seed)
        return np.array([float(b["close"]) for b in bars], dtype=float)

    def daily_closes(self, ticker: str, days: int = 260) -> np.ndarray:
        return fixtures.daily_closes(ticker, days=days, seed=self._seed)

    def intraday(self, ticker: str) -> list[tuple[float, float]]:
        return fixtures.intraday_session(ticker, seed=self._seed)

    def monthly_returns(self, tickers: list[str], months: int = 26) -> dict[str, np.ndarray]:
        return fixtures.monthly_return_panel(tickers, months=months, seed=self._seed)

    def quote_last(self, ticker: str) -> Money | None:
        for q in fixtures.load_sample_quotes().get("quotes", []):
            if q["ticker"] == ticker and q.get("last") is not None:
                return to_money(q["last"])
        return None

    def raw_option_chain(self, underlyings: set[str] | None = None) -> dict[str, Any]:
        return fixtures.load_sample_option_chains()

    def income_return_series(self) -> tuple[dict[str, list[float]], str]:
        return fixtures.load_income_returns()


def _closes_to_returns(closes: np.ndarray) -> np.ndarray:
    if closes.size < 2:
        return np.zeros(0)
    return closes[1:] / closes[:-1] - 1.0


class LiveMarketData:  # pragma: no cover - requires live credentials
    """Read-only Schwab provider. Implemented against Schwab's documented API and
    verified only at the parser level; confirm against the live API with real tokens."""

    def __init__(self, cfg: AppConfig, client: SchwabClient) -> None:
        self.cfg = cfg
        self.client = client

    def monthly_closes(self, ticker: str, months: int = 26) -> np.ndarray:
        from app.schwab_client.parse import parse_candles_closes

        raw = self.client.get_price_history(ticker, frequency_type="monthly")
        return parse_candles_closes(raw)[-months:]

    def daily_closes(self, ticker: str, days: int = 260) -> np.ndarray:
        from app.schwab_client.parse import parse_candles_closes

        raw = self.client.get_price_history(ticker, frequency_type="daily")
        return parse_candles_closes(raw)[-days:]

    def intraday(self, ticker: str) -> list[tuple[float, float]]:
        from app.schwab_client.parse import parse_candles_ohlcv

        raw = self.client.get_price_history(
            ticker, period_type="day", frequency_type="minute", frequency=5
        )
        return parse_candles_ohlcv(raw)

    def monthly_returns(self, tickers: list[str], months: int = 26) -> dict[str, np.ndarray]:
        out: dict[str, np.ndarray] = {}
        for t in tickers:
            out[t.upper()] = _closes_to_returns(self.monthly_closes(t, months=months + 1))
        return out

    def quote_last(self, ticker: str) -> Money | None:
        from app.schwab_client.parse import parse_quote_last

        last = parse_quote_last(self.client.get_quotes([ticker]), ticker)
        return to_money(last) if last is not None else None

    def raw_option_chain(self, underlyings: set[str] | None = None) -> dict[str, Any]:
        from app.schwab_client.parse import parse_option_chain

        chains: list[dict[str, Any]] = []
        for u in sorted(underlyings or set()):
            chains.extend(parse_option_chain(self.client.get_option_chain(u)).get("chains", []))
        return {"chains": chains}

    def income_return_series(self) -> tuple[dict[str, list[float]], str]:
        isc = self.cfg.income_sleeve
        cols: dict[str, list[float]] = {}
        rng = "live"
        for sym in (isc.underlying_index, isc.capped_fund, isc.peer_fallback_fund):
            cols[sym] = _closes_to_returns(self.monthly_closes(sym, months=120)).tolist()
        return cols, rng


def make_market_data(cfg: AppConfig, seed: int | None = None) -> MarketData:
    if cfg.settings.mode == "live_readonly":  # pragma: no cover - requires credentials
        from app.schwab_client.client import SchwabClient

        return LiveMarketData(cfg, SchwabClient.from_config(cfg))
    return MockMarketData(cfg, seed=seed)
