"""Portfolio exposure — TWO denominators kept distinct (critical correction #1).

Risk/exposure percentages divide by ``net_worth_total`` (includes the external
sleeve). Concentration percentages divide by ``schwab_managed_value`` (live sum,
excludes the external sleeve).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.config import AppConfig
from app.data.contracts import Holding, Sleeve
from app.money import ZERO, Money, msum, pct_of, round_money


@dataclass
class SleeveExposure:
    sleeve: Sleeve
    market_value: Money
    pct_net_worth: float  # risk denominator
    pct_schwab_managed: float  # concentration denominator
    is_ai_tech_semi: bool


@dataclass
class ExposureReport:
    net_worth_total: Money
    schwab_managed_value: Money
    external_static_value: Money
    total_invested: Money
    ai_tech_semi_value: Money
    ai_tech_semi_pct_net_worth: float
    by_sleeve: list[SleeveExposure] = field(default_factory=list)


def compute_exposure(cfg: AppConfig, holdings: list[Holding]) -> ExposureReport:
    schwab = msum(h.market_value for h in holdings if h.is_schwab_managed and h.market_value)
    manual = msum(h.market_value for h in holdings if not h.is_schwab_managed and h.market_value)
    net_worth = cfg.risk_budget.net_worth_total

    by_sleeve_mv: dict[Sleeve, Money] = {}
    for h in holdings:
        if h.market_value is None:
            continue
        by_sleeve_mv[h.sleeve] = by_sleeve_mv.get(h.sleeve, ZERO) + h.market_value

    ai_value = msum(
        h.market_value
        for h in holdings
        if h.market_value is not None
        and cfg.is_ai_tech_semi(
            (h.underlying or h.ticker) if h.asset_type.value == "option" else h.ticker
        )
    )

    rows = [
        SleeveExposure(
            sleeve=sleeve,
            market_value=round_money(mv),
            pct_net_worth=pct_of(mv, net_worth),
            pct_schwab_managed=pct_of(mv, schwab),
            is_ai_tech_semi=any(
                cfg.is_ai_tech_semi(h.ticker) for h in holdings if h.sleeve is sleeve
            ),
        )
        for sleeve, mv in sorted(by_sleeve_mv.items(), key=lambda kv: kv[1], reverse=True)
    ]

    return ExposureReport(
        net_worth_total=net_worth,
        schwab_managed_value=round_money(schwab),
        external_static_value=round_money(manual),
        total_invested=round_money(schwab + manual),
        ai_tech_semi_value=round_money(ai_value),
        ai_tech_semi_pct_net_worth=pct_of(ai_value, net_worth),
        by_sleeve=rows,
    )
