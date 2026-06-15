"""Normalize raw (Schwab-shaped) responses into domain contracts.

This is the adapter boundary: no raw Schwab field names or response shapes leak
past this module. Critical-field discipline — missing cost basis or price is
flagged, never coerced to zero.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.config import AppConfig
from app.data.contracts import (
    Account,
    AssetType,
    CashHolding,
    EquityHolding,
    FundHolding,
    Holding,
    MomentumTag,
    OptionHolding,
    OptionRight,
)
from app.data.quality import QualityLedger
from app.money import Money, to_money

_ASSET_MAP = {
    "EQUITY": AssetType.EQUITY,
    "ETF": AssetType.FUND,
    "FUND": AssetType.FUND,
    "MUTUAL_FUND": AssetType.FUND,
    "OPTION": AssetType.OPTION,
    "CASH": AssetType.CASH,
}

_HOLDING_CLASS = {
    AssetType.EQUITY: EquityHolding,
    AssetType.FUND: FundHolding,
    AssetType.OPTION: OptionHolding,
    AssetType.CASH: CashHolding,
}


def mask_account(account_number: str) -> str:
    digits = "".join(ch for ch in account_number if ch.isdigit())
    last4 = digits[-4:] if len(digits) >= 4 else digits
    return f"****{last4}"


def _option_ticker(underlying: str, expiration: date, right: OptionRight, strike: Money) -> str:
    return f"{underlying} {expiration.isoformat()} {right.value[0].upper()}{strike}"


def normalize_position(
    raw: dict[str, Any],
    account: Account,
    as_of: datetime,
    cfg: AppConfig,
    ledger: QualityLedger,
) -> Holding:
    asset_type = _ASSET_MAP.get(str(raw.get("asset_type", "EQUITY")).upper(), AssetType.EQUITY)
    multiplier = int(raw.get("multiplier", 100 if asset_type is AssetType.OPTION else 1))
    quantity = to_money(raw["quantity"])

    underlying = raw.get("underlying")
    expiration = date.fromisoformat(raw["expiration"]) if raw.get("expiration") else None
    strike = to_money(raw["strike"]) if raw.get("strike") is not None else None
    right = OptionRight(str(raw["put_call"]).lower()) if raw.get("put_call") else None

    if (
        asset_type is AssetType.OPTION
        and underlying
        and expiration
        and right
        and strike is not None
    ):
        ticker = _option_ticker(underlying, expiration, right, strike)
    else:
        ticker = str(raw["symbol"])

    price: Money | None = None
    if raw.get("price") is not None:
        price = to_money(raw["price"])
        if price < 0:
            ledger.add(
                "negative_price", f"negative price for {ticker}", ticker=ticker, field="price"
            )
    else:
        ledger.add("missing_price", f"missing price for {ticker}", ticker=ticker, field="price")

    market_value: Money | None = None
    if raw.get("market_value") is not None:
        market_value = to_money(raw["market_value"])
    elif price is not None:
        market_value = quantity * price * Decimal(multiplier)

    cost_basis: Money | None = None
    unrealized: Money | None = None
    if raw.get("cost_basis") is not None:
        cost_basis = to_money(raw["cost_basis"])
    elif raw.get("average_cost") is not None:
        cost_basis = quantity * to_money(raw["average_cost"]) * Decimal(multiplier)
    else:
        ledger.add(
            "missing_cost_basis",
            f"missing cost basis for {ticker}; repair math gated",
            ticker=ticker,
            field="cost_basis",
        )
    if market_value is not None and cost_basis is not None:
        unrealized = market_value - cost_basis

    flags: list[str] = []
    if cost_basis is None:
        flags.append("missing_cost_basis")
    if price is None:
        flags.append("missing_price")

    classify_ticker = underlying if asset_type is AssetType.OPTION and underlying else ticker
    sleeve = cfg.sleeve_for(classify_ticker)
    role_row = cfg.sleeve_classifications.get(classify_ticker.upper(), {})
    role = role_row.get("role")
    tag_raw = str(raw.get("momentum_tag", "neutral")).lower()
    momentum_tag = (
        MomentumTag(tag_raw) if tag_raw in MomentumTag._value2member_map_ else MomentumTag.NEUTRAL
    )

    cls = _HOLDING_CLASS[asset_type]
    return cls(
        account_id=account.account_id,
        account_name=account.account_name,
        masked_account_id=account.masked_account_id,
        account_type=account.account_type,
        ticker=ticker,
        name=str(raw.get("name", classify_ticker)),
        subtype=raw.get("subtype"),
        sleeve=sleeve,
        role=role,
        momentum_tag=momentum_tag,
        quantity=quantity,
        price=price,
        market_value=market_value,
        cost_basis=cost_basis,
        unrealized_gain_loss=unrealized,
        as_of_datetime=as_of,
        data_source=account.data_source,
        is_schwab_managed=account.is_schwab_managed,
        data_quality_flags=flags,
        underlying=underlying,
        expiration=expiration,
        strike=strike,
        call_put=right,
        multiplier=multiplier,
    )


def normalize_accounts(
    raw: dict[str, Any], cfg: AppConfig, ledger: QualityLedger
) -> tuple[list[Account], list[Holding]]:
    as_of = datetime.fromisoformat(raw["as_of"])
    accounts: list[Account] = []
    holdings: list[Holding] = []
    for acc_raw in raw.get("accounts", []):
        number = str(acc_raw["account_number"])
        account = Account(
            account_id=number,
            account_name=str(acc_raw.get("nickname", "Account")),
            masked_account_id=mask_account(number),
            account_type=acc_raw.get("account_type"),
            is_schwab_managed=bool(acc_raw.get("is_schwab_managed", True)),
            reported_total=(
                to_money(acc_raw["reported_total"])
                if acc_raw.get("reported_total") is not None
                else None
            ),
            data_source=str(raw.get("data_source", "mock")),
        )
        accounts.append(account)
        for pos in acc_raw.get("positions", []):
            holdings.append(normalize_position(pos, account, as_of, cfg, ledger))
    return accounts, holdings


def normalize_manual(raw: dict[str, Any], cfg: AppConfig, ledger: QualityLedger) -> list[Holding]:
    """External / manual sleeve (e.g. the 240k S&P sleeve outside Schwab).

    These are in exposure math but excluded from Schwab reconciliation
    (``is_schwab_managed=False``, ``data_source='manual_static'``).
    """
    as_of = datetime.fromisoformat(raw["as_of"])
    holdings: list[Holding] = []
    for pos in raw.get("holdings", []):
        account = Account(
            account_id=str(pos.get("account", "manual")),
            account_name=str(pos.get("account_name", "External Static Sleeve")),
            masked_account_id="manual",
            account_type="manual",
            is_schwab_managed=False,
            data_source=str(pos.get("data_source", "manual_static")),
        )
        holdings.append(normalize_position(pos, account, as_of, cfg, ledger))
    return holdings
