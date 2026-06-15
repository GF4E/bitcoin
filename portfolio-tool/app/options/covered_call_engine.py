"""Covered-call / repair engine — generalized for any holding.

CENTRAL RULE (final): write covered calls at <=0.15 delta ONLY on ballast /
low-momentum holdings the user would accept being called away. NEVER on momentum
leaders or LEAPS-replaced names (capping a leader destroys let-winners-run — the
Israelov-Ndong "devil's bargain"). The engine TAGS each holding leader vs ballast
from the momentum engine and refuses to surface call candidates on leaders unless
explicitly overridden in config.

Per candidate: shares/account, max clean contracts, avg cost, price, unrealized
P/L, strikes/expirations, bid/ask/mid/last, OI/vol/IV/delta, premium income,
effective exit if assigned, effective basis if not, dividend impact, early-
assignment risk, buyback/roll/resell rules, an 8-branch scenario tree, and a
classification. Never roll below the repaired basis unless config permits a
below-basis exit. If cost basis is missing, no repair math without manual override.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from app.config import AppConfig
from app.data.contracts import (
    ActionToken,
    AssetType,
    DividendEvent,
    Holding,
    MomentumTag,
    OptionRight,
    Triage,
)
from app.data.market_data import MarketData, make_market_data
from app.momentum.engine import compute_signals
from app.money import Money, round_money, to_float, to_money
from app.options.chains import load_chain_rows
from app.options.payoff import months_to_expiry

_AS_OF = date(2026, 6, 15)


@dataclass
class CoveredCallCandidate:
    ticker: str
    account_id: str
    shares: int
    max_contracts: int
    avg_cost: Money | None
    price: Money
    unrealized_gain_loss: Money | None
    expiration: date
    strike: Money
    delta: float
    premium: Money
    premium_income: Money
    effective_exit_if_assigned: Money | None
    effective_basis_if_not: Money | None
    dividend_amount: Money | None
    early_assignment_risk: str
    buyback_target: Money
    roll_floor_basis: Money | None
    classification: str
    momentum_tag: MomentumTag
    annualized_yield: float
    total_score: float
    score_components: dict[str, float]
    candidate_action: ActionToken
    triage: Triage
    scenario_tree: dict[str, str]
    rationale: str
    data_quality_warnings: list[str] = field(default_factory=list)


def _dividend_for(cfg: AppConfig, ticker: str) -> DividendEvent | None:
    row = cfg.dividend_overrides.get(ticker)
    if not row:
        return None
    return DividendEvent(
        ticker=ticker,
        ex_date=date.fromisoformat(row["ex_date"]),
        amount=to_money(row["amount"]),
        label=row.get("label", "estimated"),
    )


def _accept_called_away(cfg: AppConfig, ticker: str, tag: MomentumTag, allow_leader: bool) -> bool:
    override = cfg.holding_overrides.get(ticker, {})
    if "accept_called_away" in override:
        return bool(override["accept_called_away"])
    # ballast/neutral acceptable by default; leaders only when explicitly overridden.
    return tag is not MomentumTag.LEADER or allow_leader


def is_eligible(cfg: AppConfig, holding: Holding, tag: MomentumTag) -> tuple[bool, str]:
    """Leader-no-call enforcement. Returns (eligible, reason)."""
    allow_leader = bool(
        cfg.decision_thresholds.get("covered_call", {}).get("allow_leader_override", False)
    )
    if holding.asset_type not in (AssetType.EQUITY, AssetType.FUND):
        return False, "not_a_shares_position"
    if not holding.is_schwab_managed:
        return False, "external_not_schwab_managed"
    if (holding.quantity or 0) < 100:
        return False, "fewer_than_100_shares"
    if tag is MomentumTag.LEADER and not allow_leader:
        return False, "momentum_leader_protected"
    if not _accept_called_away(cfg, holding.ticker, tag, allow_leader):
        return False, "would_not_accept_called_away"
    return True, "eligible"


def _scenario_tree(
    *,
    strike: Money,
    premium: Money,
    avg_cost: Money | None,
    price: Money,
    dividend: Money | None,
    buyback_target: Money,
) -> dict[str, str]:
    proceeds = strike + premium
    gain = (proceeds - avg_cost) if avg_cost is not None else None
    return {
        "1_assignment": (
            f"Called away at {strike}: proceeds {round_money(proceeds)}/sh"
            + (
                f", gain vs basis {round_money(gain)}/sh"
                if gain is not None
                else " (basis unknown)"
            )
        ),
        "2_flat_decay": f"Expires worthless: keep {round_money(premium)}/sh premium and shares; "
        + (
            f"new basis {round_money(avg_cost - premium)}/sh"
            if avg_cost is not None
            else "basis unknown"
        ),
        "3_drop_buyback": f"Price falls: buy back at {round_money(buyback_target)} (capture target), keep shares.",
        "4_buyback_and_wait": "After buyback, wait for a higher-IV / above-VWAP window before re-writing.",
        "5_buyback_and_resell": "After buyback on weakness, resell calls into the next strength (VWAP sell window).",
        "6_roll_for_credit": "If tested, roll up/out for a net credit — never below the repaired basis.",
        "7_early_assignment_dividend": (
            f"Dividend {round_money(dividend)}/sh near expiry: ITM extrinsic < dividend => early-assignment risk."
            if dividend is not None
            else "No dividend before expiry: early-assignment risk low for OTM low-delta."
        ),
        "8_thesis_break_sell": "If the thesis breaks, close the call and sell the shares (do not defend with rolls).",
    }


def screen_covered_calls(
    cfg: AppConfig, holdings: list[Holding], market: MarketData | None = None
) -> list[CoveredCallCandidate]:
    market = market or make_market_data(cfg)
    cc = cfg.decision_thresholds.get("covered_call", {})
    max_delta = float(cc.get("max_delta", 0.15))
    capture = float(cc.get("buyback_capture_high", 0.70))
    weights = cfg.scoring_weights.get("covered_call", {})

    shares_holdings = [h for h in holdings if h.asset_type in (AssetType.EQUITY, AssetType.FUND)]
    underlyings = sorted({h.ticker for h in shares_holdings})
    tags = {s.ticker: s.momentum_tag for s in compute_signals(cfg, underlyings, market)}
    chain = [r for r in load_chain_rows(cfg, market) if r.call_put is OptionRight.CALL]

    out: list[CoveredCallCandidate] = []
    for h in shares_holdings:
        tag = tags.get(h.ticker, MomentumTag.NEUTRAL)
        eligible, _reason = is_eligible(cfg, h, tag)
        if not eligible:
            continue
        shares = int(h.quantity)
        max_contracts = shares // 100
        price = h.price or to_money(0)
        for r in chain:
            if r.underlying != h.ticker or r.delta is None or r.mid is None:
                continue
            if r.delta > max_delta or r.strike <= price:  # OTM, <=0.15 delta only
                continue
            premium = r.mid
            income = premium * Decimal(max_contracts) * Decimal(r.multiplier)
            warns: list[str] = list(r.liquidity_flags)

            eff_exit = eff_basis = roll_floor = None
            classification = "income"
            if h.cost_basis is not None and shares > 0:
                avg_cost = h.cost_basis / Decimal(shares)
                eff_exit = r.strike + premium
                eff_basis = avg_cost - premium
                roll_floor = eff_basis
                if (h.unrealized_gain_loss or Decimal(0)) < 0:
                    classification = "repair"
            else:
                avg_cost = None
                warns.append("missing_cost_basis_repair_gated")

            dividend = _dividend_for(cfg, h.ticker)
            early = "low (OTM, low delta)"
            if dividend is not None and r.strike <= price:
                early = "elevated (ITM near ex-dividend)"

            mte = max(months_to_expiry(r.expiration, _AS_OF), 0.1)
            ann_yield = to_float(premium / price) * (12.0 / mte) if price > 0 else 0.0
            buyback_target = round_money(premium * to_money(1.0 - capture))

            comp = {
                "repair_exit_math": 0.8 if classification == "repair" else 0.6,
                "premium_quality": min(ann_yield / 0.12, 1.0),
                "assignment_dividend_risk": 0.9 if "low" in early else 0.4,
                "liquidity": 1.0 if not r.liquidity_flags else 0.5,
                "portfolio_objective": 0.9,  # ballast we'd accept called away
                "vwap_timing": 0.6,
            }
            total = sum(weights.get(k, 0.0) * v for k, v in comp.items())
            action = ActionToken.WRITE_CALL if total >= 55 else ActionToken.WAIT
            triage = Triage.ACT_NOW if action is ActionToken.WRITE_CALL else Triage.WAIT

            out.append(
                CoveredCallCandidate(
                    ticker=h.ticker,
                    account_id=h.account_id,
                    shares=shares,
                    max_contracts=max_contracts,
                    avg_cost=round_money(avg_cost) if avg_cost is not None else None,
                    price=round_money(price),
                    unrealized_gain_loss=h.unrealized_gain_loss,
                    expiration=r.expiration,
                    strike=r.strike,
                    delta=r.delta,
                    premium=round_money(premium),
                    premium_income=round_money(income),
                    effective_exit_if_assigned=round_money(eff_exit)
                    if eff_exit is not None
                    else None,
                    effective_basis_if_not=round_money(eff_basis)
                    if eff_basis is not None
                    else None,
                    dividend_amount=dividend.amount if dividend else None,
                    early_assignment_risk=early,
                    buyback_target=buyback_target,
                    roll_floor_basis=round_money(roll_floor) if roll_floor is not None else None,
                    classification=classification,
                    momentum_tag=tag,
                    annualized_yield=ann_yield,
                    total_score=total,
                    score_components=comp,
                    candidate_action=action,
                    triage=triage,
                    scenario_tree=_scenario_tree(
                        strike=r.strike,
                        premium=premium,
                        avg_cost=avg_cost,
                        price=price,
                        dividend=dividend.amount if dividend else None,
                        buyback_target=buyback_target,
                    ),
                    rationale=(
                        f"{classification} overlay on ballast {h.ticker} at <= {max_delta} delta; "
                        f"annualized premium yield {ann_yield:.1%}."
                    ),
                    data_quality_warnings=warns,
                )
            )
    out.sort(key=lambda c: c.total_score, reverse=True)
    return out
