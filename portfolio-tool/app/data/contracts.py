"""Pydantic v2 data contracts (normalized domain models).

These are the *normalized* shapes the engines consume. Raw Schwab response shapes
never leak past the adapter boundary (``app/schwab_client``); they are mapped into
these models in ``app/data/normalize.py``.

Money fields use :data:`MoneyField`, which routes every input through
:func:`app.money.to_money` so floats never inherit binary noise. Statistical
fields (Greeks, IV, VWAP, probabilities) stay ``float`` by design.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

from app.money import to_money

MoneyField = Annotated[Decimal, BeforeValidator(to_money)]


# --------------------------------------------------------------------------- #
# Enumerations
# --------------------------------------------------------------------------- #
class AssetType(StrEnum):
    EQUITY = "equity"
    FUND = "fund"
    OPTION = "option"
    CASH = "cash"


class OptionRight(StrEnum):
    CALL = "call"
    PUT = "put"


class MomentumTag(StrEnum):
    LEADER = "leader"
    BALLAST = "ballast"
    NEUTRAL = "neutral"


class DataLabel(StrEnum):
    """Provenance label required on every load-bearing input."""

    VERIFIED = "verified"
    ESTIMATED = "estimated"
    ASSUMED = "assumed"


class Sleeve(StrEnum):
    BROAD_CORE = "broad_core"
    NASDAQ_GROWTH = "nasdaq_growth"
    AI_SOFTWARE = "ai_software"
    SEMIS = "semis"
    DATA_CENTER_POWER = "data_center_power"
    ENERGY_INFRASTRUCTURE = "energy_infrastructure"
    INCOME_CREDIT = "income_credit"
    COVERED_CALL_INCOME = "covered_call_income"
    CASH_TBILLS = "cash_tbills"
    GOLD_HEDGE = "gold_hedge"
    CRYPTO_PROXY = "crypto_proxy"
    OPTIONS_DERIVATIVES = "options_derivatives"
    SPECULATIVE = "speculative"
    OTHER = "other"


class HoldingRole(StrEnum):
    CORE = "core"
    GROWTH = "growth"
    INCOME = "income"
    HEDGE = "hedge"
    REPAIR = "repair"
    TACTICAL = "tactical"
    SPECULATIVE = "speculative"
    CASH_RESERVE = "cash_reserve"


class ActionToken(StrEnum):
    """Internal action vocabulary. The render layer maps these to neutral
    candidate labels when ``compliance_mode: strict`` (see app/reports/compliance.py)."""

    ADD = "add"
    TRIM = "trim"
    EXIT = "exit"
    HOLD = "hold"
    OPEN_LEAP = "open_leap"
    WRITE_CALL = "write_call"
    ROLL = "roll"
    BUYBACK = "buyback"
    REPLACE = "replace"
    GATHER_MORE_DATA = "gather_more_data"
    WAIT = "wait"


class Triage(StrEnum):
    ACT_NOW = "act_now"
    WAIT = "wait"
    GATHER_MORE_DATA = "gather_more_data"


class VWAPStatus(StrEnum):
    CLEAN_ENTRY = "clean_entry"
    ACCEPTABLE_ENTRY = "acceptable_entry"
    EXTENDED_DO_NOT_CHASE = "extended_do_not_chase"
    WEAK_WAIT = "weak_wait"
    SELL_PREMIUM_WINDOW = "sell_premium_window"
    BUYBACK_WINDOW = "buyback_window"
    NO_SIGNAL = "no_signal"


class Severity(StrEnum):
    INFO = "info"
    WARN = "warn"
    CRITICAL = "critical"


# --------------------------------------------------------------------------- #
# Cross-cutting small models
# --------------------------------------------------------------------------- #
class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=False, use_enum_values=False)


class DataQualityWarning(_Base):
    code: str
    message: str
    severity: Severity = Severity.WARN
    field: str | None = None
    ticker: str | None = None
    account_id: str | None = None
    label: DataLabel | None = None


class Assumption(_Base):
    name: str
    value: str
    label: DataLabel
    load_bearing: bool = False
    rationale: str | None = None


# --------------------------------------------------------------------------- #
# Market / account primitives
# --------------------------------------------------------------------------- #
class Account(_Base):
    account_id: str
    account_name: str
    masked_account_id: str
    account_type: str | None = None
    is_schwab_managed: bool = True
    data_source: str = "mock"


class Holding(_Base):
    """Normalized holding row. The flat schema every engine consumes."""

    account_id: str
    account_name: str
    masked_account_id: str
    account_type: str | None = None
    ticker: str
    name: str
    asset_type: AssetType
    subtype: str | None = None
    sleeve: Sleeve = Sleeve.OTHER
    role: HoldingRole | None = None
    momentum_tag: MomentumTag = MomentumTag.NEUTRAL
    quantity: MoneyField
    price: MoneyField | None = None
    market_value: MoneyField | None = None
    cost_basis: MoneyField | None = None
    unrealized_gain_loss: MoneyField | None = None
    currency: str = "USD"
    as_of_datetime: datetime
    data_source: str = "mock"
    is_schwab_managed: bool = True
    data_quality_flags: list[str] = Field(default_factory=list)

    # option-specific (present only when asset_type == option)
    underlying: str | None = None
    expiration: date | None = None
    strike: MoneyField | None = None
    call_put: OptionRight | None = None
    multiplier: int = 100

    @model_validator(mode="after")
    def _check_prices(self) -> Holding:
        # Negative price is only acceptable for a short option's market value, not
        # for the per-unit price itself. Never silently coerce missing fields to 0.
        if self.price is not None and self.price < 0:
            raise ValueError(f"negative price not allowed for {self.ticker}: {self.price}")
        if self.asset_type is AssetType.OPTION and self.call_put is None:
            raise ValueError(f"option holding {self.ticker} missing call_put")
        return self


class EquityHolding(Holding):
    asset_type: AssetType = AssetType.EQUITY


class FundHolding(Holding):
    asset_type: AssetType = AssetType.FUND


class CashHolding(Holding):
    asset_type: AssetType = AssetType.CASH


class OptionHolding(Holding):
    asset_type: AssetType = AssetType.OPTION


class Quote(_Base):
    ticker: str
    last: MoneyField | None = None
    bid: MoneyField | None = None
    ask: MoneyField | None = None
    as_of_datetime: datetime
    stale: bool = False
    data_source: str = "mock"


class PriceBar(_Base):
    ticker: str
    bar_date: date
    open: MoneyField
    high: MoneyField
    low: MoneyField
    close: MoneyField
    volume: int = 0


class DividendEvent(_Base):
    ticker: str
    ex_date: date
    amount: MoneyField
    label: DataLabel = DataLabel.ESTIMATED


class OptionContract(_Base):
    underlying: str
    expiration: date
    strike: MoneyField
    call_put: OptionRight
    multiplier: int = 100


class OptionChainRow(_Base):
    underlying: str
    expiration: date
    strike: MoneyField
    call_put: OptionRight
    bid: MoneyField | None = None
    ask: MoneyField | None = None
    last: MoneyField | None = None
    mid: MoneyField | None = None
    delta: float | None = None
    gamma: float | None = None
    theta: float | None = None
    vega: float | None = None
    rho: float | None = None
    iv: float | None = None
    open_interest: int | None = None
    volume: int | None = None
    multiplier: int = 100
    intrinsic_value: MoneyField | None = None
    extrinsic_value: MoneyField | None = None
    spread_pct: float | None = None
    liquidity_flags: list[str] = Field(default_factory=list)
    stale_data_flag: bool = False
    missing_greeks_flag: bool = False

    @model_validator(mode="after")
    def _bid_le_ask(self) -> OptionChainRow:
        if self.bid is not None and self.ask is not None and self.bid > self.ask:
            raise ValueError(f"bid>ask for {self.underlying} {self.strike}{self.call_put}")
        return self


# --------------------------------------------------------------------------- #
# Planning / risk
# --------------------------------------------------------------------------- #
class RiskBudget(_Base):
    net_worth_total: MoneyField  # denominator for risk / withdrawal / goal math
    schwab_managed_value: MoneyField  # denominator for concentration / reconciliation
    external_static_value: MoneyField = Decimal("0")
    leaps_budget: MoneyField
    existing_leaps_cost: MoneyField
    max_single_leap: MoneyField
    ai_concentration_flag_pct: float = 0.40

    @property
    def remaining_leaps_budget(self) -> Decimal:
        return self.leaps_budget - self.existing_leaps_cost


class GoalPlan(_Base):
    net_worth_total: MoneyField
    milestone_wealth: MoneyField  # reported as a crossing, NOT the optimization target
    target_date: date
    target_date_flex_years: float = 1.0
    horizon_months: int
    monthly_expenses: MoneyField
    va_monthly_floor: MoneyField  # hard floor, never cut
    monthly_gap: MoneyField  # portfolio-covered gap
    discretionary_cuttable: MoneyField  # max monthly cut under the drawdown trigger
    expected_return_annual: float  # load-bearing, label estimated
    volatility_annual: float  # load-bearing, label estimated
    income_sleeve_correlation: float  # estimated from history


# --------------------------------------------------------------------------- #
# Engine outputs
# --------------------------------------------------------------------------- #
class ConcentrationBanner(_Base):
    ai_tech_semi_pct: float
    weighted_avg_correlation: float
    effective_independent_bets: float
    flagged: bool
    flag_threshold_pct: float


class TrajectoryResult(_Base):
    solved_drawdown_threshold: float
    ruin_probability: float
    downside_guard_passed: bool
    downside_guard_metric: str
    downside_guard_value: MoneyField
    feasible: bool
    median_terminal_wealth: MoneyField
    p10_terminal: MoneyField
    p25_terminal: MoneyField
    p50_terminal: MoneyField
    p90_terminal: MoneyField
    prob_reach_milestone: float
    milestone_crossing_months: dict[str, float] = Field(default_factory=dict)
    drag_anchor_mode: str
    baseline_cagr: float
    withdrawal_cagr: float
    n_paths: int
    seed: int | None
    concentration: ConcentrationBanner
    assumptions: list[Assumption] = Field(default_factory=list)
    warnings: list[DataQualityWarning] = Field(default_factory=list)


class IncomeSleeveComparison(_Base):
    delta_terminal_p10: MoneyField  # Approach A minus Approach B
    delta_terminal_p50: MoneyField
    delta_terminal_p90: MoneyField
    a_label: str = "capped_income_reinvest_until_drawn"
    b_label: str = "uncapped_plus_buffer"
    up_capture: float
    down_capture: float
    capture_source: str
    capture_label: DataLabel = DataLabel.ESTIMATED
    capture_date_range: str
    peer_substituted: bool
    buffer_months: int
    roc_constructive_share: float  # fraction of regimes where A's ROC is constructive
    regime_note: str
    assumptions: list[Assumption] = Field(default_factory=list)
    warnings: list[DataQualityWarning] = Field(default_factory=list)


class MomentumSignal(_Base):
    ticker: str
    ts_momentum_12_1: float
    blended_momentum: float
    cross_sectional_rank: int | None = None
    trend_filter_on: bool
    realized_vol: float
    target_weight: float  # inverse-vol, vol-targeted
    momentum_tag: MomentumTag
    persistent_breach: bool = False


class ThrottleState(_Base):
    gross_exposure_multiplier: float  # 0..1
    indicator_scores: dict[str, float] = Field(default_factory=dict)
    persistent: bool
    brake_active: bool


class SleeveClassification(_Base):
    ticker: str
    sleeve: Sleeve
    role: HoldingRole | None = None
    is_ai_tech_semi: bool = False
    source: str = "config"


class _DecisionEnvelope(_Base):
    candidate_action: ActionToken
    confidence: float = Field(ge=0.0, le=1.0)
    triage: Triage
    rationale: str
    supporting_calculations: dict[str, Any] = Field(default_factory=dict)
    score_components: dict[str, float] = Field(default_factory=dict)
    assumptions: list[Assumption] = Field(default_factory=list)
    data_quality_warnings: list[DataQualityWarning] = Field(default_factory=list)
    what_would_change_the_decision: str = ""
    next_monitoring_trigger: str = ""
    adversarial_audit: str = ""


class HoldingDecision(_DecisionEnvelope):
    ticker: str
    account_id: str | None = None
    role: HoldingRole | None = None
    total_score: float = 0.0


class OpportunityDecision(_DecisionEnvelope):
    ticker: str
    thesis_bucket: str | None = None
    total_score: float = 0.0


class ReplacementCandidate(_Base):
    incumbent_ticker: str
    candidate_ticker: str
    improves_expected_return: bool
    improves_risk: bool
    improves_liquidity: bool
    improves_clarity: bool
    improves_goal_fit: bool
    overlap_flag: bool
    best_funding_source: str | None = None
    rationale: str = ""
    score_delta: float = 0.0


class VWAPFeatures(_Base):
    ticker: str
    session_vwap: MoneyField | None = None
    price_vs_vwap_pct: float | None = None
    slope: float | None = None
    above_vwap_minutes_pct: float | None = None
    distance_zscore: float | None = None
    volume_vs_avg: float | None = None
    anchored_vwaps: dict[str, float] = Field(default_factory=dict)
    status: VWAPStatus = VWAPStatus.NO_SIGNAL


class ExecutionSignal(_Base):
    ticker: str
    status: VWAPStatus
    rationale: str = ""
    timing_only: bool = True


class TradeMemo(_Base):
    ticker: str
    memo_type: str  # leaps | covered_call | rotation | holding
    title: str
    sections: dict[str, str]  # section name -> markdown body
    candidate_action: ActionToken
    path: str | None = None


class DecisionLogEntry(_Base):
    run_id: str
    timestamp: datetime
    module: str
    ticker: str
    account: str | None = None
    candidate_action: ActionToken
    confidence: float
    score_components: dict[str, float] = Field(default_factory=dict)
    key_assumptions: str = ""
    data_quality_flags: str = ""
    source_files_or_api_timestamp: str = ""
    memo_path: str | None = None


class RunMetadata(_Base):
    run_id: str
    started_at: datetime
    mode: str  # mock | live_readonly
    compliance_mode: str
    seed: int | None
    config_files: list[str] = Field(default_factory=list)
    tool_version: str = "0.1.0"
    notes: str = ""
