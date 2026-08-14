"""Portfolio simulation engine.

Everything is vectorised across *start dates*: a call simulates every rolling
window of a given horizon at once.  ``V`` always has shape ``(S, K)`` -- S
start dates by K assets -- and one loop iteration advances every window by one
month of its own calendar time.

Monthly event order (config ``timing.contribution_timing = begin``):

    1. observe the portfolio left over from the previous month
    2. deposit this month's contribution
    3. apply the rebalancing rule that is permitted this month
    4. this month's returns happen
    5. record the month-end state

Step 3 never sees step 4's returns, so no rule can use information from inside
its own month.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

RULES = ("R0", "R1", "R2", "R3")


@dataclass
class SimResult:
    """Output of :func:`simulate` for S parallel rolling windows."""

    total: np.ndarray            # (S, H+1) portfolio value at each month end
    holdings: np.ndarray         # (S, K) final per-asset values
    contributed: np.ndarray      # (S,) cumulative nominal contributions
    sold: np.ndarray             # (S,) cumulative currency amount sold
    bought_with_contrib: np.ndarray   # (S,) cumulative deposits invested
    rebalance_events: np.ndarray      # (S,) months in which assets were sold
    weight_gap_sum: np.ndarray        # (S,) sum over months of L1/2 weight gap
    gap_closed_by_contrib: np.ndarray  # (S,) weight gap removed by deposits
    gap_closed_by_sales: np.ndarray    # (S,) weight gap removed by selling
    n_months: int = 0
    meta: dict = field(default_factory=dict)

    # ---- convenience -----------------------------------------------------
    @property
    def terminal_wealth(self) -> np.ndarray:
        return self.total[:, -1]

    @property
    def monthly_returns(self) -> np.ndarray:
        """Only meaningful when the run had no cash flows."""
        return self.total[:, 1:] / self.total[:, :-1] - 1.0

    @property
    def mean_weight_gap(self) -> np.ndarray:
        return self.weight_gap_sum / max(self.n_months, 1)

    @property
    def turnover_annual(self) -> np.ndarray:
        """One-way turnover (sales / average portfolio value), annualised."""
        avg_value = self.total[:, 1:].mean(axis=1)
        years = self.n_months / 12.0
        return np.where(avg_value > 0, self.sold / avg_value / years, 0.0)

    @property
    def contrib_share_of_rebalancing(self) -> np.ndarray:
        """Share of all weight correction that deposits alone achieved."""
        denom = self.gap_closed_by_contrib + self.gap_closed_by_sales
        return np.where(denom > 0, self.gap_closed_by_contrib / denom, np.nan)


# --------------------------------------------------------------------------
# allocation primitives
# --------------------------------------------------------------------------
def water_fill(v: np.ndarray, w: np.ndarray, cash: np.ndarray) -> np.ndarray:
    """Add ``cash`` to ``v`` so the result is as close to weights ``w`` as
    possible **without selling anything**.

    The solution is ``v'_k = max(v_k, lambda * w_k)`` for the unique ``lambda``
    that makes ``sum(v') == sum(v) + cash``: money flows only into the assets
    that are below the common funding level, deepest shortfall first.

    Parameters
    ----------
    v : (S, K) current values, non-negative.
    w : (K,) target weights, strictly positive, summing to 1.
    cash : (S,) non-negative amount to invest.
    """
    v = np.asarray(v, dtype=float)
    w = np.asarray(w, dtype=float)
    cash = np.asarray(cash, dtype=float).reshape(-1)
    if np.any(w <= 0):
        raise ValueError("water_fill requires strictly positive target weights")
    if np.any(cash < -1e-12):
        raise ValueError("water_fill cannot invest a negative amount")

    ratio = v / w                                  # (S, K) funding level per asset
    order = np.argsort(ratio, axis=1, kind="stable")
    r_sorted = np.take_along_axis(ratio, order, axis=1)
    v_sorted = np.take_along_axis(v, order, axis=1)
    w_sorted = np.broadcast_to(w, v.shape)
    w_sorted = np.take_along_axis(w_sorted, order, axis=1)

    v_cum = np.cumsum(v_sorted, axis=1)
    w_cum = np.cumsum(w_sorted, axis=1)
    lam_j = (v_cum + cash[:, None]) / w_cum        # candidate level if the j
                                                   # cheapest assets are topped up
    upper = np.concatenate(
        [r_sorted[:, 1:], np.full((v.shape[0], 1), np.inf)], axis=1)
    feasible = lam_j <= upper + 1e-12
    j = np.argmax(feasible, axis=1)                # first feasible break point
    lam = lam_j[np.arange(v.shape[0]), j]

    out = np.maximum(v, lam[:, None] * w[None, :])
    # Guard against float drift: the total must be exactly what went in.
    target_total = v.sum(axis=1) + cash
    scale = np.where(out.sum(axis=1) > 0, target_total / out.sum(axis=1), 1.0)
    return out * scale[:, None]


def _weight_gap(v: np.ndarray, w: np.ndarray) -> np.ndarray:
    """Half the L1 distance between actual and target weights, per window."""
    total = v.sum(axis=1, keepdims=True)
    actual = np.divide(v, total, out=np.zeros_like(v), where=total > 0)
    return 0.5 * np.abs(actual - w[None, :]).sum(axis=1)


# --------------------------------------------------------------------------
# the simulator
# --------------------------------------------------------------------------
def simulate(
    returns: np.ndarray,
    weights: np.ndarray,
    rule: str = "R2",
    contributions: np.ndarray | None = None,
    initial: float = 1.0,
    annual_month_offset: int = 0,
    band: float = 0.20,
    contribution_timing: str = "begin",
) -> SimResult:
    """Simulate S rolling windows of a K-asset portfolio.

    Parameters
    ----------
    returns : (S, H, K) simple monthly returns.
    weights : (K,) target weights, positive, summing to 1.
    rule :
        ``R0`` deposits at target weights, never sells.
        ``R1`` deposits are water-filled into underweights, never sells.
        ``R2`` deposits at target weights, plus a full restore once a year.
        ``R3`` deposits are water-filled, plus a full restore whenever any
               asset breaches its relative band.
    contributions : (S, H) nominal deposit at the start of each month.
    initial : lump sum invested at target weights before month 0.
    annual_month_offset : month index within the window at which R2 rebalances
        (0 = the window's first month, then every 12 months).
    band : relative band for R3 (0.20 -> a 20% target may sit in 16%-24%).
    contribution_timing : ``begin`` (deposit earns the month's return) or
        ``end`` (deposit lands after the return, sensitivity test).
    """
    if rule not in RULES:
        raise ValueError(f"unknown rule {rule!r}")
    R = np.asarray(returns, dtype=float)
    if R.ndim != 3:
        raise ValueError("returns must have shape (S, H, K)")
    S, H, K = R.shape
    w = np.asarray(weights, dtype=float)
    if w.shape != (K,):
        raise ValueError("weights must have shape (K,)")
    if not np.isclose(w.sum(), 1.0):
        raise ValueError("weights must sum to 1")
    if np.any(w <= 0):
        raise ValueError("zero-weight assets must be dropped before simulating")
    if not np.isfinite(R).all():
        raise ValueError("returns contain NaN/inf")

    C = (np.zeros((S, H)) if contributions is None
         else np.asarray(contributions, dtype=float))
    if C.shape != (S, H):
        raise ValueError("contributions must have shape (S, H)")

    V = np.tile(initial * w, (S, 1))
    total = np.zeros((S, H + 1))
    total[:, 0] = V.sum(axis=1)

    contributed = np.zeros(S)
    sold = np.zeros(S)
    bought = np.zeros(S)
    events = np.zeros(S)
    gap_sum = np.zeros(S)
    gap_contrib = np.zeros(S)
    gap_sales = np.zeros(S)

    lo, hi = w * (1.0 - band), w * (1.0 + band)

    for m in range(H):
        cash = C[:, m]
        if contribution_timing == "begin":
            gap_before = _weight_gap(V, w) if (V.sum(axis=1) > 0).any() else np.zeros(S)

            # ---- step 2/3: deposit, then the permitted rebalancing rule ----
            if rule in ("R0", "R2"):
                V = V + cash[:, None] * w[None, :]
            else:                                   # R1, R3: contribution first
                V = water_fill(V, w, cash)
            contributed += cash
            bought += cash
            gap_after_contrib = _weight_gap(V, w)
            gap_contrib += np.maximum(gap_before - gap_after_contrib, 0.0)

            if rule == "R2":
                due = (m % 12) == (annual_month_offset % 12)
                if due:
                    V, s, n = _restore(V, w, np.ones(S, dtype=bool))
                    sold += s
                    events += n
                    gap_sales += np.maximum(gap_after_contrib - _weight_gap(V, w), 0.0)
            elif rule == "R3":
                tot = V.sum(axis=1, keepdims=True)
                aw = np.divide(V, tot, out=np.zeros_like(V), where=tot > 0)
                breach = ((aw < lo[None, :] - 1e-12) |
                          (aw > hi[None, :] + 1e-12)).any(axis=1)
                if breach.any():
                    V, s, n = _restore(V, w, breach)
                    sold += s
                    events += n
                    gap_sales += np.maximum(gap_after_contrib - _weight_gap(V, w), 0.0)

            gap_sum += _weight_gap(V, w)
            V = V * (1.0 + R[:, m, :])
        else:                                       # deposit at month end
            gap_sum += _weight_gap(V, w)
            V = V * (1.0 + R[:, m, :])
            if rule in ("R0", "R2"):
                V = V + cash[:, None] * w[None, :]
            else:
                V = water_fill(V, w, cash)
            contributed += cash
            bought += cash
            if rule == "R2" and (m % 12) == (annual_month_offset % 12):
                V, s, n = _restore(V, w, np.ones(S, dtype=bool))
                sold += s
                events += n
            elif rule == "R3":
                tot = V.sum(axis=1, keepdims=True)
                aw = np.divide(V, tot, out=np.zeros_like(V), where=tot > 0)
                breach = ((aw < lo[None, :] - 1e-12) |
                          (aw > hi[None, :] + 1e-12)).any(axis=1)
                if breach.any():
                    V, s, n = _restore(V, w, breach)
                    sold += s
                    events += n

        total[:, m + 1] = V.sum(axis=1)

    return SimResult(
        total=total, holdings=V, contributed=contributed, sold=sold,
        bought_with_contrib=bought, rebalance_events=events,
        weight_gap_sum=gap_sum, gap_closed_by_contrib=gap_contrib,
        gap_closed_by_sales=gap_sales, n_months=H,
        meta={"rule": rule, "band": band, "weights": w.tolist(),
              "contribution_timing": contribution_timing},
    )


def _restore(V: np.ndarray, w: np.ndarray, mask: np.ndarray):
    """Set the masked windows back to exactly the target weights."""
    tot = V.sum(axis=1, keepdims=True)
    target = tot * w[None, :]
    new = np.where(mask[:, None], target, V)
    sells = np.where(mask[:, None], np.maximum(V - target, 0.0), 0.0).sum(axis=1)
    n = mask.astype(float) * (sells > 1e-12)
    return new, sells, n


# --------------------------------------------------------------------------
# window construction
# --------------------------------------------------------------------------
def rolling_windows(returns: np.ndarray, horizon: int) -> np.ndarray:
    """(T, K) monthly returns -> (S, H, K) rolling windows, S = T-H+1."""
    R = np.asarray(returns, dtype=float)
    T, K = R.shape
    if horizon > T:
        return np.empty((0, horizon, K))
    view = np.lib.stride_tricks.sliding_window_view(R, horizon, axis=0)
    return np.ascontiguousarray(view.transpose(0, 2, 1))
