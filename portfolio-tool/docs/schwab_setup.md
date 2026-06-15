# Connect your real account (read-only) — step by step

Mock mode needs none of this. Live mode is **read-only** — the tool never places
trades. The connection runs on **your machine** with **your** tokens; the tool just
reads. Follow these in order.

## 0. Prerequisites
- The tool installed and `make check` green (see `docs/setup.md`).
- A Schwab brokerage account and a Schwab developer account
  (https://developer.schwab.com).

## 1. Register a read-only developer app
1. Sign in at the Schwab developer portal and create a new **App**.
2. For the product/API, select the **Accounts and Trading** (Trader) API. (We only
   call its read endpoints — accounts, quotes, option chains, price history.)
3. Set the app's use-case to **personal trading automation (read-only)** — not
   institutional/algorithmic.
4. Set the **callback URL** to `https://127.0.0.1` (a localhost redirect is fine for
   a personal app).
5. Save. Note your **App Key** (client id) and **App Secret**. Wait for the app to
   move to **Ready/Approved**.

## 2. Get OAuth tokens
Schwab uses OAuth 2.0 (authorization-code flow). The one-time flow:
1. In a browser, open the authorize URL for your app (App Key + your callback),
   sign in, and approve **read** access to your account.
2. You'll be redirected to `https://127.0.0.1/?code=...`. Copy the `code` value.
3. Exchange that code for tokens (a POST to Schwab's token endpoint with your App
   Key/Secret). You get an **access token** (short-lived) and a **refresh token**
   (longer-lived). Keeping a tiny helper script or using a community Schwab OAuth
   helper for this exchange is fine — just never commit the output.

> Tip: the access token expires quickly; the refresh token is what you keep. This
> tool reads both from your environment.

## 3. Put the tokens in `.env` (gitignored)
```bash
cd portfolio-tool
cp .env.example .env        # .env is gitignored; never commit it
```
Edit `.env`:
```
SCHWAB_ACCESS_TOKEN=<your access token>
SCHWAB_REFRESH_TOKEN=<your refresh token>
SCHWAB_TOKEN_EXPIRES_AT=<unix seconds when the access token expires>
```

## 4. Switch the tool to live mode
```bash
cp config/settings.example.yaml config/settings.yaml   # if you don't have one
```
In `config/settings.yaml` set:
```yaml
mode: live_readonly
```

## 5. Run it
```bash
. .venv/bin/activate
python -m app.cli load-portfolio --no-mock        # quick sanity check of positions
python -m app.cli run-all --live-readonly         # full report set on real data
```
Reports land in `reports/runs/<timestamp>/`. Inspect `goal_trajectory_report.md` and
`income_sleeve_comparison.md` first.

## What is live vs. still manual
- **Live from Schwab**: positions/accounts, quotes, option chains, and price history
  (monthly/daily/intraday) — these now flow through the read-only client.
- **Still manual/config**: the 8-indicator **macro throttle** (Brent, VIX, Hormuz
  tanker flow, FedWatch odds, etc.) — Schwab doesn't provide these; maintain them in
  the macro-state file. The **external static sleeve** (your S&P funds outside
  Schwab) stays a manual holding by design.
- Your goal-plan assumptions (`expected_return_annual`, `volatility_annual`,
  spending, budgets) are yours to set in `config/goal_plan.yaml`.

## Important caveat
The live data-pull layer is implemented against Schwab's **documented** API and is
verified here only against Schwab-shaped sample fixtures — it is **not** verified
end-to-end against the live API. On your first live run, sanity-check the numbers
against what you see in the Schwab app (a few share counts, prices, an option
strike). Field names/casing may need small tweaks against the live responses; the
parsers live in `app/schwab_client/parse.py`. Live mode also emits a data-quality
warning noting the layer is newly added.

## Safety
v1 has **no order-placement endpoints**; `order_execution_enabled` defaults `false`
and `tests/unit/test_safety.py` enforces the read-only surface. Tokens and account
numbers are never logged. See `SECURITY.md`.
