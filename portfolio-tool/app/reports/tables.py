"""Build the CSV report tables from a DecisionBundle.

Action tokens are rendered through the compliance layer so ``compliance_mode:
strict`` maps them to neutral candidate labels at the schema->report boundary.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from app.data.contracts import DecisionLogEntry, ReplacementCandidate
from app.decision_engine import DecisionBundle
from app.reports.compliance import render_action

Table = tuple[list[str], list[dict[str, Any]]]


def holdings_table(bundle: DecisionBundle, compliance_mode: str) -> Table:
    cols = [
        "ticker",
        "account",
        "candidate_action",
        "confidence",
        "triage",
        "total_score",
        "role",
        "rationale",
        "data_quality_flags",
        "next_monitoring_trigger",
    ]
    rows = [
        {
            "ticker": d.ticker,
            "account": d.account_id,
            "candidate_action": render_action(d.candidate_action, compliance_mode),
            "confidence": round(d.confidence, 2),
            "triage": d.triage.value,
            "total_score": round(d.total_score, 1),
            "role": d.role.value if d.role else "",
            "rationale": d.rationale,
            "data_quality_flags": ";".join(sorted({w.code for w in d.data_quality_warnings})),
            "next_monitoring_trigger": d.next_monitoring_trigger,
        }
        for d in bundle.holding_decisions
    ]
    return cols, rows


def opportunities_table(bundle: DecisionBundle, compliance_mode: str) -> Table:
    cols = ["ticker", "thesis_bucket", "candidate_action", "confidence", "total_score", "rationale"]
    rows = [
        {
            "ticker": o.ticker,
            "thesis_bucket": o.thesis_bucket or "",
            "candidate_action": render_action(o.candidate_action, compliance_mode),
            "confidence": round(o.confidence, 2),
            "total_score": round(o.total_score, 1),
            "rationale": o.rationale,
        }
        for o in bundle.opportunities
    ]
    return cols, rows


def replacement_table(candidates: Sequence[ReplacementCandidate]) -> Table:
    cols = [
        "incumbent",
        "candidate",
        "improves_return",
        "improves_risk",
        "improves_clarity",
        "improves_goal_fit",
        "overlap",
        "best_funding_source",
        "score_delta",
        "rationale",
    ]
    rows = [
        {
            "incumbent": r.incumbent_ticker,
            "candidate": r.candidate_ticker,
            "improves_return": r.improves_expected_return,
            "improves_risk": r.improves_risk,
            "improves_clarity": r.improves_clarity,
            "improves_goal_fit": r.improves_goal_fit,
            "overlap": r.overlap_flag,
            "best_funding_source": r.best_funding_source,
            "score_delta": round(r.score_delta, 4),
            "rationale": r.rationale,
        }
        for r in candidates
    ]
    return cols, rows


def leaps_table(bundle: DecisionBundle, compliance_mode: str) -> Table:
    cols = [
        "underlying",
        "expiration",
        "strike",
        "delta",
        "premium",
        "cost",
        "max_loss",
        "breakeven",
        "pct_net_worth",
        "pct_leaps_budget",
        "remaining_budget_after",
        "px_2x",
        "px_3x",
        "px_5x",
        "ai_overlap",
        "open_interest",
        "months_to_expiry",
        "momentum_tag",
        "trend_on",
        "total_score",
        "candidate_action",
    ]
    rows = [
        {
            "underlying": c.underlying,
            "expiration": c.expiration.isoformat(),
            "strike": str(c.strike),
            "delta": c.delta,
            "premium": str(c.premium),
            "cost": str(c.cost),
            "max_loss": str(c.max_loss),
            "breakeven": str(c.breakeven),
            "pct_net_worth": round(c.premium_pct_net_worth, 4),
            "pct_leaps_budget": round(c.premium_pct_leaps_budget, 4),
            "remaining_budget_after": str(c.remaining_budget_after),
            "px_2x": str(c.px_2x),
            "px_3x": str(c.px_3x),
            "px_5x": str(c.px_5x),
            "ai_overlap": c.ai_overlap,
            "open_interest": c.open_interest,
            "months_to_expiry": round(c.months_to_expiry, 1),
            "momentum_tag": c.momentum_tag.value,
            "trend_on": c.trend_on,
            "total_score": round(c.total_score, 1),
            "candidate_action": render_action(c.candidate_action, compliance_mode),
        }
        for c in bundle.leaps
    ]
    return cols, rows


def covered_call_table(bundle: DecisionBundle, compliance_mode: str) -> Table:
    cols = [
        "ticker",
        "account",
        "expiration",
        "strike",
        "delta",
        "premium",
        "premium_income",
        "effective_exit_if_assigned",
        "effective_basis_if_not",
        "dividend_amount",
        "early_assignment_risk",
        "buyback_target",
        "classification",
        "momentum_tag",
        "annualized_yield",
        "total_score",
        "candidate_action",
    ]
    rows = [
        {
            "ticker": c.ticker,
            "account": c.account_id,
            "expiration": c.expiration.isoformat(),
            "strike": str(c.strike),
            "delta": c.delta,
            "premium": str(c.premium),
            "premium_income": str(c.premium_income),
            "effective_exit_if_assigned": str(c.effective_exit_if_assigned)
            if c.effective_exit_if_assigned
            else "",
            "effective_basis_if_not": str(c.effective_basis_if_not)
            if c.effective_basis_if_not
            else "",
            "dividend_amount": str(c.dividend_amount) if c.dividend_amount else "",
            "early_assignment_risk": c.early_assignment_risk,
            "buyback_target": str(c.buyback_target),
            "classification": c.classification,
            "momentum_tag": c.momentum_tag.value,
            "annualized_yield": round(c.annualized_yield, 4),
            "total_score": round(c.total_score, 1),
            "candidate_action": render_action(c.candidate_action, compliance_mode),
        }
        for c in bundle.covered_calls
    ]
    return cols, rows


def momentum_table(bundle: DecisionBundle) -> Table:
    cols = [
        "ticker",
        "ts_momentum_12_1",
        "blended_momentum",
        "cross_sectional_rank",
        "trend_filter_on",
        "realized_vol",
        "target_weight",
        "momentum_tag",
        "persistent_breach",
    ]
    rows = [
        {
            "ticker": s.ticker,
            "ts_momentum_12_1": round(s.ts_momentum_12_1, 4),
            "blended_momentum": round(s.blended_momentum, 4),
            "cross_sectional_rank": s.cross_sectional_rank,
            "trend_filter_on": s.trend_filter_on,
            "realized_vol": round(s.realized_vol, 4),
            "target_weight": round(s.target_weight, 4),
            "momentum_tag": s.momentum_tag.value,
            "persistent_breach": s.persistent_breach,
        }
        for s in bundle.momentum
    ]
    return cols, rows


def execution_table(bundle: DecisionBundle) -> Table:
    cols = ["ticker", "status", "rationale", "timing_only"]
    rows = [
        {
            "ticker": e.ticker,
            "status": e.status.value,
            "rationale": e.rationale,
            "timing_only": e.timing_only,
        }
        for e in bundle.execution
    ]
    return cols, rows


def decision_log_table(log: list[DecisionLogEntry], compliance_mode: str) -> Table:
    cols = [
        "run_id",
        "timestamp",
        "module",
        "ticker",
        "account",
        "candidate_action",
        "confidence",
        "score_components",
        "key_assumptions",
        "data_quality_flags",
        "source_files_or_api_timestamp",
        "memo_path",
    ]
    rows = [
        {
            "run_id": e.run_id,
            "timestamp": e.timestamp.isoformat(),
            "module": e.module,
            "ticker": e.ticker,
            "account": e.account or "",
            "candidate_action": render_action(e.candidate_action, compliance_mode),
            "confidence": round(e.confidence, 2),
            "score_components": ";".join(f"{k}={v:.2f}" for k, v in e.score_components.items()),
            "key_assumptions": e.key_assumptions,
            "data_quality_flags": e.data_quality_flags,
            "source_files_or_api_timestamp": e.source_files_or_api_timestamp,
            "memo_path": e.memo_path or "",
        }
        for e in log
    ]
    return cols, rows
