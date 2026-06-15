"""LEAPS screener — generalized stock-replacement leverage on momentum leaders.

Filters: expiration >=18mo preferred; STOCK-REPLACEMENT delta 0.70-0.85 (NOT
0.50-0.70 for that use); reject <0.40 unless tagged lottery; OI/spread quality;
reject far-OTM junk. RULE: LEAPS-as-stock-replacement only on the highest-momentum
names and only when the trend filter is positive. Single-LEAP up to the configured
ceiling; total LEAPS premium capped at the budget. Weights 30/20/20/15/10/5.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from app.config import AppConfig
from app.data.contracts import (
    ActionToken,
    Assumption,
    DataLabel,
    MomentumTag,
    OptionRight,
    Triage,
)
from app.data.market_data import MarketData, make_market_data
from app.momentum.engine import compute_signals
from app.money import Money, pct_of, round_money, to_float, to_money
from app.options.chains import load_chain_rows, underlying_prices
from app.options.payoff import (
    breakeven,
    delta_adjusted_notional,
    max_loss_long,
    months_to_expiry,
    underlying_for_multiple,
)

_AS_OF = date(2026, 6, 15)


@dataclass
class LeapsCandidate:
    underlying: str
    expiration: date
    strike: Money
    delta: float
    premium: Money
    contracts: int
    cost: Money
    max_loss: Money
    breakeven: Money
    intrinsic: Money
    extrinsic: Money
    delta_adjusted_notional: Money
    premium_pct_net_worth: float
    premium_pct_leaps_budget: float
    remaining_budget_after: Money
    px_2x: Money
    px_3x: Money
    px_5x: Money
    ai_overlap: bool
    open_interest: int | None
    spread_pct: float | None
    months_to_expiry: float
    momentum_tag: MomentumTag
    trend_on: bool
    total_score: float
    score_components: dict[str, float]
    candidate_action: ActionToken
    triage: Triage
    rationale: str
    assumptions: list[Assumption] = field(default_factory=list)
    data_quality_warnings: list[str] = field(default_factory=list)


def _structure_score(delta: float, t: dict) -> float:
    lo, hi = (
        float(t.get("stock_replacement_delta_min", 0.70)),
        float(t.get("stock_replacement_delta_max", 0.85)),
    )
    if lo <= delta <= hi:
        return 1.0
    if 0.60 <= delta < lo or hi < delta <= 0.90:
        return 0.6
    if float(t.get("reject_delta_below", 0.40)) <= delta < 0.60:
        return 0.3
    return 0.0


def _thesis_score(tag: MomentumTag, trend_on: bool) -> float:
    if tag is MomentumTag.LEADER and trend_on:
        return 1.0
    if tag is MomentumTag.NEUTRAL and trend_on:
        return 0.5
    return 0.2


def _liquidity_score(oi: int | None, spread: float | None, t: dict) -> float:
    ideal = float(t.get("ideal_open_interest", 1000))
    oi_score = min((oi or 0) / ideal, 1.0)
    spread_pen = (
        0.0 if spread is None else min(spread / float(t.get("max_spread_pct", 0.08)), 1.0) * 0.5
    )
    return max(oi_score * (1.0 - spread_pen), 0.0)


def screen_leaps(
    cfg: AppConfig, contracts: int = 1, market: MarketData | None = None
) -> list[LeapsCandidate]:
    market = market or make_market_data(cfg)
    universe = set(cfg.watchlists.get("leaps_universe", []))
    rows = [
        r
        for r in load_chain_rows(cfg, market, underlyings=universe)
        if r.call_put is OptionRight.CALL
    ]
    prices = underlying_prices(market, universe)
    rb = cfg.risk_budget
    weights = cfg.scoring_weights.get("leaps", {})
    t = cfg.decision_thresholds.get("leaps", {})
    min_months = float(t.get("min_expiration_months", 18))
    reject_below = float(t.get("reject_delta_below", 0.40))

    tags = {s.ticker: s for s in compute_signals(cfg, sorted(universe), market)}
    candidates: list[LeapsCandidate] = []
    for r in rows:
        mte = months_to_expiry(r.expiration, _AS_OF)
        if mte < min_months or r.mid is None or r.delta is None:
            continue
        underlying = prices.get(r.underlying)
        if underlying is None:
            continue
        premium = r.mid
        cost = premium * Decimal(contracts) * Decimal(r.multiplier)
        sig = tags.get(r.underlying)
        tag = sig.momentum_tag if sig else MomentumTag.NEUTRAL
        trend_on = sig.trend_filter_on if sig else False
        ai_overlap = cfg.is_ai_tech_semi(r.underlying)

        comp = {
            "thesis": _thesis_score(tag, trend_on),
            "structure": _structure_score(r.delta, t),
            "fit_overlap": 0.4 if ai_overlap else 0.9,
            "asymmetry": min(
                max(
                    to_float(delta_adjusted_notional(r.delta, underlying, 1, r.multiplier) / cost)
                    - 1.0,
                    0.0,
                )
                / 4.0,
                1.0,
            ),
            "liquidity": _liquidity_score(r.open_interest, r.spread_pct, t),
            "timing": 0.8 if trend_on else 0.4,
        }
        total = sum(weights.get(k, 0.0) * v for k, v in comp.items())

        warns: list[str] = list(r.liquidity_flags)
        feasible = r.delta >= reject_below and cost <= rb.remaining_leaps_budget
        within_single = cost <= rb.max_single_leap
        if r.delta < reject_below:
            warns.append("delta_below_floor_lottery_only")
        if not within_single:
            warns.append("exceeds_max_single_leap")

        if not feasible:
            action, triage = ActionToken.WAIT, Triage.WAIT
            rationale = "Below delta floor or over remaining LEAPS budget."
        elif total >= 60 and trend_on and tag is MomentumTag.LEADER:
            action, triage = ActionToken.OPEN_LEAP, Triage.ACT_NOW
            rationale = "Stock-replacement on a positive-trend momentum leader within budget."
        else:
            action, triage = ActionToken.WAIT, Triage.WAIT
            rationale = "Passes structure but not a positive-trend leader; wait for confirmation."

        candidates.append(
            LeapsCandidate(
                underlying=r.underlying,
                expiration=r.expiration,
                strike=r.strike,
                delta=r.delta,
                premium=round_money(premium),
                contracts=contracts,
                cost=round_money(cost),
                max_loss=round_money(max_loss_long(premium, contracts, r.multiplier)),
                breakeven=round_money(breakeven(OptionRight.CALL, r.strike, premium)),
                intrinsic=round_money(r.intrinsic_value or to_money(0)),
                extrinsic=round_money(r.extrinsic_value or to_money(0)),
                delta_adjusted_notional=round_money(
                    delta_adjusted_notional(r.delta, underlying, contracts, r.multiplier)
                ),
                premium_pct_net_worth=pct_of(cost, rb.net_worth_total),
                premium_pct_leaps_budget=pct_of(cost, rb.leaps_budget),
                remaining_budget_after=round_money(rb.remaining_leaps_budget - cost),
                px_2x=round_money(
                    underlying_for_multiple(r.strike, premium, 2.0, OptionRight.CALL)
                ),
                px_3x=round_money(
                    underlying_for_multiple(r.strike, premium, 3.0, OptionRight.CALL)
                ),
                px_5x=round_money(
                    underlying_for_multiple(r.strike, premium, 5.0, OptionRight.CALL)
                ),
                ai_overlap=ai_overlap,
                open_interest=r.open_interest,
                spread_pct=r.spread_pct,
                months_to_expiry=mte,
                momentum_tag=tag,
                trend_on=trend_on,
                total_score=total,
                score_components=comp,
                candidate_action=action,
                triage=triage,
                rationale=rationale,
                assumptions=[
                    Assumption(
                        name="momentum_tag",
                        value=tag.value,
                        label=DataLabel.ESTIMATED,
                        load_bearing=True,
                        rationale="From the momentum engine on sample price history.",
                    ),
                ],
                data_quality_warnings=warns,
            )
        )
    candidates.sort(key=lambda c: c.total_score, reverse=True)
    return candidates
