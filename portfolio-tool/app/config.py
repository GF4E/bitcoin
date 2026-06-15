"""Typed configuration loading.

Every user-context number lives in ``config/*.yaml`` — never hardcoded in engine
logic. The config directory resolves to ``$PORTFOLIO_TOOL_CONFIG`` if set,
otherwise ``<package_parent>/config``. ``settings.yaml`` is loaded if present,
else ``settings.example.yaml`` (so the tool runs from a fresh checkout).
"""

from __future__ import annotations

import os
from datetime import date
from decimal import Decimal
from functools import cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from app.data.contracts import GoalPlan, RiskBudget, Sleeve


class _Cfg(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Settings(_Cfg):
    mode: str = "mock"  # mock | live_readonly
    compliance_mode: str = "standard"  # standard | strict
    mask_account_ids: bool = True
    reconciliation_tolerance_pct: float = 0.01
    order_execution_enabled: bool = False  # SAFETY: must stay false in v1
    cache_dir: str = ".cache"
    reports_dir: str = "reports/runs"


class TrajectoryConfig(_Cfg):
    n_paths: int = 10_000
    seed: int = 12345
    randomize_seed: bool = False
    horizon_months: int = 360  # retirement horizon for terminal wealth / ruin
    # Core-book expected_return/volatility and income-sleeve correlation are the
    # load-bearing drivers and live on GoalPlan (the sensitivity sweep perturbs them).
    # These two parameterize the income sleeve's own path inside the MC.
    income_sleeve_expected_return: float = 0.085
    income_sleeve_volatility: float = 0.16
    income_fraction: float = 0.10  # share of the book in the compounding income sleeve
    safe_annual: float = 0.045  # de-risked return when defensive
    defensive_exposure: float = 0.35  # exposure once drawdown depth >= threshold
    n_grid: int = 13  # threshold sweep resolution
    sensitivity_n_paths: int = 4000  # reduced paths for the headline grid (speed)
    sensitivity_n_grid: int = 7
    ruin_probability_max: float = 0.075
    downside_guard_mode: str = "p25_floor"  # p25_floor | cvar
    cvar_alpha: float = 0.10
    drag_anchor_mode: str = "baseline_cagr"  # baseline_cagr | required_cagr
    drag_ceiling_bps: float = 50.0
    threshold_min: float = 0.05
    threshold_max: float = 0.40
    threshold_tolerance: float = 0.0025
    sensitivity_pcts: list[float] = Field(default_factory=lambda: [-0.20, -0.10, 0.10, 0.20])


class MomentumConfig(_Cfg):
    lookback_months: int = 12
    skip_months: int = 1
    blend_horizons: list[int] = Field(default_factory=lambda: [1, 3, 12])
    use_blended: bool = True
    vol_target_annual: float = 0.13
    trend_filter_sma_days: int = 200
    trend_filter_use_tbill_excess: bool = True
    tbill_annual: float = 0.045
    persistence_months: int = 2
    throttle_indicators: list[str] = Field(
        default_factory=lambda: [
            "brent",
            "hormuz_tanker_flow",
            "fedwatch_cut_odds",
            "spx_vs_200dma",
            "vix",
            "cpi_pce",
            "geopolitical_talks",
            "gas",
        ]
    )
    throttle_persistence_months: int = 2


class IncomeSleeveConfig(_Cfg):
    capped_fund: str = "QQQI"
    uncapped_fund: str = "QQQM"
    underlying_index: str = "QQQ"
    peer_fallback_fund: str = "QYLD"
    min_series_months_for_direct: int = 36
    buffer_months: int = 18
    roc_trailing_window_months: int = 12
    peer_calibration_source: str = "sample_fixture (labeled; live mode pulls realized NAV+distros)"


class AppConfig(_Cfg):
    settings: Settings
    risk_budget: RiskBudget
    goal_plan: GoalPlan
    trajectory: TrajectoryConfig
    momentum: MomentumConfig
    income_sleeve: IncomeSleeveConfig
    sleeve_classifications: dict[str, dict[str, Any]]
    scoring_weights: dict[str, dict[str, float]]
    decision_thresholds: dict[str, Any]
    watchlists: dict[str, list[str]]
    holding_overrides: dict[str, dict[str, Any]]
    dividend_overrides: dict[str, dict[str, Any]]
    config_dir: str

    def sleeve_for(self, ticker: str) -> Sleeve:
        row = self.sleeve_classifications.get(ticker.upper())
        if row and "sleeve" in row:
            return Sleeve(row["sleeve"])
        return Sleeve.OTHER

    def is_ai_tech_semi(self, ticker: str) -> bool:
        row = self.sleeve_classifications.get(ticker.upper())
        return bool(row and row.get("is_ai_tech_semi", False))


def config_dir() -> Path:
    env = os.environ.get("PORTFOLIO_TOOL_CONFIG")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent / "config"


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return data or {}


def _settings_file(cdir: Path) -> Path:
    live = cdir / "settings.yaml"
    return live if live.exists() else cdir / "settings.example.yaml"


def _to_decimal_fields(raw: dict[str, Any], keys: list[str]) -> dict[str, Any]:
    out = dict(raw)
    for k in keys:
        if k in out and out[k] is not None:
            out[k] = Decimal(str(out[k]))
    return out


def load_config(cdir: Path | None = None) -> AppConfig:
    cdir = cdir or config_dir()
    settings = Settings(**_load_yaml(_settings_file(cdir)))

    rb_raw = _load_yaml(cdir / "risk_budget.yaml")
    risk_budget = RiskBudget(**rb_raw)

    gp_raw = _load_yaml(cdir / "goal_plan.yaml")
    # Simulation knobs live under a `trajectory:` block in goal_plan.yaml (the spec's
    # file list has no separate trajectory.yaml). Pop them before building GoalPlan.
    trajectory_raw = gp_raw.pop("trajectory", {}) or {}
    if isinstance(gp_raw.get("target_date"), str):
        gp_raw["target_date"] = date.fromisoformat(gp_raw["target_date"])
    goal_plan = GoalPlan(**gp_raw)

    return AppConfig(
        settings=settings,
        risk_budget=risk_budget,
        goal_plan=goal_plan,
        trajectory=TrajectoryConfig(**trajectory_raw),
        momentum=MomentumConfig(**_load_yaml(cdir / "momentum.yaml")),
        income_sleeve=IncomeSleeveConfig(**_load_yaml(cdir / "income_sleeve.yaml")),
        sleeve_classifications=_load_yaml(cdir / "sleeve_classifications.yaml"),
        scoring_weights=_load_yaml(cdir / "scoring_weights.yaml"),
        decision_thresholds=_load_yaml(cdir / "decision_thresholds.yaml"),
        watchlists=_load_yaml(cdir / "watchlists.yaml"),
        holding_overrides=(_load_yaml(cdir / "holding_overrides.yaml").get("overrides") or {}),
        dividend_overrides=(_load_yaml(cdir / "dividend_overrides.yaml").get("overrides") or {}),
        config_dir=str(cdir),
    )


@cache
def get_config() -> AppConfig:
    """Process-wide cached config (tests that need isolation call ``load_config``)."""
    return load_config()
