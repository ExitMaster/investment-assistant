"""Turn raw source files into monthly total-return panels.

Three datasets are produced and kept strictly separate (SC-4):

``live``        LIVE_ONLY.  Actual exchange-traded instruments only.
``index``       OFFICIAL_INDEX_EXTENDED.  Official index series (used for
                validation of the live layer; no complete six-exposure panel
                exists because no official SCHD/SPMO index history is publicly
                retrievable).
``structural``  STRUCTURAL_PROXY_TEST.  Long academic/benchmark series that
                stand in for the economic exposure an ETF provides.  These are
                *not* ETF histories and are never described as such.

All returns are simple monthly decimal returns indexed by a pandas PeriodIndex
with freq='M'.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np
import pandas as pd

from . import fetch

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
PROCESSED.mkdir(parents=True, exist_ok=True)

EXPOSURES = ["SPY", "QQQ", "SCHD", "SPMO", "GOLD", "CASH"]

FRENCH_URL = fetch.FRENCH_BASE
FRED_URL = "https://fred.stlouisfed.org/series/{}"
YAHOO_URL = "https://query2.finance.yahoo.com/v8/finance/chart/{}"


@dataclass
class SeriesSpec:
    exposure: str
    dataset: str
    source: str
    source_url: str
    series_name: str
    return_type: str        # TOTAL_RETURN | PRICE_RETURN | YIELD_DERIVED
    data_class: str         # LIVE_ETF | OFFICIAL_INDEX | STRUCTURAL_PROXY | BENCHMARK_PRICE
    transformations: str
    caveats: str


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _month_end_last(s: pd.Series) -> pd.Series:
    """Collapse a daily series to the last observation of each month."""
    out = s.copy()
    out.index = pd.PeriodIndex(out.index, freq="M")
    return out.groupby(level=0).last()


def _pct_change(levels: pd.Series) -> pd.Series:
    return levels.pct_change().dropna()


def _fill_cpi_gaps(cpi: pd.Series) -> tuple[pd.Series, list[pd.Period]]:
    """Log-interpolate months the CPI simply does not exist for.

    The October 2025 CPI was never collected or published because of the
    federal government shutdown, so there is nothing to fetch.  A one-month
    geometric interpolation is the only honest option; the affected months are
    returned so they can be disclosed.
    """
    span = pd.period_range(cpi.index[0], cpi.index[-1], freq="M")
    missing = [p for p in span if p not in cpi.index]
    if not missing:
        return cpi, []
    full = cpi.reindex(span)
    filled = np.exp(np.log(full).interpolate(method="linear"))
    filled.name = cpi.name
    return filled, missing


def _tbill_monthly_return(discount_pct: pd.Series, days: int = 91) -> pd.Series:
    """Convert a quoted T-bill *discount* rate into a monthly holding return.

    ``discount_pct`` is the annualised bank-discount quote in percent (FRED
    TB3MS).  A bill maturing in ``days`` days is priced at

        P = 1 - d * days/360                       (bank discount convention)

    so the simple yield earned over those ``days`` is ``1/P - 1``.  Spreading
    that geometrically over the ``days/30.4375`` months it covers gives the
    monthly return of a portfolio that continuously rolls the bill.

    The rate of month ``t-1`` is used to produce the return of month ``t`` so
    that no month uses a rate observed inside or after itself (SC-5).
    """
    d = discount_pct.astype(float) / 100.0
    price = 1.0 - d * (days / 360.0)
    yield_period = 1.0 / price - 1.0
    months = days / 30.4375
    monthly = (1.0 + yield_period) ** (1.0 / months) - 1.0
    return monthly.shift(1).dropna()


# --------------------------------------------------------------------------
# builders
# --------------------------------------------------------------------------
def build_all(refresh: bool = False) -> dict[str, pd.DataFrame]:
    y = fetch.Yahoo()
    specs: list[SeriesSpec] = []
    panels: dict[str, dict[str, pd.Series]] = {"live": {}, "index": {}, "structural": {}}

    # ---------------- live ETFs -------------------------------------------
    live_etfs = {
        "SPY": ("SPY", "SPDR S&P 500 ETF Trust"),
        "QQQ": ("QQQ", "Invesco QQQ Trust"),
        "SCHD": ("SCHD", "Schwab U.S. Dividend Equity ETF"),
        "SPMO": ("SPMO", "Invesco S&P 500 Momentum ETF"),
        "GOLD": ("GLD", "SPDR Gold Shares"),
    }
    for exposure, (ticker, longname) in live_etfs.items():
        px = y.daily(ticker, refresh=refresh)
        tr = _pct_change(_month_end_last(px["adjclose"]))
        panels["live"][exposure] = tr
        specs.append(SeriesSpec(
            exposure, "live", "Yahoo Finance chart API", YAHOO_URL.format(ticker),
            f"{ticker} ({longname}) adjusted close",
            "TOTAL_RETURN", "LIVE_ETF",
            "daily adjusted close -> last obs. of each month -> pct change",
            "Adjusted close reinvests distributions on the ex-date at the "
            "closing price; it is net of the fund expense ratio.",
        ))
        # price-return twin, kept for the dividend-inclusion audit (SC-3)
        pr = _pct_change(_month_end_last(px["close"]))
        panels["index"][f"{exposure}_PRICE_ONLY"] = pr

    # ---------------- cash -------------------------------------------------
    tb3ms = fetch.fred("TB3MS", refresh=refresh)
    cash_live = _tbill_monthly_return(tb3ms)
    cash_live.index = pd.PeriodIndex(cash_live.index, freq="M")
    panels["live"]["CASH"] = cash_live
    specs.append(SeriesSpec(
        "CASH", "live", "FRED (Board of Governors / U.S. Treasury)",
        FRED_URL.format("TB3MS"),
        "TB3MS - 3-Month Treasury Bill Secondary Market Rate, Discount Basis",
        "YIELD_DERIVED", "BENCHMARK_PRICE",
        "bank-discount quote -> 91-day bill price -> geometric monthly holding "
        "return; lagged one month so no month uses its own rate",
        "A rolling-bill approximation, not a traded fund.  Validated against "
        "the Fama/French 1-month T-bill return series.",
    ))

    rf = fetch.french_series("F-F_Research_Data_Factors_CSV.zip", "RF", None,
                             refresh=refresh)
    panels["structural"]["CASH"] = rf
    specs.append(SeriesSpec(
        "CASH", "structural", "Kenneth R. French data library (Dartmouth)",
        f"{FRENCH_URL}/F-F_Research_Data_Factors_CSV.zip",
        "RF - one-month Treasury bill return",
        "TOTAL_RETURN", "BENCHMARK_PRICE",
        "percent -> decimal; already a realised monthly holding return",
        "Ibbotson 1-month bill through 2024-05, Treasury thereafter.",
    ))

    # ---------------- gold -------------------------------------------------
    gold_px = fetch.lbma_gold_pm(refresh=refresh)
    gold_tr = _pct_change(_month_end_last(gold_px))
    panels["structural"]["GOLD"] = gold_tr
    specs.append(SeriesSpec(
        "GOLD", "structural", "London Bullion Market Association",
        fetch.LBMA_GOLD_PM, "LBMA Gold Price PM, USD/troy oz",
        "PRICE_RETURN", "BENCHMARK_PRICE",
        "daily PM auction price -> last obs. of each month -> pct change",
        "Gold pays no income, so price return IS total return before storage "
        "cost.  Observations before 1971-09 fall under the fixed/managed "
        "dollar-gold regime and are excluded from the primary analysis.",
    ))

    # ---------------- structural equity proxies ----------------------------
    mkt = fetch.french_series("F-F_Research_Data_Factors_CSV.zip", "Mkt-RF", None,
                              refresh=refresh)
    panels["structural"]["SPY"] = (mkt + rf).dropna()
    specs.append(SeriesSpec(
        "SPY", "structural", "Kenneth R. French data library (Dartmouth)",
        f"{FRENCH_URL}/F-F_Research_Data_Factors_CSV.zip",
        "Mkt-RF + RF - value-weighted return of all CRSP U.S. common stocks",
        "TOTAL_RETURN", "STRUCTURAL_PROXY",
        "percent -> decimal; excess market return plus the risk-free rate",
        "Broad U.S. equity, not the S&P 500 itself.  Gross of fees and trading "
        "costs.  Correlation with the S&P 500 total return is ~0.99.",
    ))

    ind = fetch.french_monthly_table(
        fetch.french_zip("49_Industry_Portfolios_CSV.zip", refresh=refresh),
        r"Value Weighted Returns\s*--\s*Monthly")
    tech = (ind[["Hardw", "Softw", "Chips"]].dropna().mean(axis=1) / 100.0)
    panels["structural"]["QQQ"] = tech
    specs.append(SeriesSpec(
        "QQQ", "structural", "Kenneth R. French data library (Dartmouth)",
        f"{FRENCH_URL}/49_Industry_Portfolios_CSV.zip",
        "Equal-weighted blend of the value-weighted Hardw (computer hardware), "
        "Softw (software) and Chips (electronic equipment) industry portfolios",
        "TOTAL_RETURN", "STRUCTURAL_PROXY",
        "percent -> decimal; simple average of the three industry returns each "
        "month; starts 1965-07, the first month all three industries exist",
        "Chosen over broad large-growth portfolios because those understate "
        "Nasdaq-100 volatility by ~33% and its dot-com drawdown by ~30pp.  "
        "This composite matches QQQ closely (corr 0.97, vol ratio 1.06, "
        "2000-02 drawdown -81.0% vs QQQ's -81.1%) but is pure technology and "
        "omits the non-tech third of the Nasdaq-100.",
    ))

    panels["structural"]["SCHD"] = fetch.french_series(
        "Portfolios_Formed_on_D-P_CSV.zip", "Hi 30",
        r"Value Weight Returns\s*--\s*Monthly", refresh=refresh)
    specs.append(SeriesSpec(
        "SCHD", "structural", "Kenneth R. French data library (Dartmouth)",
        f"{FRENCH_URL}/Portfolios_Formed_on_D-P_CSV.zip",
        "Hi 30 - highest dividend-yield 30% of U.S. stocks, value weighted",
        "TOTAL_RETURN", "STRUCTURAL_PROXY",
        "percent -> decimal",
        "Dividend-yield sort only.  SCHD additionally screens for cash-flow / "
        "debt / ROE quality and dividend persistence, which this proxy lacks.",
    ))

    panels["structural"]["SPMO"] = fetch.french_series(
        "6_Portfolios_ME_Prior_12_2_CSV.zip", "BIG HiPRIOR", refresh=refresh)
    specs.append(SeriesSpec(
        "SPMO", "structural", "Kenneth R. French data library (Dartmouth)",
        f"{FRENCH_URL}/6_Portfolios_ME_Prior_12_2_CSV.zip",
        "BIG HiPRIOR - large caps in the top prior-(12,2)-return tercile, "
        "value weighted, rebalanced monthly",
        "TOTAL_RETURN", "STRUCTURAL_PROXY",
        "percent -> decimal",
        "Academic long-only large-cap momentum.  Monthly reconstitution makes "
        "it more aggressive and higher-turnover than SPMO, which rebalances "
        "semi-annually inside the S&P 500.  Gross of all costs.",
    ))

    # ---------------- official index layer ---------------------------------
    sp500tr = y.daily("^SP500TR", refresh=refresh)
    panels["index"]["SPY"] = _pct_change(_month_end_last(sp500tr["adjclose"]))
    specs.append(SeriesSpec(
        "SPY", "index", "Yahoo Finance chart API (S&P Dow Jones Indices data)",
        YAHOO_URL.format("^SP500TR"), "^SP500TR - S&P 500 Total Return Index",
        "TOTAL_RETURN", "OFFICIAL_INDEX",
        "daily close -> last obs. of each month -> pct change",
        "Gross index: no fund fee, no tracking error.",
    ))

    ndx = y.daily("^NDX", refresh=refresh)
    panels["index"]["QQQ_PRICE_ONLY"] = _pct_change(_month_end_last(ndx["close"]))

    xndx = fetch.nasdaq_index_history("XNDX", refresh=refresh)
    panels["index"]["QQQ"] = _pct_change(_month_end_last(xndx))
    specs.append(SeriesSpec(
        "QQQ", "index", "Nasdaq Global Index Data Service",
        f"{fetch.NASDAQ_INDEX_BASE}/Index/History/XNDX",
        "XNDX - Nasdaq-100 Total Return Index",
        "TOTAL_RETURN", "OFFICIAL_INDEX",
        "official daily index close -> last obs. of each month -> pct change",
        "Nasdaq's own published history for this index begins 1999-03-04, so "
        "the exact-index layer starts 1999-04.  Gross index: no fund fee and "
        "no tracking error.",
    ))

    # The official-index layer needs a gold and a cash leg to be analysable as
    # a panel.  Neither is an "index", but both are the authoritative published
    # benchmark for their exposure, so the layer stays free of proxy series.
    panels["index"]["GOLD"] = gold_tr
    specs.append(SeriesSpec(
        "GOLD", "index", "London Bullion Market Association",
        fetch.LBMA_GOLD_PM, "LBMA Gold Price PM, USD/troy oz",
        "PRICE_RETURN", "OFFICIAL_INDEX",
        "daily PM auction price -> last obs. of each month -> pct change",
        "The published benchmark price rather than an index.  Gold pays no "
        "income, so price return is total return before storage cost.",
    ))
    panels["index"]["CASH"] = cash_live
    specs.append(SeriesSpec(
        "CASH", "index", "FRED (Board of Governors / U.S. Treasury)",
        FRED_URL.format("TB3MS"),
        "TB3MS - 3-Month Treasury Bill Secondary Market Rate, Discount Basis",
        "YIELD_DERIVED", "OFFICIAL_INDEX",
        "bank-discount quote -> 91-day bill price -> geometric monthly holding "
        "return; lagged one month so no month uses its own rate",
        "Official Treasury rate data; the holding-return conversion is ours "
        "and is validated against the Fama/French bill return.",
    ))

    # ---------------- inflation -------------------------------------------
    cpi = fetch.fred("CPIAUCNS", refresh=refresh)
    cpi.index = pd.PeriodIndex(cpi.index, freq="M")
    cpi, filled = _fill_cpi_gaps(cpi)
    specs.append(SeriesSpec(
        "CPI", "all", "FRED (U.S. Bureau of Labor Statistics)",
        FRED_URL.format("CPIAUCNS"),
        "CPIAUCNS - Consumer Price Index for All Urban Consumers, NSA",
        "INDEX_LEVEL", "BENCHMARK_PRICE",
        "monthly index level, not seasonally adjusted; "
        + (f"log-interpolated for {', '.join(str(p) for p in filled)}"
           if filled else "no interpolation needed"),
        "Contributions are scaled by CPI(t-1) so no month uses a figure that "
        "was not yet published; terminal wealth is deflated by CPI(t).  "
        + (f"BLS never published {', '.join(str(p) for p in filled)}; the "
           "level is geometrically interpolated from the neighbouring months."
           if filled else ""),
    ))

    # ---------------- assemble --------------------------------------------
    # The month in progress has no month-end observation yet, so a return
    # computed for it would be a partial-month return.  Drop it everywhere.
    last_complete = pd.Period(dt.date.today(), freq="M") - 1

    frames: dict[str, pd.DataFrame] = {}
    for name, cols in panels.items():
        df = pd.DataFrame(cols).sort_index()
        df = df.loc[df.index <= last_complete]
        df = df.dropna(how="all")
        df.index.name = "month"
        frames[name] = df
    cpi = cpi.loc[cpi.index <= last_complete]
    frames["cpi"] = cpi.to_frame("CPIAUCNS")
    frames["cpi"].index.name = "month"

    _write(frames, specs)
    return frames


def _write(frames: dict[str, pd.DataFrame], specs: list[SeriesSpec]) -> None:
    today = dt.date.today().isoformat()
    for name, df in frames.items():
        df.to_csv(PROCESSED / f"{name}_monthly.csv")

    rows = []
    for sp in specs:
        key = "cpi" if sp.exposure == "CPI" else sp.dataset
        df = frames[key]
        col = "CPIAUCNS" if sp.exposure == "CPI" else sp.exposure
        if col not in df.columns and sp.exposure != "CPI":
            col = f"{sp.exposure}_PRICE_ONLY"
        s = df[col].dropna()
        rows.append({
            "exposure": sp.exposure,
            "dataset": sp.dataset,
            "source": sp.source,
            "source_url": sp.source_url,
            "series_name": sp.series_name,
            "return_type": sp.return_type,
            "data_class": sp.data_class,
            "first_observation": str(s.index[0]),
            "last_observation": str(s.index[-1]),
            "n_observations": int(len(s)),
            "frequency": "monthly",
            "transformations": sp.transformations,
            "retrieval_date": today,
            "caveats": sp.caveats,
        })
    manifest = pd.DataFrame(rows)
    manifest.to_csv(ROOT / "data" / "data_manifest.csv", index=False)


def load(name: str) -> pd.DataFrame:
    path = PROCESSED / f"{name}_monthly.csv"
    df = pd.read_csv(path, index_col=0)
    df.index = pd.PeriodIndex(df.index, freq="M")
    df.index.name = "month"
    return df


if __name__ == "__main__":  # pragma: no cover
    out = build_all()
    for k, v in out.items():
        print(k, v.shape, v.index[0], "->", v.index[-1])
