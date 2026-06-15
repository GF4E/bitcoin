# Calculations & the Decimal/float boundary

This is the **critical correction #3** boundary. It is enforced by `app/money.py`
and `MoneyField` in `app/data/contracts.py`, and tested in
`tests/unit/test_money.py`.

## The rule
- **`Decimal` for money**: prices, market value, cost basis, premium, P/L,
  withdrawals, budgets, income, effective exit/basis, 2x/3x/5x target prices.
- **`float` for statistics**: Greeks (delta/gamma/theta/vega), IV, VWAP, z-scores,
  probabilities, correlations, CAGR/rates, and **all Monte-Carlo** work.
- **Convert explicitly at the boundary** with `to_money()` / `to_float()` /
  `pct_of()`. Never let a money value drift into float arithmetic implicitly.
- **Round money only at emit time** with `round_money()` (banker's rounding). Engines
  keep full Decimal precision internally.

## Why floats are routed through `str`
`to_money(0.1)` returns `Decimal("0.1")`, not the binary-noise
`Decimal("0.1000000000000000055...")`. `MoneyField` runs every Pydantic input
through `to_money`, so fixtures and configs can use plain numbers safely.

## Worked examples
- Holding market value: `quantity * price * multiplier` (Decimal). Short option MV
  may be negative; the per-unit **price** may not.
- Unrealized P/L: `market_value - cost_basis` (Decimal); `None` if cost basis is
  missing — never coerced to zero.
- Covered-call effective basis: `avg_cost - premium`; effective exit if assigned:
  `strike + premium`.
- LEAPS 2x/3x/5x underlying target: `strike + multiple * premium`.
- Concentration weight / percentages: `pct_of(part, whole)` crosses to `float`
  deliberately (a ratio is a statistic, not money).

## Monte-Carlo is float end-to-end
The trajectory and income-sleeve simulations run entirely in `float` (drift, vol,
draws, wealth paths). Only the **summary statistics** (median / p10 / p25 / p90
terminal wealth, deltas) are converted back to `Decimal` and rounded when written
to the `TrajectoryResult` / `IncomeSleeveComparison` contracts.
