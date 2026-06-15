# Troubleshooting

**`ModuleNotFoundError: app`** — activate the venv and `pip install -e ".[dev]"`
from inside `portfolio-tool/`. All imports are `app.*`.

**`make check` fails on coverage** — the gate is 85% (`--cov-fail-under`). Add tests
or run `pytest -o addopts="" -q` to see failures without the gate.

**`pip install` cannot reach PyPI** — the runtime works offline in mock mode, but the
initial install needs network. Use a machine/CI with PyPI access, or a local wheel
cache.

**`project-goal` / `run-all` feel slow** — the Monte-Carlo defaults are 10,000 paths
and a 5×5 sensitivity grid. Reduce `trajectory.n_paths`, `sensitivity_n_paths`, or
`sensitivity_n_grid` in `config/goal_plan.yaml` for faster (less precise) runs.

**Reports changed between runs** — they shouldn't, with a fixed seed. If you set
`trajectory.randomize_seed: true`, output is intentionally non-deterministic (real
probability mode). A single fixed-seed run is not the full probability picture.

**`SchwabAuthError` in live mode** — set `SCHWAB_ACCESS_TOKEN` /
`SCHWAB_REFRESH_TOKEN` in `.env` and `mode: live_readonly`. Mock mode needs no
credentials. See `docs/schwab_setup.md`.

**Stale-cache warning in live mode** — the API call failed and the cached copy is
older than the TTL; the adapter warns rather than serving stale data silently.

**Covered-call screener returns nothing** — momentum leaders are protected from
call-writing. Only ballast/neutral holdings you would accept being called away are
surfaced (set `allow_leader_override` to consider leaders).
