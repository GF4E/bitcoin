"""Replacement engine — should candidate X replace incumbent Y?

Evaluates whether a rotation improves expected return / risk / liquidity / clarity /
goal-fit, flags overlap, and names the best funding source. Fund AI/semi additions
from capped-upside income or excess broad growth, never the protected base.
"""

from __future__ import annotations

from app.config import AppConfig
from app.data.contracts import Holding, MomentumTag, ReplacementCandidate
from app.momentum.engine import compute_signals


def compare_replacement(
    cfg: AppConfig, incumbent: Holding, candidate_ticker: str
) -> ReplacementCandidate:
    inc_key = incumbent.underlying or incumbent.ticker
    sigs = {s.ticker: s for s in compute_signals(cfg, sorted({inc_key, candidate_ticker}))}
    inc = sigs.get(inc_key)
    cand = sigs.get(candidate_ticker)

    inc_mom = inc.blended_momentum if inc else 0.0
    cand_mom = cand.blended_momentum if cand else 0.0
    inc_vol = inc.realized_vol if inc else 1.0
    cand_vol = cand.realized_vol if cand else 1.0

    same_sleeve = cfg.sleeve_for(inc_key) is cfg.sleeve_for(candidate_ticker)
    improves_return = cand_mom > inc_mom
    improves_risk = cand_vol < inc_vol
    improves_clarity = (cand.momentum_tag is MomentumTag.LEADER) if cand else False
    improves_goal_fit = improves_return and (cand.trend_filter_on if cand else False)

    score_delta = (cand_mom - inc_mom) - 0.5 * (cand_vol - inc_vol)
    funding = (
        "covered_call_income or excess broad_core"
        if cfg.is_ai_tech_semi(candidate_ticker)
        else "rotation within sleeve"
    )

    return ReplacementCandidate(
        incumbent_ticker=incumbent.ticker,
        candidate_ticker=candidate_ticker,
        improves_expected_return=improves_return,
        improves_risk=improves_risk,
        improves_liquidity=True,  # both liquid in the configured universe
        improves_clarity=improves_clarity,
        improves_goal_fit=improves_goal_fit,
        overlap_flag=same_sleeve,
        best_funding_source=funding,
        rationale=(
            f"{candidate_ticker} momentum {cand_mom:+.2f} vs {incumbent.ticker} {inc_mom:+.2f}; "
            f"vol {cand_vol:.2f} vs {inc_vol:.2f}. "
            + (
                "Overlapping sleeve — rotation, not diversification."
                if same_sleeve
                else "Cross-sleeve rotation."
            )
        ),
        score_delta=score_delta,
    )
