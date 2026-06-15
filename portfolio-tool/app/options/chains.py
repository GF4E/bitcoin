"""Option-chain normalization from fixtures (or, in live mode, the Schwab adapter).

Computes mid, intrinsic/extrinsic, spread%, and liquidity/quality flags. No option
VWAP for illiquid contracts — we rely on bid/ask/OI/vol/mid/IV/delta.
"""

from __future__ import annotations

from datetime import date

from app.config import AppConfig
from app.data.contracts import OptionChainRow, OptionRight
from app.data.fixtures import load_sample_option_chains, load_sample_quotes
from app.money import Money, to_money
from app.options.payoff import extrinsic_value, intrinsic_value, mid_price, spread_pct


def underlying_prices() -> dict[str, Money]:
    quotes = load_sample_quotes()
    out: dict[str, Money] = {}
    for q in quotes.get("quotes", []):
        if q.get("last") is not None:
            out[q["ticker"]] = to_money(q["last"])
    return out


def load_chain_rows(cfg: AppConfig, underlyings: set[str] | None = None) -> list[OptionChainRow]:
    raw = load_sample_option_chains()
    prices = underlying_prices()
    thresholds = cfg.decision_thresholds.get("leaps", {})
    min_oi = int(thresholds.get("min_open_interest", 500))
    max_spread = float(thresholds.get("max_spread_pct", 0.08))

    rows: list[OptionChainRow] = []
    for c in raw.get("chains", []):
        underlying = str(c["underlying"])
        if underlyings is not None and underlying not in underlyings:
            continue
        right = OptionRight(str(c["put_call"]).lower())
        strike = to_money(c["strike"])
        bid = to_money(c["bid"]) if c.get("bid") is not None else None
        ask = to_money(c["ask"]) if c.get("ask") is not None else None
        last = to_money(c["last"]) if c.get("last") is not None else None
        mid = mid_price(bid, ask, last)
        sp = spread_pct(bid, ask)
        delta = c.get("delta")

        intrinsic = None
        extrinsic = None
        up = prices.get(underlying)
        if up is not None:
            intrinsic = intrinsic_value(right, up, strike)
            if mid is not None:
                extrinsic = extrinsic_value(mid, intrinsic)

        flags: list[str] = []
        oi = c.get("open_interest")
        if oi is not None and oi < min_oi:
            flags.append("low_open_interest")
        if sp is not None and sp > max_spread:
            flags.append("wide_spread")
        if delta is None:
            flags.append("missing_greeks")

        rows.append(
            OptionChainRow(
                underlying=underlying,
                expiration=date.fromisoformat(c["expiration"]),
                strike=strike,
                call_put=right,
                bid=bid,
                ask=ask,
                last=last,
                mid=mid,
                delta=delta,
                gamma=c.get("gamma"),
                theta=c.get("theta"),
                vega=c.get("vega"),
                iv=c.get("iv"),
                open_interest=oi,
                volume=c.get("volume"),
                intrinsic_value=intrinsic,
                extrinsic_value=extrinsic,
                spread_pct=sp,
                liquidity_flags=flags,
                missing_greeks_flag=delta is None,
            )
        )
    return rows
