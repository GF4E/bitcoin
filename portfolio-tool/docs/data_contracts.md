# Data contracts

Pydantic v2 models in `app/data/contracts.py` are the **normalized** shapes every
engine consumes. Raw Schwab response shapes never leak past the adapter boundary
(`app/data/normalize.py`); `app/schwab_client/models.py` documents the raw payloads.

## Models
Account, Holding (+ EquityHolding / FundHolding / OptionHolding / CashHolding),
OptionContract, OptionChainRow, Quote, PriceBar, DividendEvent, RiskBudget,
GoalPlan, TrajectoryResult, ConcentrationBanner, IncomeSleeveComparison,
MomentumSignal, ThrottleState, SleeveClassification, HoldingDecision,
OpportunityDecision, ReplacementCandidate, TradeMemo, VWAPFeatures, ExecutionSignal,
DataQualityWarning, Assumption, DecisionLogEntry, RunMetadata.

## Normalized holding row
`account_id`, `account_name`, `masked_account_id`, `account_type?`, `ticker`,
`name`, `asset_type`, `subtype`, `sleeve`, `role?`, `momentum_tag`
(leader/ballast/neutral), `quantity`, `price`, `market_value`, `cost_basis`,
`unrealized_gain_loss`, `currency`, `as_of_datetime`, `data_source`,
`is_schwab_managed`, `data_quality_flags`, and the option fields (`underlying`,
`expiration`, `strike`, `call_put`, `multiplier`).

## Option chain row
`underlying`, `expiration`, `strike`, `call_put`, `bid/ask/last/mid`,
`delta/gamma/theta/vega/rho?`, `iv`, `open_interest`, `volume`, `multiplier`,
`intrinsic_value`, `extrinsic_value`, `spread_pct`, `liquidity_flags`,
`stale_data_flag`, `missing_greeks_flag`.

## Validation rules (enforced)
- Reject negative **price** (short-option **market value** may be negative).
- Option holdings require `call_put`; option-chain rows require `bid <= ask`.
- Validate `multiplier` and `expiration`.
- Flag (never silently zero): missing cost basis, missing price, missing Greeks,
  wide spreads, low OI/volume, stale quotes. Missing critical fields surface as
  `DataQualityWarning`s and degrade decisions to `gather_more_data` / `wait`.
- Money fields parse through `MoneyField` (see `docs/calculations.md`).
