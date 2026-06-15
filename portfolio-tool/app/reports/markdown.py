"""Small markdown formatting helpers shared by report writers."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from decimal import Decimal

from app.data.contracts import Assumption

DISCLAIMER = (
    "This tool is for personal analysis only. It does not place trades and does not "
    "replace professional financial, tax, or legal advice."
)


def fmt_money(value: Decimal | float) -> str:
    return f"${float(value):,.0f}"


def fmt_money_m(value: Decimal | float) -> str:
    return f"${float(value) / 1e6:,.2f}M"


def fmt_pct(value: float, places: int = 1) -> str:
    return f"{value * 100:.{places}f}%"


def assumptions_table(assumptions: Sequence[Assumption]) -> str:
    lines = ["| Assumption | Value | Label | Load-bearing | Rationale |", "|---|---|---|---|---|"]
    for a in assumptions:
        lines.append(
            f"| {a.name} | {a.value} | {a.label.value} | {'yes' if a.load_bearing else 'no'} "
            f"| {a.rationale or ''} |"
        )
    return "\n".join(lines)


def grid_table(
    row_levels: Sequence[float],
    col_levels: Sequence[float],
    cell: Callable[[float, float], str],
    *,
    row_label: str = "ret \\ vol",
) -> str:
    header = f"| {row_label} | " + " | ".join(f"vol x{c:.2f}" for c in col_levels) + " |"
    sep = "|" + "---|" * (len(col_levels) + 1)
    lines = [header, sep]
    for r in row_levels:
        cells = " | ".join(cell(r, c) for c in col_levels)
        lines.append(f"| **ret x{r:.2f}** | {cells} |")
    return "\n".join(lines)


def footer(compliance_mode: str) -> str:
    note = ""
    if compliance_mode == "strict":
        note = "\n_Compliance mode: strict — actions are shown as neutral candidate labels._"
    return f"\n---\n_{DISCLAIMER}_{note}\n"
