"""Data-integrity tests (SC-18, data section; SC-3; SC-6).

These run against the cached processed panels, so they fail loudly if a
refetch ever changes history or corrupts alignment.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src import fetch
from src.build_dataset import load, _tbill_monthly_return
from src.samples import build_all_samples, load_config

DATASETS = ["structural", "live", "index"]
EQUITY_LIKE = {"SPY", "QQQ", "SCHD", "SPMO", "GOLD"}


@pytest.fixture(scope="module")
def panels():
    return {name: load(name) for name in DATASETS + ["cpi"]}


@pytest.fixture(scope="module")
def cfg():
    return load_config()


# --------------------------------------------------------------------------
# index integrity
# --------------------------------------------------------------------------
@pytest.mark.parametrize("name", DATASETS + ["cpi"])
def test_no_duplicate_dates(panels, name):
    idx = panels[name].index
    assert not idx.duplicated().any()


@pytest.mark.parametrize("name", DATASETS + ["cpi"])
def test_dates_sorted_and_monthly(panels, name):
    idx = panels[name].index
    assert isinstance(idx, pd.PeriodIndex) and idx.freqstr == "M"
    assert idx.is_monotonic_increasing


@pytest.mark.parametrize("name", DATASETS + ["cpi"])
def test_no_missing_months_inside_a_series(panels, name):
    """Each column must be contiguous between its own first and last month."""
    df = panels[name]
    for col in df.columns:
        s = df[col].dropna()
        span = pd.period_range(s.index[0], s.index[-1], freq="M")
        missing = sorted(set(span) - set(s.index))
        assert not missing, f"{name}.{col} missing {len(missing)} months, " \
                            f"first {missing[0]}"


def test_cpi_interpolation_is_disclosed_and_minimal(panels):
    """Only the never-published 2025-10 CPI may be interpolated, and the
    manifest has to say so."""
    manifest = pd.read_csv(fetch.RAW.parent / "data_manifest.csv")
    row = manifest[manifest.exposure == "CPI"].iloc[0]
    note = f"{row.transformations} {row.caveats}"
    assert "2025-10" in note and "interpolat" in note.lower()
    assert note.count("2025-") == note.count("2025-10")  # nothing else filled


# --------------------------------------------------------------------------
# value plausibility
# --------------------------------------------------------------------------
@pytest.mark.parametrize("name", DATASETS)
def test_returns_are_possible(panels, name):
    df = panels[name]
    vals = df.to_numpy(dtype=float)
    finite = vals[np.isfinite(vals)]
    assert (finite > -1.0).all(), "a monthly return below -100% is impossible"
    assert (finite < 1.0).all(), "a >100% monthly return needs investigation"


def test_cash_is_never_negative_by_much(panels):
    """T-bill returns may print a hair below zero; equity-like values mean a
    construction error."""
    for name in ("structural", "live"):
        cash = panels[name]["CASH"].dropna()
        assert cash.min() > -0.01
        assert cash.max() < 0.02, "a >2%/month T-bill return is not a T-bill"


def test_cash_is_not_zero_return(panels):
    """SC-6: cash must earn an actual short-term Treasury return."""
    for name in ("structural", "live"):
        cash = panels[name]["CASH"].dropna()
        annual = (1 + cash.mean()) ** 12 - 1
        assert 0.015 < annual < 0.07, f"{name} cash annualises to {annual:.2%}"


def test_cash_is_not_equity_like(panels):
    """SC-19: cash volatility must be an order of magnitude below equity."""
    for name in ("structural", "live"):
        df = panels[name]
        assert df["CASH"].std() < 0.1 * df["SPY"].dropna().std()


def test_no_long_runs_of_identical_returns(panels):
    """Catches accidental forward filling of a stale price."""
    for name in DATASETS:
        df = panels[name]
        for col in df.columns:
            if not any(col.startswith(e) for e in EQUITY_LIKE):
                continue
            s = df[col].dropna()
            runs = (s != s.shift()).cumsum()
            longest = s.groupby(runs).size().max()
            assert longest <= 2, f"{name}.{col} repeats a value {longest} times"


# --------------------------------------------------------------------------
# SC-3: dividends are actually in the equity series
# --------------------------------------------------------------------------
@pytest.mark.parametrize("etf,lo,hi", [("SPY", 0.010, 0.030),
                                       ("QQQ", 0.000, 0.015),
                                       ("SCHD", 0.020, 0.045),
                                       ("SPMO", 0.002, 0.020)])
def test_total_return_exceeds_price_return_by_a_dividend_yield(panels, etf, lo, hi):
    live = panels["live"][etf].dropna()
    price = panels["index"][f"{etf}_PRICE_ONLY"].dropna()
    joined = pd.concat([live, price], axis=1).dropna()
    tr = (1 + joined.iloc[:, 0]).prod() ** (12 / len(joined)) - 1
    pr = (1 + joined.iloc[:, 1]).prod() ** (12 / len(joined)) - 1
    assert lo < tr - pr < hi, f"{etf} TR-PR = {tr - pr:.4f}"


def test_gold_etf_total_return_equals_its_price_return(panels):
    """GLD makes no distributions, so its adjusted and unadjusted closes must
    give the same return.  Any gap would mean a phantom dividend."""
    a = panels["live"]["GOLD"].dropna()
    b = panels["index"]["GOLD_PRICE_ONLY"].dropna()
    joined = pd.concat([a, b], axis=1).dropna()
    assert len(joined) > 100
    assert (joined.iloc[:, 0] - joined.iloc[:, 1]).abs().max() < 1e-6


def test_gold_etf_tracks_the_lbma_benchmark(panels):
    """GLD should follow the LBMA price closely and lag it slightly (fees).

    They are measured at different moments of the day -- the London PM auction
    versus the New York close -- so individual months differ; the long-run
    growth rates should not.
    """
    etf = panels["live"]["GOLD"].dropna()
    bench = panels["structural"]["GOLD"].dropna()
    joined = pd.concat([etf, bench], axis=1).dropna()
    assert joined.iloc[:, 0].corr(joined.iloc[:, 1]) > 0.93
    n = len(joined)
    g_etf = (1 + joined.iloc[:, 0]).prod() ** (12 / n) - 1
    g_bench = (1 + joined.iloc[:, 1]).prod() ** (12 / n) - 1
    assert -0.001 < g_bench - g_etf < 0.010, (
        f"LBMA {g_bench:.4f} vs GLD {g_etf:.4f}")


def test_equity_total_and_price_series_are_not_identical(panels):
    """SC-19: identical TR and PR over decades means a mix-up."""
    for etf in ("SPY", "QQQ", "SCHD"):
        tr = panels["live"][etf].dropna()
        pr = panels["index"][f"{etf}_PRICE_ONLY"].dropna()
        joined = pd.concat([tr, pr], axis=1).dropna()
        assert (joined.iloc[:, 0] - joined.iloc[:, 1]).abs().mean() > 1e-5


def test_structural_equity_series_are_total_returns(panels):
    """Every structural equity proxy must beat cash over a century; a
    price-return series of dividend payers would not."""
    df = panels["structural"]
    cash = (1 + df["CASH"].dropna()).prod() ** (12 / df["CASH"].dropna().size) - 1
    for col in ("SPY", "SCHD", "SPMO"):
        s = df[col].dropna()
        c = (1 + s).prod() ** (12 / len(s)) - 1
        assert c > cash + 0.02, f"{col} annualises {c:.2%} vs cash {cash:.2%}"


# --------------------------------------------------------------------------
# SC-6: the cash construction is right
# --------------------------------------------------------------------------
def test_tbill_conversion_matches_the_academic_bill_return(panels):
    """The TB3MS-derived monthly return must track Fama/French's realised
    1-month bill return.  A naive rate/12 or an un-annualised quote would not."""
    built = panels["live"]["CASH"].dropna()
    academic = panels["structural"]["CASH"].dropna()
    joined = pd.concat([built, academic], axis=1).dropna()
    diff = (joined.iloc[:, 0] - joined.iloc[:, 1]).abs()
    assert diff.mean() < 0.0006, f"mean abs monthly gap {diff.mean():.5f}"
    assert joined.iloc[:, 0].corr(joined.iloc[:, 1]) > 0.97


def test_quoted_yield_is_not_used_directly_as_a_monthly_return():
    """A 5% annual quote must not turn into a 5% month."""
    quote = pd.Series([5.0, 5.0, 5.0], index=pd.period_range("2000-01", periods=3,
                                                             freq="M"))
    monthly = _tbill_monthly_return(quote)
    assert 0.003 < monthly.iloc[0] < 0.005


# --------------------------------------------------------------------------
# sample alignment
# --------------------------------------------------------------------------
def test_samples_align_and_are_contiguous(cfg):
    samples = build_all_samples(cfg)
    for name, s in samples.items():
        assert s.returns.notna().all().all()
        assert s.cpi.notna().all(), f"{name} has no CPI cover"
        assert s.cpi_lagged.notna().all()
        span = pd.period_range(s.returns.index[0], s.returns.index[-1], freq="M")
        assert len(span) == s.n_months


def test_primary_sample_starts_after_the_gold_peg_broke(cfg):
    samples = build_all_samples(cfg)
    primary = [s for s in samples.values() if s.primary]
    assert len(primary) == 1
    free_float = pd.Period(cfg["gold"]["free_float_start"], freq="M")
    assert primary[0].returns.index[0] >= free_float


def test_primary_sample_contains_the_dot_com_collapse(cfg):
    """SC-19: the QQQ exposure's history must include 2000-2002."""
    s = build_all_samples(cfg)["structural"]
    window = s.returns.loc[pd.Period("2000-03"):pd.Period("2002-10"), "QQQ"]
    wealth = (1 + window).cumprod()
    assert (wealth / wealth.cummax() - 1).min() < -0.60


def test_manifest_covers_every_series_used(cfg):
    manifest = pd.read_csv(fetch.RAW.parent / "data_manifest.csv")
    samples = build_all_samples(cfg)
    for s in samples.values():
        dataset = cfg["samples"][s.name]["dataset"]
        for exposure in s.exposures:
            hit = manifest[(manifest.exposure == exposure)
                           & (manifest.dataset == dataset)]
            assert len(hit) == 1, f"no manifest row for {dataset}.{exposure}"
            row = hit.iloc[0]
            assert isinstance(row.source_url, str) and row.source_url.startswith("http")
            assert row.return_type in {"TOTAL_RETURN", "PRICE_RETURN", "YIELD_DERIVED"}
            assert row.data_class in {"LIVE_ETF", "OFFICIAL_INDEX",
                                      "STRUCTURAL_PROXY", "BENCHMARK_PRICE"}


# --------------------------------------------------------------------------
# cost drag behaves like a cost
# --------------------------------------------------------------------------
def test_drag_reduces_returns_by_the_stated_amount(cfg):
    """A 100 bp annual drag must multiply the annual growth factor by 0.99."""
    import numpy as np
    from src.analysis import Engine
    from src.metrics import cagr
    from src.samples import build_sample

    eng = Engine(build_sample("structural", cfg), cfg)
    H = eng.sample.n_months
    base = eng.run(("SPMO",), np.array([1.0]), "R2", H, with_contributions=False)
    drag = eng.run(("SPMO",), np.array([1.0]), "R2", H, with_contributions=False,
                   drag_bps={"SPMO": 100.0})
    ratio = (1 + cagr(drag.total)[0]) / (1 + cagr(base.total)[0])
    assert ratio == pytest.approx(0.99, abs=1e-6)


# --------------------------------------------------------------------------
# no price-return series may ever reach a simulation
# --------------------------------------------------------------------------
def test_no_sample_uses_a_price_return_equity_series(cfg):
    """Requirement 1: never mix price and total-return series.

    Every column an analysis sample exposes must be classified TOTAL_RETURN in
    the manifest -- except gold, which has no income so its price return *is*
    its total return, and cash, which is derived from a Treasury yield.
    """
    manifest = pd.read_csv(fetch.RAW.parent / "data_manifest.csv")
    allowed = {"GOLD": {"PRICE_RETURN", "TOTAL_RETURN"},
               "CASH": {"YIELD_DERIVED", "TOTAL_RETURN"}}
    for name, s in build_all_samples(cfg).items():
        dataset = cfg["samples"][name]["dataset"]
        for exposure in s.exposures:
            assert not exposure.endswith("_PRICE_ONLY")
            row = manifest[(manifest.exposure == exposure)
                           & (manifest.dataset == dataset)].iloc[0]
            assert row.return_type in allowed.get(exposure, {"TOTAL_RETURN"}), (
                f"{name}: {exposure} is {row.return_type}")


def test_price_only_columns_are_rejected_by_the_sample_builder(cfg):
    from src.samples import build_sample
    broken = {**cfg, "exposures": ["SPY_PRICE_ONLY"],
              "samples": {"x": {"dataset": "index", "start": "2000-01"}}}
    with pytest.raises(ValueError, match="price returns"):
        build_sample("x", broken)


def test_official_index_layer_holds_no_proxy_series(cfg):
    """The OFFICIAL_INDEX_EXTENDED layer must contain nothing proxied."""
    manifest = pd.read_csv(fetch.RAW.parent / "data_manifest.csv")
    s = build_all_samples(cfg)["official_index"]
    for exposure in s.exposures:
        row = manifest[(manifest.exposure == exposure)
                       & (manifest.dataset == "index")].iloc[0]
        assert row.data_class == "OFFICIAL_INDEX", f"{exposure}: {row.data_class}"


# --------------------------------------------------------------------------
# the exact-index layer
# --------------------------------------------------------------------------
def test_nasdaq_total_return_index_is_total_return(panels):
    """XNDX must beat the Nasdaq-100 price index by a dividend yield."""
    tr = panels["index"]["QQQ"].dropna()
    pr = panels["index"]["QQQ_PRICE_ONLY"].dropna()
    j = pd.concat([tr, pr], axis=1).dropna()
    n = len(j)
    gap = ((1 + j.iloc[:, 0]).prod() ** (12 / n)
           - (1 + j.iloc[:, 1]).prod() ** (12 / n))
    assert 0.0 < gap < 0.02, f"XNDX minus NDX price return = {gap:.4f}/yr"


def test_nasdaq_index_contains_the_dot_com_collapse(panels):
    w = (1 + panels["index"]["QQQ"].dropna().loc["2000-01":"2002-12"]).cumprod()
    assert (w / w.cummax() - 1).min() < -0.70


def test_exact_index_layer_matches_the_live_etfs_over_the_overlap(panels):
    """The official indices must track their ETFs, the ETF lagging by fees."""
    for exposure in ("SPY", "QQQ"):
        idx = panels["index"][exposure].dropna()
        etf = panels["live"][exposure].dropna()
        j = pd.concat([idx, etf], axis=1).dropna()
        assert j.iloc[:, 0].corr(j.iloc[:, 1]) > 0.995
        n = len(j)
        g_idx = (1 + j.iloc[:, 0]).prod() ** (12 / n) - 1
        g_etf = (1 + j.iloc[:, 1]).prod() ** (12 / n) - 1
        assert 0.0 < g_idx - g_etf < 0.006, (
            f"{exposure}: index {g_idx:.4f} vs ETF {g_etf:.4f}")
