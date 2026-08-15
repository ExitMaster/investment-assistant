"""Tests for the contribution/wealth-ratio analysis (task 3)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src import investor
from src.analysis import Engine
from src.samples import build_all_samples, load_config


@pytest.fixture(scope="module")
def cfg():
    return load_config()


@pytest.fixture(scope="module")
def eng(cfg):
    return Engine(build_all_samples(cfg)["structural"], cfg)


def test_scenario_schedule_switches_at_the_right_year():
    s = investor.scenario_schedule(20, before=1.0, after=0.25, switch_year=5)
    assert len(s) == 20
    assert list(s[:5]) == [1.0] * 5
    assert list(s[5:]) == [0.25] * 15
    assert s.sum() == pytest.approx(5 * 1.0 + 15 * 0.25)


def test_contribution_matrix_delivers_the_scheduled_real_amount(eng):
    """Each year's deposits must be worth the scheduled real units, whatever
    inflation did."""
    H = 240
    sched = investor.scenario_schedule(20, 1.0, 0.5, 5)
    C = investor._contribution_matrix(eng, H, sched, initial=20.0)
    assert C.shape == (eng.n_starts(H), H)
    # deflate each nominal deposit back to start-date money
    real = C / eng.contributions(H)          # undo the price-level scaling
    for year in (0, 4):
        assert real[0, year * 12:(year + 1) * 12].sum() == pytest.approx(1.0)
    for year in (5, 19):
        assert real[0, year * 12:(year + 1) * 12].sum() == pytest.approx(0.5)


def test_zero_contribution_scenario_deposits_nothing_after_the_switch(eng, cfg):
    H = 240
    sched = investor.scenario_schedule(20, 1.0, 0.0, 5)
    C = investor._contribution_matrix(eng, H, sched, initial=20.0)
    assert C[:, 60:].sum() == 0.0
    assert C[:, :60].sum() > 0.0


def test_contribution_capture_falls_as_the_contribution_ratio_falls(eng, cfg):
    """The headline correction: contribution-only rebalancing captures less of
    the annual-rebalance gain when contributions are small next to wealth."""
    grid = investor.run_ratio_grid(eng, [("QQQ", "SCHD", "SPMO")], cfg)
    cap = investor.capture_summary(grid, ["annual_contribution_ratio", "combo"])
    cap = cap.sort_values("annual_contribution_ratio")
    shares = cap["contribution_capture_share"].to_numpy(dtype=float)
    assert np.all(np.diff(shares) > -1e-9), "capture share must not increase as " \
                                            "the contribution ratio falls"
    lo = float(cap[cap.annual_contribution_ratio == 0.05]
               ["contribution_capture_share"].iloc[0])
    assert lo < 0.5, f"at a 5% contribution ratio capture was {lo:.2f}"


def test_no_contributions_means_no_contribution_rebalancing(eng, cfg):
    """With zero contributions, R1 must be identical to R0."""
    grid = investor.run_ratio_grid(eng, [("QQQ", "SCHD", "SPMO")], cfg)
    row = grid[(grid.annual_contribution_ratio == 0.0)
               & (grid.rule == "R1_contribution_only")].iloc[0]
    assert row.median_tw_ratio_vs_R0 == pytest.approx(1.0)
    assert row.mean_turnover_annual == 0.0


def test_weight_gap_is_worse_under_contribution_only_than_under_bands(eng, cfg):
    scen = investor.run_investor_scenarios(eng, [("QQQ", "SCHD", "SPMO")], cfg)
    d = scen[scen.scenario == "D_none_0.0"].set_index("rule")["mean_weight_gap"]
    assert d["R1_contribution_only"] > d["R2_annual"]
    assert d["R1_contribution_only"] > d["R3_band_20pct"]


def test_weight_drift_path_shows_contribution_only_degrading(eng, cfg):
    """Contribution-only rebalancing holds the allocation while contributions
    continue and loses it after they stop; band rules do not."""
    d = investor.weight_drift_path(eng, ("QQQ", "SCHD", "SPMO"), cfg)
    assert set(d.year) == set(range(1, cfg["investor"]["horizon_years"] + 1))

    def gap(scenario, rule, year):
        row = d[(d.scenario == scenario) & (d.rule == rule) & (d.year == year)]
        return float(row.median_weight_gap.iloc[0])

    # with contributions continuing, R1 stays closer to target than no rule
    assert gap("A_unchanged_1.0", "R1_contribution_only", 20) < \
           gap("A_unchanged_1.0", "R0_none", 20)
    # once contributions stop, R1 drifts far more than it did with them
    assert gap("D_none_0.0", "R1_contribution_only", 20) > \
           gap("A_unchanged_1.0", "R1_contribution_only", 20)
    # a band rule keeps the gap small in every scenario
    for scen in ("A_unchanged_1.0", "D_none_0.0"):
        assert gap(scen, "R3_band_20pct", 20) < 0.05
        assert gap(scen, "R2_annual", 20) < 0.05


def test_contribution_only_crosses_the_drift_threshold_only_when_cash_stops(eng, cfg):
    d = investor.weight_drift_path(eng, ("QQQ", "SCHD", "SPMO"), cfg)
    first = d.groupby(["scenario", "rule"]).first_year_above_threshold.first()
    # 0 means "never crossed"
    assert first[("A_unchanged_1.0", "R1_contribution_only")] == 0
    for scen in ("B_half_0.5", "C_quarter_0.25", "D_none_0.0"):
        assert first[(scen, "R1_contribution_only")] > 0
    for scen in ("A_unchanged_1.0", "D_none_0.0"):
        assert first[(scen, "R2_annual")] == 0
        assert first[(scen, "R3_band_20pct")] == 0
