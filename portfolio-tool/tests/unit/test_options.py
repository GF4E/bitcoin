"""Options engines: payoff math, LEAPS budget/filters, covered-call repair + leader rule."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from app.config import AppConfig
from app.data.contracts import AssetType, EquityHolding, MomentumTag, OptionRight
from app.data.loader import load_portfolio
from app.options.covered_call_engine import is_eligible, screen_covered_calls
from app.options.leaps_screener import _structure_score, screen_leaps
from app.options.payoff import (
    breakeven,
    intrinsic_value,
    max_loss_long,
    spread_pct,
    underlying_for_multiple,
)

_AS_OF = datetime(2026, 6, 15, 16, 0, 0)


# ---- payoff math -----------------------------------------------------------
def test_intrinsic_and_breakeven() -> None:
    assert intrinsic_value(OptionRight.CALL, Decimal("180"), Decimal("160")) == Decimal("20")
    assert intrinsic_value(OptionRight.CALL, Decimal("150"), Decimal("160")) == Decimal("0")
    assert breakeven(OptionRight.CALL, Decimal("200"), Decimal("30")) == Decimal("230")


def test_multiple_targets_and_max_loss() -> None:
    assert underlying_for_multiple(Decimal("200"), Decimal("30"), 2.0, OptionRight.CALL) == Decimal(
        "260"
    )
    assert underlying_for_multiple(Decimal("200"), Decimal("30"), 5.0, OptionRight.CALL) == Decimal(
        "350"
    )
    assert max_loss_long(Decimal("30.75"), 2, 100) == Decimal("6150.00")


def test_spread_pct() -> None:
    assert abs(spread_pct(Decimal("0.70"), Decimal("0.85")) - (0.15 / 0.775)) < 1e-9


# ---- LEAPS -----------------------------------------------------------------
def test_structure_score_prefers_stock_replacement_band(cfg: AppConfig) -> None:
    t = cfg.decision_thresholds["leaps"]
    assert _structure_score(0.78, t) == 1.0  # in 0.70-0.85 band
    assert _structure_score(0.62, t) < 1.0  # below band
    assert _structure_score(0.30, t) == 0.0  # rejected (< 0.40)


def test_leaps_budget_math_and_filters(cfg: AppConfig) -> None:
    cands = screen_leaps(cfg)
    assert cands, "expected LEAPS candidates"
    top = cands[0]
    # budget math is internally consistent
    assert top.remaining_budget_after == cfg.risk_budget.remaining_leaps_budget - top.cost
    assert abs(top.premium_pct_net_worth - float(top.cost / cfg.risk_budget.net_worth_total)) < 1e-9
    # >=18 month expirations only, and 2x target above strike
    assert all(c.months_to_expiry >= 18 for c in cands)
    assert top.px_2x > top.strike
    # the highest score is a positive-trend momentum leader (stock-replacement rule)
    assert top.momentum_tag is MomentumTag.LEADER and top.trend_on


# ---- covered calls ---------------------------------------------------------
def test_covered_call_only_ballast_low_delta(cfg: AppConfig) -> None:
    pf = load_portfolio(cfg)
    cands = screen_covered_calls(cfg, pf.holdings)
    assert cands
    assert all(c.momentum_tag is not MomentumTag.LEADER for c in cands)  # leader-no-call
    assert all(c.delta <= 0.15 for c in cands)  # <=0.15 delta only
    assert all(c.strike > c.price for c in cands)  # OTM


def test_leader_no_call_enforced_and_override(cfg: AppConfig) -> None:
    pf = load_portfolio(cfg)
    nvda = next(h for h in pf.holdings if h.ticker == "NVDA")
    # NVDA is a momentum leader -> refused by default
    eligible, reason = is_eligible(cfg, nvda, MomentumTag.LEADER)
    assert eligible is False and reason == "momentum_leader_protected"
    # explicit config override surfaces it
    cfg.decision_thresholds["covered_call"]["allow_leader_override"] = True
    eligible2, _ = is_eligible(cfg, nvda, MomentumTag.LEADER)
    assert eligible2 is True
    assert any(c.ticker == "NVDA" for c in screen_covered_calls(cfg, pf.holdings))


def test_covered_call_basis_repair_and_dividend(cfg: AppConfig) -> None:
    cfg.dividend_overrides["KO"] = {"ex_date": "2026-09-10", "amount": 0.485, "label": "estimated"}
    pf = load_portfolio(cfg)
    cands = [c for c in screen_covered_calls(cfg, pf.holdings) if c.ticker == "KO"]
    c = cands[0]
    # effective basis = avg cost (58) - premium; effective exit = strike + premium
    assert c.effective_basis_if_not == c.avg_cost - c.premium
    assert c.effective_exit_if_assigned == c.strike + c.premium
    assert c.dividend_amount == Decimal("0.485")
    assert len(c.scenario_tree) == 8  # full 8-branch tree
    assert c.buyback_target < c.premium  # buy back after capture


def test_missing_cost_basis_gates_repair_math(cfg: AppConfig) -> None:
    h = EquityHolding(
        account_id="A1",
        account_name="T",
        masked_account_id="****1",
        ticker="KO",
        name="KO",
        asset_type=AssetType.EQUITY,
        quantity=Decimal("500"),
        price=Decimal("62"),
        as_of_datetime=_AS_OF,
        momentum_tag=MomentumTag.BALLAST,
    )
    cands = [c for c in screen_covered_calls(cfg, [h]) if c.ticker == "KO"]
    assert cands
    assert all(c.effective_basis_if_not is None for c in cands)  # no repair math without basis
    assert all("missing_cost_basis_repair_gated" in c.data_quality_warnings for c in cands)
