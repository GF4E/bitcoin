"""Safety/security: v1 is read-only, no order endpoints, no hardcoded credentials."""

from __future__ import annotations

import pytest

from app.config import AppConfig
from app.schwab_client.auth import OAuthTokens, load_tokens, needs_refresh
from app.schwab_client.client import SchwabClient, verify_read_only
from app.schwab_client.errors import SchwabAuthError
from app.schwab_client.rate_limit import RateLimiter


def test_no_order_or_execution_endpoints() -> None:
    assert verify_read_only(SchwabClient) == []
    assert SchwabClient.READ_ONLY is True


def test_order_execution_disabled_by_default(cfg: AppConfig) -> None:
    assert cfg.settings.order_execution_enabled is False


def test_mock_mode_needs_no_credentials() -> None:
    with pytest.raises(SchwabAuthError):
        load_tokens(env={})


def test_load_tokens_and_masking() -> None:
    tok = load_tokens(env={"SCHWAB_ACCESS_TOKEN": "abcd1234", "SCHWAB_REFRESH_TOKEN": "wxyz5678"})
    assert tok.access_token == "abcd1234"
    masked = tok.masked()
    assert "abcd1234" not in masked and "1234" in masked  # never expose the full token
    assert needs_refresh(OAuthTokens("a", "b", expires_at=0.0), now=10.0) is True


def test_from_config_requires_credentials(cfg: AppConfig, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SCHWAB_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("SCHWAB_REFRESH_TOKEN", raising=False)
    with pytest.raises(SchwabAuthError):
        SchwabClient.from_config(cfg)


def test_rate_limiter_min_interval() -> None:
    rl = RateLimiter(min_interval_s=0.5)
    assert rl.wait(now=100.0) == 0.0  # first call, no wait
    assert rl.wait(now=100.1) == pytest.approx(0.4)  # too soon -> wait the remainder
