"""Measure each structural proxy against the instrument it stands in for.

This is what makes the STRUCTURAL_PROXY_TEST label meaningful: the report can
say exactly how close (and in which direction wrong) each long series is.
The candidate lists below are the ones that were compared when the proxies
were chosen, so re-running this reproduces the choice.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import fetch
from .build_dataset import load

VW = r"Value Weight(ed)? Returns\s*--\s*Monthly"

CANDIDATES: dict[str, list[tuple[str, str, str]]] = {
    "SPY": [("F-F_Research_Data_Factors_CSV.zip", "Mkt-RF+RF",
             "CRSP value-weighted U.S. market (ADOPTED)")],
    "QQQ": [("49_Industry_Portfolios_CSV.zip", "Hardw+Softw+Chips",
             "technology-industry composite (ADOPTED)"),
            ("6_Portfolios_2x3_CSV.zip", "BIG LoBM", "large-cap growth"),
            ("Portfolios_Formed_on_BE-ME_CSV.zip", "Lo 10",
             "lowest book-to-market decile"),
            ("25_Portfolios_5x5_CSV.zip", "BIG LoBM",
             "largest size / lowest BM 5x5 cell")],
    "SCHD": [("Portfolios_Formed_on_D-P_CSV.zip", "Hi 30",
              "top-30% dividend yield (ADOPTED)"),
             ("Portfolios_Formed_on_D-P_CSV.zip", "Hi 20", "top-20% dividend yield"),
             ("Portfolios_Formed_on_D-P_CSV.zip", "Hi 10", "top-10% dividend yield"),
             ("6_Portfolios_2x3_CSV.zip", "BIG HiBM", "large-cap value")],
    "SPMO": [("6_Portfolios_ME_Prior_12_2_CSV.zip", "BIG HiPRIOR",
              "large-cap top-tercile momentum (ADOPTED)"),
             ("10_Portfolios_Prior_12_2_CSV.zip", "Hi PRIOR",
              "top-decile momentum, all sizes"),
             ("25_Portfolios_ME_Prior_12_2_CSV.zip", "BIG HiPRIOR",
              "large-cap top-quintile momentum")],
}


def _series(zip_name: str, column: str) -> pd.Series:
    if column == "Mkt-RF+RF":
        rf = fetch.french_series("F-F_Research_Data_Factors_CSV.zip", "RF", None)
        mk = fetch.french_series("F-F_Research_Data_Factors_CSV.zip", "Mkt-RF", None)
        return (mk + rf).dropna()
    if "+" in column:
        tbl = fetch.french_monthly_table(fetch.french_zip(zip_name), VW)
        cols = column.split("+")
        return (tbl[cols].dropna().mean(axis=1) / 100.0)
    return fetch.french_series(zip_name, column, VW)


def _compare(etf: pd.Series, proxy: pd.Series) -> dict:
    j = pd.concat([etf, proxy], axis=1).dropna()
    x, y = j.iloc[:, 0], j.iloc[:, 1]
    n = len(j)
    wx, wy = (1 + x).cumprod(), (1 + y).cumprod()
    return {
        "overlap_months": n,
        "overlap_start": str(j.index[0]),
        "overlap_end": str(j.index[-1]),
        "correlation": float(x.corr(y)),
        "vol_ratio_proxy_over_etf": float(y.std() / x.std()),
        "cagr_etf": float((1 + x).prod() ** (12 / n) - 1),
        "cagr_proxy": float((1 + y).prod() ** (12 / n) - 1),
        "cagr_gap_proxy_minus_etf": float((1 + y).prod() ** (12 / n)
                                          - (1 + x).prod() ** (12 / n)),
        "maxdd_etf": float((wx / wx.cummax() - 1).min()),
        "maxdd_proxy": float((wy / wy.cummax() - 1).min()),
        "tracking_error_annual": float((y - x).std() * np.sqrt(12)),
    }


def proxy_validation_table() -> pd.DataFrame:
    live = load("live")
    rows = []
    for exposure, cands in CANDIDATES.items():
        etf = live[exposure].dropna()
        for zip_name, column, desc in cands:
            try:
                proxy = _series(zip_name, column)
            except Exception as exc:                      # pragma: no cover
                rows.append({"exposure": exposure, "candidate": column,
                             "description": desc, "error": str(exc)})
                continue
            row = {"exposure": exposure, "source_file": zip_name,
                   "candidate": column, "description": desc,
                   "adopted": "ADOPTED" in desc,
                   "proxy_first_month": str(proxy.index[0])}
            row.update(_compare(etf, proxy))
            rows.append(row)

    # gold and cash: real series, validated against their traded counterparts
    struct = load("structural")
    rows.append({"exposure": "GOLD", "source_file": "lbma_gold_pm.json",
                 "candidate": "LBMA Gold Price PM", "adopted": True,
                 "description": "actual benchmark price, not a proxy",
                 "proxy_first_month": str(struct["GOLD"].dropna().index[0]),
                 **_compare(live["GOLD"].dropna(), struct["GOLD"].dropna())})
    rows.append({"exposure": "CASH", "source_file": "F-F factors / FRED TB3MS",
                 "candidate": "Fama-French RF vs TB3MS construction",
                 "adopted": True,
                 "description": "two independent short-Treasury constructions",
                 "proxy_first_month": str(struct["CASH"].dropna().index[0]),
                 **_compare(live["CASH"].dropna(), struct["CASH"].dropna())})
    return pd.DataFrame(rows)


if __name__ == "__main__":  # pragma: no cover
    pd.set_option("display.width", 200)
    print(proxy_validation_table().to_string(index=False))
