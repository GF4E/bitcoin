"""Schema validation rules (data contracts)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.data.contracts import (
    AssetType,
    Holding,
    OptionChainRow,
    OptionHolding,
    OptionRight,
)

_AS_OF = datetime(2026, 6, 15, 16, 0, 0)


def _equity(**kw: object) -> Holding:
    base: dict[str, object] = {
        "account_id": "A1",
        "account_name": "Taxable",
        "masked_account_id": "****1234",
        "ticker": "NVDA",
        "name": "NVIDIA",
        "asset_type": AssetType.EQUITY,
        "quantity": Decimal("100"),
        "price": Decimal("180"),
        "as_of_datetime": _AS_OF,
    }
    base.update(kw)
    return Holding(**base)


def test_negative_price_rejected() -> None:
    with pytest.raises(ValidationError):
        _equity(price=Decimal("-1"))


def test_money_field_parses_float_without_noise() -> None:
    h = _equity(price=0.1, market_value=0.3)
    assert h.price == Decimal("0.1")
    assert h.market_value == Decimal("0.3")


def test_option_requires_call_put() -> None:
    with pytest.raises(ValidationError):
        OptionHolding(
            account_id="A1",
            account_name="Taxable",
            masked_account_id="****1234",
            ticker="NVDA 2027-12-17 C200",
            name="opt",
            asset_type=AssetType.OPTION,
            quantity=Decimal("1"),
            as_of_datetime=_AS_OF,
            underlying="NVDA",
            expiration=date(2027, 12, 17),
            strike=Decimal("200"),
        )


def test_short_option_negative_market_value_allowed() -> None:
    h = OptionHolding(
        account_id="A1",
        account_name="Taxable",
        masked_account_id="****1234",
        ticker="KO 2026-09-18 C65",
        name="opt",
        asset_type=AssetType.OPTION,
        quantity=Decimal("-10"),
        price=Decimal("0.80"),
        market_value=Decimal("-800"),
        as_of_datetime=_AS_OF,
        underlying="KO",
        expiration=date(2026, 9, 18),
        strike=Decimal("65"),
        call_put=OptionRight.CALL,
    )
    assert h.market_value == Decimal("-800")
    assert h.price == Decimal("0.80")


def test_option_chain_bid_le_ask() -> None:
    with pytest.raises(ValidationError):
        OptionChainRow(
            underlying="NVDA",
            expiration=date(2027, 12, 17),
            strike=Decimal("200"),
            call_put=OptionRight.CALL,
            bid=Decimal("5"),
            ask=Decimal("4"),
        )
