"""Analytical charts.

Charts are evidence, not the decision procedure -- every one of them plots a
number that also exists in results/tables.

Design rules applied: one axis per chart, a fixed categorical hue order (never
cycled), a single-hue sequential ramp for magnitude, recessive grid and axes,
a legend whenever more than one series is present.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt          # noqa: E402
import numpy as np                        # noqa: E402
import pandas as pd                       # noqa: E402

from . import analysis as A               # noqa: E402
from . import metrics                     # noqa: E402

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
GRID = "#dedddb"
# validated categorical order (light mode); assigned by slot, never cycled
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100",
          "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
SEQ_HUE = "#2a78d6"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE, "font.size": 10,
    "axes.edgecolor": GRID, "axes.labelcolor": INK_2,
    "xtick.color": INK_2, "ytick.color": INK_2,
    "axes.titlecolor": INK, "axes.grid": True, "grid.color": GRID,
    "grid.linewidth": 0.6, "axes.axisbelow": True,
})


def _finish(ax, title, subtitle=None, xlabel=None, ylabel=None, wrap=110):
    lines = textwrap.wrap(subtitle, wrap) if subtitle else []
    ax.set_title(title, loc="left", fontsize=12, fontweight="bold",
                 pad=14 + 12 * len(lines))
    if lines:
        ax.text(0, 1.012, "\n".join(lines), transform=ax.transAxes, fontsize=9,
                color=INK_2, va="bottom", linespacing=1.4)
    if xlabel:
        ax.set_xlabel(xlabel)
    if ylabel:
        ax.set_ylabel(ylabel)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)


def _pct(ax, axis="x"):
    fmt = matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:.0%}")
    (ax.xaxis if axis == "x" else ax.yaxis).set_major_formatter(fmt)


def _focus_combos(roll: pd.DataFrame, horizon: int, n: int = 14,
                  always: tuple[str, ...] = ()) -> list[str]:
    """Six single assets, the screening survivors, then the best by median."""
    sub = roll[(roll["sample"] == "structural") & (roll.horizon_years == horizon)
               & (roll.window_scheme == "monthly")]
    singles = [c for c in sub[sub.n_assets == 1].combo]
    picked = list(dict.fromkeys(singles + [a for a in always
                                           if a in set(sub.combo)]))
    multi = [c for c in sub[sub.n_assets > 1]
             .sort_values("cagr_median", ascending=False).combo
             if c not in picked]
    return picked + multi[: max(n - len(picked), 0)]


# --------------------------------------------------------------------------
def _distribution_chart(values: dict[str, np.ndarray], title, subtitle, xlabel,
                        path: Path, percent=True):
    labels = list(values)
    data = [values[k] for k in labels]
    fig, ax = plt.subplots(figsize=(9, 0.42 * len(labels) + 2.2))
    bp = ax.boxplot(data, vert=False, widths=0.6, patch_artist=True,
                    whis=(0, 100), medianprops=dict(color=INK, linewidth=1.6),
                    flierprops=dict(marker="", linestyle="none"))
    for i, box in enumerate(bp["boxes"]):
        box.set_facecolor(SERIES[0] if "+" in labels[i] else SERIES[1])
        box.set_alpha(0.55)
        box.set_edgecolor(SURFACE)
        box.set_linewidth(2)
    for part in ("whiskers", "caps"):
        for art in bp[part]:
            art.set_color(INK_2)
            art.set_linewidth(1)
    ax.set_yticks(range(1, len(labels) + 1))
    ax.set_yticklabels(labels, fontsize=9)
    ax.invert_yaxis()
    ax.grid(axis="y", visible=False)
    if percent:
        _pct(ax)
    _finish(ax, title, subtitle, xlabel)
    handles = [plt.Line2D([], [], marker="s", linestyle="none", markersize=9,
                          color=SERIES[1], alpha=0.55, label="single exposure"),
               plt.Line2D([], [], marker="s", linestyle="none", markersize=9,
                          color=SERIES[0], alpha=0.55, label="multi-asset")]
    ax.legend(handles=handles, frameon=False, loc="lower right", fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def rolling_cagr_charts(eng: A.Engine, roll: pd.DataFrame, out: Path,
                        always: tuple[str, ...] = ()):
    for hz in (10, 20, 30):
        H = hz * 12
        if eng.n_starts(H) <= 0:
            continue
        combos = _focus_combos(roll, hz, always=always)
        values = {}
        for name in combos:
            combo = tuple(name.split("+"))
            res = eng.run(combo, np.full(len(combo), 1 / len(combo)),
                          A.PHASE1_RULE, H, with_contributions=False)
            values[name] = metrics.cagr(res.total)
        order = sorted(values, key=lambda k: np.median(values[k]), reverse=True)
        _distribution_chart(
            {k: values[k] for k in order},
            f"Rolling {hz}-year CAGR, every monthly start date",
            f"{eng.sample.label} sample, {eng.sample.returns.index[0]}"
            f"-{eng.sample.returns.index[-1]}, equal weights, annual rebalancing. "
            f"Whiskers span the full range of {eng.n_starts(H)} overlapping windows.",
            f"annualised return over {hz} years",
            out / f"rolling_cagr_{hz}y.png")


def contribution_charts(eng: A.Engine, roll: pd.DataFrame, out: Path,
                        horizon: int = 20, always: tuple[str, ...] = ()):
    H = horizon * 12
    if eng.n_starts(H) <= 0:
        return
    combos = _focus_combos(roll, horizon, always=always)
    defl = eng.deflator(H)
    tw, refs = {}, {}
    for bench in ("QQQ", "SPY"):
        r = eng.run((bench,), np.array([1.0]), A.PHASE1_RULE, H,
                    with_contributions=True)
        refs[bench] = r.terminal_wealth * defl
    for name in combos:
        combo = tuple(name.split("+"))
        r = eng.run(combo, np.full(len(combo), 1 / len(combo)), A.PHASE1_RULE, H,
                    with_contributions=True)
        tw[name] = r.terminal_wealth * defl / H          # per real unit paid in

    order = sorted(tw, key=lambda k: np.median(tw[k]), reverse=True)
    _distribution_chart(
        {k: tw[k] for k in order},
        f"Real terminal wealth per unit contributed, {horizon}-year accumulation",
        "One real unit deposited at the start of every month; wealth deflated "
        "back to start-date purchasing power.",
        "multiple of total real contributions",
        out / "contribution_terminal_wealth.png", percent=False)

    for bench in refs:
        rel = {k: tw[k] * H / refs[bench] for k in order}
        rel_order = sorted(rel, key=lambda k: np.median(rel[k]), reverse=True)
        _distribution_chart(
            {k: rel[k] for k in rel_order},
            f"Terminal wealth relative to 100% {bench} ({horizon}-year accumulation)",
            f"Values above 1.0 mean the portfolio finished ahead of {bench} for "
            "that starting month.",
            f"terminal wealth / {bench} terminal wealth",
            out / f"relative_tw_vs_{bench.lower()}.png", percent=False)


def drawdown_chart(full: pd.DataFrame, out: Path):
    sub = full[full["sample"] == "structural"].copy()
    keep = sub[(sub.n_assets == 1) | (sub.n_assets.between(2, 3))]
    keep = pd.concat([keep[keep.n_assets == 1],
                      keep[keep.n_assets > 1].nsmallest(10, "max_drawdown")])
    keep = keep.sort_values("max_drawdown")
    fig, ax = plt.subplots(figsize=(9, 0.36 * len(keep) + 2.2))
    colors = [SERIES[0] if "+" in c else SERIES[1] for c in keep.combo]
    ax.barh(keep.combo, keep.max_drawdown, color=colors, alpha=0.85,
            edgecolor=SURFACE, linewidth=2)
    for y, (c, v) in enumerate(zip(keep.combo, keep.max_drawdown)):
        ax.text(v - 0.01, y, f"{v:.0%}", va="center", ha="right", fontsize=8,
                color=INK)
    ax.invert_yaxis()
    ax.grid(axis="y", visible=False)
    _pct(ax)
    _finish(ax, "Worst peak-to-trough decline over the full sample",
            "Equal weights, annual rebalancing, no contributions. Deeper is worse.",
            "maximum drawdown")
    handles = [plt.Line2D([], [], marker="s", linestyle="none", markersize=9,
                          color=SERIES[1], label="single exposure"),
               plt.Line2D([], [], marker="s", linestyle="none", markersize=9,
                          color=SERIES[0], label="multi-asset")]
    ax.legend(handles=handles, frameon=False, loc="lower left", fontsize=9)
    fig.tight_layout()
    fig.savefig(out / "max_drawdown_comparison.png", dpi=150)
    plt.close(fig)


def rebalancing_chart(reb: pd.DataFrame, out: Path, horizon: int = 20):
    sub = reb[(reb["sample"] == "structural") & (reb.horizon_years == horizon)]
    if sub.empty:
        return
    rules = list(dict.fromkeys(sub.rule))
    fig, ax = plt.subplots(figsize=(9, 5))
    for i, rule in enumerate(rules):
        r = sub[sub.rule == rule]
        y = np.full(len(r), i, dtype=float) + np.linspace(-0.18, 0.18, len(r))
        ax.scatter(r.tw_ratio_vs_R0_median, y, s=22, color=SERIES[i % len(SERIES)],
                   alpha=0.75, edgecolor=SURFACE, linewidth=0.8, label=rule)
        ax.hlines(i, r.tw_ratio_vs_R0_p10.median(), r.tw_ratio_vs_R0_p90.median(),
                  color=INK_2, linewidth=1)
    ax.axvline(1.0, color=INK, linewidth=1.2, linestyle="--")
    ax.set_yticks(range(len(rules)))
    ax.set_yticklabels(rules)
    ax.grid(axis="y", visible=False)
    _finish(ax, f"Rebalancing benefit: terminal wealth relative to no rebalancing",
            f"One dot per multi-asset combination ({horizon}-year accumulation "
            "windows, median across all monthly start dates). The bar shows the "
            "typical 10th-90th percentile spread across start dates.",
            "TW(rule) / TW(R0)")
    ax.legend(frameon=False, fontsize=9, loc="upper left", ncol=2)
    fig.tight_layout()
    fig.savefig(out / "rebalancing_benefit.png", dpi=150)
    plt.close(fig)


def _plateau_panel(ax, pivot, vmin, vmax, cmap):
    arr = pivot.to_numpy()
    im = ax.imshow(arr, origin="lower", cmap=cmap, aspect="auto",
                   vmin=vmin, vmax=vmax)
    ax.set_xticks(range(len(pivot.columns)), [f"{v:.0%}" for v in pivot.columns],
                  fontsize=8)
    ax.set_yticks(range(len(pivot.index)), [f"{v:.0%}" for v in pivot.index],
                  fontsize=8)
    mid = (vmin + vmax) / 2
    for i in range(arr.shape[0]):
        for j in range(arr.shape[1]):
            if np.isnan(arr[i, j]):
                continue
            ax.text(j, i, f"{arr[i, j]:.1%}", ha="center", va="center",
                    fontsize=7, color=INK if arr[i, j] < mid else SURFACE)
    best = np.unravel_index(np.nanargmax(arr), arr.shape)
    ax.add_patch(plt.Rectangle((best[1] - .5, best[0] - .5), 1, 1, fill=False,
                               edgecolor=SERIES[1], linewidth=2.2))
    ax.grid(visible=False)
    return im


def plateau_charts(grid: pd.DataFrame, out: Path, horizon: int = 20):
    """Heatmap of the coarse grid; four-asset sets are facetted by the fourth."""
    if grid.empty:
        return
    cmap = matplotlib.colors.LinearSegmentedColormap.from_list(
        "seq", ["#eef4fc", SEQ_HUE])
    sub = grid[grid.horizon_years == horizon]
    for combo, g in sub.groupby("combo"):
        assets = combo.split("+")
        if len(assets) < 3:
            continue
        a, b, c = assets[0], assets[1], assets[2]
        vmin, vmax = g.cagr_median.min(), g.cagr_median.max()
        facet_col = f"w_{assets[3]}" if len(assets) == 4 else None
        facets = sorted(g[facet_col].unique()) if facet_col else [None]

        ncol = min(len(facets), 3)
        nrow = int(np.ceil(len(facets) / ncol))
        fig, axes = plt.subplots(nrow, ncol, figsize=(4.6 * ncol, 4.3 * nrow),
                                 squeeze=False)
        fig.subplots_adjust(hspace=0.55, wspace=0.28, top=0.86)
        im = None
        for k, f in enumerate(facets):
            ax = axes[k // ncol][k % ncol]
            gg = g if f is None else g[g[facet_col] == f]
            pivot = gg.pivot_table(index=f"w_{b}", columns=f"w_{a}",
                                   values="cagr_median")
            im = _plateau_panel(ax, pivot, vmin, vmax, cmap)
            ax.set_xlabel(f"{a} weight", fontsize=9)
            ax.set_ylabel(f"{b} weight", fontsize=9)
            if f is not None:
                ax.set_title(f"{assets[3]} = {f:.0%}", fontsize=10, color=INK)
        for k in range(len(facets), nrow * ncol):
            axes[k // ncol][k % ncol].set_visible(False)

        remainder = c if len(assets) == 3 else f"{c} (the rest)"
        cbar = fig.colorbar(im, ax=axes, fraction=0.025, pad=0.02)
        cbar.set_label(f"median rolling {horizon}y CAGR", fontsize=9)
        cbar.formatter = matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:.1%}")
        cbar.update_ticks()
        subtitle = textwrap.wrap(
            f"Each cell is one coarse 10-point allocation; the remainder goes "
            f"to {remainder}. Orange box = grid maximum. A broad block of "
            "similar colour is a plateau; an isolated bright cell is a fitted "
            "optimum.", 55 * ncol)
        fig.text(0.02, 1.0, f"Allocation plateau: {combo}", fontsize=13,
                 fontweight="bold", color=INK, va="top")
        fig.text(0.02, 0.985 - 0.012 * nrow, "\n".join(subtitle), fontsize=9,
                 color=INK_2, va="top", linespacing=1.4)
        fig.savefig(out / f"plateau_{combo.replace('+', '_')}.png", dpi=150,
                    bbox_inches="tight")
        plt.close(fig)


def cumulative_wealth_chart(eng: A.Engine, roll: pd.DataFrame, out: Path,
                            always: tuple[str, ...] = ()):
    combos = _focus_combos(roll, 20, n=8, always=always)[:8]
    fig, ax = plt.subplots(figsize=(9.5, 5.6))
    idx = eng.sample.returns.index.to_timestamp()
    for i, name in enumerate(combos):
        combo = tuple(name.split("+"))
        res = eng.run(combo, np.full(len(combo), 1 / len(combo)), A.PHASE1_RULE,
                      eng.sample.n_months, with_contributions=False)
        path = res.total[0]
        ax.plot(np.concatenate([[idx[0]], idx]), path, linewidth=2,
                color=SERIES[i % len(SERIES)], label=name)
        ax.annotate(name, (idx[-1], path[-1]), xytext=(6, 0),
                    textcoords="offset points", fontsize=8,
                    color=SERIES[i % len(SERIES)], va="center")
    ax.set_yscale("log")
    ax.set_xlim(idx[0], idx[-1] + pd.Timedelta(days=2600))
    _finish(ax, "Growth of 1 unit invested once at the start",
            f"{eng.sample.label} sample, equal weights, annual rebalancing, "
            "log scale. Nominal, before tax and fees.",
            None, "wealth (log scale)")
    fig.savefig(out / "cumulative_wealth.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def cost_breakeven_chart(out: Path, horizon: int = 20):
    """How much annual implementation cost erases the momentum advantage."""
    path = out.parent / "tables" / "implementation_cost_breakeven.csv"
    if not path.exists():
        return
    df = pd.read_csv(path)
    df = df[df.horizon_years == horizon]
    if df.empty:
        return
    fig, ax = plt.subplots(figsize=(9, 5.4))
    combos = ["SPMO", "QQQ+SPMO", "QQQ+SCHD+SPMO", "SPY", "QQQ", "SCHD"]
    for i, combo in enumerate(combos):
        g = df[df.combo == combo].sort_values("drag_bps")
        if g.empty:
            continue
        style = "-" if "SPMO" in combo else "--"
        ax.plot(g.drag_bps, g.cagr_median, style, linewidth=2,
                color=SERIES[i % len(SERIES)], label=combo)
        if "SPMO" in combo:            # label the affected lines only
            ax.annotate(combo, (g.drag_bps.iloc[-1], g.cagr_median.iloc[-1]),
                        xytext=(6, 0), textcoords="offset points", fontsize=8,
                        color=SERIES[i % len(SERIES)], va="center")
    ax.set_xlim(df.drag_bps.min(), df.drag_bps.max() * 1.30)
    _pct(ax, "y")
    _finish(ax, "Break-even implementation cost for the momentum exposure",
            f"Median rolling {horizon}-year CAGR when an annual cost is charged "
            "to the SPMO exposure only (solid lines). The dashed lines are the "
            "unaffected alternatives. Where a solid line drops below a dashed "
            "one, the momentum advantage has been spent on trading.",
            "annual cost charged to SPMO (basis points)",
            f"median rolling {horizon}y CAGR")
    ax.legend(frameon=False, fontsize=9, ncol=3, loc="lower left")
    fig.savefig(out / "cost_breakeven.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


# --------------------------------------------------------------------------
def build_all(engines, roll, reb, grid, cfg, out: Path,
              always: tuple[str, ...] = ()):
    out.mkdir(parents=True, exist_ok=True)
    eng = engines["structural"]
    full = pd.read_csv(out.parent / "tables" / "all_equal_weight_combinations.csv")
    rolling_cagr_charts(eng, roll, out, always)
    contribution_charts(eng, roll, out, always=always)
    drawdown_chart(full, out)
    rebalancing_chart(reb, out)
    plateau_charts(grid, out)
    cumulative_wealth_chart(eng, roll, out, always)
    cost_breakeven_chart(out)
