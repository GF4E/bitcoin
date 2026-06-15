"""OAuth token handling — secrets stay out of the repo.

Tokens are read from environment variables (loaded from a gitignored .env), never
committed. Refresh uses the refresh token; the access token is never logged.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from app.schwab_client.errors import SchwabAuthError


@dataclass
class OAuthTokens:
    access_token: str
    refresh_token: str
    expires_at: float = 0.0

    def masked(self) -> str:
        return f"access=****{self.access_token[-4:]} refresh=****{self.refresh_token[-4:]}"


def load_tokens(env: dict[str, str] | None = None) -> OAuthTokens:
    """Load tokens from the environment. Raises if absent (mock mode needs none)."""
    e = env if env is not None else dict(os.environ)
    access = e.get("SCHWAB_ACCESS_TOKEN")
    refresh = e.get("SCHWAB_REFRESH_TOKEN")
    if not access or not refresh:
        raise SchwabAuthError(
            "SCHWAB_ACCESS_TOKEN / SCHWAB_REFRESH_TOKEN not set. Use --mock for credential-free runs."
        )
    return OAuthTokens(
        access_token=access,
        refresh_token=refresh,
        expires_at=float(e.get("SCHWAB_TOKEN_EXPIRES_AT", "0")),
    )


def needs_refresh(tokens: OAuthTokens, now: float) -> bool:
    return tokens.expires_at <= now
