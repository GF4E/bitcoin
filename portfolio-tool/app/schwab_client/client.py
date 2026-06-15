"""Read-only Schwab client.

v1 is READ-ONLY: account/position, quote, option-chain, and price-history pulls
only. There are NO order-placement / execution endpoints — by design and enforced
by tests/unit/test_safety.py. OAuth load/refresh, tenacity retry/backoff, and a
local timestamped cache with freshness validation wrap the read paths. Account
numbers and tokens are never logged. Application use-case for the Schwab developer
portal is "personal trading automation" (read-only), not institutional.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from app.schwab_client.auth import OAuthTokens, load_tokens
from app.schwab_client.errors import SchwabAPIError, StaleCacheError
from app.schwab_client.rate_limit import RateLimiter

# Method-name fragments that would indicate an execution endpoint. The safety test
# asserts no public method matches any of these — v1 must remain read-only.
FORBIDDEN_METHOD_FRAGMENTS = (
    "order",
    "place",
    "execute",
    "submit",
    "trade",
    "buy",
    "sell",
    "cancel",
)


class SchwabClient:
    """Read-only adapter. Construct via :meth:`from_config` for live use."""

    READ_ONLY = True
    base_url = "https://api.schwabapi.com/trader/v1"

    def __init__(
        self,
        tokens: OAuthTokens,
        cache_dir: str = ".cache",
        cache_ttl_s: float = 900.0,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        self._tokens = tokens
        self._cache_dir = Path(cache_dir)
        self._cache_ttl_s = cache_ttl_s
        self._rate = rate_limiter or RateLimiter()

    @classmethod
    def from_config(cls, cfg: Any) -> SchwabClient:
        tokens = load_tokens()  # raises SchwabAuthError without credentials
        return cls(tokens=tokens, cache_dir=cfg.settings.cache_dir)

    # -- read-only endpoints (network; exercised only with live credentials) ----
    def get_accounts_raw(self) -> dict[str, Any]:  # pragma: no cover - requires credentials
        return self._cached_get("accounts", "/accounts?fields=positions")

    def get_quotes(self, symbols: list[str]) -> dict[str, Any]:  # pragma: no cover
        return self._cached_get(
            f"quotes:{','.join(symbols)}", f"/quotes?symbols={','.join(symbols)}"
        )

    def get_option_chain(self, symbol: str) -> dict[str, Any]:  # pragma: no cover
        return self._cached_get(f"chain:{symbol}", f"/chains?symbol={symbol}")

    def get_price_history(self, symbol: str) -> dict[str, Any]:  # pragma: no cover
        return self._cached_get(f"history:{symbol}", f"/pricehistory?symbol={symbol}")

    # -- internals --------------------------------------------------------------
    def _cached_get(self, key: str, path: str) -> dict[str, Any]:  # pragma: no cover - network
        import diskcache  # local import keeps mock mode dependency-light

        cache = diskcache.Cache(str(self._cache_dir))
        now = time.time()
        try:
            time.sleep(self._rate.wait())
            payload = self._http_get(path)
            cache.set(key, {"ts": now, "payload": payload})
            return payload
        except SchwabAPIError:
            cached = cache.get(key)
            if cached is None:
                raise
            age = now - float(cached["ts"])
            if age > self._cache_ttl_s:
                raise StaleCacheError(
                    f"cache for {key} is stale ({age:.0f}s > {self._cache_ttl_s:.0f}s)"
                ) from None
            return dict(cached["payload"])

    def _http_get(self, path: str) -> dict[str, Any]:  # pragma: no cover - network
        import httpx
        from tenacity import retry, stop_after_attempt, wait_exponential

        @retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, max=16))
        def _do() -> dict[str, Any]:
            headers = {"Authorization": f"Bearer {self._tokens.access_token}"}
            resp = httpx.get(f"{self.base_url}{path}", headers=headers, timeout=15.0)
            if resp.status_code >= 400:
                raise SchwabAPIError(f"GET {path} -> {resp.status_code}")
            return dict(resp.json())

        return _do()


def verify_read_only(client_cls: type = SchwabClient) -> list[str]:
    """Return any public method whose name implies execution (must be empty)."""
    return [
        name
        for name in dir(client_cls)
        if not name.startswith("_")
        and callable(getattr(client_cls, name))
        and any(frag in name.lower() for frag in FORBIDDEN_METHOD_FRAGMENTS)
    ]
