"""Shared test fixtures."""

from __future__ import annotations

import pytest

from app.config import AppConfig, load_config
from app.data.quality import QualityLedger


@pytest.fixture
def cfg() -> AppConfig:
    return load_config()


@pytest.fixture
def ledger() -> QualityLedger:
    return QualityLedger()
