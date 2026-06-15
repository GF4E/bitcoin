"""The Decimal/float boundary (critical correction #3).

Money is ``Decimal``: prices, market value, cost basis, premium, P/L, withdrawals,
budgets. Statistical quantities are ``float``: Greeks, IV, VWAP, z-scores,
probabilities, Monte Carlo draws. Conversions across the boundary are **explicit**
via :func:`to_money` / :func:`to_float`; money is rounded only at emit time with
:func:`round_money`. See ``docs/calculations.md``.
"""

from __future__ import annotations

from collections.abc import Iterable
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from typing import TypeAlias

# A money value. Kept as a thin alias so call sites read as intent, not mechanism.
Money: TypeAlias = Decimal

CENTS = Decimal("0.01")
ZERO: Money = Decimal("0")


def to_money(value: object) -> Money:
    """Convert a scalar to ``Decimal`` money at the boundary.

    Floats are routed through ``str`` so we never inherit binary-float noise
    (``Decimal(0.1)`` != ``Decimal("0.1")``). Raises ``ValueError`` on junk rather
    than silently coercing — missing critical fields must surface, never become 0.
    """
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):  # bool is an int subclass; reject to avoid surprises
        raise ValueError(f"refusing to treat bool as money: {value!r}")
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, str):
        try:
            return Decimal(value.strip().replace(",", "").replace("$", ""))
        except InvalidOperation as exc:
            raise ValueError(f"not a money string: {value!r}") from exc
    raise ValueError(f"cannot convert {type(value).__name__} to money: {value!r}")


def to_float(value: Money | float | int) -> float:
    """Convert money (or a numeric) to ``float`` for statistical math.

    Use only when crossing into Greeks/IV/VWAP/Monte-Carlo territory.
    """
    return float(value)


def round_money(value: Money, quantum: Decimal = CENTS) -> Money:
    """Round at emit time using banker's rounding (round-half-even)."""
    return to_money(value).quantize(quantum, rounding=ROUND_HALF_EVEN)


def msum(values: Iterable[Money]) -> Money:
    """Sum money values, preserving Decimal exactness (``sum`` would seed with int 0)."""
    total: Money = ZERO
    for v in values:
        total += v
    return total


def pct_of(part: Money, whole: Money) -> float:
    """Return ``part/whole`` as a float fraction (e.g. concentration weight).

    Crosses the boundary deliberately: a ratio is a statistic, not money. Returns
    ``0.0`` when the denominator is zero (callers flag empty denominators upstream).
    """
    if whole == ZERO:
        return 0.0
    return to_float(part) / to_float(whole)
