"""Data-quality helpers (the data-integrity discipline).

Engines accumulate :class:`DataQualityWarning` objects rather than silently
coercing missing critical fields. A ``QualityLedger`` is the simple collector
threaded through evaluation so warnings surface in reports.
"""

from __future__ import annotations

from app.data.contracts import DataLabel, DataQualityWarning, Severity


class QualityLedger:
    """Collects data-quality warnings during a run."""

    def __init__(self) -> None:
        self._warnings: list[DataQualityWarning] = []

    def add(
        self,
        code: str,
        message: str,
        *,
        severity: Severity = Severity.WARN,
        field: str | None = None,
        ticker: str | None = None,
        account_id: str | None = None,
        label: DataLabel | None = None,
    ) -> DataQualityWarning:
        w = DataQualityWarning(
            code=code,
            message=message,
            severity=severity,
            field=field,
            ticker=ticker,
            account_id=account_id,
            label=label,
        )
        self._warnings.append(w)
        return w

    def extend(self, warnings: list[DataQualityWarning]) -> None:
        self._warnings.extend(warnings)

    @property
    def warnings(self) -> list[DataQualityWarning]:
        return list(self._warnings)

    def has_critical(self) -> bool:
        return any(w.severity is Severity.CRITICAL for w in self._warnings)

    def codes(self) -> list[str]:
        return [w.code for w in self._warnings]
