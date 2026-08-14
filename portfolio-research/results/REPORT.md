# What survives: six exposures, 63 combinations, 658 months

**Primary evidence**: `structural` sample, 1971-09 → 2026-06 (658 months), all six
exposures, equal weights, annual rebalancing, monthly rolling start dates.
**Validation**: `live` sample, 2015-11 → 2026-07 (129 months), actual ETFs.
**Official-index cross-check**: `official_index`, 1988-02 → 2026-07 (462 months), SPY/GOLD/CASH only.
**Century check**: `structural_long`, 1927-07 → 2026-06 (1188 months), four exposures.

Everything below is reproduced by `python run_research.py`; every number cited
appears in `results/tables/`.  Read §3 (Limitations) before acting on §1.

> **The single most important caveat.** Four of the six long series are
> *structural proxies*, not the funds.  SPMO's proxy is an academic momentum
> portfolio that reconstitutes monthly and is quoted gross of all costs.  Its
> measured advantage is worth about **145 basis points a year of implementation
> cost** and no more (§1.7).  Every statement about "SPMO" over 1971-2026 is a
> statement about large-cap momentum as an *idea*, not about the ETF.

---

## 1. Verified findings

Directly supported by the reproduced results.

### 1.1 The six exposures, on their own (full sample, 1971-09 → 2026-06)

| | CAGR | real CAGR | vol | max drawdown | longest underwater | worst calendar year |
|---|---|---|---|---|---|---|
| SPMO | 13.64% | 9.37% | 16.9% | −48.0% | 63 months | −36.4% |
| SCHD | 12.45% | 8.22% | 14.2% | −56.1% | 60 months | −33.0% |
| QQQ | 12.15% | 7.94% | 24.9% | **−81.0%** | **201 months** | −43.1% |
| SPY | 11.26% | 7.08% | 15.7% | −50.3% | 72 months | −36.7% |
| GOLD | 8.74% | 4.65% | 19.7% | −61.8% | **318 months** | −32.6% |
| CASH | 4.39% | 0.46% | 1.0% | 0.0% | 0 | 0.0% |

Source: `results/tables/all_equal_weight_combinations.csv`.

Two numbers deserve to be read slowly.  The technology exposure spent
**16 years and 9 months** below its March-2000 peak.  Gold spent **26 years and
6 months** below its January-1980 peak.  Both are properties of the actual
historical record, not artefacts.

### 1.2 Rolling-horizon robustness

Median / 10th-percentile / worst annualised return across every monthly start:

| horizon | SPMO | SCHD | QQQ | SPY | GOLD | CASH |
|---|---|---|---|---|---|---|
| 10y | 14.27 / 7.43 / −0.42 | 13.21 / 6.65 / +0.10 | 13.45 / 4.36 / −8.35 | 12.75 / 5.54 / −2.52 | 4.41 / −2.95 / −5.99 | 4.16 / 0.55 / 0.26 |
| 20y | 12.46 / 9.36 / 5.73 | 11.31 / 8.44 / 6.96 | 11.74 / 7.77 / 2.25 | 10.81 / 7.76 / 4.98 | 5.84 / −0.82 / −4.36 | 4.22 / 1.42 / 1.13 |
| 30y | 13.18 / 11.64 / 10.63 | 12.46 / 10.56 / 9.41 | 12.24 / 10.34 / 8.98 | 10.84 / 9.93 / 9.42 | 4.68 / 3.26 / 1.69 | 3.98 / 2.28 / 2.21 |

(percent; `results/tables/rolling_{10,20,30}y.csv`)

The ordering SPMO > SCHD ≈ QQQ > SPY > GOLD > CASH is stable at every horizon
from 5 to 30 years, and it also holds on the independent 1927-2026 sample for
the four exposures that reach back that far (SPMO 14.16%, SCHD 12.83%,
SPY 10.89%, CASH 3.28% median rolling 20-year CAGR).

### 1.3 The best combinations are not the highest-return ones

Rolling 20-year windows, real terminal wealth per unit of real contributions:

| portfolio | median CAGR | p10 CAGR | median max DD | TW per real unit (median / p10) | % of windows beating SPY |
|---|---|---|---|---|---|
| QQQ+SCHD+SPMO | 12.77% | 9.56% | −47.4% | 3.10 / 2.05 | 100% |
| QQQ+SPMO | 12.54% | 9.12% | −63.1% | 3.09 / 1.95 | 100% |
| SPMO | 12.46% | 9.36% | −42.7% | 3.06 / 1.96 | 87.6% |
| **QQQ+SCHD+SPMO+GOLD** | 11.76% | **9.57%** | **−34.7%** | 2.47 / **2.16** | 59.7% |
| QQQ | 11.74% | 7.77% | −81.0% | 2.59 / 1.75 | 79.2% |
| SPY | 10.81% | 7.76% | −46.5% | 2.34 / — | — |

Adding gold costs about **1.0 percentage point of median annual return** and
**0.63 of a unit of median terminal wealth**, and buys the **best 10th-percentile
outcome of any portfolio tested** plus a drawdown 12.7 points shallower.  That
is the central trade in this study.

### 1.4 The screening survivors

Four of the 63 equal-weight combinations survive the pre-specified Pareto
screen on (median, 10th-percentile) rolling 10-year CAGR:

```
QQQ+SPMO           QQQ+SCHD+SPMO
QQQ+SCHD+SPMO+GOLD SPY+QQQ+SCHD+SPMO+GOLD
```

Every survivor contains SPMO and QQQ.  No survivor contains CASH.  Only one
contains SPY, and it is dominated in growth by the same portfolio without SPY.
(`results/tables/screening_survivors.csv`)

### 1.5 Favourable allocations are a broad plateau, not a fitted point

For QQQ+SCHD+SPMO over rolling 20-year windows, the coarse 10-point grid
maximum is 12.92% at 30/20/50.  Its six grid neighbours range 12.61%–12.92% —
a **2.4% relative shortfall at worst**.  The entire region

```
QQQ 20-50%    SCHD 10-40%    SPMO 30-70%
```

sits between 12.4% and 12.9%.  Only the SCHD-dominant corner (SCHD ≥ 70%)
falls away, to 11.9%.  This is a genuine plateau: no allocation inside it is
distinguishable from any other given the sampling error, so the choice within
it is not a research finding and should be made on other grounds (simplicity).

For the four-asset set the picture is the same in the equity dimensions, and
gold behaves monotonically: **more gold always lowers median return and always
lowers drawdown**, with no interior optimum.  Choosing a gold weight is
therefore a preference, not an estimate.
(`results/tables/candidate_weight_grid.csv`, `plateau_analysis.csv`,
`charts/plateau_*.png`)

### 1.6 Rebalancing: there is no general premium, and the sign depends on the mix

Rolling 20-year accumulation windows, terminal wealth relative to never
rebalancing (R0), median across the 57 multi-asset combinations:

| rule | all-equity mixes (11) | mixes with CASH or GOLD (46) | turnover/yr | drawdown vs R0, equity mixes | drawdown vs R0, CASH/GOLD mixes |
|---|---|---|---|---|---|
| R1 contribution-only | **+1.47%** (82% of windows improved) | −5.05% (23% improved) | 0.0% | unchanged | unchanged |
| R2 annual | **+2.04%** (80% improved) | −2.95% (39% improved) | 4.1% | 0.3pp *deeper* | 4.9pp shallower |
| R3 ±10% band | +1.92% (80% improved) | −3.38% (28% improved) | 4.0% | 0.2pp shallower | 4.0pp shallower |
| R3 ±20% band | +1.71% (80% improved) | −3.27% (34% improved) | 2.4% | 0.2pp deeper | 4.6pp shallower |
| R3 ±30% band | +1.62% (82% improved) | −2.76% (44% improved) | 1.7% | 0.3pp deeper | 4.3pp shallower |

The drawdown columns matter: **rebalancing an all-equity mix does not reduce
drawdown at all** (±0.3pp).  The drawdown benefit attributed to rebalancing in
this study comes entirely from mixes that hold gold or cash — that is, from
*owning* a defensive asset, not from *rebalancing* into it.

Across *all* 57 combinations the median effect of every rule on terminal wealth
is **negative**, and fewer than half of windows improve.  The worst single
window under annual rebalancing finished at **0.44×** the no-rebalancing result.

The mechanism is not mysterious: rebalancing systematically moves money from
the higher-drift asset to the lower-drift one.  Among assets with similar
long-run drifts (the equity mixes) the variance harvest wins; when one asset
drifts far below the others (cash, gold) the transfer dominates and rebalancing
converts return into drawdown reduction.

This is not a January artefact: rebalancing in January, April, July or October
gives median ratios of 1.0031–1.0059 for QQQ+SPMO and 1.0051–1.0059 for
QQQ+SCHD+SPMO. (`results/tables/rebalance_month_sensitivity.csv`)

**How much do contributions alone capture?**  Among the 18 combinations where
annual rebalancing raised median 20-year terminal wealth, contribution-only
rebalancing captured a median **55%** of that gain — and for the all-equity
candidates specifically, **79%–94%** (QQQ+SPMO 79%, QQQ+SCHD+SPMO 82%,
QQQ+SCHD 91%, SPY+QQQ+SCHD 94%).  At the 10-year horizon contribution-only
rebalancing *beat* annual rebalancing outright (median capture 123%).
Contributions also do most of the mechanical work under a band rule: 77% of all
weight correction under a ±20% band, 83% under ±30%.

### 1.7 What implementation cost would erase the momentum advantage

Median rolling 20-year CAGR with an annual cost charged to the SPMO exposure
only (`results/tables/implementation_cost_breakeven.csv`,
`charts/cost_breakeven.png`):

| SPMO falls below… | at an annual cost of |
|---|---|
| QQQ (11.74%) | ≈ 77 bp |
| SCHD (11.31%) | ≈ 102 bp |
| SPY (10.81%) | ≈ 146 bp |

The blended QQQ+SCHD+SPMO portfolio is far more tolerant: it stays above QQQ up
to ≈ 268 bp and above SPY beyond 500 bp, because only a third of it carries the
cost.  **Diversifying the momentum exposure is what makes the momentum finding
survivable.**

For calibration, the live SPMO ETF charges 13 bp and reconstitutes twice a year,
while the proxy reconstitutes monthly; the proxy therefore overstates achievable
momentum returns, and by how much is not measurable from these data.

### 1.8 Gold: the return is one episode, the risk reduction is not

Adding GOLD to QQQ+SCHD+SPMO, by era (`results/tables/subperiod_stability.csv`):

| era | Δ CAGR | Δ max drawdown | Δ volatility |
|---|---|---|---|
| 1971-09 → 1980-12 | **+7.53pp** | +19.3pp better | −2.3pp |
| 1981-01 → 1994-12 | −4.05pp | +8.3pp better | −3.0pp |
| 1995-01 → 2009-12 | −0.17pp | +14.7pp better | −4.0pp |
| 2010-01 → 2018-12 | −2.35pp | +4.8pp better | −2.1pp |
| 2019-01 → 2026-06 | −0.61pp | +3.3pp better | −3.4pp |

Gold's *return* contribution is entirely the 1970s: its own CAGR falls from
8.74% measured from 1971-09 to 6.15% from 1975-01 and 4.53% from 1980-01
(`results/tables/gold_start_sensitivity.csv`).  Its *risk* contribution is
present in all five eras without exception, and the drawdown improvement from
adding gold is essentially unchanged whichever start date is used
(−51.6%→−35.6% from 1971; −51.3%→−36.6% from 1975 and from 1980).

### 1.9 Cash: a consistent, one-directional trade

Adding CASH to QQQ+SCHD+SPMO reduced CAGR in **every** era tested (−0.62pp to
−4.40pp) and reduced max drawdown in **every** era (+3.5pp to +12.6pp).  Over
the full sample it costs 1.97 percentage points a year and returns 11.9 points
of drawdown.  No CASH-containing combination survived the screen.

### 1.10 Live-ETF validation

Rank correlation between the structural median 10-year CAGR ranking and the
actual 2015-11 → 2026-07 ETF ranking, across all 63 combinations: **0.809**.
The structural ordering broadly reproduced out of sample.

Where it disagreed is informative and expected: QQQ ranked 12th structurally
and **1st** live (2015-2026 was an exceptional decade for concentrated
technology), while gold-containing combinations moved up 20-28 places.  A
single decade re-ranks individual exposures; it did not overturn the top of the
list — QQQ+SPMO ranked 1st structurally and 2nd live, SPMO 5th and 3rd.

Live full-period results (`results/tables/live_period_validation.csv`):

| | CAGR | max DD | wealth per real unit contributed |
|---|---|---|---|
| QQQ | 19.13% | −32.6% | 2.49 |
| QQQ+SPMO | 19.05% | −26.9% | 2.60 |
| SPMO | 18.54% | −21.3% | 2.65 |
| QQQ+SCHD+SPMO | 17.25% | −23.1% | 2.29 |
| QQQ+SCHD+SPMO+GOLD | 16.25% | −19.7% | 2.21 |
| SPY | 14.50% | −23.9% | 1.93 |
| SCHD | 12.85% | −21.5% | 1.67 |

No weight, rule or exposure was chosen using this period.

### 1.11 Official-index cross-check, and an independent confirmation of §1.6

A third layer uses **only official index / published-benchmark data and no
proxies at all**: the S&P 500 Total Return index, the LBMA gold price and the
Treasury bill, 1988-02 → 2026-07 (462 months, 7 combinations).  It cannot
include QQQ, SCHD or SPMO, because no public total-return history of the
Nasdaq-100, the Dow Jones U.S. Dividend 100 or the S&P 500 Momentum index is
retrievable.

Rolling 20-year windows, `OFFICIAL_INDEX_EXTENDED` layer:

| | median CAGR | p10 CAGR | median max DD | TW per real unit |
|---|---|---|---|---|
| SPY+GOLD | 8.68% | **7.62%** | −25.5% | 2.04 |
| SPY | 8.59% | 6.42% | −51.0% | 1.92 |
| GOLD | 7.75% | 5.13% | −41.6% | 1.90 |
| SPY+GOLD+CASH | 6.89% | 6.01% | −17.0% | 1.60 |
| SPY+CASH | 6.11% | 4.49% | −26.4% | 1.40 |
| CASH | 2.11% | 1.30% | 0.0% | 0.93 |

The gold result of §1.8 reproduces on data that shares no series with the
structural layer: adding gold to equity lifts the 10th percentile (6.42% →
7.62%) and halves the drawdown, at a small cost in median return.

More importantly, this layer **independently confirms the mechanism claimed in
§1.6**.  Over 1988-2026 the S&P 500 and gold had unusually *similar* drifts
(8.59% vs 7.75% median 20-year CAGR), and exactly as the drift explanation
predicts, rebalancing SPY+GOLD is strongly positive here — R1 contribution-only
**+4.81%** improving **99.6%** of windows, a ±30% band **+5.98%** — whereas the
same pair over 1971-2026, where gold's drift was far below equity's, showed no
such gain.  SPY+CASH and GOLD+CASH, whose drifts remain far apart in this
period too, stay negative (−3.4% and −4.9%).

The sign of the rebalancing effect tracks the drift gap, not the sample.  That
is a mechanism, not a curve fit.

### 1.12 Timing, fee and tax sensitivities change nothing

* Contributing at month-end instead of month-start: 0.989× median terminal
  wealth, uniformly across every portfolio tested — a level effect, not a
  ranking effect.
* `FEE_ADJUSTED_SIMULATION` (fund fee plus a deliberately harsh 100 bp proxy
  drag on SPMO): 0.975×–0.992×.
* Worst-case investor-level capital-gains tax at 22% on every rebalancing
  disposal: 0.967×–1.000×.  Single-asset portfolios are unaffected because they
  never sell.

(`results/tables/sensitivity_analysis.csv`)

---

## 2. Inferences

Reasonable readings of §1, not measurements.

1. **Momentum, not the momentum ETF, is what the long record supports.**  The
   effect is large, present in every era and on an independent 1927-2026 sample,
   and it is the single most consistent source of excess return in the data.
   It is also the exposure whose measurement is most flattered by the proxy.
   The defensible position is that momentum earns something real but smaller
   than 13.6% versus 11.3% suggests, and that a portfolio should not depend on
   its full magnitude.
2. **Concentration is a growth engine that needs a partner.**  QQQ raises the
   median but its −81% drawdown and 17-year recovery are the kind of event that
   ends real investment programmes.  In combination, its tail is halved
   (QQQ alone −81.0% vs QQQ+SCHD+SPMO −47.4% median 20-year drawdown) while most
   of its growth survives.
3. **Gold is drawdown insurance priced in return.**  Roughly 1 point of annual
   return buys roughly 13 points of drawdown and the best 10th-percentile
   outcome in the study.  Whether that is worth buying is a preference about the
   left tail, not a question these data answer.
4. **The rebalancing literature's "premium" is conditional.**  It is real for
   assets of similar drift and negative for mixes containing a low-drift asset.
   Anyone quoting a universal rebalancing bonus is generalising from the
   favourable case.
5. **A large recurring contribution is itself a rebalancing mechanism.**  For an
   accumulating investor it does most of the work of a formal rule, with zero
   turnover, zero realised gains and no selling decision to get wrong.
6. **Simplicity is nearly free here.**  Within the plateau, moving between
   allocations changes median 20-year CAGR by less than the width of the
   sampling error.  There is no return to precision.

---

## 3. Limitations

Read these as constraints on §1 and §2, not as boilerplate.

**Index backtests and proxies.**  Four of the six long series are not the
instruments named:

| exposure | long series actually used | corr. with the ETF | vol ratio | overlap |
|---|---|---|---|---|
| SPY | CRSP value-weighted U.S. market | 0.987 | 1.03 | 401 months |
| QQQ | Hardw+Softw+Chips industry composite | 0.974 | 1.07 | 327 months |
| SCHD | top-30% dividend-yield portfolio | 0.940 | 1.03 | 176 months |
| SPMO | large-cap top-tercile momentum | 0.925 | 0.97 | 128 months |
| GOLD | LBMA Gold Price PM (a real benchmark) | 0.975 | 1.01 | 260 months |
| CASH | Fama-French 1-month bill return (real) | 0.992 | 0.96 | 1109 months |

The QQQ proxy is pure technology and omits the non-technology third of the
Nasdaq-100.  The SCHD proxy sorts on dividend yield only and lacks SCHD's
quality and dividend-persistence screens — it was 6 points deeper in the 2020
drawdown than the ETF.  The SPMO proxy reconstitutes monthly.  None of these
are ETF histories and none are described as such anywhere in this repository.

**Limited common history.**  All six exposures coexist as real instruments for
only 129 months.  The 55-year primary window exists only because of the
proxies.  The proxy-free `official_index` layer reaches back to 1988 but can
only carry three of the six exposures, so it corroborates the gold, cash and
rebalancing findings and says nothing about QQQ, SCHD or SPMO.

**Overlapping windows are not independent observations.**  658 months contain
**5** independent 10-year windows, **2** independent 20-year windows and
**1** independent 30-year window.  Every rolling table reports
`n_independent_windows` beside `n_windows` for this reason.  The 30-year
results in §1.2 are a single history, not a distribution — treat the
percentile columns there as descriptive, not inferential.  On the 2 independent
20-year windows the ordering does shift (QQQ falls to 9.03% and SPY to 9.94%,
while SCHD 12.25% and SPMO 13.10% hold up), and on the 35 annual-start windows
it matches the monthly-start result closely.

**Sensitivity to start date is large and real.**  Ten-year windows for QQQ range
from −8.35% to +35.6% annualised depending only on the starting month.
The 10th-percentile columns, not the medians, are the honest planning inputs.

**Fees and costs.**  Primary results are `INDEX_GROSS`.  Real funds charge fees
and real momentum strategies pay spreads; §1.7 quantifies how much of the
conclusion that could consume rather than assuming a number.  Today's expense
ratios were never applied to decades before the funds existed.

**Taxes.**  A single configurable investor-level rate applied to rebalancing
disposals, treating the entire disposal as gain (a deliberate worst case).  No
jurisdiction's tax law is encoded, and ETF-internal turnover is explicitly not
taxed.

**Gold and monetary regime.**  The dollar-gold price was institutionally fixed
or constrained before August 1971 and U.S. private bullion ownership was illegal
until 1975.  Data back to 1968-04 exist in `data/processed` and are never used
in the primary analysis.  Even post-1971, §1.8 shows the return result is
regime-dependent.

**CPI.**  October 2025 was never collected or published; it is geometrically
interpolated and disclosed in `data/data_manifest.csv`.  One month in 658.

**Survivorship.**  Historical total-return index and portfolio series are used
throughout rather than reconstructing holdings from today's constituent lists,
so current-membership survivorship bias is avoided.  Residual academic-database
biases in the CRSP-derived series remain.

**Not forecast.**  Nothing here predicts future returns.  Every statement is
about what happened between 1927 and 2026.

---

## 4. Final exposure classification

| Exposure | Classification | Why |
|---|---|---|
| **SPMO** | **CORE** | Highest median rolling CAGR at every horizon and on the independent 1927-2026 sample; in all four screening survivors. Discounted for proxy optimism (§1.7). |
| **QQQ** | **CORE** | Raises median and terminal wealth in every survivor; its tail is only tolerable in combination. |
| **SCHD** | **USEFUL DIVERSIFIER** | Lowered volatility and drawdown in all five eras and raised median 20-year CAGR by 0.71pp when added to QQQ+SPMO. The prior that it adds nothing was **rejected**. |
| **GOLD** | **USEFUL DIVERSIFIER** | Consistent drawdown and volatility reduction in every era, and the best 10th-percentile outcome in the study — bought with about 1pp/yr of median return. |
| **SPY** | **NO EVIDENCE OF ADDITIONAL VALUE** | Adding it to QQQ+SCHD+SPMO lowered CAGR in all five eras and changed drawdown by at most 1.0 point in any era. It is dominated by, not different from, the mix. |
| **CASH** | **NO EVIDENCE OF ADDITIONAL VALUE** *(as a permanent allocation for an accumulating investor)* | Consistent, one-directional cost; no CASH combination survived screening. Distinct from cash held for spending needs, which this study does not model. |

### The fourteen questions

**1. Is SPMO alone sufficient?**  Nearly, and it is the best single exposure at
every horizon (20-year median 12.46% vs SPY 10.81%).  It is not *sufficient*,
because a single-factor bet whose measured edge is worth ~146 bp of cost is a
concentrated wager on one anomaly continuing.  Blending is what makes it robust.

**2. Does adding QQQ materially improve long-run wealth or robustness?**  Wealth,
modestly and unevenly.  QQQ+SPMO beats SPMO alone on median 20-year CAGR
(12.54% vs 12.46%) but is *worse* on the 10th percentile (9.12% vs 9.36%) and
much worse on drawdown (−63.1% vs −42.7%).  Adding QQQ to SCHD+SPMO helped in
1995-2026 and hurt in 1971-1994.  **H3 is rejected**: the pair does not improve
robustness over the better single.

**3. Does Gold materially improve SPMO+QQQ?**  For robustness, yes.  It lifts the
10th-percentile 20-year CAGR from 9.12% to 9.57%, the worst window from 4.37% to
6.69%, and cuts median drawdown from −63.1% to −34.7%.  For wealth, no: median
terminal wealth falls from 3.09 to 2.47 units per unit contributed.

**4. Does SPY provide incremental value?**  No.  Negative in every era, on every
horizon, on both growth and robustness. **H5 supported.**

**5. Does SCHD provide incremental value?**  Yes — this was the prior that broke.
Adding SCHD to QQQ+SPMO raised the 20-year median from 12.54% to 12.77%, the
10th percentile from 9.12% to 9.56%, and cut median drawdown by 15.7 points.
**H6 rejected.**

**6. Is a permanent Cash allocation justified?**  Not for accumulation. **H7
supported** at both horizons.

**7. Which rebalancing rule performs most robustly?**  For all-equity mixes,
**annual rebalancing (R2)** has the highest median (+2.04% vs R0 over 20 years,
80% of windows improved), with a ±20% relative band close behind at
**40% less turnover**.  For mixes containing gold or cash, no rebalancing rule
improves terminal wealth; they buy drawdown reduction instead.  Given that a
band rule needs no calendar and trades less, **R3 with a ±20% relative band,
contributions first**, is the most defensible general rule.

**8. How much of full-rebalancing benefit is captured by contributions alone?**
For the candidate all-equity portfolios, **79%–94%** at 20 years and **more than
100%** at 10 years — with zero turnover, zero realised gains and no sell
decisions.  Under a ±20% band, contributions do **77%** of all weight correction.

**9. Is there credible evidence of a Shannon-style rebalancing premium?**
Conditionally, and the condition is the **drift gap**, not the asset class.  Yes
for assets of similar drift: +1.5% to +2.0% median terminal wealth over 20 years
for all-equity mixes (80%+ of windows), and **+4.8%** for SPY+GOLD on the
official-index layer where the two drifted within 0.8pp/yr of each other (99.6%
of windows).  No in general: across all 57 multi-asset combinations on the
primary sample the median effect is negative and the worst window is 0.44×.
A universal rebalancing premium is **not** supported; a drift-conditional one
is, and it reproduces out of sample.

**10. Are favourable allocations broad plateaus or narrow fitted optima?**
Broad plateaus.  The grid maximum's worst neighbour is 2.4% below it, and a
region spanning QQQ 20-50% / SCHD 10-40% / SPMO 30-70% is statistically
indistinguishable.  No apparent optimum was fragile.

**11. How sensitive are conclusions to historical starting dates?**  The
*ranking* of exposures is stable at every horizon and on an independent
1927-2026 sample.  The *magnitudes* are not: 10-year outcomes vary by more than
20 percentage points annualised depending on the start month, and gold's entire
return contribution is one decade.

**12. Which findings survive actual ETF live-period validation?**  The ranking
(Spearman 0.809), SPMO's strength, QQQ's tail, the value of blending, and gold's
volatility reduction.  What the live period does *not* validate is any specific
magnitude — 2015-2026 was extreme for technology.

**13. Which findings survive longer structural proxy tests?**  On 1927-2026 with
four exposures: SPMO > SCHD > SPY > CASH holds at both the 20- and 30-year
horizon, on medians, 10th percentiles and worst windows alike.  The
momentum-then-dividend ordering is the study's most durable result.

**14. What is the simplest portfolio that captures essentially all of the robust
benefit?**

> **Equal thirds of SPMO, QQQ and SCHD**, rebalanced with contributions first
> and a ±20% relative band.

It is on the plateau, it beat SPY in **100%** of rolling 20-year windows, it
carries the highest median terminal wealth per unit contributed (3.10), and it
tolerates roughly 268 bp of momentum implementation cost before losing to plain
QQQ.  Adding SPY to it makes it worse.  Adding cash makes it worse.

**Adding 10–20% gold** to it is the one defensible variation: it is the only
change tested that improves the 10th-percentile outcome, and it does so in every
era.  It costs about a point of median annual return.  That is a preference
about the left tail, and this study does not decide it for you.

---

*Generated by `run_research.py`.  Tables: `results/tables/`.  Charts:
`results/charts/`.  Corrections and failures: `results/run_log.md`.*
