"""CLI smoke tests (Typer CliRunner) with a fast injected config."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

import app.cli as cli_mod
from app.cli import app
from app.config import load_config

runner = CliRunner()


@pytest.fixture
def fast_cfg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    def _make() -> object:
        cfg = load_config()
        cfg.trajectory.n_paths = 600
        cfg.trajectory.sensitivity_n_paths = 400
        cfg.trajectory.sensitivity_n_grid = 5
        cfg.trajectory.horizon_months = 96
        cfg.settings.reports_dir = str(tmp_path)
        return cfg

    monkeypatch.setattr(cli_mod, "load_config", _make)
    return _make


def test_load_portfolio_cmd(fast_cfg: object) -> None:
    result = runner.invoke(app, ["load-portfolio"])
    assert result.exit_code == 0
    assert "Schwab-managed value" in result.stdout
    assert "net_worth_total" in result.stdout


def test_compare_income_sleeve_cmd(fast_cfg: object) -> None:
    result = runner.invoke(app, ["compare-income-sleeve", "--no-write"])
    assert result.exit_code == 0
    assert "Capture up=" in result.stdout


def test_project_goal_cmd_writes_report(fast_cfg: object, tmp_path: Path) -> None:
    result = runner.invoke(app, ["project-goal"])
    assert result.exit_code == 0
    assert "Solved threshold" in result.stdout
    assert list(tmp_path.rglob("goal_trajectory_report.md"))


def test_run_all_cmd(fast_cfg: object, tmp_path: Path) -> None:
    result = runner.invoke(app, ["run-all", "--mock"])
    assert result.exit_code == 0
    assert "Run complete" in result.stdout
    assert list(tmp_path.rglob("income_sleeve_comparison.md"))
