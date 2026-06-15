"""MockMarketData must reproduce the direct-fixture behavior exactly (determinism)."""

from __future__ import annotations

import numpy as np

from app.config import AppConfig
from app.data import fixtures
from app.data.market_data import MockMarketData, make_market_data


def test_make_market_data_mock_by_default(cfg: AppConfig) -> None:
    assert isinstance(make_market_data(cfg), MockMarketData)


def test_monthly_and_daily_closes_match_fixtures(cfg: AppConfig) -> None:
    m = MockMarketData(cfg)
    seed = cfg.trajectory.seed
    expected_monthly = np.array(
        [float(b["close"]) for b in fixtures.monthly_price_bars("NVDA", months=26, seed=seed)]
    )
    assert np.array_equal(m.monthly_closes("NVDA", months=26), expected_monthly)
    assert np.array_equal(
        m.daily_closes("SMH", days=220), fixtures.daily_closes("SMH", days=220, seed=seed)
    )


def test_intraday_and_returns_match_fixtures(cfg: AppConfig) -> None:
    m = MockMarketData(cfg)
    seed = cfg.trajectory.seed
    assert m.intraday("NVDA") == fixtures.intraday_session("NVDA", seed=seed)
    panel = m.monthly_returns(["NVDA", "AVGO"], months=26)
    expected = fixtures.monthly_return_panel(["NVDA", "AVGO"], months=26, seed=seed)
    assert np.array_equal(panel["NVDA"], expected["NVDA"])


def test_quotes_chains_income_match_fixtures(cfg: AppConfig) -> None:
    m = MockMarketData(cfg)
    from decimal import Decimal

    assert m.quote_last("NVDA") == Decimal("180.00")
    assert m.quote_last("NOPE") is None
    assert m.raw_option_chain() == fixtures.load_sample_option_chains()
    assert m.income_return_series() == fixtures.load_income_returns()
