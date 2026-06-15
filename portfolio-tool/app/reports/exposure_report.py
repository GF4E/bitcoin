"""portfolio_exposure_report.md — exposure, reconciliation, and the macro throttle."""

from __future__ import annotations

from app.config import AppConfig
from app.data.contracts import ThrottleState
from app.portfolio.exposure import ExposureReport
from app.portfolio.reconciliation import AccountReconciliation
from app.reports.markdown import fmt_money, fmt_pct, footer


def render_exposure_report(
    cfg: AppConfig,
    exposure: ExposureReport,
    reconciliation: list[AccountReconciliation],
    throttle: ThrottleState,
) -> str:
    parts: list[str] = ["# Portfolio Exposure Report\n"]
    parts.append(
        "Two denominators are kept distinct: **risk/exposure** percentages divide by "
        f"net_worth_total ({fmt_money(exposure.net_worth_total)}); **concentration/"
        f"reconciliation** divide by schwab_managed_value ({fmt_money(exposure.schwab_managed_value)}).\n"
    )
    parts.append(
        "## Totals\n\n"
        f"- Schwab-managed value: {fmt_money(exposure.schwab_managed_value)}\n"
        f"- External/manual sleeve (in exposure math, excluded from Schwab reconciliation): "
        f"{fmt_money(exposure.external_static_value)}\n"
        f"- Total invested: {fmt_money(exposure.total_invested)}\n"
        f"- AI/tech/semi exposure: {fmt_money(exposure.ai_tech_semi_value)} "
        f"(**{fmt_pct(exposure.ai_tech_semi_pct_net_worth)}** of net worth)\n"
    )

    parts.append("\n## Exposure by sleeve\n")
    parts.append("| Sleeve | Market value | % net worth | % Schwab-managed | AI/tech/semi |")
    parts.append("|---|---|---|---|---|")
    for s in exposure.by_sleeve:
        parts.append(
            f"| {s.sleeve.value} | {fmt_money(s.market_value)} | {fmt_pct(s.pct_net_worth)} "
            f"| {fmt_pct(s.pct_schwab_managed)} | {'yes' if s.is_ai_tech_semi else 'no'} |"
        )

    parts.append("\n## Reconciliation to account totals\n")
    parts.append("| Account | Computed | Reported | Diff % | Within tolerance |")
    parts.append("|---|---|---|---|---|")
    for r in reconciliation:
        diff = "n/a" if r.diff_pct is None else fmt_pct(r.diff_pct, 3)
        rep = fmt_money(r.reported_total) if r.reported_total is not None else "n/a"
        parts.append(
            f"| {r.masked_account_id} | {fmt_money(r.computed_total)} | {rep} | {diff} "
            f"| {'yes' if r.within_tolerance else '**NO**'} |"
        )

    brake = "ACTIVE" if throttle.brake_active else "off"
    parts.append(
        "\n## Macro throttle\n\n"
        f"- Gross-exposure multiplier: **{throttle.gross_exposure_multiplier:.0%}** (brake {brake}, "
        f"persistent={throttle.persistent})\n"
        "- Conflict rule: brake wins on sizing, the momentum engine wins on selection.\n"
    )
    parts.append(footer(cfg.settings.compliance_mode))
    return "\n".join(parts)
