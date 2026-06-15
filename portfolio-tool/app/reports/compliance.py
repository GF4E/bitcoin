"""compliance_mode functional at the render boundary (critical correction #5).

When ``compliance_mode: strict``, internal action tokens are mapped to neutral
"candidate" labels at render time — the engines still reason in action tokens; only
the *output* changes. Tested at the schema->report boundary
(tests/unit/test_compliance.py).
"""

from __future__ import annotations

from app.data.contracts import ActionToken

# Internal token -> neutral candidate label (strict mode).
_NEUTRAL: dict[ActionToken, str] = {
    ActionToken.ADD: "candidate_for_increase",
    ActionToken.TRIM: "candidate_for_reduction",
    ActionToken.EXIT: "candidate_for_full_reduction",
    ActionToken.HOLD: "no_change_indicated",
    ActionToken.OPEN_LEAP: "leveraged_exposure_candidate",
    ActionToken.WRITE_CALL: "income_overlay_candidate",
    ActionToken.ROLL: "position_adjustment_candidate",
    ActionToken.BUYBACK: "overlay_close_candidate",
    ActionToken.REPLACE: "rotation_candidate",
    ActionToken.GATHER_MORE_DATA: "insufficient_data",
    ActionToken.WAIT: "no_action_indicated",
}

# Standard (non-strict) human-readable labels.
_STANDARD: dict[ActionToken, str] = {
    ActionToken.ADD: "add",
    ActionToken.TRIM: "trim",
    ActionToken.EXIT: "exit",
    ActionToken.HOLD: "hold",
    ActionToken.OPEN_LEAP: "open_leap",
    ActionToken.WRITE_CALL: "write_covered_call",
    ActionToken.ROLL: "roll",
    ActionToken.BUYBACK: "buyback",
    ActionToken.REPLACE: "replace",
    ActionToken.GATHER_MORE_DATA: "gather_more_data",
    ActionToken.WAIT: "wait",
}


def render_action(token: ActionToken, compliance_mode: str) -> str:
    table = _NEUTRAL if compliance_mode == "strict" else _STANDARD
    return table[token]


def is_strict(compliance_mode: str) -> bool:
    return compliance_mode == "strict"
