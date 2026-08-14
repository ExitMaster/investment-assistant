# Research run log

Chronological record of what was built, what failed, what was corrected and
why.  Entries are append-only.

---

## 2026-08-14 — Loop 1: data acquisition

### Source reachability probe
| Source | Result |
|---|---|
| FRED (`fredgraph.csv`) | OK — **but** silently black-holes requests carrying a browser `User-Agent`. Fixed by leaving the library's own UA in place. |
| Yahoo Finance chart API | OK after a cookie + crumb handshake (`fc.yahoo.com` → `finance.yahoo.com/quote/...` → `/v1/test/getcrumb`). Returns HTTP 429 when hit quickly; retry backoff and a 1.5 s throttle added. |
| LBMA (`prices.lbma.org.uk/json/gold_pm.json`) | OK — daily Gold Price PM in USD from 1968-04-01. |
| Kenneth French data library | OK. |
| S&P Dow Jones Indices export endpoint | **403** — no official SCHD (Dow Jones U.S. Dividend 100) or SPMO (S&P 500 Momentum) index history retrievable. |
| stooq.com | **Blocked** by a JavaScript proof-of-work challenge. Not used. |

### Consequences of the two unavailable index histories
No public total-return history exists for the Dow Jones U.S. Dividend 100 or
the S&P 500 Momentum index, and no total-return history of the Nasdaq-100
either (Yahoo carries `^NDX`, which is **price return only**).  The research
therefore cannot have a six-exposure official-index layer.  Rather than
fabricate one, the design splits into:

* `live` — actual ETF total returns only (common window starts 2015-11, when
  SPMO began trading);
* `structural` — long academic/benchmark series standing in for each economic
  exposure (primary layer, 1971-09 onwards);
* `index` — official `^SP500TR` and `^NDX` plus ETF price-return twins, used
  only for validation and dividend-inclusion audits.

### QQQ structural proxy — first choice rejected
The obvious proxy, French `BIG LoBM` (large-cap growth), was measured against
live QQQ over 1999-04..2026-06 and **rejected**: correlation 0.90 but
volatility ratio 0.67 and a dot-com drawdown of only −50.2% against QQQ's
−81.1%.  Using it would have flattered every QQQ-containing portfolio's tail
risk.  Candidates measured:

| candidate | corr | vol ratio | 2000-02 max DD |
|---|---|---|---|
| 2x3 `BIG LoBM` | 0.902 | 0.67 | −50.2% |
| BE-ME `Lo 10` | 0.911 | 0.74 | −58.1% |
| 5x5 `BIG LoBM` | 0.896 | 0.69 | −52.4% |
| 49-industry `Telcm/BusSv`-inclusive blend | 0.961 | 0.88 | −73.3% |
| **49-industry `Hardw`+`Softw`+`Chips`, equal weighted** | **0.974** | **1.06** | **−81.0%** |

Adopted the technology-industry composite.  It starts 1965-07 (first month all
three industries exist), which is before the primary sample's 1971-09 start.
Because it does not reach 1927, the secondary century-long sample excludes QQQ
as well as GOLD.

### Other proxy validations (same method)
* SPMO ← French `BIG HiPRIOR` (2x3 size × prior-12-2): corr 0.925, vol ratio
  0.97. Preferred over the top-decile `Hi PRIOR` (corr 0.868, vol ratio 1.36 —
  far more aggressive than SPMO).
* SCHD ← French `Hi 30` dividend-yield portfolio: corr 0.940, vol ratio 1.03.
  Preferred over `Hi 20`, `Hi 10` and large-value.
* SPY ← CRSP value-weighted U.S. market: corr 0.987, vol ratio 1.03.

These proxy choices were made by fitting **the proxy to the ETF**, not by
fitting portfolio results.  No portfolio outcome was consulted.

### Data defects found and handled
1. **CPI 2025-10 does not exist.** BLS never collected or published it
   (federal shutdown).  Log-interpolated between 2025-09 and 2025-11; the
   interpolation is named in `data_manifest.csv` and enforced by a test that
   refuses any other filled month.
2. **Partial current month.** The first build produced a 2026-08 "return"
   from 13 days of data.  Corrected: every panel is truncated to the last
   completed month.
3. **`GOLD` vs `GOLD_PRICE_ONLY` mismatch** in the first test run turned out
   to be a naming collision, not a data fault — the former was the LBMA
   benchmark, the latter GLD's unadjusted close.  Tests rewritten to compare
   like with like: GLD adjusted vs unadjusted close (identical, as a
   non-distributing trust must be) and GLD vs LBMA (corr > 0.93, GLD lagging
   by roughly its expense ratio).

### Tests at end of loop 1
56 passed, 0 failed.
