# Decision methodology

## Minimum calibrated stochastic drivers (reject over-parameterization)
The model uses the **minimum set of stochastic drivers that captures the real
dynamics**, each calibrated to a sourceable series; everything else is held fixed
and **labeled fixed**. A small calibrated model beats a large guessed one. The
drivers are: (1) the core-book total-return path (expected_return, volatility),
(2) a compounding income sleeve correlated to the core, and (3) the spending /
sequence-risk response. Greeks, IV, capture, and correlations are computed from
series, never invented.

## Data-integrity discipline
Every load-bearing input is labeled **verified / estimated / assumed**. No financial
figure that drives a decision is hardcoded from a secondary or scraped source.
Where a number drives a decision it is computed from a primary return/price series,
or the position is flagged and the engine degrades to `gather_more_data` / `wait`.
In **mock mode** the series are clearly-labeled `sample_fixture` stand-ins
(`app/data/fixtures.py`, `sample_fixtures/*.csv|json`); in **live mode** the same
math runs on real read-only Schwab pulls.

## Goal-trajectory objective
Find the **drawdown threshold** that **maximizes median terminal wealth** subject to
(a) **ruin probability ≤ 7.5%** and (b) a **downside-dispersion guard** (default:
p25 terminal ≥ `net_worth_total`; configurable to a CVaR floor on the worst 10% of
non-ruined paths). The threshold is an **output**, not an input. The optimizer
sweeps the threshold across a deterministic grid and selects the feasible candidate
with the highest median terminal wealth; if none is feasible it returns the
least-bad tradeoff, flagged. `bisect_boundary` is a separately-tested monotone
root-finder for constraint boundaries.

The threshold parameterizes a Markov response to drawdown depth from the high-water
mark: discretionary spend (≤ \$2,000/mo) is cut, scaling in with depth and full at
the threshold, while the VA floor (\$4,158/mo) is **never** cut; and exposure
de-risks once depth ≥ threshold (the "growth cost of a withdrawn dollar rises with
drawdown depth" — sequence risk). Higher thresholds stay risk-on through deeper
drawdowns (higher median terminal wealth in most regimes) at the cost of more ruin
and a fatter lower tail — which is exactly what the two constraints bound.

**Ruin** = a path can no longer fund the essential (non-discretionary) gap for the
remainder of the horizon given the VA income floor.

**Drag-ceiling modes** (`drag_anchor_mode`): `baseline_cagr` solves the largest
withdrawal whose CAGR stays within `drag_ceiling_bps` of the zero-withdrawal
baseline; `required_cagr` anchors to the CAGR required to reach the milestone minus
the drag. Both are implemented and differ on identical inputs.

## Sensitivity is the headline
`goal_trajectory_report.md` **leads** with a ±10/±20% sweep on expected_return AND
volatility (the two least-sourceable, most load-bearing inputs). The honest result
is the spread, not a single point estimate. A single fixed-seed Monte-Carlo run is
reproducible but is **not** the full probability picture (set `randomize_seed: true`
for real probability work).

## Income-sleeve comparison
Up/down capture is **regressed from a realized monthly total-return series** (fund
NAV+distributions vs the underlying index). If the fund's history is < 3 years
(e.g., QQQI), we substitute the longest-record peer (QYLD) for the capped bound and
say so. ROC is modeled as **regime-dependent**: when the trailing window is flat or
negative, Approach A's distributions may be eroding principal (destructive ROC). The
tool reports the A−B terminal-wealth delta and the regime dependence; the user
arbitrates.

## Momentum & macro
12-1 (skip-month) time-series + cross-sectional momentum, a blended-horizon option,
an absolute-momentum trend filter (the crash protection), and inverse-vol sizing to
a portfolio vol target. The 8-indicator macro framework maps to a 0–100% gross
multiplier with persistence thresholds. **Conflict rule**: when momentum says press
and macro says brake, the **brake wins on sizing** and the **engine wins on
selection**.

## Concentration banner
Every trajectory run shows AI/tech/semi exposure (% of `net_worth_total`), the
value-weighted average pairwise correlation of the risk sleeve, and the effective
independent bets (Meucci entropy). The book is a concentrated single-factor wager
being **monitored**, not diversified away; flagged above a configurable threshold.
