"""Parsers for Schwab's real read-only API JSON.

These map Schwab's documented response shapes into the simplified intermediate
shapes the rest of the app already consumes (``app/data/normalize.py`` for
accounts; ``app/options/chains.py`` for option rows). Raw Schwab shapes never leak
past this module.

IMPORTANT: implemented against Schwab's *documented* Trader API schema and verified
here only against Schwab-shaped sample fixtures (``tests/fixtures/schwab_raw/``).
The end-to-end live path is unverified until run with real credentials — field
names/casing may need small adjustments against the live API.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import numpy as np

# Schwab assetType -> our simplified asset_type.
_ASSET = {
    "EQUITY": "EQUITY",
    "ETF": "ETF",
    "COLLECTIVE_INVESTMENT": "ETF",
    "MUTUAL_FUND": "MUTUAL_FUND",
    "OPTION": "OPTION",
    "CASH_EQUIVALENT": "CASH",
    "CURRENCY": "CASH",
}


def parse_osi(symbol: str) -> tuple[str, date, str, float] | None:
    """Parse an OSI option symbol like ``NVDA  271217C00200000`` ->
    (underlying, expiration, 'CALL'|'PUT', strike). Returns None if not OSI-shaped."""
    s = symbol.strip()
    if len(s) < 15 or symbol[-9] not in ("C", "P"):
        return None
    root = symbol[:-15].strip()
    yymmdd = symbol[-15:-9]
    cp = symbol[-9]
    strike = int(symbol[-8:]) / 1000.0
    try:
        exp = date(2000 + int(yymmdd[:2]), int(yymmdd[2:4]), int(yymmdd[4:6]))
    except ValueError:
        return None
    return root, exp, "CALL" if cp == "C" else "PUT", strike


def parse_accounts(raw: Any, as_of: datetime | None = None) -> dict[str, Any]:
    """Schwab ``GET /accounts?fields=positions`` -> the dict normalize_accounts consumes.

    Tolerant of the top-level list (documented) or a dict wrapper.
    """
    stamp = (as_of or datetime.now()).isoformat()
    entries = (
        raw if isinstance(raw, list) else raw.get("accounts", []) if isinstance(raw, dict) else []
    )
    accounts: list[dict[str, Any]] = []
    for entry in entries:
        sa = entry.get("securitiesAccount", entry)
        positions: list[dict[str, Any]] = []
        for pos in sa.get("positions", []):
            inst = pos.get("instrument", {})
            asset = _ASSET.get(str(inst.get("assetType", "EQUITY")).upper(), "EQUITY")
            qty = float(pos.get("longQuantity", 0.0)) - float(pos.get("shortQuantity", 0.0))
            mult = int(inst.get("optionMultiplier", 100)) if asset == "OPTION" else 1
            mv = pos.get("marketValue")
            row: dict[str, Any] = {
                "symbol": inst.get("symbol", ""),
                "asset_type": asset,
                "quantity": qty,
                "average_cost": pos.get("averagePrice"),
                "market_value": mv,
                "name": inst.get("description"),
                "multiplier": mult,
            }
            if qty and mv is not None:
                row["price"] = abs(float(mv)) / (abs(qty) * mult)
            if asset == "OPTION":
                osi = parse_osi(str(inst.get("symbol", "")))
                row["underlying"] = inst.get("underlyingSymbol") or (osi[0] if osi else None)
                if osi:
                    row["expiration"] = osi[1].isoformat()
                    row["put_call"] = osi[2]
                    row["strike"] = osi[3]
                else:
                    row["put_call"] = inst.get("putCall")
            positions.append(row)
        balances = sa.get("currentBalances", {})
        accounts.append(
            {
                "account_number": str(sa.get("accountNumber", "")),
                "account_type": sa.get("type"),
                "nickname": sa.get("type", "Schwab Account"),
                "is_schwab_managed": True,
                "reported_total": balances.get("liquidationValue"),
                "positions": positions,
            }
        )
    return {"as_of": stamp, "data_source": "live_readonly", "accounts": accounts}


def parse_quote_last(raw: dict[str, Any], ticker: str) -> float | None:
    entry = raw.get(ticker) or raw.get(ticker.upper())
    if not entry:
        return None
    quote = entry.get("quote", entry)
    val = quote.get("lastPrice", quote.get("mark"))
    return float(val) if val is not None else None


def parse_candles_closes(raw: dict[str, Any]) -> np.ndarray:
    return np.array([float(c["close"]) for c in raw.get("candles", [])], dtype=float)


def parse_candles_ohlcv(raw: dict[str, Any]) -> list[tuple[float, float]]:
    return [(float(c["close"]), float(c.get("volume", 0.0))) for c in raw.get("candles", [])]


def parse_option_chain(raw: dict[str, Any]) -> dict[str, Any]:
    """Schwab ``GET /chains`` -> {"chains": [row, ...]} in the shape app/options/chains.py uses."""
    underlying = raw.get("symbol", "")
    rows: list[dict[str, Any]] = []
    for map_key in ("callExpDateMap", "putExpDateMap"):
        for _exp_key, strikes in raw.get(map_key, {}).items():
            for _strike_key, contracts in strikes.items():
                for c in contracts:
                    vol_pct = c.get("volatility")
                    iv = float(vol_pct) / 100.0 if vol_pct is not None else None
                    exp_iso = str(c.get("expirationDate", ""))[:10]
                    rows.append(
                        {
                            "underlying": underlying,
                            "expiration": exp_iso,
                            "strike": c.get("strikePrice"),
                            "put_call": c.get("putCall", "CALL"),
                            "bid": c.get("bid"),
                            "ask": c.get("ask"),
                            "last": c.get("last"),
                            "delta": c.get("delta"),
                            "gamma": c.get("gamma"),
                            "theta": c.get("theta"),
                            "vega": c.get("vega"),
                            "iv": iv,
                            "open_interest": c.get("openInterest"),
                            "volume": c.get("totalVolume"),
                            "multiplier": int(c.get("multiplier", 100)),
                        }
                    )
    return {
        "as_of": raw.get("fromDate", ""),
        "chains": rows,
        "underlying_price": raw.get("underlyingPrice"),
    }
