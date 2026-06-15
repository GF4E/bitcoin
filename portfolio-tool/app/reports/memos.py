"""Trade-memo builders (13 sections + LEAPS / covered-call extras).

Sections: 1 Summary, 2 Fit with terminal-wealth plan (and 5M milestone timing),
3 Portfolio overlap, 4 Budget/risk impact, 5 Breakeven and 2x/3x/5x or repair math,
6 Bull/base/bear scenario tree, 7 Path-dependent management, 8 Alternatives/
rotations, 9 Sizing or source-of-funds, 10 Candidate action, 11 Adversarial audit,
12 Data-quality warnings, 13 Assumptions and disclaimers.
"""

from __future__ import annotations

from app.config import AppConfig
from app.data.contracts import TradeMemo
from app.options.covered_call_engine import CoveredCallCandidate
from app.options.leaps_screener import LeapsCandidate
from app.reports.compliance import render_action
from app.reports.markdown import DISCLAIMER, fmt_money, fmt_pct


def build_leaps_memo(cfg: AppConfig, c: LeapsCandidate) -> TradeMemo:
    extras = (
        f"- Max premium loss: {fmt_money(c.max_loss)}\n"
        f"- % LEAPS budget: {fmt_pct(c.premium_pct_leaps_budget)}; % net worth: {fmt_pct(c.premium_pct_net_worth)}\n"
        f"- Delta-adjusted notional: {fmt_money(c.delta_adjusted_notional)}; AI/tech/semi overlap: {c.ai_overlap}\n"
        f"- 2x/3x/5x underlying targets: {fmt_money(c.px_2x)} / {fmt_money(c.px_3x)} / {fmt_money(c.px_5x)}\n"
    )
    sections = {
        "1_summary": f"Stock-replacement LEAP on {c.underlying} {c.expiration} C{c.strike} "
        f"(delta {c.delta:.2f}), premium {fmt_money(c.premium)} x{c.contracts}, cost {fmt_money(c.cost)}.",
        "2_fit_with_plan": f"Momentum tag {c.momentum_tag.value}, trend {'on' if c.trend_on else 'off'}. "
        "LEAPS-as-stock-replacement only on positive-trend leaders; supports terminal-wealth "
        "via leveraged participation, not income.",
        "3_portfolio_overlap": f"AI/tech/semi overlap: {c.ai_overlap}. Adds to the concentrated single-factor wager.",
        "4_budget_risk_impact": f"Premium {fmt_pct(c.premium_pct_leaps_budget)} of the LEAPS budget; remaining after "
        f"{fmt_money(c.remaining_budget_after)}. Single-LEAP within the configured ceiling.",
        "5_breakeven_targets": f"Breakeven {fmt_money(c.breakeven)}; intrinsic {fmt_money(c.intrinsic)}, "
        f"extrinsic {fmt_money(c.extrinsic)}.\n" + extras,
        "6_scenario_tree": "Bull: 2x/3x/5x targets above. Base: holds delta-adjusted exposure. "
        "Bear: max loss capped at the premium; roll 3-6 months before expiry.",
        "7_path_dependent": "Roll 3-6 months before expiration; do not let theta accelerate into the last months. "
        "Tax: >1yr holds favored.",
        "8_alternatives": "Alternatives: hold the underlying shares (no leverage), or a lower-delta lottery (rejected "
        "for stock-replacement use).",
        "9_sizing_source_of_funds": "Fund from the LEAPS premium budget; never from the protected base. Size to the "
        "max-single-new and weekly caps.",
        "10_candidate_action": f"Candidate action: {render_action(c.candidate_action, cfg.settings.compliance_mode)} "
        f"(score {c.total_score:.0f}, {c.triage.value}). {c.rationale}",
        "11_adversarial_audit": "What did this miss: a momentum crash hits leveraged leaders hardest exactly when the "
        "macro throttle brakes; IV crush on the long option; the trend filter can whipsaw.",
        "12_data_quality": "; ".join(c.data_quality_warnings) or "none",
        "13_assumptions_disclaimers": "Capture/Greeks from sample fixtures in mock mode (estimated). "
        + DISCLAIMER,
    }
    return TradeMemo(
        ticker=c.underlying,
        memo_type="leaps",
        title=f"LEAPS {c.underlying} {c.expiration} C{c.strike}",
        sections=sections,
        candidate_action=c.candidate_action,
    )


def build_covered_call_memo(cfg: AppConfig, c: CoveredCallCandidate) -> TradeMemo:
    extras = (
        f"- Avg cost: {fmt_money(c.avg_cost) if c.avg_cost else 'unknown'}; "
        f"effective exit if assigned: {fmt_money(c.effective_exit_if_assigned) if c.effective_exit_if_assigned else 'n/a'}\n"
        f"- Effective basis after premium: {fmt_money(c.effective_basis_if_not) if c.effective_basis_if_not else 'n/a'}\n"
        f"- Buyback target (60-70% capture): {fmt_money(c.buyback_target)}; never roll below the repaired basis\n"
        f"- Early-assignment/dividend risk: {c.early_assignment_risk}; leader/ballast tag: {c.momentum_tag.value}; "
        f"classification: {c.classification}\n"
    )
    sections = {
        "1_summary": f"{c.classification} covered call on ballast {c.ticker} {c.expiration} C{c.strike} "
        f"(delta {c.delta:.2f}), premium {fmt_money(c.premium)}, income {fmt_money(c.premium_income)}.",
        "2_fit_with_plan": "Ballast you would accept being called away; income/repair without capping a winner. "
        "Does not impair terminal-wealth participation.",
        "3_portfolio_overlap": f"Single-name overlay on {c.ticker}; {c.max_contracts} clean contracts.",
        "4_budget_risk_impact": f"Premium income {fmt_money(c.premium_income)}; annualized yield {fmt_pct(c.annualized_yield)}.",
        "5_repair_math": extras,
        "6_scenario_tree": "\n".join(f"- {k}: {v}" for k, v in c.scenario_tree.items()),
        "7_path_dependent": "Assignment/dividends/roll/buyback/resell per the scenario tree; default buyback at "
        "60-70% capture; never roll below the repaired basis unless config permits a below-basis exit.",
        "8_alternatives": "Alternatives: hold uncovered (full upside), or sell shares outright if the thesis is broken.",
        "9_sizing_source_of_funds": f"Size to {c.max_contracts} contracts (100 shares each); no new capital required.",
        "10_candidate_action": f"Candidate action: {render_action(c.candidate_action, cfg.settings.compliance_mode)} "
        f"(score {c.total_score:.0f}, {c.triage.value}). {c.rationale}",
        "11_adversarial_audit": "What did this miss: a sharp rally caps the upside (devil's bargain); early assignment "
        "around a dividend; the leader/ballast tag is momentum-derived and can lag a regime change.",
        "12_data_quality": "; ".join(c.data_quality_warnings) or "none",
        "13_assumptions_disclaimers": "Greeks/quotes from sample fixtures in mock mode (estimated). "
        + DISCLAIMER,
    }
    return TradeMemo(
        ticker=c.ticker,
        memo_type="covered_call",
        title=f"Covered call {c.ticker} {c.expiration} C{c.strike}",
        sections=sections,
        candidate_action=c.candidate_action,
    )


def render_memo(memo: TradeMemo) -> str:
    lines = [f"# Trade Memo — {memo.title}\n", f"_Type: {memo.memo_type}_\n"]
    for key, body in memo.sections.items():
        heading = key.split("_", 1)[1].replace("_", " ").title()
        lines.append(f"## {key.split('_', 1)[0]}. {heading}\n\n{body}\n")
    return "\n".join(lines)
