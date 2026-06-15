"""Critical correction #1: two net-worth denominators, never conflated.

net_worth_total (config, 3.19M) drives risk/withdrawal/goal math.
schwab_managed_value (live sum, excludes the external sleeve) drives
concentration/reconciliation.
"""

from __future__ import annotations

from decimal import Decimal

from app.config import AppConfig
from app.data.fixtures import load_sample_accounts, load_sample_manual
from app.data.normalize import normalize_accounts, normalize_manual
from app.data.quality import QualityLedger
from app.money import msum


def test_two_denominators_differ(cfg: AppConfig) -> None:
    assert cfg.risk_budget.net_worth_total == Decimal("3190000")
    assert cfg.risk_budget.schwab_managed_value == Decimal("2950000")
    assert cfg.risk_budget.net_worth_total != cfg.risk_budget.schwab_managed_value


def test_live_schwab_sum_reconciles_within_tolerance(cfg: AppConfig) -> None:
    ledger = QualityLedger()
    _, holdings = normalize_accounts(load_sample_accounts(), cfg, ledger)
    schwab_sum = msum(h.market_value for h in holdings if h.is_schwab_managed and h.market_value)
    ref = cfg.risk_budget.schwab_managed_value
    tol = cfg.settings.reconciliation_tolerance_pct
    assert abs(float(schwab_sum - ref)) / float(ref) <= tol


def test_external_sleeve_excluded_from_schwab_but_in_networth(cfg: AppConfig) -> None:
    ledger = QualityLedger()
    _, schwab = normalize_accounts(load_sample_accounts(), cfg, ledger)
    manual = normalize_manual(load_sample_manual(), cfg, ledger)
    schwab_sum = msum(h.market_value for h in schwab if h.is_schwab_managed and h.market_value)
    manual_sum = msum(h.market_value for h in manual if h.market_value)
    # external sleeve is NOT part of the Schwab-managed denominator
    assert all(not h.is_schwab_managed for h in manual)
    assert manual_sum == Decimal("240000.00")
    # but total invested approaches net_worth_total (the rest is held outside / cash buffers)
    assert schwab_sum + manual_sum <= cfg.risk_budget.net_worth_total
