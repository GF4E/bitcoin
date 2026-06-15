# Security

This is a **local, read-only personal analysis tool**. It is not a server, not a
trading bot, and not multi-tenant.

## v1 safety guarantees
- **Read-only.** No order-placement / execution endpoints exist. `SchwabClient`
  exposes only account/quote/chain/price-history reads;
  `tests/unit/test_safety.py` fails if any method name implies execution.
- **`order_execution_enabled` defaults `false`** in `config/settings.example.yaml`.
  If execution code is ever added, it must be gated behind this flag and tests must
  fail unless it is explicitly enabled.
- **Mock mode needs no credentials.** `python -m app.cli run-all --mock` runs
  entirely from packaged fixtures.

## Secret handling
- Tokens live in environment variables, loaded from a **gitignored `.env`**. Only
  `.env.example` (empty placeholders) is tracked.
- `.gitignore` excludes `.env`, `*.token`, `*token*.json`, the local cache, and
  generated run outputs (which may contain account values).
- Access/refresh tokens are **never logged**; `OAuthTokens.masked()` shows only the
  last 4 characters.
- Account numbers are **masked** (`****1234`) unless `mask_account_ids: false`.

## Reporting
This is a personal project; report issues to the repository owner. Do not paste
real tokens or account numbers into issues or logs.
