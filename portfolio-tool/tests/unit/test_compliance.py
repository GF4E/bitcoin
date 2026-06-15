"""compliance_mode functional at the render boundary (critical correction #5)."""

from __future__ import annotations

from app.data.contracts import ActionToken
from app.reports.compliance import is_strict, render_action


def test_standard_mode_uses_plain_labels() -> None:
    assert render_action(ActionToken.ADD, "standard") == "add"
    assert render_action(ActionToken.WRITE_CALL, "standard") == "write_covered_call"


def test_strict_mode_maps_to_neutral_candidate_labels() -> None:
    assert render_action(ActionToken.ADD, "strict") == "candidate_for_increase"
    assert render_action(ActionToken.TRIM, "strict") == "candidate_for_reduction"
    assert render_action(ActionToken.WRITE_CALL, "strict") == "income_overlay_candidate"
    assert "candidate" in render_action(
        ActionToken.OPEN_LEAP, "strict"
    ) or "exposure" in render_action(ActionToken.OPEN_LEAP, "strict")


def test_every_action_token_has_both_labels() -> None:
    for tok in ActionToken:
        assert render_action(tok, "standard")
        assert render_action(tok, "strict")
        # strict labels must not leak the raw action verb for directional tokens
    assert is_strict("strict") and not is_strict("standard")
