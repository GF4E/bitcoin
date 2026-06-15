"""Lean Streamlit dashboard over the latest run folder.

Run:  streamlit run app/dashboard/app.py
It reads reports/runs/<latest>/ (generate it first with `python -m app.cli
run-all --mock`). Read-only: the dashboard never places trades.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from app.config import load_config

REPORTS = Path(load_config().config_dir).parent / "reports" / "runs"


def latest_run() -> Path | None:
    runs = sorted((p for p in REPORTS.glob("*") if p.is_dir()), reverse=True)
    return runs[0] if runs else None


def _md(run: Path, name: str) -> None:
    f = run / name
    st.markdown(f.read_text("utf-8") if f.exists() else f"_{name} not found_")


def _csv(run: Path, name: str) -> None:
    f = run / name
    if f.exists():
        st.dataframe(pd.read_csv(f), use_container_width=True)
    else:
        st.info(f"{name} not found")


def main() -> None:
    st.set_page_config(page_title="portfolio-tool", layout="wide")
    st.title("portfolio-tool — read-only decision support")
    st.caption("Does not place trades. Personal analysis only; not financial advice.")

    run = latest_run()
    if run is None:
        st.warning("No run folder found. Run `python -m app.cli run-all --mock` first.")
        return
    st.sidebar.success(f"Run: {run.name}")

    tabs = st.tabs(
        [
            "Portfolio Overview",
            "Holdings Decisions",
            "Opportunities",
            "Replacement",
            "Momentum",
            "LEAPS",
            "Covered Calls/Repair",
            "Execution/VWAP",
            "Goal Trajectory",
            "Income Sleeve",
            "Data Quality",
            "Trade Memos",
            "Settings",
        ]
    )
    with tabs[0]:
        _md(run, "portfolio_exposure_report.md")
    with tabs[1]:
        _csv(run, "current_holdings_decisions.csv")
    with tabs[2]:
        _csv(run, "opportunities_ranked.csv")
    with tabs[3]:
        _csv(run, "replacement_candidates.csv")
    with tabs[4]:
        _csv(run, "momentum_signals.csv")
    with tabs[5]:
        _csv(run, "leaps_candidates.csv")
    with tabs[6]:
        _csv(run, "covered_call_candidates.csv")
    with tabs[7]:
        _csv(run, "execution_flags.csv")
    with tabs[8]:
        _md(run, "goal_trajectory_report.md")
    with tabs[9]:
        _md(run, "income_sleeve_comparison.md")
    with tabs[10]:
        _csv(run, "data_quality_warnings.csv")
        _csv(run, "decision_log.csv")
    with tabs[11]:
        memos = sorted((run / "trade_memos").glob("*.md"))
        choice = st.selectbox("Memo", [m.name for m in memos]) if memos else None
        if choice:
            st.markdown((run / "trade_memos" / choice).read_text("utf-8"))
    with tabs[12]:
        meta = run / "run_metadata.yaml"
        cfgs = run / "configs_used.yaml"
        st.code(meta.read_text("utf-8") if meta.exists() else "run_metadata.yaml not found")
        if cfgs.exists():
            st.code(cfgs.read_text("utf-8"))


if __name__ == "__main__":
    main()
