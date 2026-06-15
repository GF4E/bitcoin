"""Integration: run_all writes the headline reports deterministically from fixtures."""

from __future__ import annotations

from pathlib import Path

from app.config import AppConfig, load_config
from app.reports.run_all import run_all


def _fast(tmp: Path) -> AppConfig:
    cfg = load_config()
    cfg.trajectory.n_paths = 800
    cfg.trajectory.sensitivity_n_paths = 500
    cfg.trajectory.sensitivity_n_grid = 5
    cfg.trajectory.horizon_months = 120
    cfg.settings.reports_dir = str(tmp)
    return cfg


def test_run_all_writes_headline_reports(tmp_path: Path) -> None:
    cfg = _fast(tmp_path)
    path = run_all(cfg, run_id="t1", base=tmp_path)

    gt = (path / "goal_trajectory_report.md").read_text("utf-8")
    assert "Sensitivity sweep (headline)" in gt
    assert "Concentration banner" in gt
    assert "Solved drawdown threshold" in gt
    assert "milestone-crossing distribution" in gt
    assert "does not place trades" in gt  # compliance footer

    isr = (path / "income_sleeve_comparison.md").read_text("utf-8")
    assert "Terminal-wealth delta (A minus B)" in isr
    assert "Empirically-derived capture" in isr
    assert "ROC regime flag" in isr

    for f in ("data_quality_warnings.csv", "assumptions_used.yaml", "run_metadata.yaml"):
        assert (path / f).exists()
    assert (path / "trade_memos").is_dir()


def test_run_all_is_deterministic(tmp_path: Path) -> None:
    cfg = _fast(tmp_path)
    a = run_all(cfg, run_id="a", base=tmp_path)
    b = run_all(cfg, run_id="b", base=tmp_path)
    # Report content is identical (fixed seed, fixed fixtures); only folder name differs.
    assert (a / "goal_trajectory_report.md").read_text("utf-8") == (
        b / "goal_trajectory_report.md"
    ).read_text("utf-8")
    assert (a / "income_sleeve_comparison.md").read_text("utf-8") == (
        b / "income_sleeve_comparison.md"
    ).read_text("utf-8")


def test_strict_compliance_footer(tmp_path: Path) -> None:
    cfg = _fast(tmp_path)
    cfg.settings.compliance_mode = "strict"
    path = run_all(cfg, run_id="strict", base=tmp_path)
    gt = (path / "goal_trajectory_report.md").read_text("utf-8")
    assert "neutral candidate labels" in gt
