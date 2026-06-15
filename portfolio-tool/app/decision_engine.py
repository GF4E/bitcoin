"""Decision engine — combine every signal into a consolidated decision set.

Combines holding scores, opportunity scores, momentum + macro throttle, execution
timing, the scenario trees, and the adversarial audits. Every decision carries the
full envelope; if a decision depends on incomplete data the upstream evaluators
emit gather_more_data / wait rather than an overconfident action.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.config import AppConfig
from app.data.contracts import (
    DataQualityWarning,
    DecisionLogEntry,
    ExecutionSignal,
    Holding,
    HoldingDecision,
    MomentumSignal,
    OpportunityDecision,
    ThrottleState,
)
from app.execution.vwap import vwap_signal
from app.momentum.engine import run_momentum
from app.momentum.throttle import load_throttle
from app.opportunities.screener import screen_opportunities
from app.options.covered_call_engine import CoveredCallCandidate, screen_covered_calls
from app.options.leaps_screener import LeapsCandidate, screen_leaps
from app.portfolio.exposure import ExposureReport, compute_exposure
from app.portfolio.holding_evaluator import evaluate_holdings
from app.portfolio.reconciliation import AccountReconciliation, reconcile


@dataclass
class DecisionBundle:
    exposure: ExposureReport
    reconciliation: list[AccountReconciliation]
    holding_decisions: list[HoldingDecision]
    opportunities: list[OpportunityDecision]
    leaps: list[LeapsCandidate]
    covered_calls: list[CoveredCallCandidate]
    momentum: list[MomentumSignal]
    throttle: ThrottleState
    execution: list[ExecutionSignal]
    recon_warnings: list[DataQualityWarning] = field(default_factory=list)
    decision_log: list[DecisionLogEntry] = field(default_factory=list)


def _flags(warnings: list) -> str:
    return ";".join(sorted({w.code for w in warnings})) if warnings else ""


def compile_decision_log(
    run_id: str,
    ts: datetime,
    holding_decisions: list[HoldingDecision],
    opportunities: list[OpportunityDecision],
    leaps: list[LeapsCandidate],
    covered_calls: list[CoveredCallCandidate],
) -> list[DecisionLogEntry]:
    log: list[DecisionLogEntry] = []
    for d in holding_decisions:
        log.append(
            DecisionLogEntry(
                run_id=run_id,
                timestamp=ts,
                module="holding_evaluator",
                ticker=d.ticker,
                account=d.account_id,
                candidate_action=d.candidate_action,
                confidence=d.confidence,
                score_components=d.score_components,
                key_assumptions=";".join(a.name for a in d.assumptions),
                data_quality_flags=_flags(d.data_quality_warnings),
                source_files_or_api_timestamp="mock_fixtures",
            )
        )
    for o in opportunities:
        log.append(
            DecisionLogEntry(
                run_id=run_id,
                timestamp=ts,
                module="opportunity_screener",
                ticker=o.ticker,
                candidate_action=o.candidate_action,
                confidence=o.confidence,
                score_components=o.score_components,
                key_assumptions=o.thesis_bucket or "",
                source_files_or_api_timestamp="mock_fixtures",
            )
        )
    for lc in leaps:
        log.append(
            DecisionLogEntry(
                run_id=run_id,
                timestamp=ts,
                module="leaps_screener",
                ticker=f"{lc.underlying} {lc.expiration} C{lc.strike}",
                candidate_action=lc.candidate_action,
                confidence=min(lc.total_score / 100.0, 1.0),
                score_components=lc.score_components,
                data_quality_flags=";".join(lc.data_quality_warnings),
                source_files_or_api_timestamp="mock_fixtures",
            )
        )
    for cc in covered_calls:
        log.append(
            DecisionLogEntry(
                run_id=run_id,
                timestamp=ts,
                module="covered_call_engine",
                ticker=f"{cc.ticker} {cc.expiration} C{cc.strike}",
                account=cc.account_id,
                candidate_action=cc.candidate_action,
                confidence=min(cc.total_score / 100.0, 1.0),
                score_components=cc.score_components,
                data_quality_flags=";".join(cc.data_quality_warnings),
                source_files_or_api_timestamp="mock_fixtures",
            )
        )
    return log


def run_decision_engine(
    cfg: AppConfig, accounts: list, holdings: list[Holding], run_id: str, ts: datetime
) -> DecisionBundle:
    exposure = compute_exposure(cfg, holdings)
    recon, recon_warnings = reconcile(cfg, accounts, holdings)
    covered_calls = screen_covered_calls(cfg, holdings)
    # the holdings view defers to the screener so it never suggests a call without a
    # real writable contract.
    holding_decisions = evaluate_holdings(cfg, holdings, {c.ticker for c in covered_calls})
    opportunities = screen_opportunities(cfg, holdings)
    leaps = screen_leaps(cfg)
    momentum = run_momentum(cfg)
    throttle = load_throttle(cfg)
    held = sorted({(h.underlying or h.ticker) for h in holdings if h.market_value})
    execution = [vwap_signal(cfg, t) for t in held]
    log = compile_decision_log(run_id, ts, holding_decisions, opportunities, leaps, covered_calls)
    return DecisionBundle(
        exposure=exposure,
        reconciliation=recon,
        holding_decisions=holding_decisions,
        opportunities=opportunities,
        leaps=leaps,
        covered_calls=covered_calls,
        momentum=momentum,
        throttle=throttle,
        execution=execution,
        recon_warnings=recon_warnings,
        decision_log=log,
    )
