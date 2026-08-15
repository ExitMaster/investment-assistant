"""Research analyses built on top of the simulator.

Nothing in here chooses a portfolio.  It produces the tables that the report
reasons from, using rules fixed in ``config.yaml`` before any result was seen.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import metrics
from .portfolio import RULES, rolling_windows, simulate
from .samples import Sample

PHASE1_RULE = "R2"          # annual rebalancing is the Phase-1 base rule


def all_combinations(exposures: list[str]) -> list[tuple[str, ...]]:
    """Every non-empty subset, ordered by size then by the config's order."""
    out: list[tuple[str, ...]] = []
    for k in range(1, len(exposures) + 1):
        out.extend(itertools.combinations(exposures, k))
    return out


def combo_name(combo: tuple[str, ...]) -> str:
    return "+".join(combo)


# --------------------------------------------------------------------------
@dataclass
class Engine:
    """Caches the rolling-window tensors for one sample."""

    sample: Sample
    cfg: dict

    def __post_init__(self) -> None:
        self._win: dict[int, np.ndarray] = {}
        self._contrib: dict[int, np.ndarray] = {}
        self._cols = {c: i for i, c in enumerate(self.sample.returns.columns)}
        self._R = self.sample.returns.to_numpy(dtype=float)
        self._P = self.sample.cpi_lagged.to_numpy(dtype=float)   # start-of-month level
        self._C = self.sample.cpi.to_numpy(dtype=float)          # month-end level

    # ---- windows ---------------------------------------------------------
    def windows(self, horizon: int) -> np.ndarray:
        if horizon not in self._win:
            self._win[horizon] = rolling_windows(self._R, horizon)
        return self._win[horizon]

    def n_starts(self, horizon: int) -> int:
        return max(len(self._R) - horizon + 1, 0)

    def start_periods(self, horizon: int) -> pd.PeriodIndex:
        return self.sample.returns.index[: self.n_starts(horizon)]

    def contributions(self, horizon: int) -> np.ndarray:
        """(S, H) nominal deposits worth exactly 1 start-date unit each."""
        if horizon not in self._contrib:
            S = self.n_starts(horizon)
            if S <= 0:
                self._contrib[horizon] = np.empty((0, horizon))
            else:
                view = np.lib.stride_tricks.sliding_window_view(self._P, horizon)
                view = view[:S]
                self._contrib[horizon] = view / view[:, [0]]
        return self._contrib[horizon]

    def deflator(self, horizon: int) -> np.ndarray:
        """(S,) multiply nominal terminal wealth by this to get real wealth."""
        S = self.n_starts(horizon)
        return self._P[:S] / self._C[horizon - 1: horizon - 1 + S]

    # ---- runs ------------------------------------------------------------
    def run_with_schedule(self, combo: tuple[str, ...], weights: np.ndarray,
                          rule: str, horizon: int, contributions: np.ndarray,
                          initial: float, band: float = 0.20,
                          annual_month_offset: int = 0):
        """Like :meth:`run`, but with an explicit deposit schedule and a
        starting portfolio -- the case where contributions are small relative
        to wealth."""
        idx = [self._cols[c] for c in combo]
        R = self.windows(horizon)[:, :, idx]
        return simulate(R, weights, rule=rule, contributions=contributions,
                        initial=initial, band=band,
                        annual_month_offset=annual_month_offset)

    def run(self, combo: tuple[str, ...], weights: np.ndarray, rule: str,
            horizon: int, with_contributions: bool, band: float = 0.20,
            annual_month_offset: int = 0, contribution_timing: str = "begin",
            drag_bps: dict[str, float] | None = None):
        idx = [self._cols[c] for c in combo]
        R = self.windows(horizon)[:, :, idx]
        if drag_bps:
            bps = np.array([drag_bps.get(c, 0.0) for c in combo], dtype=float)
            if np.any(bps):
                monthly = (1 - bps / 10000.0) ** (1 / 12) - 1
                R = (1 + R) * (1 + monthly[None, None, :]) - 1
        contrib = self.contributions(horizon) if with_contributions else None
        return simulate(
            R, weights, rule=rule,
            contributions=contrib,
            initial=0.0 if with_contributions else 1.0,
            band=band, annual_month_offset=annual_month_offset,
            contribution_timing=contribution_timing,
        )


# --------------------------------------------------------------------------
# full-sample (single window) statistics
# --------------------------------------------------------------------------
def full_sample_stats(eng: Engine, combo: tuple[str, ...], weights: np.ndarray,
                      rule: str = PHASE1_RULE) -> dict:
    H = eng.sample.n_months
    lump = eng.run(combo, weights, rule, H, with_contributions=False)
    acc = eng.run(combo, weights, rule, H, with_contributions=True)
    rets = pd.Series(lump.monthly_returns[0], index=eng.sample.returns.index)
    defl = eng.deflator(H)[0]

    real_growth = lump.terminal_wealth[0] * defl
    return {
        "n_months": H,
        "start": str(eng.sample.returns.index[0]),
        "end": str(eng.sample.returns.index[-1]),
        "cagr": float(metrics.cagr(lump.total)[0]),
        "real_cagr": float(real_growth ** (12 / H) - 1),
        "terminal_wealth_lump1": float(lump.terminal_wealth[0]),
        "real_terminal_wealth_lump1": float(real_growth),
        "max_drawdown": float(metrics.max_drawdown(lump.total)[0]),
        "underwater_months_max": float(metrics.underwater_months(lump.total)[0]),
        "vol_annual": float(metrics.annualised_vol(lump.monthly_returns)[0]),
        "downside_deviation": float(metrics.downside_deviation(lump.monthly_returns)[0]),
        "worst_calendar_year": metrics.worst_calendar_year(rets),
        "contrib_terminal_wealth": float(acc.terminal_wealth[0]),
        "contrib_real_terminal_wealth": float(acc.terminal_wealth[0] * defl),
        "contrib_total_paid": float(acc.contributed[0]),
        "contrib_tw_over_real_contributions": float(acc.terminal_wealth[0] * defl / H),
        "rebalance_events": float(acc.rebalance_events[0]),
        "turnover_annual": float(acc.turnover_annual[0]),
        "amount_sold": float(acc.sold[0]),
        "mean_weight_gap": float(acc.mean_weight_gap[0]),
        "contrib_share_of_rebalancing": float(acc.contrib_share_of_rebalancing[0]),
    }


# --------------------------------------------------------------------------
# rolling-horizon statistics
# --------------------------------------------------------------------------
def _window_subsets(starts: pd.PeriodIndex, horizon: int) -> dict[str, np.ndarray]:
    """Index masks for the three window schemes required by SC-8."""
    n = len(starts)
    monthly = np.ones(n, dtype=bool)
    annual = np.asarray(starts.month == 1)
    non_overlap = np.zeros(n, dtype=bool)
    non_overlap[::horizon] = True
    return {"monthly": monthly, "annual": annual, "nonoverlap": non_overlap}


def rolling_stats(eng: Engine, combo: tuple[str, ...], weights: np.ndarray,
                  horizon_years: int, rule: str = PHASE1_RULE,
                  refs: dict[str, np.ndarray] | None = None) -> list[dict]:
    """One row per window scheme for a single combination and horizon."""
    H = horizon_years * 12
    if eng.n_starts(H) <= 0:
        return []
    lump = eng.run(combo, weights, rule, H, with_contributions=False)
    acc = eng.run(combo, weights, rule, H, with_contributions=True)
    defl = eng.deflator(H)

    cagrs = metrics.cagr(lump.total)
    dds = metrics.max_drawdown(lump.total)
    vols = metrics.annualised_vol(lump.monthly_returns)
    dsd = metrics.downside_deviation(lump.monthly_returns)
    uw = metrics.underwater_months(lump.total)
    tw = acc.terminal_wealth
    real_tw = tw * defl
    real_cagr = (lump.terminal_wealth * defl) ** (12 / H) - 1

    starts = eng.start_periods(H)
    rows = []
    for scheme, mask in _window_subsets(starts, H).items():
        if mask.sum() == 0:
            continue
        row = {
            "combo": combo_name(combo),
            "n_assets": len(combo),
            "sample": eng.sample.name,
            "sample_label": eng.sample.label,
            "horizon_years": horizon_years,
            "window_scheme": scheme,
            "n_windows": int(mask.sum()),
            "n_independent_windows": metrics.effective_independent_windows(
                eng.sample.n_months, H),
            "first_start": str(starts[mask][0]),
            "last_start": str(starts[mask][-1]),
            "rule": rule,
        }
        row.update(metrics.summarise(cagrs[mask], "cagr"))
        row.update(metrics.summarise(real_cagr[mask], "real_cagr"))
        row.update(metrics.summarise(dds[mask], "maxdd"))
        row.update(metrics.summarise(vols[mask], "vol"))
        row.update(metrics.summarise(dsd[mask], "downside_dev"))
        row.update(metrics.summarise(uw[mask], "underwater_months"))
        row.update(metrics.summarise(tw[mask], "contrib_tw"))
        row.update(metrics.summarise(real_tw[mask], "contrib_real_tw"))
        row.update(metrics.summarise(real_tw[mask] / H, "contrib_tw_per_real_unit"))
        row["pct_positive_real_return"] = metrics.share(real_cagr[mask] > 0)
        if refs:
            for bench, bench_tw in refs.items():
                if combo == (bench,):
                    # a benchmark cannot beat itself; leave the cells empty
                    row[f"pct_windows_beating_{bench}"] = np.nan
                    row.update({k: np.nan for k in
                                metrics.summarise(np.array([]), f"tw_rel_{bench}")})
                    row[f"excess_tw_vs_{bench}_median"] = np.nan
                    continue
                rel = real_tw / bench_tw
                row[f"pct_windows_beating_{bench}"] = metrics.share(rel[mask] > 1.0)
                row.update(metrics.summarise(rel[mask], f"tw_rel_{bench}"))
                row[f"excess_tw_vs_{bench}_median"] = float(
                    np.median(real_tw[mask] - bench_tw[mask]))
        rows.append(row)
    return rows


def benchmark_terminal_wealth(eng: Engine, horizon_years: int,
                              rule: str = PHASE1_RULE) -> dict[str, np.ndarray]:
    """Real contribution terminal wealth of the single-asset benchmarks."""
    H = horizon_years * 12
    out: dict[str, np.ndarray] = {}
    defl = eng.deflator(H)
    for bench in ("QQQ", "SPY"):
        if bench not in eng.sample.exposures:
            continue
        res = eng.run((bench,), np.array([1.0]), rule, H, with_contributions=True)
        out[bench] = res.terminal_wealth * defl
    return out


# --------------------------------------------------------------------------
# rebalancing comparison (SC-10, SC-11)
# --------------------------------------------------------------------------
def rebalance_variants(cfg: dict) -> list[dict]:
    v = [{"rule": "R0", "band": np.nan, "label": "R0_none"},
         {"rule": "R1", "band": np.nan, "label": "R1_contribution_only"},
         {"rule": "R2", "band": np.nan, "label": "R2_annual"}]
    for b in cfg["rebalancing"]["relative_bands"]:
        v.append({"rule": "R3", "band": b, "label": f"R3_band_{int(b * 100)}pct"})
    return v


def rebalance_comparison(eng: Engine, combo: tuple[str, ...], weights: np.ndarray,
                         horizon_years: int, cfg: dict) -> list[dict]:
    """Distribution of TW(rule)/TW(R0) across every rolling window."""
    H = horizon_years * 12
    if eng.n_starts(H) <= 0 or len(combo) < 2:
        return []
    base = eng.run(combo, weights, "R0", H, with_contributions=True)
    base_tw = base.terminal_wealth
    base_lump = eng.run(combo, weights, "R0", H, with_contributions=False)

    rows = []
    for var in rebalance_variants(cfg):
        band = 0.20 if np.isnan(var["band"]) else var["band"]
        acc = eng.run(combo, weights, var["rule"], H, with_contributions=True,
                      band=band)
        lump = eng.run(combo, weights, var["rule"], H, with_contributions=False,
                       band=band)
        ratio = acc.terminal_wealth / base_tw
        row = {
            "combo": combo_name(combo),
            "n_assets": len(combo),
            "sample": eng.sample.name,
            "horizon_years": horizon_years,
            "rule": var["label"],
            "band": var["band"],
            "n_windows": int(len(ratio)),
            "n_independent_windows": metrics.effective_independent_windows(
                eng.sample.n_months, H),
            "pct_windows_improved": metrics.share(ratio > 1.0 + 1e-9),
            "pct_windows_worsened": metrics.share(ratio < 1.0 - 1e-9),
            "mean_rebalance_events": float(acc.rebalance_events.mean()),
            "mean_turnover_annual": float(acc.turnover_annual.mean()),
            "selling_required": bool(acc.sold.max() > 1e-9),
            "mean_amount_sold_per_unit_contributed": float(
                (acc.sold / np.maximum(acc.contributed, 1e-12)).mean()),
            "contrib_share_of_rebalancing": float(
                np.nanmean(acc.contrib_share_of_rebalancing)),
            "mean_weight_gap": float(acc.mean_weight_gap.mean()),
            "median_cagr_lump": float(np.median(metrics.cagr(lump.total))),
            "median_maxdd_lump": float(np.median(metrics.max_drawdown(lump.total))),
            "median_maxdd_vs_R0": float(
                np.median(metrics.max_drawdown(lump.total))
                - np.median(metrics.max_drawdown(base_lump.total))),
        }
        row.update(metrics.summarise(ratio, "tw_ratio_vs_R0"))
        rows.append(row)
    return rows


# --------------------------------------------------------------------------
# screening (SC-14)
# --------------------------------------------------------------------------
def pareto_survivors(table: pd.DataFrame, growth_col: str, robust_col: str
                     ) -> pd.DataFrame:
    """Keep combinations that nothing else beats on growth *and* robustness."""
    keep = []
    vals = table[[growth_col, robust_col]].to_numpy(dtype=float)
    for i in range(len(table)):
        dominated = np.any((vals[:, 0] > vals[i, 0] + 1e-12)
                           & (vals[:, 1] > vals[i, 1] + 1e-12))
        keep.append(not dominated)
    return table[np.array(keep)]


def screen(equal_weight_table: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Phase-1 survivors, chosen by a rule fixed before results were seen."""
    hz = cfg["screening"]["horizon_for_screen_years"]
    sub = equal_weight_table[
        (equal_weight_table.horizon_years == hz)
        & (equal_weight_table.window_scheme == "monthly")
    ].copy()
    surv = pareto_survivors(sub, "cagr_median", "cagr_p10")
    surv = surv.sort_values("cagr_median", ascending=False)
    return surv.head(cfg["screening"]["top_n_by_median_rolling_10y"])


# --------------------------------------------------------------------------
# coarse weight grid (SC-14, SC-15)
# --------------------------------------------------------------------------
def weight_grid(n_assets: int, step: float = 0.10) -> list[np.ndarray]:
    """All weight vectors on a coarse simplex grid with every weight > 0."""
    units = int(round(1.0 / step))
    out = []
    for parts in itertools.product(range(1, units + 1), repeat=n_assets):
        if sum(parts) == units:
            out.append(np.array(parts, dtype=float) / units)
    return out


# --------------------------------------------------------------------------
# how much implementation cost would erase an advantage?
# --------------------------------------------------------------------------
def cost_breakeven(eng: Engine, exposure: str, combos: list[tuple[str, ...]],
                   horizon_years: int, drags_bps: list[float]) -> pd.DataFrame:
    """Re-run combinations with an annual drag charged only to ``exposure``.

    The academic momentum and dividend portfolios reconstitute far more often
    than the ETFs they stand in for and are quoted gross of every cost, so the
    honest question is not "what is the right fee?" but "how large would the
    cost have to be before the conclusion flips?".
    """
    H = horizon_years * 12
    rows = []
    for d in drags_bps:
        for combo in combos:
            w = np.full(len(combo), 1.0 / len(combo))
            res = eng.run(combo, w, PHASE1_RULE, H, with_contributions=False,
                          drag_bps={exposure: d})
            c = metrics.cagr(res.total)
            rows.append({
                "sample": eng.sample.name,
                "charged_exposure": exposure,
                "drag_bps": d,
                "combo": combo_name(combo),
                "horizon_years": horizon_years,
                "cagr_median": float(np.median(c)),
                "cagr_p10": float(np.percentile(c, 10)),
                "cagr_worst": float(c.min()),
            })
    return pd.DataFrame(rows)


def subperiod_stability(eng: Engine, base: tuple[str, ...], added: str,
                        periods: list[tuple[str, str]]) -> pd.DataFrame:
    """Does adding one exposure help in every era, or only in one episode?"""
    rows = []
    idx = eng.sample.returns.index
    with_ = tuple(list(base) + [added])
    for start, end in periods:
        lo, hi = pd.Period(start, freq="M"), pd.Period(end, freq="M")
        mask = (idx >= lo) & (idx <= hi)
        n = int(mask.sum())
        if n < 24:
            continue
        sub = eng.sample.returns.loc[mask]
        out = {"period": f"{start}..{end}", "months": n,
               "base": combo_name(base), "added": added}
        for label, combo in (("without", base), ("with", with_)):
            R = sub[list(combo)].to_numpy()[None, :, :]
            w = np.full(len(combo), 1.0 / len(combo))
            res = simulate(R, w, rule=PHASE1_RULE)
            out[f"cagr_{label}"] = float(metrics.cagr(res.total)[0])
            out[f"maxdd_{label}"] = float(metrics.max_drawdown(res.total)[0])
            out[f"vol_{label}"] = float(metrics.annualised_vol(res.monthly_returns)[0])
        out["cagr_delta"] = out["cagr_with"] - out["cagr_without"]
        out["maxdd_delta"] = out["maxdd_with"] - out["maxdd_without"]
        out["vol_delta"] = out["vol_with"] - out["vol_without"]
        rows.append(out)
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# incremental effect of adding one exposure to a base portfolio
# --------------------------------------------------------------------------
def incremental_effect(eng: Engine, base: tuple[str, ...], added: str,
                       horizon_years: int, rule: str = PHASE1_RULE) -> dict | None:
    """What does adding one exposure to ``base`` do, on every rolling window?

    Both portfolios are equal-weighted, so the comparison is "one more equally
    weighted holding", not a weight optimisation.
    """
    H = horizon_years * 12
    if eng.n_starts(H) <= 0:
        return None
    if added in base or added not in eng.sample.exposures:
        return None
    if any(a not in eng.sample.exposures for a in base):
        return None
    with_ = tuple(list(base) + [added])
    defl = eng.deflator(H)
    refs = benchmark_terminal_wealth(eng, horizon_years, rule)

    out: dict[str, object] = {
        "sample": eng.sample.name, "sample_label": eng.sample.label,
        "base": combo_name(base), "added": added, "result": combo_name(with_),
        "horizon_years": horizon_years, "n_windows": eng.n_starts(H),
        "n_independent_windows": metrics.effective_independent_windows(
            eng.sample.n_months, H),
        "first_start": str(eng.start_periods(H)[0]),
        "last_start": str(eng.start_periods(H)[-1]),
    }
    stats: dict[str, dict[str, np.ndarray]] = {}
    for label, combo in (("base", base), ("with", with_)):
        w = np.full(len(combo), 1.0 / len(combo))
        lump = eng.run(combo, w, rule, H, with_contributions=False)
        acc = eng.run(combo, w, rule, H, with_contributions=True)
        c = metrics.cagr(lump.total)
        stats[label] = {
            "cagr": c,
            "maxdd": metrics.max_drawdown(lump.total),
            "vol": metrics.annualised_vol(lump.monthly_returns),
            "real_tw": acc.terminal_wealth * defl,
        }
    for key, agg in (("median", np.median), ("p10", lambda v: np.percentile(v, 10)),
                     ("worst", np.min)):
        for field in ("cagr", "maxdd", "vol", "real_tw"):
            b = float(agg(stats["base"][field]))
            a = float(agg(stats["with"][field]))
            out[f"{field}_{key}_base"] = b
            out[f"{field}_{key}_with"] = a
            out[f"{field}_{key}_delta"] = a - b
    out["pct_windows_added_helped_tw"] = metrics.share(
        stats["with"]["real_tw"] > stats["base"]["real_tw"])
    out["pct_windows_added_helped_cagr"] = metrics.share(
        stats["with"]["cagr"] > stats["base"]["cagr"])
    for bench, btw in refs.items():
        out[f"pct_beating_{bench}_base"] = metrics.share(
            stats["base"]["real_tw"] / btw > 1.0)
        out[f"pct_beating_{bench}_with"] = metrics.share(
            stats["with"]["real_tw"] / btw > 1.0)
    return out


INCREMENTAL_STEPS: list[tuple[tuple[str, ...], str]] = [
    (("SPMO",), "QQQ"),                       # (QQQ+SPMO) vs SPMO
    (("QQQ", "SPMO"), "SCHD"),                # (QQQ+SCHD+SPMO) vs (QQQ+SPMO)
    (("QQQ", "SCHD", "SPMO"), "GOLD"),        # +GOLD
    (("QQQ", "SCHD", "SPMO"), "SPY"),         # +SPY
    (("QQQ", "SCHD", "SPMO"), "CASH"),        # +CASH
    (("QQQ", "SPMO"), "GOLD"),                # SPMO+QQQ+Gold, asked explicitly
    (("SPY",), "QQQ"),                        # runs on the exact-index layer too
    (("SPY", "QQQ"), "GOLD"),
    (("SPY", "QQQ"), "CASH"),
]


def incremental_table(eng: Engine, horizons: tuple[int, ...]) -> pd.DataFrame:
    rows = []
    for hy in horizons:
        for base, added in INCREMENTAL_STEPS:
            row = incremental_effect(eng, base, added, hy)
            if row:
                rows.append(row)
    return pd.DataFrame(rows)


def neighbours(w: np.ndarray, grid: list[np.ndarray], step: float) -> list[int]:
    """Grid points one step away in exactly two coordinates (a simplex move)."""
    out = []
    for i, g in enumerate(grid):
        d = np.abs(g - w)
        if np.isclose(d.sum(), 2 * step) and np.count_nonzero(d > 1e-9) == 2:
            out.append(i)
    return out
