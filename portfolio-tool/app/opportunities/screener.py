"""Opportunity screener — generalized candidate evaluation.

Per candidate: thesis bucket, quality, trend/momentum, overlap, complement vs
duplicate, best funding source, and whether it improves expected return / risk /
clarity / goal-fit. AI/semi additions are funded from capped-upside income or
excess broad growth — never from the protected base.
"""

from __future__ import annotations

from app.config import AppConfig
from app.data.contracts import (
    ActionToken,
    Assumption,
    DataLabel,
    Holding,
    MomentumTag,
    OpportunityDecision,
    Sleeve,
    Triage,
)
from app.momentum.engine import compute_signals


def screen_opportunities(cfg: AppConfig, holdings: list[Holding]) -> list[OpportunityDecision]:
    universe = cfg.watchlists.get("opportunity_universe", [])
    held_sleeves: dict[Sleeve, int] = {}
    for h in holdings:
        held_sleeves[h.sleeve] = held_sleeves.get(h.sleeve, 0) + 1
    held_tickers = {(h.underlying or h.ticker) for h in holdings}
    sigs = {s.ticker: s for s in compute_signals(cfg, sorted(set(universe)))}

    out: list[OpportunityDecision] = []
    for ticker in universe:
        sig = sigs.get(ticker)
        tag = sig.momentum_tag if sig else MomentumTag.NEUTRAL
        trend_on = sig.trend_filter_on if sig else False
        sleeve = cfg.sleeve_for(ticker)
        duplicate = ticker in held_tickers
        crowded = held_sleeves.get(sleeve, 0) >= 3

        comp = {
            "thesis_quality": 0.9 if (tag is MomentumTag.LEADER and trend_on) else 0.5,
            "trend_momentum": 0.9 if trend_on else 0.3,
            "valuation_risk": 0.5,  # neutral without fundamentals in mock mode
            "complement_vs_duplicate": 0.3 if duplicate else (0.5 if crowded else 0.9),
            "liquidity": 0.8,
        }
        weights = cfg.scoring_weights.get("opportunity", {})
        total = sum(weights.get(k, 0.0) * v for k, v in comp.items())

        if duplicate:
            action, triage, conf = ActionToken.HOLD, Triage.WAIT, 0.5
            rationale = f"Already held; not a new opportunity. Consider sizing, not adding a duplicate {sleeve.value} name."
        elif tag is MomentumTag.LEADER and trend_on and total >= 60:
            action, triage, conf = ActionToken.ADD, Triage.WAIT, 0.62
            rationale = (
                f"Positive-trend leader in {sleeve.value}; rotate INTO from capped-upside income or "
                "excess broad growth — never the protected base."
            )
        else:
            action, triage, conf = ActionToken.WAIT, Triage.WAIT, 0.5
            rationale = "Momentum/trend not confirmed; wait for a persistent breach."

        out.append(
            OpportunityDecision(
                ticker=ticker,
                thesis_bucket=sleeve.value,
                total_score=total,
                candidate_action=action,
                confidence=conf,
                triage=triage,
                rationale=rationale,
                score_components=comp,
                supporting_calculations={
                    "momentum_tag": tag.value,
                    "trend_filter_on": trend_on,
                    "duplicate_of_holding": duplicate,
                },
                assumptions=[
                    Assumption(
                        name="funding_source",
                        value="covered_call_income or excess broad_core",
                        label=DataLabel.ASSUMED,
                        rationale="Never fund AI adds from the protected base.",
                    ),
                ],
                what_would_change_the_decision="A trend-filter flip or a valuation signal (needs fundamentals).",
                next_monitoring_trigger="Monthly cross-sectional momentum rank.",
                adversarial_audit="Mock mode lacks valuation/fundamental data; thesis quality is momentum-only.",
            )
        )
    out.sort(key=lambda d: d.total_score, reverse=True)
    return out
