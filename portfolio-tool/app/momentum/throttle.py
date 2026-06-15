"""Macro throttle — the brake/sizing system, and the momentum/macro conflict rule.

The user's 8-indicator framework maps to a 0-100% gross-exposure multiplier with
persistence thresholds. CONFLICT RULE (final): when momentum says press and macro
says brake, the BRAKE WINS ON SIZING and the ENGINE WINS ON SELECTION — reduce gross
exposure per the throttle but keep the residual in the highest-momentum names.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config import AppConfig
from app.data.contracts import MomentumSignal, ThrottleState
from app.data.fixtures import load_macro_state


def macro_throttle(
    scores: dict[str, float], persistence_months: dict[str, int], required: int
) -> ThrottleState:
    """Mean of indicator scores -> gross-exposure multiplier in [0, 1]. The brake is
    'persistent' when a risk-off indicator has held for >= ``required`` months."""
    if not scores:
        return ThrottleState(gross_exposure_multiplier=1.0, persistent=False, brake_active=False)
    mult = max(0.0, min(1.0, sum(scores.values()) / len(scores)))
    persistent = any(
        s < 0.5 and persistence_months.get(k, 0) >= required for k, s in scores.items()
    )
    return ThrottleState(
        gross_exposure_multiplier=mult,
        indicator_scores=dict(scores),
        persistent=persistent,
        brake_active=mult < 0.999,
    )


def load_throttle(cfg: AppConfig) -> ThrottleState:
    raw = load_macro_state()
    indicators = raw.get("indicators", {})
    scores = {k: float(v["score"]) for k, v in indicators.items()}
    persistence = {k: int(v.get("persistence_months", 0)) for k, v in indicators.items()}
    return macro_throttle(scores, persistence, cfg.momentum.throttle_persistence_months)


@dataclass(frozen=True)
class ConflictResolution:
    sized_weights: dict[str, float]  # brake applied to sizing
    selection: list[str]  # engine keeps selection (highest-momentum first)
    gross_before: float
    gross_after: float
    brake_applied: bool


def apply_conflict_rule(
    signals: list[MomentumSignal], throttle: ThrottleState
) -> ConflictResolution:
    """Brake wins on sizing; engine wins on selection."""
    mult = throttle.gross_exposure_multiplier
    selection = [s.ticker for s in sorted(signals, key=lambda x: x.blended_momentum, reverse=True)]
    sized = {s.ticker: s.target_weight * mult for s in signals}
    gross_before = sum(s.target_weight for s in signals)
    return ConflictResolution(
        sized_weights=sized,
        selection=selection,
        gross_before=gross_before,
        gross_after=sum(sized.values()),
        brake_applied=mult < 0.999,
    )
