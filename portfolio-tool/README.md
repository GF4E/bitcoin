# portfolio-tool

A **local, read-only** Schwab portfolio + trade-decision **support** tool. It is
decision support, screening, and scenario analysis only — it **places no trades**
and contains no order-execution endpoints. Generalized, not hardcoded around any
holding.

> This tool is for personal analysis only. It does not place trades and does not
> replace professional financial, tax, or legal advice.

## What it does
- **Goal-trajectory engine** (the centerpiece): a calibrated Monte-Carlo model that
  *solves* for the drawdown-spending threshold maximizing median terminal wealth,
  subject to a ruin cap and a downside-dispersion guard. Leads with a sensitivity
  sweep and a live concentration banner. Reports the 5M milestone-crossing
  distribution (a milestone, not the target).
- **Income-sleeve comparison**: capped income (A) vs uncapped + buffer (B) under
  identical paths, with **empirically-derived** up/down capture (never hardcoded)
  and a regime-dependent ROC flag.
- **Holdings / opportunities / replacement** evaluation, a **vol-targeted momentum
  engine** with an 8-indicator macro throttle and the conflict rule, **LEAPS** and
  **covered-call/repair** screeners (with leader-no-call enforcement), and a **VWAP**
  execution overlay.
- Deterministic reports + trade memos + a decision log, all reproducible from
  fixtures.

## Quick start (mock mode — zero credentials)
```bash
cd portfolio-tool
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
make check            # ruff + mypy + pytest (coverage gate)
python -m app.cli run-all --mock
```
Then inspect, in this order:
1. `reports/runs/<timestamp>/goal_trajectory_report.md`
2. `reports/runs/<timestamp>/income_sleeve_comparison.md`
3. the CSVs (`current_holdings_decisions.csv`, `leaps_candidates.csv`,
   `covered_call_candidates.csv`, `momentum_signals.csv`, `decision_log.csv`).

## CLI
`load-portfolio`, `evaluate-holdings`, `evaluate-opportunities`, `screen-leaps`,
`screen-covered-calls`, `run-momentum`, `project-goal`, `compare-income-sleeve`,
`generate-reports`, `run-all --mock` / `--live-readonly`.

## Live read-only
Copy `.env.example` to `.env`, fill in Schwab OAuth tokens, set
`mode: live_readonly` in `config/settings.yaml`, then `run-all --live-readonly`.
See `docs/schwab_setup.md`. Live mode is isolated behind config; mock is the default.

## Dashboard (optional)
```bash
pip install -e ".[dashboard]"
streamlit run app/dashboard/app.py
```

## Docs
`docs/setup.md`, `docs/schwab_setup.md`, `docs/data_contracts.md`,
`docs/calculations.md`, `docs/decision_methodology.md`, `docs/risk_disclosures.md`,
`docs/architecture.md`, `docs/troubleshooting.md`. Security: `SECURITY.md`.

## Key design rules
- **Two net-worth denominators**: `net_worth_total` for risk/withdrawal/goal math;
  `schwab_managed_value` for concentration/reconciliation. Never conflated.
- **Decimal/float boundary**: money is `Decimal`; statistics (Greeks, IV, VWAP,
  Monte-Carlo) are `float`; conversions are explicit; money is rounded at emit.
- **No hardcoded financial figures from secondary sources** — capture/momentum are
  computed from return series (live pulls, or clearly-labeled sample fixtures in
  mock mode).
