"""Schwab live-API parsers, verified against Schwab-shaped sample payloads."""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from app.config import AppConfig
from app.data.contracts import AssetType, OptionRight
from app.data.normalize import normalize_accounts
from app.data.quality import QualityLedger
from app.schwab_client.parse import (
    parse_accounts,
    parse_candles_closes,
    parse_candles_ohlcv,
    parse_option_chain,
    parse_osi,
    parse_quote_last,
)

RAW = Path(__file__).resolve().parent.parent / "fixtures" / "schwab_raw"


def _load(name: str) -> object:
    return json.loads((RAW / name).read_text("utf-8"))


def test_parse_osi() -> None:
    assert parse_osi("NVDA  271217C00200000") == ("NVDA", date(2027, 12, 17), "CALL", 200.0)
    assert parse_osi("KO    260918P00065000") == ("KO", date(2026, 9, 18), "PUT", 65.0)
    assert parse_osi("NVDA") is None


def test_parse_accounts_shapes() -> None:
    out = parse_accounts(_load("accounts.json"), as_of=datetime(2026, 6, 15, 16, 0, 0))
    acct = out["accounts"][0]
    assert acct["account_number"] == "12345678"
    assert acct["reported_total"] == 594000.0
    by = {p["symbol"]: p for p in acct["positions"]}
    assert by["NVDA"]["asset_type"] == "EQUITY" and by["NVDA"]["price"] == 180.0  # mv/(qty*mult)
    assert by["KO"]["asset_type"] == "ETF" and by["KO"]["price"] == 62.0
    opt = by["NVDA  271217C00200000"]
    assert opt["asset_type"] == "OPTION" and opt["underlying"] == "NVDA"
    assert (
        opt["expiration"] == "2027-12-17" and opt["put_call"] == "CALL" and opt["strike"] == 200.0
    )
    assert opt["price"] == 120.0  # 48000 / (4 * 100)


def test_parse_accounts_flows_to_normalize(cfg: AppConfig) -> None:
    raw = parse_accounts(_load("accounts.json"), as_of=datetime(2026, 6, 15, 16, 0, 0))
    accounts, holdings = normalize_accounts(raw, cfg, QualityLedger())
    assert accounts[0].reported_total == Decimal("594000.0")
    nvda = next(h for h in holdings if h.ticker == "NVDA")
    assert nvda.market_value == Decimal("360000.0") and nvda.asset_type is AssetType.EQUITY
    ko = next(h for h in holdings if h.ticker == "KO")
    assert ko.asset_type is AssetType.FUND  # COLLECTIVE_INVESTMENT -> ETF -> FUND
    opt = next(h for h in holdings if h.asset_type is AssetType.OPTION)
    assert opt.underlying == "NVDA" and opt.call_put is OptionRight.CALL
    assert opt.strike == Decimal("200.0") and opt.expiration == date(2027, 12, 17)


def test_parse_quote_last() -> None:
    raw = _load("quotes.json")
    assert parse_quote_last(raw, "NVDA") == 180.05
    assert parse_quote_last(raw, "KO") == 62.0
    assert parse_quote_last(raw, "MISSING") is None


def test_parse_candles() -> None:
    raw = _load("pricehistory.json")
    closes = parse_candles_closes(raw)
    assert list(closes) == [102.0, 108.0, 111.0]
    assert parse_candles_ohlcv(raw) == [(102.0, 1000.0), (108.0, 1200.0), (111.0, 900.0)]


def test_parse_option_chain() -> None:
    out = parse_option_chain(_load("chain.json"))
    row = out["chains"][0]
    assert row["underlying"] == "NVDA" and row["strike"] == 200.0
    assert row["put_call"] == "CALL" and row["expiration"] == "2027-12-17"
    assert row["iv"] == 0.47  # Schwab volatility (47.0%) -> 0.47
    assert row["open_interest"] == 1800 and row["volume"] == 600
