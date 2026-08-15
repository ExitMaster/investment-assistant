"""Rebalancing when contributions are small relative to wealth.

The accumulation-phase result -- that contributions alone do most of the
rebalancing work -- is only meaningful at a stated contribution/wealth ratio.
This module varies that ratio directly, and models the specific life path in
``config.yaml``: a portfolio of 20 units, 1 unit a year of new cash for five
years, then a retirement cliff of one of four sizes.

Everything reuses the simulator in :mod:`portfolio`; nothing here re-optimises
weights or rules.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import warnings

from . import metrics
from .analysis import Engine, PHASE1_RULE, combo_name, rebalance_variants


def _nanmean(values: np.ndarray) -> float:
    """Mean ignoring NaN, returning NaN for an all-NaN input without warning.

    An all-NaN input is meaningful here: it means no window ever had a weight
    gap for a contribution to close (e.g. there were no contributions at all).
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return float(np.nanmean(values)) if np.any(np.isfinite(values)) else float("nan")


def _contribution_matrix(eng: Engine, horizon: int, annual_units: np.ndarray,
                         initial: float) -> np.ndarray:
    """(S, H) nominal deposits from a per-year schedule of *real* units.

    ``annual_units[y]`` is the real cash contributed during year ``y``,
    expressed in units of the starting portfolio's purchasing power.  It is
    spread evenly over the twelve months of that year and inflated by the
    price level, so its real value is constant within the year.
    """
    real = eng.contributions(horizon)          # (S, H), each month worth 1 real unit
    per_month = np.repeat(annual_units / 12.0, 12)[:horizon]
    if len(per_month) < horizon:               # schedule shorter than the horizon
        per_month = np.concatenate(
            [per_month, np.full(horizon - len(per_month), annual_units[-1] / 12.0)])
    return real * per_month[None, :]


def scenario_schedule(horizon_years: int, before: float, after: float,
                      switch_year: int) -> np.ndarray:
    """Real units contributed per year: ``before`` until ``switch_year``, then
    ``after``."""
    yrs = np.full(horizon_years, float(after))
    yrs[:min(switch_year, horizon_years)] = float(before)
    return yrs


def run_investor_scenarios(eng: Engine, combos: list[tuple[str, ...]],
                           cfg: dict) -> pd.DataFrame:
    """The four post-retirement contribution paths, for every rebalancing rule."""
    inv = cfg["investor"]
    initial = float(inv["initial_wealth"])
    horizon_years = int(inv["horizon_years"])
    H = horizon_years * 12
    if eng.n_starts(H) <= 0:
        return pd.DataFrame()

    defl = eng.deflator(H)
    rows = []
    for scen in inv["scenarios"]:
        sched = scenario_schedule(horizon_years, inv["annual_contribution"],
                                  scen["after"], int(inv["switch_year"]))
        contrib = _contribution_matrix(eng, H, sched, initial)
        for combo in combos:
            w = np.full(len(combo), 1.0 / len(combo))
            base = eng.run_with_schedule(combo, w, "R0", H, contrib, initial)
            base_tw = base.terminal_wealth
            for var in rebalance_variants(cfg):
                band = 0.20 if np.isnan(var["band"]) else var["band"]
                res = eng.run_with_schedule(combo, w, var["rule"], H, contrib,
                                            initial, band=band)
                ratio = res.terminal_wealth / base_tw
                real_tw = res.terminal_wealth * defl
                row = {
                    "sample": eng.sample.name,
                    "scenario": scen["name"],
                    "post_switch_annual_contribution": scen["after"],
                    "initial_wealth": initial,
                    "first_year_contribution_ratio": inv["annual_contribution"] / initial,
                    "combo": combo_name(combo),
                    "rule": var["label"],
                    "band": var["band"],
                    "horizon_years": horizon_years,
                    "n_windows": len(ratio),
                    "total_real_contributed": float(sched.sum()),
                    "median_terminal_wealth": float(np.median(res.terminal_wealth)),
                    "median_real_terminal_wealth": float(np.median(real_tw)),
                    "p10_real_terminal_wealth": float(np.percentile(real_tw, 10)),
                    "median_tw_ratio_vs_R0": float(np.median(ratio)),
                    "p10_tw_ratio_vs_R0": float(np.percentile(ratio, 10)),
                    "worst_tw_ratio_vs_R0": float(ratio.min()),
                    "pct_windows_improved": metrics.share(ratio > 1.0 + 1e-9),
                    "mean_rebalance_events": float(res.rebalance_events.mean()),
                    "mean_turnover_annual": float(res.turnover_annual.mean()),
                    "median_amount_sold": float(np.median(res.sold)),
                    "sold_over_initial_wealth": float(np.median(res.sold) / initial),
                    "mean_weight_gap": float(res.mean_weight_gap.mean()),
                    "contrib_share_of_rebalancing": _nanmean(
                        res.contrib_share_of_rebalancing),
                }
                rows.append(row)
    return pd.DataFrame(rows)


def run_ratio_grid(eng: Engine, combos: list[tuple[str, ...]], cfg: dict
                   ) -> pd.DataFrame:
    """Contribution/wealth ratio sweep: the general relationship, not one life."""
    inv = cfg["investor"]
    horizon_years = int(inv["horizon_years"])
    H = horizon_years * 12
    if eng.n_starts(H) <= 0:
        return pd.DataFrame()
    initial = float(inv["initial_wealth"])
    rows = []
    for ratio in inv["contribution_ratio_grid"]:
        sched = np.full(horizon_years, ratio * initial)
        contrib = _contribution_matrix(eng, H, sched, initial)
        for combo in combos:
            w = np.full(len(combo), 1.0 / len(combo))
            base = eng.run_with_schedule(combo, w, "R0", H, contrib, initial)
            for var in rebalance_variants(cfg):
                band = 0.20 if np.isnan(var["band"]) else var["band"]
                res = eng.run_with_schedule(combo, w, var["rule"], H, contrib,
                                            initial, band=band)
                r = res.terminal_wealth / base.terminal_wealth
                rows.append({
                    "sample": eng.sample.name,
                    "annual_contribution_ratio": ratio,
                    "combo": combo_name(combo),
                    "rule": var["label"],
                    "horizon_years": horizon_years,
                    "median_tw_ratio_vs_R0": float(np.median(r)),
                    "p10_tw_ratio_vs_R0": float(np.percentile(r, 10)),
                    "pct_windows_improved": metrics.share(r > 1.0 + 1e-9),
                    "mean_turnover_annual": float(res.turnover_annual.mean()),
                    "mean_weight_gap": float(res.mean_weight_gap.mean()),
                    "contrib_share_of_rebalancing": _nanmean(
                        res.contrib_share_of_rebalancing),
                })
    return pd.DataFrame(rows)


def capture_summary(scen_or_grid: pd.DataFrame, group_cols: list[str]
                    ) -> pd.DataFrame:
    """Share of the annual-rebalance gain that contribution-only achieved.

    Only defined where annual rebalancing actually gained something; rows where
    it did not are reported with the gain itself so the reader can see why.
    """
    if scen_or_grid.empty:
        return pd.DataFrame()
    piv = scen_or_grid.pivot_table(index=group_cols, columns="rule",
                                   values="median_tw_ratio_vs_R0")
    out = piv.copy()
    gain_annual = piv["R2_annual"] - 1.0
    gain_contrib = piv["R1_contribution_only"] - 1.0
    out["annual_gain_vs_R0"] = gain_annual
    out["contribution_only_gain_vs_R0"] = gain_contrib
    out["contribution_capture_share"] = np.where(
        gain_annual > 0.0005, gain_contrib / gain_annual, np.nan)
    out["annual_rebalancing_helped"] = gain_annual > 0.0005
    return out.reset_index()


def weight_drift_path(eng: Engine, combo: tuple[str, ...], cfg: dict,
                      threshold: float = 0.05) -> pd.DataFrame:
    """Year-by-year distance from target weights, per scenario and rule.

    Answers "when do shrinking contributions stop keeping the allocation near
    target?" -- ``threshold`` is the gap (half the L1 distance, i.e. the share
    of the portfolio sitting in the wrong asset) treated as "no longer near".
    """
    inv = cfg["investor"]
    initial = float(inv["initial_wealth"])
    horizon_years = int(inv["horizon_years"])
    H = horizon_years * 12
    if eng.n_starts(H) <= 0:
        return pd.DataFrame()

    w = np.full(len(combo), 1.0 / len(combo))
    rows = []
    for scen in inv["scenarios"]:
        sched = scenario_schedule(horizon_years, inv["annual_contribution"],
                                  scen["after"], int(inv["switch_year"]))
        contrib = _contribution_matrix(eng, H, sched, initial)
        for var in rebalance_variants(cfg):
            band = 0.20 if np.isnan(var["band"]) else var["band"]
            res = eng.run_with_schedule(combo, w, var["rule"], H, contrib,
                                        initial, band=band, track_gap=True)
            gap = res.weight_gap_path                     # (S, H)
            by_year = gap.reshape(gap.shape[0], horizon_years, 12).mean(axis=2)
            median_by_year = np.median(by_year, axis=0)
            crossed = np.argmax(median_by_year > threshold) \
                if (median_by_year > threshold).any() else -1
            for y in range(horizon_years):
                rows.append({
                    "sample": eng.sample.name,
                    "combo": combo_name(combo),
                    "scenario": scen["name"],
                    "rule": var["label"],
                    "year": y + 1,
                    "median_weight_gap": float(median_by_year[y]),
                    "p90_weight_gap": float(np.percentile(by_year[:, y], 90)),
                    "first_year_above_threshold": int(crossed + 1) if crossed >= 0 else 0,
                    "threshold": threshold,
                })
    return pd.DataFrame(rows)
