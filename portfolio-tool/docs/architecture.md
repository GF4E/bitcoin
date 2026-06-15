# Architecture

Package root is `app/`; all imports are `app.*`; the CLI is `app.cli`.

## Data flow
```
config/*.yaml ─► app.config (typed)                         sample_fixtures/* (mock)
                     │                                            │  live: app.schwab_client (read-only)
                     ▼                                            ▼
            app.data.normalize  ◄──────────────────────  raw Schwab-shaped dicts
                     │  (Holding, Account; masking; P/L; quality flags)
                     ▼
        ┌──────────── engines (consume normalized contracts) ────────────┐
        │ goal/ (monte_carlo, objective, concentration, trajectory,       │
        │        income_sleeve)   portfolio/ (exposure, reconciliation,   │
        │        holding_evaluator, replacement)   opportunities/         │
        │        options/ (leaps, covered_call, payoff, chains)           │
        │        momentum/ (engine, throttle)   execution/ (vwap)         │
        └─────────────────────────┬──────────────────────────────────────┘
                                   ▼
                        app.decision_engine  (DecisionBundle + decision log)
                                   ▼
              app.reports (run_all → markdown + CSV + memos + run folder)
                                   ▼
                    reports/runs/<timestamp>/   ── app.dashboard reads these
```

## Boundaries
- **Adapter boundary**: raw shapes are normalized in `app.data.normalize`; no Schwab
  field names leak into engines.
- **Decimal/float boundary**: `app.money` + `MoneyField` (see `docs/calculations.md`).
- **Render boundary**: `app.reports.compliance` maps action tokens to neutral labels
  under strict mode.

## Determinism
Fixed seeds + fixed fixtures + money rounded at emit ⇒ byte-identical report content
across runs (only the run-folder timestamp differs). Snapshot/equality tests guard
this.

## Two denominators
`net_worth_total` (risk/withdrawal/goal) and `schwab_managed_value`
(concentration/reconciliation) are carried separately on `RiskBudget` and used by
distinct engines; a unit test asserts they are never conflated.
