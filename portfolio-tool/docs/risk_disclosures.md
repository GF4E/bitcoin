# Risk disclosures & compliance framing

This tool provides **decision support, screening, and scenario analysis** only. It
makes **no promised or guaranteed returns**, and it **places no trades**.

> This tool is for personal analysis only. It does not place trades and does not
> replace professional financial, tax, or legal advice.

## Options risk
Any options output (LEAPS, covered calls) carries these risks:
- **Max loss**: a long option can lose 100% of premium; the report shows max premium
  loss, % of net worth, and % of the LEAPS budget.
- **Assignment / early assignment**: short calls can be assigned, especially ITM
  around an ex-dividend date; the covered-call scenario tree models this.
- **Liquidity**: wide spreads and low open interest degrade fills; flagged per
  contract. No option VWAP is used for illiquid contracts.
- **Implied volatility / theta**: long options decay and are exposed to IV crush;
  LEAPS should be rolled 3–6 months before expiry.

## Concentration
The book is a concentrated single-factor (AI/tech/semi) wager. The concentration
banner runs every trajectory and flags exposure above the configured threshold. The
covered-call engine refuses to cap momentum leaders (let-winners-run); the LEAPS
engine adds leverage only to positive-trend leaders within budget.

## compliance_mode
With `compliance_mode: strict`, internal action tokens are mapped to **neutral
candidate labels** at the report boundary (e.g., `add` → `candidate_for_increase`),
tested in `tests/integration/test_run_all.py`. Audit logs (the decision log, run
metadata, assumptions) are preserved on every run.

## Assumptions
Every load-bearing input is labeled verified / estimated / assumed. In mock mode,
prices, Greeks, and capture come from clearly-labeled **sample fixtures**, not real
measurements — precise outputs built on sample inputs are illustrations, not results.
