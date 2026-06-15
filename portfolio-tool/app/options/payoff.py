"""Option payoff / structure math (shared by the LEAPS and covered-call engines).

Money stays ``Decimal``; Greeks/IV stay ``float``; conversions are explicit.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.data.contracts import OptionRight
from app.money import Money, to_float, to_money


def mid_price(bid: Money | None, ask: Money | None, last: Money | None = None) -> Money | None:
    if bid is not None and ask is not None:
        return (bid + ask) / 2
    return last


def spread_pct(bid: Money | None, ask: Money | None) -> float | None:
    if bid is None or ask is None:
        return None
    m = (bid + ask) / 2
    if m <= 0:
        return None
    return to_float((ask - bid) / m)


def intrinsic_value(right: OptionRight, underlying: Money, strike: Money) -> Money:
    if right is OptionRight.CALL:
        return max(underlying - strike, Decimal("0"))
    return max(strike - underlying, Decimal("0"))


def extrinsic_value(premium: Money, intrinsic: Money) -> Money:
    return premium - intrinsic


def breakeven(right: OptionRight, strike: Money, premium: Money) -> Money:
    if right is OptionRight.CALL:
        return strike + premium
    return strike - premium


def max_loss_long(premium: Money, contracts: int, multiplier: int = 100) -> Money:
    return premium * Decimal(contracts) * Decimal(multiplier)


def delta_adjusted_notional(
    delta: float, underlying: Money, contracts: int, multiplier: int = 100
) -> Money:
    return to_money(abs(delta)) * underlying * Decimal(contracts) * Decimal(multiplier)


def underlying_for_multiple(
    strike: Money, premium: Money, target_multiple: float, right: OptionRight
) -> Money:
    """Underlying price at expiration for a long option to be worth ``target_multiple`` x premium.

    At expiration the option is pure intrinsic. For a call: strike + target*premium.
    For a put: strike - target*premium.
    """
    move = premium * to_money(target_multiple)
    if right is OptionRight.CALL:
        return strike + move
    return strike - move


def months_to_expiry(expiration: date, as_of: date) -> float:
    return (expiration - as_of).days / 30.4375
