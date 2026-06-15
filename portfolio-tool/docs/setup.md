# Setup

## Requirements
- Python 3.11+ (3.11/3.12/3.13 tested).
- A network connection to install dependencies from PyPI (the runtime itself works
  offline in mock mode).

## Install
```bash
cd portfolio-tool
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"          # add ,dashboard for Streamlit
```

## Verify
```bash
make check        # ruff format-check + ruff lint + mypy + pytest (coverage gate)
make run-mock     # == python -m app.cli run-all --mock
```
`make check` must pass before committing. Reports land in `reports/runs/<timestamp>/`
(gitignored).

## Configuration
All user-context numbers live in `config/*.yaml` — never in code. Copy
`config/settings.example.yaml` to `config/settings.yaml` to override locally
(gitignored). Point `PORTFOLIO_TOOL_CONFIG` at an alternate config directory if you
keep configs elsewhere.

Key files: `goal_plan.yaml` (net worth, milestone, spending, trajectory knobs),
`risk_budget.yaml` (two denominators, LEAPS budget), `momentum.yaml`,
`income_sleeve.yaml`, `sleeve_classifications.yaml`, `watchlists.yaml`,
`scoring_weights.yaml`, `decision_thresholds.yaml`, plus `holding_overrides.yaml`
and `dividend_overrides.yaml` for manual overrides.

## Live read-only (optional)
See `docs/schwab_setup.md`.
