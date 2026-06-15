"""Decision engine: orchestration, decision log, envelope completeness, replacement."""

from __future__ import annotations

from datetime import datetime

from app.config import AppConfig
from app.data.loader import load_portfolio
from app.decision_engine import run_decision_engine
from app.portfolio.replacement_engine import compare_replacement

_TS = datetime(2026, 6, 15, 16, 0, 0)


def test_bundle_has_all_pieces_and_decision_log(cfg: AppConfig) -> None:
    pf = load_portfolio(cfg)
    b = run_decision_engine(cfg, pf.accounts, pf.holdings, "run1", _TS)
    assert b.holding_decisions and b.opportunities and b.leaps and b.covered_calls
    assert b.momentum and b.execution and b.decision_log
    # every log entry carries a confidence and an action
    assert all(0.0 <= e.confidence <= 1.0 for e in b.decision_log)
    assert all(e.candidate_action for e in b.decision_log)


def test_every_decision_carries_adversarial_audit(cfg: AppConfig) -> None:
    pf = load_portfolio(cfg)
    b = run_decision_engine(cfg, pf.accounts, pf.holdings, "run1", _TS)
    assert all(d.adversarial_audit for d in b.holding_decisions)
    assert all(o.adversarial_audit for o in b.opportunities)


def test_replacement_overlap_and_improvement(cfg: AppConfig) -> None:
    pf = load_portfolio(cfg)
    incumbent = next(h for h in pf.holdings if h.ticker == "QQQM")
    rc = compare_replacement(cfg, incumbent, "SMH")
    assert isinstance(rc.improves_expected_return, bool)
    assert isinstance(rc.overlap_flag, bool)
    assert rc.best_funding_source
    # SMH vs QQQM are both AI/tech -> funding should not come from the protected base
    assert (
        "protected" not in rc.best_funding_source.lower()
        or "never" not in rc.best_funding_source.lower()
    )


def test_opportunities_add_positive_trend_leaders(cfg: AppConfig) -> None:
    pf = load_portfolio(cfg)
    b = run_decision_engine(cfg, pf.accounts, pf.holdings, "run1", _TS)
    adds = [o for o in b.opportunities if o.candidate_action.value == "add"]
    assert adds  # at least one positive-trend leader surfaces as ADD
    assert all(o.confidence > 0 for o in adds)
