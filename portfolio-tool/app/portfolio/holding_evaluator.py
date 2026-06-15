"""Holding evaluator — a full decision envelope per holding.

Every decision carries candidate_action, confidence, rationale,
supporting_calculations, score_components, assumptions, data_quality_warnings,
what_would_change_the_decision, next_monitoring_trigger, triage, and an
adversarial audit. If a decision depends on incomplete data it degrades to
gather_more_data / wait — never an overconfident action.
"""

from __future__ import annotations

from app.config import AppConfig
from app.data.contracts import (
    ActionToken,
    Assumption,
    DataLabel,
    DataQualityWarning,
    Holding,
    HoldingDecision,
    MomentumTag,
    Severity,
    Sleeve,
    Triage,
)
from app.momentum.engine import compute_signals
from app.money import pct_of


def _fit_with_plan(h: Holding) -> float:
    return {
        "core": 0.9,
        "growth": 0.9,
        "income": 0.7,
        "hedge": 0.6,
        "repair": 0.6,
        "tactical": 0.55,
        "cash_reserve": 0.5,
        "speculative": 0.4,
    }.get(h.role.value if h.role else "", 0.6)


def evaluate_holdings(
    cfg: AppConfig, holdings: list[Holding], writable_tickers: set[str] | None = None
) -> list[HoldingDecision]:
    weights = cfg.scoring_weights.get("holding", {})
    net_worth = cfg.risk_budget.net_worth_total
    if writable_tickers is None:
        # Defer to the covered-call screener so the holdings view never suggests a
        # call on something without a real writable contract (cash, no-options ETFs,
        # external holdings). Local import avoids a module-load cycle.
        from app.options.covered_call_engine import screen_covered_calls

        writable_tickers = {c.ticker for c in screen_covered_calls(cfg, holdings)}
    tickers = sorted({(h.underlying or h.ticker) for h in holdings})
    tags = {s.ticker: s for s in compute_signals(cfg, tickers)}
    sleeve_counts: dict[Sleeve, int] = {}
    for h in holdings:
        sleeve_counts[h.sleeve] = sleeve_counts.get(h.sleeve, 0) + 1

    out: list[HoldingDecision] = []
    for h in holdings:
        key = h.underlying or h.ticker
        sig = tags.get(key)
        tag = sig.momentum_tag if sig else MomentumTag.NEUTRAL
        trend_on = sig.trend_filter_on if sig else False
        pct_nw = pct_of(h.market_value, net_worth) if h.market_value is not None else 0.0
        is_ai = cfg.is_ai_tech_semi(key)
        upl = h.unrealized_gain_loss

        comp = {
            "fit_with_plan": _fit_with_plan(h),
            "role_clarity": 1.0 if h.role is not None else 0.5,
            "concentration": 1.0 - (min(pct_nw / 0.10, 1.0) * 0.5 if is_ai else 0.0),
            "overlap_redundancy": 0.5 if sleeve_counts.get(h.sleeve, 0) > 2 else 0.9,
            "opportunity_cost": 0.9
            if tag is MomentumTag.LEADER
            else (0.4 if tag is MomentumTag.BALLAST else 0.6),
            "unrealized_pl": 0.8
            if (upl is not None and upl > 0)
            else (0.4 if upl is not None else 0.5),
            "thesis_quality": 0.9 if (tag is MomentumTag.LEADER and trend_on) else 0.6,
        }
        total = sum(weights.get(k, 0.0) * v for k, v in comp.items())

        warnings = [
            DataQualityWarning(
                code=f, message=f"{h.ticker}: {f}", severity=Severity.WARN, ticker=h.ticker, field=f
            )
            for f in h.data_quality_flags
        ]
        action, triage, conf, rationale, monitor, audit = _decide(
            h, tag, trend_on, pct_nw, total, is_ai, h.ticker in writable_tickers
        )

        out.append(
            HoldingDecision(
                ticker=h.ticker,
                account_id=h.account_id,
                role=h.role,
                total_score=total,
                candidate_action=action,
                confidence=conf,
                triage=triage,
                rationale=rationale,
                supporting_calculations={
                    "market_value": str(h.market_value),
                    "pct_net_worth": round(pct_nw, 4),
                    "unrealized_gain_loss": str(upl),
                    "momentum_tag": tag.value,
                    "trend_filter_on": trend_on,
                },
                score_components=comp,
                assumptions=[
                    Assumption(
                        name="momentum_tag",
                        value=tag.value,
                        label=DataLabel.ESTIMATED,
                        load_bearing=True,
                        rationale="From the momentum engine on sample price history.",
                    ),
                ],
                data_quality_warnings=warnings,
                what_would_change_the_decision=(
                    "A trend-filter flip, a persistent momentum breach, or a concentration move "
                    "through the 40% banner threshold."
                ),
                next_monitoring_trigger=monitor,
                adversarial_audit=audit,
            )
        )
    return out


def _decide(
    h: Holding,
    tag: MomentumTag,
    trend_on: bool,
    pct_nw: float,
    score: float,
    is_ai: bool,
    writable: bool,
) -> tuple[ActionToken, Triage, float, str, str, str]:
    if "missing_cost_basis" in h.data_quality_flags or "missing_price" in h.data_quality_flags:
        return (
            ActionToken.GATHER_MORE_DATA,
            Triage.GATHER_MORE_DATA,
            0.30,
            "Incomplete data (missing cost basis or price); cannot evaluate confidently.",
            "Refresh cost basis / quote.",
            "Could be over- or under-valued; the missing field is load-bearing.",
        )
    if tag is MomentumTag.LEADER and trend_on:
        return (
            ActionToken.HOLD,
            Triage.WAIT,
            0.72,
            f"Positive-trend momentum leader; let it run (do not cap with calls). Score {score:.0f}.",
            "Monthly momentum + 200-DMA trend filter.",
            "Concentration adds to a single-factor AI wager; a momentum crash would hit hardest here.",
        )
    if (
        tag is MomentumTag.BALLAST
        and writable
        and (h.unrealized_gain_loss is None or h.unrealized_gain_loss >= 0)
    ):
        return (
            ActionToken.WRITE_CALL,
            Triage.WAIT,
            0.6,
            "Ballast holding you would accept being called away; a <=0.15-delta covered call adds income.",
            "Premium decay / 60-70% capture buyback window.",
            "Caps upside if it unexpectedly rallies; acceptable for ballast only.",
        )
    if is_ai and pct_nw > 0.10 and tag is not MomentumTag.LEADER:
        return (
            ActionToken.TRIM,
            Triage.WAIT,
            0.58,
            f"Large AI/tech/semi position ({pct_nw:.1%} of NW) without leader-grade momentum; trim to fund clarity.",
            "Concentration banner / momentum rank.",
            "Trimming a future winner is the risk; size the trim, do not exit wholesale.",
        )
    if tag is MomentumTag.BALLAST:
        return (
            ActionToken.HOLD,
            Triage.WAIT,
            0.55,
            "Ballast holding, but no writable covered-call candidate this run "
            "(no shares position with a liquid <=0.15-delta strike); hold and monitor.",
            "Watch for an actionable <=0.15-delta strike or a momentum/trend change.",
            "Doing nothing forgoes potential income; revisit when a clean strike appears.",
        )
    return (
        ActionToken.HOLD,
        Triage.WAIT,
        0.55,
        f"No clear edge to act; hold and monitor. Score {score:.0f}.",
        "Monthly momentum + concentration review.",
        "Holding by default can mask slow drift; revisit on the next monitoring trigger.",
    )
