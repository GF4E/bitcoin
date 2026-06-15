"""Monte-Carlo trajectory simulation.

Per the Decimal/float boundary, the *entire* simulation runs in ``float`` (it is
Monte-Carlo / probability work). Money is reconstructed as ``Decimal`` only when
summary statistics are emitted (see ``trajectory.py``).

Model (documented in docs/decision_methodology.md):
- Correlated monthly lognormal/GBM steps for a core book and a compounding income
  sleeve; blended into a portfolio return.
- The drawdown threshold ``T`` (the quantity the objective solves for) drives the
  Markov spending response AND a sequence-risk de-risk response:
    * discretionary spend is cut, scaling in with drawdown depth, full at d>=T;
      the VA-covered floor is never cut.
    * once drawdown depth d>=T, exposure drops to ``defensive_exposure`` (the
      "growth cost of a withdrawn dollar rises with drawdown depth" — sequence
      risk). Higher T => stays risk-on through deeper drawdowns => higher MEDIAN
      terminal wealth but higher ruin and a fatter lower tail. This makes the
      objective well-posed with an interior/boundary optimum.
- RUIN: a path is ruined the first month its wealth can no longer fund the
  essential (non-discretionary) gap for the remainder of the horizon, given the VA
  income floor. Essential gap = (expenses - VA) - discretionary.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class SimInputs:
    start_wealth: float
    horizon_months: int
    core_mu: float  # annual expected return (load-bearing; perturbed in sensitivity)
    core_vol: float  # annual volatility (load-bearing; perturbed in sensitivity)
    income_mu: float
    income_vol: float
    income_fraction: float  # share of book in the compounding income sleeve
    correlation: float  # income-sleeve vs core, estimated from history
    safe_annual: float  # de-risked return when defensive
    defensive_exposure: float
    monthly_expenses: float
    va_floor: float  # VA income; never cut; offsets the portfolio draw
    discretionary: float  # cuttable band of the gap
    milestone: float
    n_paths: int
    seed: int
    randomize: bool = False


@dataclass(frozen=True)
class SimResult:
    terminal: np.ndarray
    ruined: np.ndarray
    crossing_month: np.ndarray  # -1 if never crossed
    gap: float
    essential: float

    @property
    def ruin_probability(self) -> float:
        return float(self.ruined.mean())

    @property
    def prob_reach_milestone(self) -> float:
        return float((self.crossing_month >= 0).mean())


def _draws(inp: SimInputs) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(None if inp.randomize else inp.seed)
    h, n = inp.horizon_months, inp.n_paths
    mu_c = inp.core_mu / 12.0 - 0.5 * inp.core_vol**2 / 12.0
    sd_c = inp.core_vol / np.sqrt(12.0)
    mu_i = inp.income_mu / 12.0 - 0.5 * inp.income_vol**2 / 12.0
    sd_i = inp.income_vol / np.sqrt(12.0)
    zc = rng.standard_normal((h, n))
    zind = rng.standard_normal((h, n))
    rho = float(np.clip(inp.correlation, -0.999, 0.999))
    zi = rho * zc + np.sqrt(1.0 - rho**2) * zind
    r_core = mu_c + sd_c * zc
    r_income = mu_i + sd_i * zi
    return r_core, r_income


def simulate(inp: SimInputs, threshold: float) -> SimResult:
    """Run the path simulation for a single candidate drawdown threshold."""
    threshold = max(threshold, 1e-6)
    r_core, r_income = _draws(inp)
    r_risky = (1.0 - inp.income_fraction) * r_core + inp.income_fraction * r_income
    safe_m = inp.safe_annual / 12.0

    n = inp.n_paths
    w = np.full(n, inp.start_wealth, dtype=float)
    hwm = np.full(n, inp.start_wealth, dtype=float)
    ruined = np.zeros(n, dtype=bool)
    crossing = np.full(n, -1, dtype=int)

    gap = inp.monthly_expenses - inp.va_floor
    essential = max(gap - inp.discretionary, 0.0)

    for t in range(inp.horizon_months):
        depth = np.clip((hwm - w) / np.maximum(hwm, 1e-9), 0.0, None)
        defensive = depth >= threshold
        exposure = np.where(defensive, inp.defensive_exposure, 1.0)
        r = exposure * r_risky[t] + (1.0 - exposure) * safe_m
        cut = inp.discretionary * np.clip(depth / threshold, 0.0, 1.0)
        draw = gap - cut
        w = w * (1.0 + r) - draw
        hwm = np.maximum(hwm, w)
        remaining = inp.horizon_months - (t + 1)
        newly_ruined = (~ruined) & (w < remaining * essential)
        ruined |= newly_ruined
        crossed = (crossing < 0) & (w >= inp.milestone)
        crossing[crossed] = t + 1

    return SimResult(
        terminal=w, ruined=ruined, crossing_month=crossing, gap=gap, essential=essential
    )


def percentile(arr: np.ndarray, q: float) -> float:
    return float(np.percentile(arr, q))


def cvar_lower(terminal: np.ndarray, ruined: np.ndarray, alpha: float) -> float:
    """Expected shortfall of the worst ``alpha`` fraction of NON-ruined paths."""
    survivors = terminal[~ruined]
    if survivors.size == 0:
        return float("nan")
    cutoff = np.percentile(survivors, alpha * 100.0)
    tail = survivors[survivors <= cutoff]
    return float(tail.mean()) if tail.size else float(cutoff)
