"""Portfolio engines: exposure (two denominators), reconciliation, holding evaluator."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from app.config import AppConfig
from app.data.contracts import (
    Account,
    ActionToken,
    AssetType,
    EquityHolding,
    MomentumTag,
    Triage,
)
from app.data.loader import load_portfolio
from app.portfolio.exposure import compute_exposure
from app.portfolio.holding_evaluator import evaluate_holdings
from app.portfolio.reconciliation import reconcile

_AS_OF = datetime(2026, 6, 15, 16, 0, 0)


def test_exposure_uses_two_denominators(cfg: AppConfig) -> None:
    pf = load_portfolio(cfg)
    exp = compute_exposure(cfg, pf.holdings)
    assert exp.schwab_managed_value == Decimal("2945700.00")
    assert exp.external_static_value == Decimal("240000.00")
    # a sleeve's % of net worth differs from its % of the (smaller) schwab denominator
    s = exp.by_sleeve[0]
    assert s.pct_net_worth != s.pct_schwab_managed
    assert exp.ai_tech_semi_pct_net_worth > 0.40


def test_reconciliation_within_tolerance(cfg: AppConfig) -> None:
    pf = load_portfolio(cfg)
    results, warnings = reconcile(cfg, pf.accounts, pf.holdings)
    assert all(r.within_tolerance for r in results)
    assert not warnings


def test_reconciliation_flags_out_of_tolerance(cfg: AppConfig) -> None:
    acc = Account(
        account_id="Z",
        account_name="T",
        masked_account_id="****9",
        is_schwab_managed=True,
        reported_total=Decimal("1000000"),
    )
    h = EquityHolding(
        account_id="Z",
        account_name="T",
        masked_account_id="****9",
        ticker="NVDA",
        name="NVIDIA",
        asset_type=AssetType.EQUITY,
        quantity=Decimal("100"),
        price=Decimal("1100"),
        market_value=Decimal("1100000"),
        as_of_datetime=_AS_OF,
    )
    results, warnings = reconcile(cfg, [acc], [h])
    assert results[0].within_tolerance is False
    assert any(w.code == "reconciliation_out_of_tolerance" for w in warnings)


def test_holding_decisions_carry_full_envelope(cfg: AppConfig) -> None:
    pf = load_portfolio(cfg)
    decisions = evaluate_holdings(cfg, pf.holdings)
    assert len(decisions) == len(pf.holdings)
    for d in decisions:
        assert 0.0 <= d.confidence <= 1.0
        assert d.score_components and d.rationale
        assert d.assumptions and d.adversarial_audit
        assert d.what_would_change_the_decision and d.next_monitoring_trigger
        assert isinstance(d.triage, Triage)
    # a momentum leader is HELD (let winners run), never auto-capped
    nvda = next(d for d in decisions if d.ticker == "NVDA")
    assert nvda.candidate_action is ActionToken.HOLD


def test_missing_data_degrades_to_gather_more_data(cfg: AppConfig) -> None:
    h = EquityHolding(
        account_id="A",
        account_name="T",
        masked_account_id="****1",
        ticker="MU",
        name="Micron",
        asset_type=AssetType.EQUITY,
        quantity=Decimal("10"),
        price=Decimal("130"),
        market_value=Decimal("1300"),
        as_of_datetime=_AS_OF,
        momentum_tag=MomentumTag.NEUTRAL,
        data_quality_flags=["missing_cost_basis"],
    )
    d = evaluate_holdings(cfg, [h])[0]
    assert d.candidate_action is ActionToken.GATHER_MORE_DATA
    assert d.triage is Triage.GATHER_MORE_DATA
    assert d.confidence < 0.5
