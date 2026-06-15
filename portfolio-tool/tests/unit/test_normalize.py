"""Normalization from mock Schwab responses + manual sleeve."""

from __future__ import annotations

from decimal import Decimal

from app.config import AppConfig
from app.data.contracts import AssetType, MomentumTag, Sleeve
from app.data.fixtures import load_sample_accounts, load_sample_manual
from app.data.normalize import mask_account, normalize_accounts, normalize_manual
from app.data.quality import QualityLedger


def test_mask_account_keeps_last4() -> None:
    assert mask_account("12345678") == "****5678"


def test_normalize_accounts_computes_value_and_pl(cfg: AppConfig, ledger: QualityLedger) -> None:
    accounts, holdings = normalize_accounts(load_sample_accounts(), cfg, ledger)
    assert len(accounts) == 2
    by_ticker = {h.ticker: h for h in holdings}
    nvda = by_ticker["NVDA"]
    assert nvda.market_value == Decimal("360000.00")  # 2000 * 180
    assert nvda.cost_basis == Decimal("190000.00")  # 2000 * 95
    assert nvda.unrealized_gain_loss == Decimal("170000.00")
    assert nvda.sleeve is Sleeve.SEMIS
    assert nvda.masked_account_id == "****5678"


def test_short_option_sign_conventions(cfg: AppConfig, ledger: QualityLedger) -> None:
    _, holdings = normalize_accounts(load_sample_accounts(), cfg, ledger)
    cc = next(h for h in holdings if h.asset_type is AssetType.OPTION and h.underlying == "KO")
    assert cc.quantity == Decimal("-10")
    assert cc.market_value == Decimal("-800.00")  # -10 * 0.80 * 100
    assert cc.cost_basis == Decimal("-1100.00")  # -10 * 1.10 * 100
    assert cc.unrealized_gain_loss == Decimal("300.00")  # credit decayed in our favor
    assert cc.momentum_tag is MomentumTag.BALLAST


def test_manual_sleeve_excluded_from_schwab(cfg: AppConfig, ledger: QualityLedger) -> None:
    manual = normalize_manual(load_sample_manual(), cfg, ledger)
    voo = manual[0]
    assert voo.is_schwab_managed is False
    assert voo.data_source == "manual_static"
    assert voo.market_value == Decimal("240000.00")  # 480 * 500
    assert voo.sleeve is Sleeve.BROAD_CORE


def test_missing_cost_basis_flagged_not_zeroed(cfg: AppConfig, ledger: QualityLedger) -> None:
    raw = {
        "as_of": "2026-06-15T16:00:00",
        "accounts": [
            {
                "account_number": "99998888",
                "account_type": "MARGIN",
                "nickname": "T",
                "positions": [
                    {"symbol": "MU", "asset_type": "EQUITY", "quantity": 10, "price": 130.0}
                ],
            }
        ],
    }
    _, holdings = normalize_accounts(raw, cfg, ledger)
    mu = holdings[0]
    assert mu.cost_basis is None  # never silently zeroed
    assert mu.unrealized_gain_loss is None
    assert "missing_cost_basis" in mu.data_quality_flags
    assert "missing_cost_basis" in ledger.codes()
