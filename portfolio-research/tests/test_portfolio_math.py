"""Portfolio-arithmetic tests (SC-18, portfolio-math section)."""
from __future__ import annotations

import numpy as np
import pytest

from src import metrics
from src.portfolio import rolling_windows, simulate, water_fill


def const(returns, months, n_start=1):
    """(S, H, K) array of constant per-asset returns."""
    r = np.asarray(returns, dtype=float)
    return np.tile(r, (n_start, months, 1))


# --------------------------------------------------------------------------
# compounding and contribution accounting
# --------------------------------------------------------------------------
def test_deterministic_compounding():
    res = simulate(const([0.01], 120), np.array([1.0]), rule="R0", initial=1.0)
    assert res.terminal_wealth[0] == pytest.approx(1.01 ** 120)
    assert metrics.cagr(res.total)[0] == pytest.approx(1.01 ** 12 - 1)


def test_contribution_accounting_zero_returns():
    H = 36
    res = simulate(const([0.0], H), np.array([1.0]), rule="R0",
                   contributions=np.ones((1, H)), initial=0.0)
    assert res.contributed[0] == pytest.approx(H)
    assert res.terminal_wealth[0] == pytest.approx(H)


def test_contribution_timing_begin_vs_end():
    """A deposit made at the start of a month must earn that month's return."""
    H = 1
    R = const([0.10], H)
    begin = simulate(R, np.array([1.0]), rule="R0", contributions=np.ones((1, H)),
                     initial=0.0, contribution_timing="begin")
    end = simulate(R, np.array([1.0]), rule="R0", contributions=np.ones((1, H)),
                   initial=0.0, contribution_timing="end")
    assert begin.terminal_wealth[0] == pytest.approx(1.10)
    assert end.terminal_wealth[0] == pytest.approx(1.00)


def test_no_look_ahead_last_month_return_is_used_once():
    """Changing only the final month's return changes wealth by exactly that
    month's factor -- i.e. no earlier decision could have seen it."""
    H = 12
    base = const([0.0, 0.0], H, 1)
    a = base.copy()
    b = base.copy()
    b[0, -1, 0] = 0.5
    w = np.array([0.5, 0.5])
    ta = simulate(a, w, rule="R2").terminal_wealth[0]
    tb = simulate(b, w, rule="R2").terminal_wealth[0]
    assert tb - ta == pytest.approx(0.5 * 0.5)


# --------------------------------------------------------------------------
# drawdown / risk
# --------------------------------------------------------------------------
def test_known_drawdown():
    path = np.array([[1.0, 1.5, 0.75, 1.2]])
    assert metrics.max_drawdown(path)[0] == pytest.approx(-0.5)


def test_underwater_duration():
    path = np.array([[1.0, 2.0, 1.0, 1.5, 1.9, 2.5]])
    assert metrics.underwater_months(path)[0] == 3


def test_volatility_and_downside_deviation():
    r = np.array([[0.02, -0.02, 0.02, -0.02] * 3])
    assert metrics.annualised_vol(r)[0] == pytest.approx(
        np.std(r[0], ddof=1) * np.sqrt(12))
    # only the negative months count towards downside deviation
    assert metrics.downside_deviation(r)[0] == pytest.approx(
        np.sqrt(np.mean(np.minimum(r[0], 0) ** 2)) * np.sqrt(12))


# --------------------------------------------------------------------------
# water filling / contribution-only rebalancing
# --------------------------------------------------------------------------
def test_water_fill_conserves_money_and_never_sells():
    rng = np.random.default_rng(0)
    v = rng.random((200, 4)) * 10
    w = np.array([0.4, 0.3, 0.2, 0.1])
    cash = rng.random(200) * 5
    out = water_fill(v, w, cash)
    assert np.allclose(out.sum(axis=1), v.sum(axis=1) + cash)
    assert np.all(out >= v - 1e-9)          # nothing was ever sold


def test_water_fill_reaches_target_when_cash_is_ample():
    v = np.array([[10.0, 0.0]])
    w = np.array([0.5, 0.5])
    out = water_fill(v, w, np.array([90.0]))
    assert out[0] == pytest.approx([50.0, 50.0])


def test_water_fill_minimises_weight_gap():
    """The water-fill allocation beats any other no-sell allocation."""
    v = np.array([[8.0, 1.0, 1.0]])
    w = np.array([1 / 3, 1 / 3, 1 / 3])
    cash = 6.0
    best = water_fill(v, w, np.array([cash]))[0]

    def gap(x):
        return 0.5 * np.abs(x / x.sum() - w).sum()

    rng = np.random.default_rng(1)
    for _ in range(3000):
        add = rng.random(3)
        add = add / add.sum() * cash
        assert gap(v[0] + add) >= gap(best) - 1e-12


def test_r1_never_sells():
    rng = np.random.default_rng(2)
    H = 60
    R = rng.normal(0.01, 0.06, size=(1, H, 3))
    res = simulate(R, np.array([0.5, 0.3, 0.2]), rule="R1",
                   contributions=np.ones((1, H)), initial=1.0)
    assert res.sold[0] == 0.0
    assert res.rebalance_events[0] == 0


# --------------------------------------------------------------------------
# annual and band rebalancing
# --------------------------------------------------------------------------
def test_annual_rebalance_restores_target_weights():
    """After the annual restore month the weights are exactly on target."""
    H = 13
    R = np.zeros((1, H, 2))
    R[0, :, 0] = 0.20          # asset 0 races ahead for a year
    res = simulate(R, np.array([0.5, 0.5]), rule="R2", annual_month_offset=0)
    # month 12 (the second rebalance) restores before that month's return
    v = res.holdings[0] / (1 + np.array([0.20, 0.0]))
    assert v[0] / v.sum() == pytest.approx(0.5)


def test_annual_rebalance_hand_computed():
    """Two assets, +20%/0% for 12 months, then restore, then one more month."""
    H = 13
    R = np.zeros((1, H, 2))
    R[0, :, 0] = 0.20
    res = simulate(R, np.array([0.5, 0.5]), rule="R2", annual_month_offset=0)
    a, b = 0.5 * 1.2 ** 12, 0.5
    total_after_12 = a + b
    expected = total_after_12 * (0.5 * 1.2 + 0.5 * 1.0)
    assert res.terminal_wealth[0] == pytest.approx(expected)


def test_band_rebalance_triggers_only_outside_the_band():
    w = np.array([0.5, 0.5])
    # +15% on one asset -> weights 53.5/46.5; a +-20% relative band is 40-60%
    R = np.zeros((1, 2, 2))
    R[0, 0, 0] = 0.15
    inside = simulate(R, w, rule="R3", band=0.20)
    assert inside.sold[0] == 0.0
    # a +-5% relative band is 47.5-52.5 -> breached
    outside = simulate(R, w, rule="R3", band=0.05)
    assert outside.sold[0] > 0.0
    assert outside.rebalance_events[0] == 1


def test_band_rebalance_restores_exactly_to_target():
    R = np.zeros((1, 2, 2))
    R[0, 0, 0] = 1.0           # asset 0 doubles in month 0
    res = simulate(R, np.array([0.5, 0.5]), rule="R3", band=0.0)
    assert res.holdings[0][0] / res.holdings[0].sum() == pytest.approx(0.5)


# --------------------------------------------------------------------------
# the Shannon rebalancing example
# --------------------------------------------------------------------------
def test_shannon_alternating_returns():
    """A zero-CAGR volatile asset plus zero-return cash compounds when
    rebalanced, and does not when left alone."""
    H = 12
    R = np.zeros((1, H, 2))
    R[0, 0::2, 0] = 1.0        # +100%
    R[0, 1::2, 0] = -0.5       # -50%   (asset CAGR is exactly zero)
    w = np.array([0.5, 0.5])

    rebalanced = simulate(R, w, rule="R3", band=0.0).terminal_wealth[0]
    buy_and_hold = simulate(R, w, rule="R0").terminal_wealth[0]

    assert rebalanced == pytest.approx(1.125 ** 6)
    assert buy_and_hold == pytest.approx(1.0)
    assert rebalanced > buy_and_hold


# --------------------------------------------------------------------------
# rolling window construction
# --------------------------------------------------------------------------
def test_rolling_windows_shape_and_content():
    R = np.arange(24, dtype=float).reshape(12, 2)
    W = rolling_windows(R, 5)
    assert W.shape == (8, 5, 2)
    assert np.allclose(W[0], R[0:5])
    assert np.allclose(W[-1], R[7:12])


def test_rolling_windows_too_short():
    assert rolling_windows(np.zeros((3, 2)), 5).shape[0] == 0


# --------------------------------------------------------------------------
# guards
# --------------------------------------------------------------------------
def test_weights_must_sum_to_one():
    with pytest.raises(ValueError):
        simulate(const([0.0, 0.0], 3), np.array([0.5, 0.4]))


def test_nan_returns_rejected():
    R = const([0.0], 3)
    R[0, 1, 0] = np.nan
    with pytest.raises(ValueError):
        simulate(R, np.array([1.0]))


def test_turnover_and_contribution_share():
    """When deposits are small relative to the portfolio, bands eventually
    force sales, and the contribution share of rebalancing is a fraction."""
    H = 24
    R = np.zeros((1, H, 2))
    R[0, :, 0] = 0.05
    res = simulate(R, np.array([0.5, 0.5]), rule="R3", band=0.10,
                   contributions=np.ones((1, H)), initial=1000.0)
    assert res.sold[0] > 0
    assert 0.0 < res.contrib_share_of_rebalancing[0] < 1.0
    assert res.turnover_annual[0] > 0


def test_large_contributions_remove_the_need_to_sell():
    """A big enough deposit stream keeps a banded portfolio on target without
    ever selling -- the mechanism SC-10/R1 is about."""
    H = 24
    R = np.zeros((1, H, 2))
    R[0, :, 0] = 0.05
    res = simulate(R, np.array([0.5, 0.5]), rule="R3", band=0.10,
                   contributions=np.ones((1, H)), initial=1.0)
    assert res.sold[0] == 0.0
    assert res.contrib_share_of_rebalancing[0] == pytest.approx(1.0)


# --------------------------------------------------------------------------
# rule-degeneracy invariants (SC-19: "different rules give identical results")
# --------------------------------------------------------------------------
def test_wide_band_degenerates_to_contribution_only():
    """A band that is never breached must make R3 numerically equal to R1 --
    identical results are only acceptable when the mechanism explains them."""
    rng = np.random.default_rng(7)
    H = 120
    R = rng.normal(0.006, 0.03, size=(30, H, 2))
    w = np.array([0.5, 0.5])
    c = np.ones((30, H))
    wide = simulate(R, w, rule="R3", band=5.0, contributions=c, initial=1.0)
    r1 = simulate(R, w, rule="R1", contributions=c, initial=1.0)
    assert wide.rebalance_events.sum() == 0
    assert np.allclose(wide.terminal_wealth, r1.terminal_wealth)


def test_single_asset_rules_are_all_identical():
    rng = np.random.default_rng(8)
    R = rng.normal(0.006, 0.04, size=(5, 60, 1))
    c = np.ones((5, 60))
    tws = [simulate(R, np.array([1.0]), rule=r, contributions=c,
                    initial=1.0).terminal_wealth for r in ("R0", "R1", "R2", "R3")]
    for t in tws[1:]:
        assert np.allclose(t, tws[0])


def test_zero_band_rebalances_every_month():
    rng = np.random.default_rng(9)
    H = 24
    R = rng.normal(0.005, 0.03, size=(3, H, 3))
    res = simulate(R, np.full(3, 1 / 3), rule="R3", band=0.0)
    # month 0 starts exactly on target, so there is nothing to correct yet
    assert (res.rebalance_events == H - 1).all()


# --------------------------------------------------------------------------
# systematic no-look-ahead check across every rule
# --------------------------------------------------------------------------
@pytest.mark.parametrize("rule", ["R0", "R1", "R2", "R3"])
@pytest.mark.parametrize("timing", ["begin", "end"])
def test_no_state_before_month_t_depends_on_month_t(rule, timing):
    """Perturbing one month's returns must leave every earlier month-end value
    bit-for-bit identical, whatever the rebalancing rule."""
    rng = np.random.default_rng(11)
    H, T = 36, 18
    R = rng.normal(0.006, 0.04, size=(4, H, 3))
    w = np.array([0.5, 0.3, 0.2])
    c = np.ones((4, H))
    kw = dict(rule=rule, contributions=c, initial=1.0, band=0.15,
              contribution_timing=timing)
    base = simulate(R, w, **kw)
    bumped = R.copy()
    bumped[:, T, :] += 0.25
    after = simulate(bumped, w, **kw)
    assert np.array_equal(base.total[:, :T + 1], after.total[:, :T + 1])
    assert not np.allclose(base.total[:, T + 1], after.total[:, T + 1])
