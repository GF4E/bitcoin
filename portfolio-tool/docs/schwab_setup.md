# Schwab live read-only setup

Mock mode needs none of this. Live mode is **read-only** and isolated behind config.

## 1. Register a developer app
On the Schwab developer portal, create an app with the use-case **"personal trading
automation" (read-only)** — not institutional/algorithmic. Request only the
read scopes you need (accounts/positions, quotes, option chains, price history).

## 2. Obtain OAuth tokens
Complete the OAuth flow to get an **access token** and a **refresh token**. Keep
them out of the repo.

## 3. Configure locally
```bash
cp .env.example .env     # .env is gitignored
# edit .env:
# SCHWAB_ACCESS_TOKEN=...
# SCHWAB_REFRESH_TOKEN=...
# SCHWAB_TOKEN_EXPIRES_AT=<unix-seconds>
```
Set `mode: live_readonly` in `config/settings.yaml`.

## 4. Run
```bash
python -m app.cli run-all --live-readonly
```
The adapter (`app/schwab_client/`) applies tenacity retry/backoff and a local
timestamped cache; on an API failure it falls back to cache **only if fresh**, and
warns loudly if stale. Account numbers and tokens are never logged.

## Safety
v1 has **no order-placement endpoints**. `order_execution_enabled` defaults `false`
and `tests/unit/test_safety.py` enforces the read-only surface. See `SECURITY.md`.
