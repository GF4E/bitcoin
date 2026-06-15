"""VWAP overlay: calculation + status classification, timing-only."""

from __future__ import annotations

from app.config import AppConfig
from app.data.contracts import VWAPStatus
from app.execution.vwap import classify_status, compute_vwap_features, vwap_signal


def test_session_vwap_value() -> None:
    # vwap = sum(price*vol)/sum(vol)
    session = [(100.0, 10.0), (102.0, 30.0), (101.0, 10.0)]
    feats = compute_vwap_features("X", session)
    expected = (100 * 10 + 102 * 30 + 101 * 10) / 50
    assert abs(float(feats.session_vwap) - expected) < 1e-6


def test_missing_data_defaults_no_signal() -> None:
    feats = compute_vwap_features("X", [(100.0, 1.0)])
    assert feats.status is VWAPStatus.NO_SIGNAL


def test_status_classifier_extended_and_buyback() -> None:
    assert (
        classify_status(pvp=0.05, slope=0.5, zscore=2.0, above_pct=0.9)
        is VWAPStatus.EXTENDED_DO_NOT_CHASE
    )
    assert (
        classify_status(pvp=-0.02, slope=-0.3, zscore=-1.0, above_pct=0.2)
        is VWAPStatus.BUYBACK_WINDOW
    )
    assert classify_status(pvp=0.0, slope=0.0, zscore=0.0, above_pct=0.5) in (
        VWAPStatus.CLEAN_ENTRY,
        VWAPStatus.ACCEPTABLE_ENTRY,
    )


def test_vwap_signal_is_timing_only(cfg: AppConfig) -> None:
    sig = vwap_signal(cfg, "NVDA")
    assert sig.timing_only is True
    assert sig.status is not None
