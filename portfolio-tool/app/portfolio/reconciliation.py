"""Reconcile computed Schwab-managed positions to account-reported totals.

Uses the schwab_managed denominator (the external/manual sleeve is excluded). Warns
over a configurable tolerance.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config import AppConfig
from app.data.contracts import Account, DataQualityWarning, Holding, Severity
from app.money import ZERO, Money, msum, round_money


@dataclass
class AccountReconciliation:
    account_id: str
    masked_account_id: str
    reported_total: Money | None
    computed_total: Money
    diff: Money | None
    diff_pct: float | None
    within_tolerance: bool


def reconcile(
    cfg: AppConfig, accounts: list[Account], holdings: list[Holding]
) -> tuple[list[AccountReconciliation], list[DataQualityWarning]]:
    tol = float(
        cfg.decision_thresholds.get("reconciliation", {}).get(
            "tolerance_pct", cfg.settings.reconciliation_tolerance_pct
        )
    )
    results: list[AccountReconciliation] = []
    warnings: list[DataQualityWarning] = []
    for acc in accounts:
        if not acc.is_schwab_managed:
            continue
        computed = msum(
            h.market_value
            for h in holdings
            if h.account_id == acc.account_id and h.is_schwab_managed and h.market_value
        )
        diff = diff_pct = None
        within = True
        if acc.reported_total is not None:
            diff = computed - acc.reported_total
            denom = float(acc.reported_total) if acc.reported_total != ZERO else 1.0
            diff_pct = abs(float(diff)) / denom
            within = diff_pct <= tol
            if not within:
                warnings.append(
                    DataQualityWarning(
                        code="reconciliation_out_of_tolerance",
                        message=(
                            f"{acc.masked_account_id}: computed {round_money(computed)} vs reported "
                            f"{round_money(acc.reported_total)} ({diff_pct:.2%} > {tol:.2%})"
                        ),
                        severity=Severity.WARN,
                        account_id=acc.account_id,
                    )
                )
        results.append(
            AccountReconciliation(
                account_id=acc.account_id,
                masked_account_id=acc.masked_account_id,
                reported_total=round_money(acc.reported_total)
                if acc.reported_total is not None
                else None,
                computed_total=round_money(computed),
                diff=round_money(diff) if diff is not None else None,
                diff_pct=diff_pct,
                within_tolerance=within,
            )
        )
    return results, warnings
