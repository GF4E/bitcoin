"""Raw Schwab response shapes (kept thin).

Raw shapes never leak past the adapter — ``app/data/normalize.py`` maps them into
domain contracts. These TypedDicts document the expected read-only payloads.
"""

from __future__ import annotations

from typing import TypedDict


class RawPosition(TypedDict, total=False):
    symbol: str
    asset_type: str
    quantity: float
    price: float
    average_cost: float
    market_value: float
    underlying: str
    expiration: str
    strike: float
    put_call: str
    multiplier: int


class RawAccount(TypedDict, total=False):
    account_number: str
    account_type: str
    nickname: str
    is_schwab_managed: bool
    reported_total: float
    positions: list[RawPosition]


class RawAccountsResponse(TypedDict, total=False):
    as_of: str
    data_source: str
    accounts: list[RawAccount]
