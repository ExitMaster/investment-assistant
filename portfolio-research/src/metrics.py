"""Performance, robustness and risk statistics.

All functions take arrays shaped ``(S, ...)`` -- one row per rolling window --
and return one number per window unless stated otherwise.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

MONTHS = 12


# --------------------------------------------------------------------------
# growth
# --------------------------------------------------------------------------
def cagr(wealth_path: np.ndarray) -> np.ndarray:
    """Compound annual growth rate of a no-cash-flow wealth path (S, H+1)."""
    w = np.asarray(wealth_path, dtype=float)
    n = w.shape[1] - 1
    growth = w[:, -1] / w[:, 0]
    return growth ** (MONTHS / n) - 1.0


def real_terminal_wealth(nominal: np.ndarray, cpi_start: np.ndarray,
                         cpi_end: np.ndarray) -> np.ndarray:
    """Terminal wealth expressed in the purchasing power of the start date."""
    return np.asarray(nominal, dtype=float) * (np.asarray(cpi_start, dtype=float)
                                               / np.asarray(cpi_end, dtype=float))


# --------------------------------------------------------------------------
# risk
# --------------------------------------------------------------------------
def max_drawdown(wealth_path: np.ndarray) -> np.ndarray:
    """Largest peak-to-trough decline of a no-cash-flow wealth path."""
    w = np.asarray(wealth_path, dtype=float)
    peak = np.maximum.accumulate(w, axis=1)
    return (w / peak - 1.0).min(axis=1)


def underwater_months(wealth_path: np.ndarray) -> np.ndarray:
    """Longest run of months spent below a previous peak."""
    w = np.asarray(wealth_path, dtype=float)
    peak = np.maximum.accumulate(w, axis=1)
    under = w < peak - 1e-12
    out = np.zeros(w.shape[0])
    run = np.zeros(w.shape[0])
    for j in range(w.shape[1]):
        run = np.where(under[:, j], run + 1.0, 0.0)
        out = np.maximum(out, run)
    return out


def annualised_vol(monthly_returns: np.ndarray) -> np.ndarray:
    r = np.asarray(monthly_returns, dtype=float)
    return r.std(axis=1, ddof=1) * np.sqrt(MONTHS)


def downside_deviation(monthly_returns: np.ndarray, mar: float = 0.0) -> np.ndarray:
    r = np.asarray(monthly_returns, dtype=float)
    shortfall = np.minimum(r - mar / MONTHS, 0.0)
    return np.sqrt((shortfall ** 2).mean(axis=1)) * np.sqrt(MONTHS)


def worst_calendar_year(monthly_returns: pd.Series) -> float:
    """Worst full-calendar-year return of a single monthly return series."""
    idx = monthly_returns.index
    years = idx.year
    full = [y for y in np.unique(years) if (years == y).sum() == 12]
    if not full:
        return float("nan")
    rets = [(1 + monthly_returns[years == y]).prod() - 1 for y in full]
    return float(np.min(rets))


# --------------------------------------------------------------------------
# distribution summaries
# --------------------------------------------------------------------------
def summarise(values: np.ndarray, prefix: str) -> dict[str, float]:
    v = np.asarray(values, dtype=float)
    v = v[np.isfinite(v)]
    if v.size == 0:
        return {f"{prefix}_{k}": float("nan")
                for k in ("median", "p25", "p10", "p90", "worst", "best", "mean")}
    return {
        f"{prefix}_median": float(np.median(v)),
        f"{prefix}_p25": float(np.percentile(v, 25)),
        f"{prefix}_p10": float(np.percentile(v, 10)),
        f"{prefix}_p90": float(np.percentile(v, 90)),
        f"{prefix}_worst": float(v.min()),
        f"{prefix}_best": float(v.max()),
        f"{prefix}_mean": float(v.mean()),
    }


def share(mask: np.ndarray) -> float:
    m = np.asarray(mask, dtype=bool)
    return float(m.mean()) if m.size else float("nan")


# --------------------------------------------------------------------------
# effective sample size for overlapping windows
# --------------------------------------------------------------------------
def effective_independent_windows(n_months: int, horizon_months: int) -> int:
    """Number of *non-overlapping* windows the sample actually contains.

    Overlapping rolling windows are not independent observations; this is the
    honest denominator to quote alongside any rolling statistic.
    """
    return int(max(n_months // horizon_months, 0))
