# Six-exposure portfolio research

A reproducible study of what long-term portfolio structure and rebalancing rule
survive across many historical starting dates, using only six exposures:

```
SPY    S&P 500 / broad U.S. equity
QQQ    Nasdaq-100 / concentrated large-cap technology
SCHD   Dow Jones U.S. Dividend 100 / high-quality dividend equity
SPMO   S&P 500 Momentum / large-cap momentum
GOLD   physical gold
CASH   ~3-month U.S. Treasury bills
```

The investor is modelled as a saver with recurring cash flow, so a constant
**real** monthly contribution is the primary accumulation test, not a lump sum.

## Reproduce

```bash
pip install -r requirements.txt
python run_research.py          # rebuilds every table and chart from data/raw
```

`run_research.py --refresh` re-downloads all source data first (network
required).  Without `--refresh` the run is entirely offline and deterministic:
`data/raw` holds the exact source payloads the published results came from.

```bash
python -m pytest tests/ -q      # 70 data-integrity and portfolio-math tests
```

## What is where

| Path | Contents |
|---|---|
| `config.yaml` | every research parameter — samples, horizons, bands, costs, tax rates |
| `data/raw/` | untouched source payloads (Yahoo JSON, FRED CSV, LBMA JSON, French ZIPs) |
| `data/processed/` | monthly total-return panels, one CSV per dataset |
| `data/data_manifest.csv` | provenance of every series used (SC-2) |
| `src/fetch.py` | source clients |
| `src/build_dataset.py` | raw → monthly total returns, three separated datasets |
| `src/samples.py` | dataset + date range + exposure list → an analysis window |
| `src/portfolio.py` | the simulator (R0–R3), vectorised across rolling start dates |
| `src/metrics.py` | growth / risk / distribution statistics |
| `src/analysis.py` | combination screening, rolling stats, rebalancing, weight grid |
| `src/proxy_validation.py` | measures each structural proxy against its ETF |
| `src/charts.py` | the ten analytical charts |
| `results/REPORT.md` | findings, inferences, limitations |
| `results/run_log.md` | what failed, what was corrected, and why |

## The three datasets, kept strictly separate

| Dataset | Class | Window | What it is |
|---|---|---|---|
| `live` | `LIVE_ONLY` | 2015-11 → 2026-07 | actual ETF total returns (SPY, QQQ, SCHD, SPMO, GLD) plus a T-bill return |
| `index` | `OFFICIAL_INDEX_EXTENDED` | 1985-11 → 2026-07 | `^SP500TR`, `^NDX` (price return, diagnostics only) and ETF price-return twins |
| `structural` | `STRUCTURAL_PROXY_TEST` | 1926-07 → 2026-07 | long academic/benchmark series standing in for each exposure |

No public total-return history exists for the Dow Jones U.S. Dividend 100 or
the S&P 500 Momentum index, and none for the Nasdaq-100 either, so there is no
six-exposure official-index layer.  Nothing here presents a pre-launch series
as ETF performance.

## Samples used in the analysis

| Sample | Window | Exposures | Role |
|---|---|---|---|
| `structural` | 1971-09 → 2026-06 (658 months) | all six | **primary** |
| `structural_long` | 1927-07 → 2026-06 (1188 months) | SPY, SCHD, SPMO, CASH | century-long robustness check |
| `live` | 2015-11 → 2026-07 (129 months) | all six | out-of-sample validation, never training |

The primary sample starts the month after the dollar-gold peg broke; gold data
back to 1968 exist in `data/processed` but are never used in the primary
analysis.  `structural_long` drops GOLD for that reason and QQQ because its
proxy only begins in 1965.

## File-name deviations from the required output list

`results/tables/` contains everything the specification asks for under the
specified names.  Two additions are worth knowing about:

* `rolling_all_horizons.csv` — the five per-horizon files concatenated, for
  convenience; it is not a separate analysis.
* `recurring_contribution_results.csv` — the contribution-specific columns of
  the rolling tables, extracted so the accumulation results can be read alone.

## Conventions

Monthly event order (configurable, primary setting first):

1. observe the portfolio carried over from last month
2. deposit this month's contribution
3. apply the rebalancing rule permitted this month
4. this month's returns happen
5. record the month-end state

No step uses a return from inside its own month.  A
contribution-at-month-end sensitivity is reported in
`results/tables/sensitivity_analysis.csv`.

Primary results are **pre-tax** and **gross of fees** (`INDEX_GROSS`).  Fee and
tax effects are sensitivities, and today's expense ratios are never applied to
decades before the funds existed.
