"""The Decimal/float boundary must not leak binary-float noise."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.money import msum, pct_of, round_money, to_float, to_money


def test_float_routed_through_str_no_binary_noise() -> None:
    assert to_money(0.1) + to_money(0.2) == Decimal("0.3")
    assert to_money(0.1) == Decimal("0.1")


def test_money_string_cleaning() -> None:
    assert to_money("$1,234.56") == Decimal("1234.56")


def test_round_money_banker_rounding() -> None:
    assert round_money(Decimal("2.345")) == Decimal("2.34")  # round-half-even
    assert round_money(Decimal("2.355")) == Decimal("2.36")


def test_reject_bool_and_junk() -> None:
    with pytest.raises(ValueError):
        to_money(True)
    with pytest.raises(ValueError):
        to_money("not-a-number")


def test_msum_preserves_decimal() -> None:
    total = msum([Decimal("0.1"), Decimal("0.2"), Decimal("0.3")])
    assert total == Decimal("0.6")
    assert isinstance(total, Decimal)


def test_pct_of_crosses_boundary_to_float() -> None:
    frac = pct_of(Decimal("1000"), Decimal("4000"))
    assert isinstance(frac, float)
    assert frac == 0.25
    assert pct_of(Decimal("5"), Decimal("0")) == 0.0  # empty denominator guarded


def test_to_float_is_explicit() -> None:
    assert to_float(Decimal("3.5")) == 3.5
