#!/usr/bin/env python3
"""Reproduce the whole study.

    python run_research.py              # use the cached raw data
    python run_research.py --refresh    # re-download every source first
    python run_research.py --no-charts  # tables only

Outputs land in results/tables, results/charts and results/summary_facts.json.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from src import analysis as A
from src import build_dataset, metrics
from src.samples import build_all_samples, load_config

ROOT = Path(__file__).resolve().parent
TABLES = ROOT / "results" / "tables"
CHARTS = ROOT / "results" / "charts"
TABLES.mkdir(parents=True, exist_ok=True)
CHARTS.mkdir(parents=True, exist_ok=True)


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def eq(n: int) -> np.ndarray:
    return np.full(n, 1.0 / n)


# --------------------------------------------------------------------------
def phase1_equal_weight(engines: dict[str, A.Engine], cfg: dict):
    """All 63 equal-weight combinations, full sample and every rolling horizon."""
    full_rows, roll_rows = [], []
    for sname, eng in engines.items():
        combos = A.all_combinations(eng.sample.exposures)
        log(f"  {sname}: {len(combos)} combinations, "
            f"{eng.sample.n_months} months")
        for combo in combos:
            w = eq(len(combo))
            row = {"combo": A.combo_name(combo), "n_assets": len(combo),
                   "sample": sname, "sample_label": eng.sample.label,
                   "rule": A.PHASE1_RULE, "weights": "equal"}
            row.update(A.full_sample_stats(eng, combo, w))
            full_rows.append(row)
        for hy in cfg["rolling_horizons_years"]:
            if eng.n_starts(hy * 12) <= 0:
                continue
            refs = A.benchmark_terminal_wealth(eng, hy)
            for combo in combos:
                roll_rows.extend(
                    A.rolling_stats(eng, combo, eq(len(combo)), hy, refs=refs))
            log(f"    rolling {hy}y done ({eng.n_starts(hy * 12)} starts)")
    return pd.DataFrame(full_rows), pd.DataFrame(roll_rows)


def phase2_rebalancing(engines: dict[str, A.Engine], cfg: dict,
                       horizons: tuple[int, ...] = (10, 20)):
    rows = []
    for sname, eng in engines.items():
        combos = [c for c in A.all_combinations(eng.sample.exposures) if len(c) > 1]
        for hy in horizons:
            if eng.n_starts(hy * 12) <= 0:
                continue
            for combo in combos:
                rows.extend(A.rebalance_comparison(eng, combo, eq(len(combo)),
                                                   hy, cfg))
            log(f"  {sname}: rebalance comparison {hy}y done "
                f"({len(combos)} combinations)")
    return pd.DataFrame(rows)


def phase2b_annual_month_sensitivity(eng: A.Engine, cfg: dict,
                                     combos: list[tuple[str, ...]]):
    """Is the annual-rebalancing result a January artefact?"""
    rows = []
    H = 10 * 12
    for combo in combos:
        w = eq(len(combo))
        base = eng.run(combo, w, "R0", H, with_contributions=True).terminal_wealth
        for month_no in cfg["rebalancing"]["annual_month_sensitivity"]:
            offset = (month_no - 1) % 12
            acc = eng.run(combo, w, "R2", H, with_contributions=True,
                          annual_month_offset=offset)
            ratio = acc.terminal_wealth / base
            row = {"combo": A.combo_name(combo), "sample": eng.sample.name,
                   "horizon_years": 10, "rebalance_month_offset": month_no,
                   "pct_windows_improved": metrics.share(ratio > 1.0)}
            row.update(metrics.summarise(ratio, "tw_ratio_vs_R0"))
            rows.append(row)
    return pd.DataFrame(rows)


def phase3_weight_grid(eng: A.Engine, cfg: dict, asset_sets: list[tuple[str, ...]],
                       horizons: tuple[int, ...] = (10, 20)):
    step = cfg["weight_search"]["step"]
    rows = []
    for combo in asset_sets:
        grid = A.weight_grid(len(combo), step)
        for hy in horizons:
            H = hy * 12
            if eng.n_starts(H) <= 0:
                continue
            refs = A.benchmark_terminal_wealth(eng, hy)
            defl = eng.deflator(H)
            for w in grid:
                lump = eng.run(combo, w, A.PHASE1_RULE, H, with_contributions=False)
                acc = eng.run(combo, w, A.PHASE1_RULE, H, with_contributions=True)
                cagrs = metrics.cagr(lump.total)
                real_tw = acc.terminal_wealth * defl
                row = {
                    "combo": A.combo_name(combo),
                    "weights": "/".join(f"{x:.0%}" for x in w),
                    "sample": eng.sample.name,
                    "horizon_years": hy,
                    "n_windows": len(cagrs),
                    "cagr_median": float(np.median(cagrs)),
                    "cagr_p10": float(np.percentile(cagrs, 10)),
                    "cagr_worst": float(cagrs.min()),
                    "maxdd_median": float(np.median(metrics.max_drawdown(lump.total))),
                    "contrib_real_tw_median": float(np.median(real_tw)),
                    "contrib_real_tw_p10": float(np.percentile(real_tw, 10)),
                }
                for k, v in zip(combo, w):
                    row[f"w_{k}"] = float(v)
                for bench, btw in refs.items():
                    row[f"pct_beating_{bench}"] = metrics.share(real_tw / btw > 1.0)
                rows.append(row)
        log(f"  weight grid {A.combo_name(combo)}: {len(grid)} allocations")
    return pd.DataFrame(rows)


def phase4_plateau(grid_table: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """How much of the neighbourhood of each allocation holds up (SC-15)."""
    step = cfg["weight_search"]["step"]
    out = []
    for (combo, hz, sample), sub in grid_table.groupby(
            ["combo", "horizon_years", "sample"]):
        assets = combo.split("+")
        sub = sub.reset_index(drop=True)
        W = sub[[f"w_{a}" for a in assets]].to_numpy(dtype=float)
        for metric in ("cagr_median", "contrib_real_tw_median", "cagr_p10"):
            vals = sub[metric].to_numpy(dtype=float)
            best = int(np.argmax(vals))
            for i in range(len(sub)):
                d = np.abs(W - W[i]).sum(axis=1)
                nb = (d > 1e-9) & (d <= 2 * step + 1e-9)
                if nb.sum() == 0:
                    continue
                out.append({
                    "combo": combo, "sample": sample, "horizon_years": hz,
                    "metric": metric,
                    "weights": sub.loc[i, "weights"],
                    "value": float(vals[i]),
                    "rank": int((vals > vals[i]).sum()) + 1,
                    "is_grid_max": i == best,
                    "n_neighbours": int(nb.sum()),
                    "neighbour_min": float(vals[nb].min()),
                    "neighbour_median": float(np.median(vals[nb])),
                    "neighbour_worst_shortfall": float(vals[i] - vals[nb].min()),
                    "relative_neighbour_shortfall": float(
                        (vals[i] - vals[nb].min()) / abs(vals[i]))
                    if vals[i] != 0 else np.nan,
                })
    return pd.DataFrame(out)


# --------------------------------------------------------------------------
def phase5_hypotheses(tables: dict[str, pd.DataFrame], cfg: dict) -> pd.DataFrame:
    """Explicit, falsifiable statements with the numbers that settle them."""
    roll = tables["rolling"]
    prim = roll[(roll["sample"] == "structural") & (roll.window_scheme == "monthly")]

    def g(combo: str, hz: int, col: str):
        r = prim[(prim.combo == combo) & (prim.horizon_years == hz)]
        return float(r[col].iloc[0]) if len(r) else np.nan

    rows = []

    def add(hid, statement, hz, verdict_fn, fields):
        vals = {k: g(c, hz, col) for k, (c, col) in fields.items()}
        verdict, note = verdict_fn(vals)
        rows.append({"hypothesis": hid, "statement": statement,
                     "horizon_years": hz, "verdict": verdict, "evidence": note,
                     **{f"x_{k}": v for k, v in vals.items()}})

    for hz in (10, 20):
        add("H1", "SPMO alone is a robust one-asset solution.", hz,
            lambda v: (
                "SUPPORTED" if (v["spmo_p10"] > v["spy_p10"]
                                and v["spmo_dd"] > v["spy_dd"]) else
                "PARTLY SUPPORTED" if v["spmo_med"] > v["spy_med"] else "REJECTED",
                f"SPMO median/p10 rolling CAGR {v['spmo_med']:.2%}/{v['spmo_p10']:.2%} "
                f"vs SPY {v['spy_med']:.2%}/{v['spy_p10']:.2%}; "
                f"median max drawdown {v['spmo_dd']:.1%} vs {v['spy_dd']:.1%}"),
            {"spmo_med": ("SPMO", "cagr_median"), "spmo_p10": ("SPMO", "cagr_p10"),
             "spmo_dd": ("SPMO", "maxdd_median"),
             "spy_med": ("SPY", "cagr_median"), "spy_p10": ("SPY", "cagr_p10"),
             "spy_dd": ("SPY", "maxdd_median")})

        add("H2", "QQQ alone offers higher growth but materially greater tail risk.",
            hz,
            lambda v: (
                "SUPPORTED" if (v["qqq_med"] > v["spy_med"]
                                and v["qqq_dd"] < v["spy_dd"] - 0.05) else
                "PARTLY SUPPORTED" if v["qqq_dd"] < v["spy_dd"] else "REJECTED",
                f"QQQ median rolling CAGR {v['qqq_med']:.2%} vs SPY {v['spy_med']:.2%}; "
                f"worst rolling CAGR {v['qqq_worst']:.2%} vs {v['spy_worst']:.2%}; "
                f"median max drawdown {v['qqq_dd']:.1%} vs {v['spy_dd']:.1%}"),
            {"qqq_med": ("QQQ", "cagr_median"), "qqq_worst": ("QQQ", "cagr_worst"),
             "qqq_dd": ("QQQ", "maxdd_median"),
             "spy_med": ("SPY", "cagr_median"), "spy_worst": ("SPY", "cagr_worst"),
             "spy_dd": ("SPY", "maxdd_median")})

        add("H3", "SPMO+QQQ improves robustness without excessive return dilution.",
            hz,
            lambda v: (
                "SUPPORTED" if (v["pair_p10"] > max(v["spmo_p10"], v["qqq_p10"])
                                and v["pair_med"] >= min(v["spmo_med"], v["qqq_med"]))
                else "REJECTED",
                f"pair p10 {v['pair_p10']:.2%} vs SPMO {v['spmo_p10']:.2%} / "
                f"QQQ {v['qqq_p10']:.2%}; pair median {v['pair_med']:.2%} vs "
                f"SPMO {v['spmo_med']:.2%} / QQQ {v['qqq_med']:.2%}"),
            {"pair_p10": ("QQQ+SPMO", "cagr_p10"), "pair_med": ("QQQ+SPMO", "cagr_median"),
             "spmo_p10": ("SPMO", "cagr_p10"), "spmo_med": ("SPMO", "cagr_median"),
             "qqq_p10": ("QQQ", "cagr_p10"), "qqq_med": ("QQQ", "cagr_median")})

        add("H4", "Adding Gold to SPMO+QQQ further improves long-horizon robustness.",
            hz,
            lambda v: (
                "SUPPORTED" if (v["trio_p10"] > v["pair_p10"] + 0.0025
                                and v["trio_dd"] > v["pair_dd"]) else
                "PARTLY SUPPORTED" if v["trio_p10"] > v["pair_p10"] else "REJECTED",
                f"p10 rolling CAGR {v['trio_p10']:.2%} vs {v['pair_p10']:.2%}; "
                f"worst {v['trio_worst']:.2%} vs {v['pair_worst']:.2%}; "
                f"median max drawdown {v['trio_dd']:.1%} vs {v['pair_dd']:.1%}; "
                f"median real terminal wealth {v['trio_tw']:.1f} vs {v['pair_tw']:.1f}"),
            {"trio_p10": ("QQQ+SPMO+GOLD", "cagr_p10"),
             "trio_worst": ("QQQ+SPMO+GOLD", "cagr_worst"),
             "trio_dd": ("QQQ+SPMO+GOLD", "maxdd_median"),
             "trio_tw": ("QQQ+SPMO+GOLD", "contrib_real_tw_median"),
             "pair_p10": ("QQQ+SPMO", "cagr_p10"),
             "pair_worst": ("QQQ+SPMO", "cagr_worst"),
             "pair_dd": ("QQQ+SPMO", "maxdd_median"),
             "pair_tw": ("QQQ+SPMO", "contrib_real_tw_median")})

        add("H5", "SPY adds little incremental value once SPMO+QQQ are present.", hz,
            lambda v: (
                "SUPPORTED" if (v["with_p10"] <= v["without_p10"] + 0.0025
                                and v["with_med"] <= v["without_med"] + 0.0025)
                else "REJECTED",
                f"adding SPY moves median rolling CAGR "
                f"{v['without_med']:.2%} -> {v['with_med']:.2%} and p10 "
                f"{v['without_p10']:.2%} -> {v['with_p10']:.2%}"),
            {"with_p10": ("SPY+QQQ+SPMO", "cagr_p10"),
             "with_med": ("SPY+QQQ+SPMO", "cagr_median"),
             "without_p10": ("QQQ+SPMO", "cagr_p10"),
             "without_med": ("QQQ+SPMO", "cagr_median")})

        add("H6", "SCHD adds little incremental value once SPMO+QQQ are present.", hz,
            lambda v: (
                "SUPPORTED" if (v["with_p10"] <= v["without_p10"] + 0.0025
                                and v["with_med"] <= v["without_med"] + 0.0025)
                else "REJECTED",
                f"adding SCHD moves median rolling CAGR "
                f"{v['without_med']:.2%} -> {v['with_med']:.2%} and p10 "
                f"{v['without_p10']:.2%} -> {v['with_p10']:.2%}"),
            {"with_p10": ("QQQ+SCHD+SPMO", "cagr_p10"),
             "with_med": ("QQQ+SCHD+SPMO", "cagr_median"),
             "without_p10": ("QQQ+SPMO", "cagr_p10"),
             "without_med": ("QQQ+SPMO", "cagr_median")})

        add("H7", "Permanent Cash costs more than its diversification is worth.", hz,
            lambda v: (
                "SUPPORTED" if (v["with_med"] < v["without_med"]
                                and v["with_p10"] <= v["without_p10"] + 0.0025)
                else "REJECTED",
                f"adding CASH moves median rolling CAGR "
                f"{v['without_med']:.2%} -> {v['with_med']:.2%}, p10 "
                f"{v['without_p10']:.2%} -> {v['with_p10']:.2%}, median max "
                f"drawdown {v['without_dd']:.1%} -> {v['with_dd']:.1%}"),
            {"with_med": ("QQQ+SPMO+CASH", "cagr_median"),
             "with_p10": ("QQQ+SPMO+CASH", "cagr_p10"),
             "with_dd": ("QQQ+SPMO+CASH", "maxdd_median"),
             "without_med": ("QQQ+SPMO", "cagr_median"),
             "without_p10": ("QQQ+SPMO", "cagr_p10"),
             "without_dd": ("QQQ+SPMO", "maxdd_median")})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
def phase6_sensitivities(eng: A.Engine, cfg: dict,
                         combos: list[tuple[str, ...]]) -> pd.DataFrame:
    """Timing, fee and tax sensitivities.  None of these drive conclusions."""
    rows = []
    H = 10 * 12
    defl = eng.deflator(H)
    fees = cfg["costs"]["expense_ratios_bps"]
    drag = cfg["costs"]["proxy_implementation_drag_bps"]

    for combo in combos:
        w = eq(len(combo))
        base = eng.run(combo, w, A.PHASE1_RULE, H, with_contributions=True)
        base_tw = base.terminal_wealth * defl

        # contribution at month end instead of month start
        end = eng.run(combo, w, A.PHASE1_RULE, H, with_contributions=True,
                      contribution_timing="end")
        rows.append({"combo": A.combo_name(combo), "scenario": "contribution_at_month_end",
                     "median_real_tw": float(np.median(end.terminal_wealth * defl)),
                     "median_ratio_vs_base": float(
                         np.median(end.terminal_wealth * defl / base_tw))})

        # fee-adjusted simulation
        idx = [eng._cols[c] for c in combo]
        R = eng.windows(H)[:, :, idx].copy()
        total_bps = np.array([fees[c] + drag[c] for c in combo], dtype=float)
        monthly_drag = (1 - total_bps / 10000.0) ** (1 / 12) - 1
        R = (1 + R) * (1 + monthly_drag[None, None, :]) - 1
        from src.portfolio import simulate as _sim
        fee = _sim(R, w, rule=A.PHASE1_RULE,
                   contributions=eng.contributions(H), initial=0.0)
        rows.append({"combo": A.combo_name(combo), "scenario": "FEE_ADJUSTED_SIMULATION",
                     "median_real_tw": float(np.median(fee.terminal_wealth * defl)),
                     "median_ratio_vs_base": float(
                         np.median(fee.terminal_wealth * defl / base_tw))})

        # investor-level capital-gains tax on rebalancing sales
        rate = cfg["taxes"]["capital_gains_rate"]
        exempt = cfg["taxes"]["annual_exemption"]
        taxable = np.maximum(base.sold - exempt * (H / 12), 0.0)
        # conservative: the whole disposal is treated as gain
        after = base.terminal_wealth - rate * taxable
        rows.append({"combo": A.combo_name(combo),
                     "scenario": f"tax_on_sales_{rate:.0%}_worst_case",
                     "median_real_tw": float(np.median(after * defl)),
                     "median_ratio_vs_base": float(np.median(after * defl / base_tw))})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true",
                    help="re-download every raw source before running")
    ap.add_argument("--no-charts", action="store_true")
    args = ap.parse_args()

    cfg = load_config()
    if args.refresh or not (ROOT / "data" / "processed" / "structural_monthly.csv").exists():
        log("building datasets from source")
        build_dataset.build_all(refresh=args.refresh)

    samples = build_all_samples(cfg)
    engines = {n: A.Engine(s, cfg) for n, s in samples.items()}
    for n, s in samples.items():
        log(f"sample {n}: {s.returns.index[0]}..{s.returns.index[-1]} "
            f"n={s.n_months} exposures={s.exposures}")
    primary = engines["structural"]

    log("phase 1: equal-weight screening")
    full, roll = phase1_equal_weight(engines, cfg)
    full.to_csv(TABLES / "all_equal_weight_combinations.csv", index=False)
    for hy in cfg["rolling_horizons_years"]:
        sub = roll[roll.horizon_years == hy]
        sub.to_csv(TABLES / f"rolling_{hy}y.csv", index=False)
    roll.to_csv(TABLES / "rolling_all_horizons.csv", index=False)

    contrib_cols = [c for c in roll.columns
                    if c.startswith(("contrib_", "tw_rel_", "pct_windows_beating",
                                     "excess_tw_vs"))
                    or c in ("combo", "n_assets", "sample", "sample_label",
                             "horizon_years", "window_scheme", "n_windows",
                             "n_independent_windows", "first_start", "last_start",
                             "rule", "pct_positive_real_return")]
    roll[contrib_cols].to_csv(TABLES / "recurring_contribution_results.csv",
                              index=False)

    log("phase 2: rebalancing comparison")
    reb = phase2_rebalancing(engines, cfg)
    reb.to_csv(TABLES / "rebalance_comparison.csv", index=False)

    log("phase 3: screening")
    prim_roll = roll[roll["sample"] == "structural"]
    survivors = A.screen(prim_roll, cfg)
    survivors.to_csv(TABLES / "screening_survivors.csv", index=False)
    log(f"  {len(survivors)} survivors: {list(survivors.combo)}")

    max_assets = cfg["weight_search"]["max_assets"]
    asset_sets = [tuple(c.split("+")) for c in survivors.combo
                  if 2 <= len(c.split("+")) <= max_assets]
    log(f"  weight-grid asset sets: {[A.combo_name(a) for a in asset_sets]}")

    log("phase 3b: annual-rebalance month sensitivity")
    month_sens = phase2b_annual_month_sensitivity(
        primary, cfg, asset_sets or [("SPY", "GOLD")])
    month_sens.to_csv(TABLES / "rebalance_month_sensitivity.csv", index=False)

    log("phase 4: coarse weight grid")
    grid = phase3_weight_grid(primary, cfg, asset_sets)
    grid.to_csv(TABLES / "candidate_weight_grid.csv", index=False)

    log("phase 5: plateau analysis")
    plateau = phase4_plateau(grid, cfg)
    plateau.to_csv(TABLES / "plateau_analysis.csv", index=False)

    log("phase 6: hypotheses")
    hyp = phase5_hypotheses({"rolling": roll}, cfg)
    hyp.to_csv(TABLES / "hypothesis_tests.csv", index=False)

    log("phase 7: live-period validation")
    live_eng = engines["live"]
    live_rows = []
    for combo in A.all_combinations(live_eng.sample.exposures):
        w = eq(len(combo))
        row = {"combo": A.combo_name(combo), "n_assets": len(combo),
               "sample": "live", "sample_label": live_eng.sample.label,
               "weights": "equal"}
        row.update(A.full_sample_stats(live_eng, combo, w))
        live_rows.append(row)
    live_tbl = pd.DataFrame(live_rows)
    live_tbl.to_csv(TABLES / "live_period_validation.csv", index=False)

    log("phase 8: sensitivities")
    sens_combos = (asset_sets or []) + [("SPMO",), ("QQQ",), ("SPY",)]
    sens = phase6_sensitivities(primary, cfg, sens_combos)
    sens.to_csv(TABLES / "sensitivity_analysis.csv", index=False)

    log("phase 7b: incremental effect of each added exposure")
    inc = pd.concat(
        [A.incremental_table(engines[s], (5, 10, 15, 20))
         for s in ("structural", "exact_index", "live", "official_index")],
        ignore_index=True)
    inc.to_csv(TABLES / "incremental_effects.csv", index=False)
    log(f"  {len(inc)} incremental comparisons across "
        f"{inc['sample'].nunique()} samples")

    log("phase 7c: investor-specific contribution scenarios")
    from src import investor
    cand = [tuple(c.split("+")) for c in survivors.combo] + [("SPMO",), ("QQQ",)]
    cand = [c for c in cand if all(a in primary.sample.exposures for a in c)]
    scen = investor.run_investor_scenarios(primary, cand, cfg)
    scen.to_csv(TABLES / "investor_scenarios.csv", index=False)
    grid_ratio = investor.run_ratio_grid(primary, cand, cfg)
    grid_ratio.to_csv(TABLES / "contribution_ratio_grid.csv", index=False)
    investor.capture_summary(scen, ["scenario", "combo"]).to_csv(
        TABLES / "contribution_capture_by_scenario.csv", index=False)
    investor.capture_summary(grid_ratio, ["annual_contribution_ratio", "combo"]
                             ).to_csv(TABLES / "contribution_capture_by_ratio.csv",
                                      index=False)
    log(f"  {len(scen)} scenario rows, {len(grid_ratio)} ratio-grid rows")

    log("phase 8b: implementation-cost break-even for the proxy exposures")
    drags = [0, 25, 50, 75, 100, 150, 200, 250, 300, 400, 500]
    cost_combos = [("SPMO",), ("SPY",), ("QQQ",), ("SCHD",),
                   ("QQQ", "SPMO"), ("QQQ", "SCHD", "SPMO"),
                   ("QQQ", "SCHD", "SPMO", "GOLD")]
    cost = pd.concat([
        A.cost_breakeven(primary, "SPMO", cost_combos, hz, drags)
        for hz in (10, 20, 30)
    ], ignore_index=True)
    cost.to_csv(TABLES / "implementation_cost_breakeven.csv", index=False)

    log("phase 8c: sub-period stability of each exposure's contribution")
    periods = [("1971-09", "1980-12"), ("1981-01", "1994-12"),
               ("1995-01", "2009-12"), ("2010-01", "2018-12"),
               ("2019-01", "2026-06"), ("1971-09", "2018-12"),
               ("1971-09", "2026-06")]
    subs = []
    for added in ("GOLD", "CASH", "SPY", "SCHD", "QQQ", "SPMO"):
        base = tuple(a for a in ("QQQ", "SCHD", "SPMO") if a != added)
        subs.append(A.subperiod_stability(primary, base, added, periods))
    pd.concat(subs, ignore_index=True).to_csv(
        TABLES / "subperiod_stability.csv", index=False)

    log("phase 8d: gold start-date sensitivity")
    gold_rows = []
    for start in (cfg["gold"]["free_float_start"],
                  cfg["gold"]["us_private_ownership_start"], "1980-01"):
        sub_returns = primary.sample.returns.loc[pd.Period(start, freq="M"):]
        for combo in (("QQQ", "SCHD", "SPMO"), ("QQQ", "SCHD", "SPMO", "GOLD"),
                      ("GOLD",), ("SPY", "GOLD")):
            R = sub_returns[list(combo)].to_numpy()[None, :, :]
            w = np.full(len(combo), 1.0 / len(combo))
            from src.portfolio import simulate as _s
            res = _s(R, w, rule=A.PHASE1_RULE)
            gold_rows.append({
                "gold_history_start": start, "combo": A.combo_name(combo),
                "months": R.shape[1],
                "cagr": float(metrics.cagr(res.total)[0]),
                "max_drawdown": float(metrics.max_drawdown(res.total)[0]),
                "vol_annual": float(metrics.annualised_vol(res.monthly_returns)[0]),
            })
    pd.DataFrame(gold_rows).to_csv(TABLES / "gold_start_sensitivity.csv",
                                   index=False)

    log("phase 8e: live-period rank agreement")
    prim10 = roll[(roll["sample"] == "structural") & (roll.horizon_years == 10)
                  & (roll.window_scheme == "monthly")][["combo", "cagr_median"]]
    agree = live_tbl[["combo", "n_assets", "cagr", "max_drawdown"]].merge(
        prim10.rename(columns={"cagr_median": "structural_median_10y_cagr"}),
        on="combo", how="inner")
    agree["structural_rank"] = agree["structural_median_10y_cagr"].rank(
        ascending=False).astype(int)
    agree["live_rank"] = agree["cagr"].rank(ascending=False).astype(int)
    agree["rank_gap"] = agree["live_rank"] - agree["structural_rank"]
    agree = agree.sort_values("structural_rank")
    agree.to_csv(TABLES / "live_vs_structural_rank_agreement.csv", index=False)
    # Spearman = Pearson on the ranks; computed directly to avoid a scipy dep.
    spearman = float(agree["structural_rank"].corr(agree["live_rank"]))
    log(f"  Spearman rank correlation live vs structural: {spearman:.3f}")

    log("phase 9: proxy validation")
    from src.proxy_validation import proxy_validation_table
    proxy_validation_table().to_csv(TABLES / "proxy_validation.csv", index=False)

    facts = {
        "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "samples": {n: {"start": str(s.returns.index[0]),
                        "end": str(s.returns.index[-1]),
                        "months": s.n_months,
                        "exposures": s.exposures,
                        "label": s.label} for n, s in samples.items()},
        "n_combinations_primary": len(A.all_combinations(primary.sample.exposures)),
        "survivors": list(survivors.combo),
        "weight_grid_sets": [A.combo_name(a) for a in asset_sets],
        "live_vs_structural_spearman": spearman,
    }
    (ROOT / "results" / "summary_facts.json").write_text(json.dumps(facts, indent=2))

    if not args.no_charts:
        log("phase 10: charts")
        from src import charts
        charts.build_all(engines, roll, reb, grid, cfg, CHARTS,
                         always=tuple(survivors.combo))

    log("done")


if __name__ == "__main__":
    main()
