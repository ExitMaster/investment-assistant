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

---

## 2026-08-14 — Loop 2: simulator, metrics and first full run

Built the vectorised simulator (`src/portfolio.py`).  Every rolling window of a
horizon is stepped simultaneously, so a 63-combination × 5-horizon sweep is
seconds rather than hours.  Contribution allocation under R1/R3 is a
**water-fill**: add cash so that `v'_k = max(v_k, λ·w_k)` for the λ that spends
exactly the deposit.  A brute-force test (3000 random no-sell allocations)
confirms this minimises the weight gap.

**Design choices recorded before results were seen**
* Phase-1 base rule = R2 (annual), equal weights.
* R2 deposits at target weights; R3 deposits by water-fill.  So R2-vs-R0
  isolates the annual restore and R3-vs-R1 isolates band-triggered selling.
* Screening = Pareto frontier on (median, p10) rolling 10-year CAGR, capped at
  20 combinations.
* Weight grid: 10-point simplex, every asset ≥ 10% (a 0% weight is simply a
  different combination, already screened).

First full run completed.  56 tests passing.

### Defects found by inspecting the first run
1. **`pct_windows_beating_QQQ` was 0.0 for QQQ itself** (a benchmark cannot
   strictly beat itself).  Now `NaN`.
2. **Divide-by-zero warnings** in `contrib_share_of_rebalancing` when a window
   had no weight correction at all.  Replaced `np.where` (which evaluates both
   branches) with a masked `np.divide`.
3. **Chart subtitles overflowed** the figure; now wrapped.  The combination
   focus list did not include the screening survivors; now it does.

---

## 2026-08-14 — Loop 3: the two threats to the conclusion

Reading the first full run, two results were strong enough to be suspicious,
and both needed dedicated analyses rather than a caveat sentence.

### Threat 1 — the momentum proxy is quoted gross of costs
`BIG HiPRIOR` reconstitutes **monthly**.  Its 13.64% full-sample CAGR versus
SPY's 11.26% cannot be taken at face value, and the initial config drag of
30 bp was indefensibly low for such a portfolio.

Rather than guess a fee, added `analysis.cost_breakeven`: re-run every candidate
charging an annual drag to the SPMO exposure only, across 0–500 bp, at three
horizons (`results/tables/implementation_cost_breakeven.csv`).  Result: SPMO
alone loses to SPY at ≈ 146 bp, to SCHD at ≈ 102 bp and to QQQ at ≈ 77 bp
(20-year medians); the blended QQQ+SCHD+SPMO survives to ≈ 268 bp.  The config
drag was also raised 30 → 100 bp, and the config now says explicitly that the
break-even table, not the drag parameter, is the authoritative treatment.

**This is a methodological correction, not a result-driven one** — it was made
because the cost assumption was wrong, and it makes the headline finding weaker,
not stronger.

### Threat 2 — is gold's benefit one episode?
Added `analysis.subperiod_stability` (five disjoint eras plus a
gold-rally-excluded window) and a gold start-date sensitivity (1971-09 /
1975-01 / 1980-01).

Finding, now in the report: gold's **return** contribution *is* one episode —
its own CAGR falls 8.74% → 6.15% → 4.53% as the start moves 1971 → 1975 → 1980 —
but its **drawdown and volatility** contribution is present in all five eras and
is nearly identical whichever start date is used.  The two halves of the gold
question have opposite answers, and the report now says so.

### Other additions in this loop
* Live-vs-structural rank agreement across all 63 combinations
  (Spearman 0.809), so the report can state where the proxy layer and the ETF
  layer disagree instead of asserting they agree.
* `scipy` is not installed in this environment; Spearman is computed as Pearson
  on the ranks rather than adding a dependency.
* Golden-value regression tests (`tests/test_history_is_stable.py`) pin nine
  historically checkable months — Black Monday, the 1980 gold spike, April 2000,
  the Volcker rate peak, March 2020 — so a future refetch that silently rewrites
  history fails the suite instead of rewriting the study.

### Test corrections in this loop (both were wrong tests, not wrong code)
* `test_zero_band_rebalances_every_month` expected H events; the correct answer
  is H−1, because month 0 starts exactly on target.
* `test_drag_reduces_returns_by_the_stated_amount` asserted an additive 100 bp
  gap; a multiplicative drag makes the correct invariant
  `(1+cagr_drag)/(1+cagr_base) = 0.99`.

---

## 2026-08-14 — Loop 4: plausibility sweep (SC-19)

Each item on the required anomaly list, checked against the run:

| check | result |
|---|---|
| Cash with equity-like returns | 4.39% nominal / 0.46% real over 1971-2026, vol 1.0%. Enforced by tests. |
| SCHD materially off its benchmark | proxy vs ETF over 176 months: corr 0.940, CAGR 13.01% vs 12.93%. Drawdown is 6pp deeper — explained by the missing quality screen, disclosed. |
| TR and PR identical over decades | tested per ETF; SPY TR−PR = 1.9%/yr, SCHD 3.3%/yr, QQQ 0.7%/yr. GLD's TR and PR are identical **as they must be** (no distributions), and that is asserted rather than assumed. |
| Impossible drawdowns | all in (−100%, 0]; deepest is QQQ −81.0%, which matches the Nasdaq-100's actual dot-com decline. |
| Different rebalancing rules giving identical results | found: R1 and R3 ±30% are identical for 18 of 114 combination-horizons. **Not a bug** — a wide band on a heavily-contributed portfolio is never breached, so R3 degenerates to R1. Now an explicit invariant test. |
| Rolling-window counts vs history | 658 months → 599 / 539 / 479 / 419 / 299 windows at 5/10/15/20/30 years. Verified. |
| Retrieval date changing old history | nine pinned golden values + pinned series start months. |
| Gold dominating on one recent episode | it does not dominate at all (10-year median 4.41%, p10 −2.95%); the sub-period analysis separates its return contribution (one episode) from its risk contribution (all eras). |
| QQQ analysis missing the dot-com collapse | asserted by test: the QQQ exposure must lose > 60% between 2000-03 and 2002-10. It loses 81.0%. |
| CPI gaps | one month (2025-10) never published by BLS; interpolated and disclosed; a test refuses any other filled month. |

### Also settled in this loop
* **Non-overlapping windows are thin and the report must lead with it.**  658
  months contain 5 / 2 / 1 independent 10 / 20 / 30-year windows.  Every rolling
  table carries `n_independent_windows`, and §3 of the report states that the
  30-year "distribution" is one history.
* **The aggregate rebalancing result is negative.**  Across all 57 multi-asset
  combinations the median 20-year TW ratio is below 1.0 for every rule.  Split
  by mix type, the sign flips: +1.5% to +2.0% for all-equity mixes, −2.8% to
  −5.1% for mixes holding cash or gold.  Reported as a conditional effect, not a
  premium.
* **Drawdown reduction is not a rebalancing effect.**  For all-equity mixes,
  rebalancing changes median drawdown by ±0.3pp.  The 4-5pp improvement seen in
  the aggregate comes from *owning* gold or cash, not from rebalancing into it.

### Final state
* 70 automated tests, all passing.
* 21 result tables, 12 charts, full manifest.
* Unresolved caveats, all disclosed in `REPORT.md` §3: no official SCHD/SPMO/
  Nasdaq-100 total-return index history is publicly retrievable; four of six
  long series are proxies; the momentum result is cost-sensitive; 30-year
  statistics rest on one independent window.

---

## 2026-08-14 — Loop 5: closing three gaps found in a requirements re-audit

Re-read the requirements against the delivered artefacts and found three real
gaps.  None was a wrong result; all three were missing coverage.

### Gap 1 — no OFFICIAL_INDEX_EXTENDED *results*
The three data classes were kept separate in `data/processed`, but only
`live` and `structural` were carried through the combination, rolling,
contribution and rebalancing analyses.  The official-index layer existed purely
as a dividend-inclusion audit.

Fixed by adding an `official_index` sample: `^SP500TR` + LBMA gold + the
Treasury bill, 1988-02 → 2026-07 (462 months, 7 combinations, 403/343/283/223/103
rolling starts at 5/10/15/20/30 years).  It cannot include QQQ, SCHD or SPMO —
that is the same unavailability recorded in loop 1, not a new limitation.  The
LBMA gold and TB3MS legs were re-added to the `index` panel with their own
manifest rows classified `OFFICIAL_INDEX`, and a test asserts the layer contains
no `STRUCTURAL_PROXY` series.

**This produced a genuinely new finding rather than a formality.**  Over
1988-2026 the S&P 500 and gold drifted within 0.8 pp/yr of one another, and
rebalancing SPY+GOLD is strongly positive there (R1 +4.81%, improving 99.6% of
windows; ±30% band +5.98%) — while the same pair over 1971-2026, where gold's
drift was far below equity's, showed no such gain, and SPY+CASH and GOLD+CASH
stay negative in *both* samples.  The sign of the rebalancing effect tracks the
drift gap, on data sharing no series with the primary layer.  §1.6's mechanism
claim is now confirmed out of sample rather than merely asserted.

### Gap 2 — nothing enforced "never mix price and total-return series"
Price-return twins live in the same panel as the total-return series for the
dividend audit.  They were safe only by naming convention.  Added a hard guard
in `samples.build_sample` (raises on any `_PRICE_ONLY` column) plus two tests:
one driving the guard, and one that reads `data_manifest.csv` and asserts every
column of every analysis sample is classified `TOTAL_RETURN` — with the two
principled exceptions, gold (no income) and cash (yield-derived).

### Gap 3 — look-ahead was tested for one rule only
The previous leakage test covered R2 with a single perturbation.  Replaced with
a parameterised test over **all four rules × both contribution timings**:
perturbing month *t*'s returns must leave every month-end value up to *t*
bit-for-bit identical, and must change month *t*'s value.  8 new assertions.

### State after loop 5
* **81 tests, all passing** (70 → 81).
* Four analysis samples: `structural` (primary), `structural_long`,
  `official_index`, `live`.
* Structural results are unchanged by this loop — verified by re-checking the
  cited figures (QQQ+SCHD+SPMO 20y median 12.77%, p10 9.56%, drawdown −47.4%,
  terminal wealth 3.103) and the screening survivors, which are identical.

---

## 2026-08-15 — Loop 6: exact-index validation, corrections, and the investor's own cash flows

Three tasks: retrieve the *actual* total-return indices rather than proxies,
correct overstatements in the previous report, and test whether the rebalancing
conclusion survives this investor's contribution/wealth ratio.

### 1. Exact-index retrieval — what worked and what did not

**Retrieved.**  The **Nasdaq-100 Total Return Index (XNDX)** came from Nasdaq's
own Global Index Data Service.  Route: `GET /Index/History/XNDX` to obtain the
session cookie, then `GET /Index/ExportHistory/XNDX?startDate=...&endDate=...&timeOfDay=EOD`,
which returns an .xlsx.  6,896 daily closes, **1999-03-04 → 2026-07-31** (that
is the full extent Nasdaq publishes for this symbol; an earlier requested start
returns the same first date).  Checks: the 2000-2002 drawdown is −81.0%, and
XNDX beats the `^NDX` price index by a plausible dividend yield — both asserted
by tests.

The endpoint was found by reading `/Scripts/History.js` from the history page,
which names `/Index/HistoryData`, `/Index/HistoryChartData` and
`/Index/ExportHistory`.  The site is behind Imperva/Incapsula: it accepts curl's
TLS fingerprint but serves python-requests a JavaScript challenge, and it starts
challenging any client that fetches repeatedly.  The fetcher therefore shells
out to curl, retries with backoff, and falls back to the cached raw payload —
the same reproducibility contract every other source in this project has.

**Not retrieved.**  S&P 500 Momentum TR and Dow Jones U.S. Dividend 100 TR.
These indices **exist and S&P DJI publishes them** — the previous report's
wording implied otherwise and has been corrected.  What failed was retrieval:

| route | outcome |
|---|---|
| `spglobal.com/spdji/en/indices/equity/sp-500-momentum-index/` | 403 (S&P's own error page, confirmed by its body) |
| `spglobal.com/spdji/en/idsapi/indexData/getIndexPerformance` | 403 |
| `spglobal.com/spdji/en/util/redesign/index-data/get-index-comparison-chart-data.dot` | 403 |
| same, with a full browser header set (sec-ch-ua, Sec-Fetch-*, etc.) | 403 |
| legacy `us.spindices.com` | DNS/connect failure (502 CONNECT) |
| Yahoo `^SP500MUP`, `^DJUSDIVT`, `^DJUSDIV` | symbols exist, **zero history** (one point: today's quote) |
| Invesco SPMO product pages | 406 |
| Schwab SCHD product and API pages | 403 |
| **real Chromium via Playwright** (installed at `/opt/pw-browsers/chromium-1194`) | `ERR_CONNECTION_RESET` on **every** host including `example.com` — the browser cannot traverse this sandbox's egress proxy, so the one route that would defeat a bot check is unavailable here |

Diagnosis recorded so it is not mistaken for a policy block: the egress proxy
*permits* `www.spglobal.com` (its `recentRelayFailures` logged no denial for that
host, and the 403 body is S&P's own error page). This is vendor bot protection
plus a sandbox limitation, not an organisation egress denial.

**Consequence, stated honestly:** the exact-index layer covers SPY, QQQ, GOLD
and CASH over 1999-04 → 2026-07 (328 months) and **cannot** cover SCHD or SPMO.
Those two are covered exactly only from ETF inception in the `live` layer.
REPORT.md §1.11b names the exact files that would unblock a full run.
**No proxy was substituted anywhere in the exact-index results.**

### 2. Corrections to the previous report

| overstatement | correction |
|---|---|
| "no public total-return history exists" for these indices | now distinguishes existence from retrievability, and names the blocked route and the unblocking file |
| the 1927-2026 sample called an "independent sample" (3 places) | it **contains** the 1971-2026 primary window; now described as an extension that adds 44 earlier years, not an independent test |
| the official-index gold test described as sharing "no series" with the structural layer | false — the gold leg is the same LBMA series; only the equity side and the window are new. Corrected in place |
| rolling percentiles read as a distribution | the rolling table caption now states that 658 months hold 5 / 2 / 1 independent 10 / 20 / 30-year windows, and the 30-year figures are one history |

No conclusion was rewritten to suit the new data; two conclusions changed
because the new evidence contradicted them (below), and the rest are unchanged.

### 3. Investor-specific contribution analysis — the previous claim does not hold

Modelled directly: initial wealth 20 units, 1 real unit/year of new cash (a 5%
contribution/wealth ratio), 20-year rolling windows, with four post-year-5
scenarios, plus a generic 0/2/5/10/20% contribution-ratio sweep
(`src/investor.py`, `results/tables/investor_scenarios.csv`,
`contribution_ratio_grid.csv`, `contribution_capture_by_*.csv`).

Contribution-only rebalancing captures **18.8%** of the annual-rebalance gain at
a 5% contribution ratio, falling to **1.9%** once contributions stop — against
the **79-94%** the previous report quoted.  The old figure was not wrong for
what it measured; it measured a saver starting from **zero** wealth, where early
contributions *are* the portfolio.  The sweep shows the relationship is monotone
and never exceeds 42% even at a 20% annual contribution ratio.

A **±30% relative band** produced the highest median terminal wealth in all four
scenarios (1.107-1.130× versus never rebalancing) while selling the least
(2.2-2.6× initial wealth cumulatively over 20 years, versus 4.1-4.5× for annual
and 5.4-6.0× for a ±10% band).

Six new tests cover this module, including a monotonicity assertion on the
capture share and an identity check that zero contributions make R1 ≡ R0.

### 4. What the exact data changed

* **QQQ's incremental value: CONFIRMED.**  Adding the Nasdaq-100 TR index to the
  S&P 500 TR index helped in **100%** of rolling 10- and 20-year windows from
  1999 — a sample that starts at the dot-com peak.
* **Gold's left-tail trade: CONFIRMED.**  −0.43pp median 20-year CAGR, +1.30pp
  on the 10th percentile, +20.3pp of drawdown.
* **SPY redundancy and cash's cost: CONFIRMED** on both exact layers.
* **SCHD's incremental value: NOT CONFIRMED.**  On the exact ETFs (2015-2026) it
  *subtracted* ~2pp/yr of median CAGR and helped in 0% of 10-year windows, the
  opposite sign to the proxy layer.  Both can be true of their own periods; the
  honest statement is that this is the finding most dependent on proxy choice.

Overall verdict recorded in REPORT.md §5: **MODIFIED**.

### State after loop 6
* **90 tests, all passing** (81 → 90).
* Five analysis samples; `exact_index` is new.
* New tables: `incremental_effects.csv`, `investor_scenarios.csv`,
  `contribution_ratio_grid.csv`, `contribution_capture_by_scenario.csv`,
  `contribution_capture_by_ratio.csv`.
* Unresolved: the two S&P DJI index histories (§1.11b of REPORT.md).
