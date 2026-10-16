"""Walk-forward backtest: at each rebalance point, estimate the covariance
(and, where needed, expected returns) from a trailing window that ends
*strictly before* that point, apply the resulting weights to the realized
returns of the next holding period, charge a transaction cost on turnover,
and roll forward. No step ever uses information that would not have been
available on the decision date — this is the out-of-sample check that the
Phase 0 in-sample weights (docs/methodology.md) explicitly could not make.

Confidence intervals come from a block bootstrap over the sequence of
realized holding-period returns, not from a single point estimate — a
method that happened to win on one 5-year history is not evidence it will
keep winning, and with ~45-50 holding periods, differences between methods
are mostly not statistically distinguishable (see scripts/run_backtest.py
output and docs/methodology.md § Phase 1).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class BacktestResult:
    method: str
    dates: list              # rebalance dates (period start)
    weights: list             # list of np.ndarray, one per period
    period_returns: np.ndarray   # gross log-return realized over each holding period
    turnover: np.ndarray         # sum(|w_new - w_old|) at each rebalance
    cost: np.ndarray             # turnover * cost_bps / 1e4, charged against that period's return
    net_period_returns: np.ndarray = field(init=False)

    def __post_init__(self):
        self.net_period_returns = self.period_returns - self.cost

    def equity_curve(self) -> np.ndarray:
        return np.exp(np.cumsum(self.net_period_returns))

    def annualized_return(self, periods_per_year: float) -> float:
        total_log_ret = self.net_period_returns.sum()
        years = len(self.net_period_returns) / periods_per_year
        return float(np.expm1(total_log_ret / years))

    def annualized_vol(self, periods_per_year: float) -> float:
        return float(self.net_period_returns.std(ddof=1) * np.sqrt(periods_per_year))

    def sharpe(self, rf: float, periods_per_year: float) -> float:
        ret = self.annualized_return(periods_per_year)
        vol = self.annualized_vol(periods_per_year)
        return (ret - rf) / vol if vol > 0 else float("nan")

    def max_drawdown(self) -> float:
        """Peak-to-trough decline, anchored to a starting equity of 1.0
        *before* the first period — found to matter via a real discrepancy
        against quantstats on identical data (-4.33% here vs its -5.56%):
        this project's first out-of-sample period return is itself
        negative (-4.09%), and `np.maximum.accumulate` starting from
        `equity_curve()`'s first point (which has no entry *before* any
        return is applied) silently took that first value as its own
        running peak, so the loss that opened the whole track record
        never registered as a drawdown. Prepending the implicit 1.0
        start fixes this and matches quantstats on the same series
        (tests/test_backtest.py)."""
        curve = np.concatenate(([1.0], self.equity_curve()))
        running_max = np.maximum.accumulate(curve)
        drawdown = curve / running_max - 1.0
        return float(drawdown.min())

    def avg_turnover(self) -> float:
        return float(self.turnover.mean())

    def sortino_ratio(self, rf: float, periods_per_year: float, mar: float = 0.0) -> float:
        """Sortino & van der Meer (1991): like Sharpe, but the denominator
        only counts downside deviation (returns below `mar`, the minimum
        acceptable return — 0 by default, a common convention), so upside
        volatility — which investors don't experience as risk — isn't
        penalized the way plain Sharpe penalizes it. CFA Institute, "The
        Sortino Ratio" (rpc.cfainstitute.org)."""
        downside = np.minimum(self.net_period_returns - mar, 0.0)
        downside_dev = np.sqrt(np.mean(downside ** 2)) * np.sqrt(periods_per_year)
        ret = self.annualized_return(periods_per_year)
        return (ret - rf) / downside_dev if downside_dev > 0 else float("nan")

    def calmar_ratio(self, periods_per_year: float) -> float:
        """Annualized return / |max drawdown| — standard definition, see
        docs/methodology.md. Penalizes depth of loss specifically, unlike
        Sharpe/Sortino which penalize dispersion of returns."""
        mdd = self.max_drawdown()
        ret = self.annualized_return(periods_per_year)
        return ret / abs(mdd) if mdd != 0 else float("nan")

    def historical_var(self, alpha: float = 0.95) -> float:
        """Empirical (historical) VaR: the loss threshold not expected to
        be exceeded with probability `alpha`, estimated directly from the
        realized period-return distribution rather than assuming
        normality — appropriate given every return series examined in
        this project (§5) rejected normality. Reported as a negative
        number (a loss), consistent with `max_drawdown`'s sign convention."""
        return float(np.percentile(self.net_period_returns, 100 * (1 - alpha)))

    def cvar(self, alpha: float = 0.95) -> float:
        """Conditional VaR / Expected Shortfall: the average loss *given*
        that the VaR threshold is breached. Preferred over VaR for
        optimization/comparison because VaR isn't subadditive (it can
        penalize diversification) while CVaR is a coherent risk measure.
        With only a few dozen holding periods (see §5's small-sample
        caveat), this is estimated from very few tail observations —
        report it, but don't read more precision into it than a handful
        of data points can support."""
        var_threshold = self.historical_var(alpha)
        tail = self.net_period_returns[self.net_period_returns <= var_threshold]
        if len(tail) == 0:
            return var_threshold
        return float(tail.mean())


def walk_forward(
    log_returns: pd.DataFrame,
    weight_fn,
    *,
    window: int = 756,
    rebal_every: int = 21,
    cost_bps: float = 10.0,
    method_name: str = "method",
    drift_band: float | None = None,
) -> BacktestResult:
    """
    log_returns: DataFrame, rows = trading days (ascending), cols = tickers.
    weight_fn: callable(trailing_log_returns_df) -> np.ndarray of weights
        summing to 1. Receives ONLY `log_returns.iloc[start:i]` — the
        strictly-past window — never anything at or after position i.
    window: trading days of trailing history used to estimate each rebalance.
    rebal_every: trading days held before re-estimating and rebalancing.
    cost_bps: one-way transaction cost in basis points, applied to turnover.
    drift_band: if set, skip rebalancing at a given date when the proposed
        new target doesn't differ from the *actual, drifted* current
        holdings by more than this much on any single name — avoids
        trading on noise-level drift. None (default) always rebalances to
        the new target every `rebal_every` days.

    Turnover is computed against the actual drifted holdings at the start
    of each rebalance date, not the previous period's un-drifted target —
    a buy-and-hold position doesn't stay at its target weights between
    rebalances (a winner's weight rises on its own), so comparing a new
    target only to the stale old target understates real-world turnover.
    Found and fixed together with adding `drift_band` (the band logic
    needs real drift tracked anyway) — see docs/methodology.md for the
    effect size on previously-published turnover figures.
    """
    n_days, n_assets = log_returns.shape
    rebal_idx = list(range(window, n_days, rebal_every))
    if len(rebal_idx) < 2:
        raise ValueError(f"not enough history for window={window}, rebal_every={rebal_every}, n_days={n_days}")

    dates, weights_list, period_rets, turnovers, costs = [], [], [], [], []
    actual_weights = None  # drifted holdings carried from the end of the previous period
    for k, i in enumerate(rebal_idx):
        trailing = log_returns.iloc[i - window:i]
        target_w = np.asarray(weight_fn(trailing), dtype=float)
        assert abs(target_w.sum() - 1.0) < 1e-4, f"weights must sum to 1, got {target_w.sum()}"

        if drift_band is not None and actual_weights is not None and \
                np.abs(actual_weights - target_w).max() <= drift_band:
            w = actual_weights  # drift within band -- hold, don't trade
        else:
            w = target_w

        j = rebal_idx[k + 1] if k + 1 < len(rebal_idx) else n_days
        holding = log_returns.iloc[i:j]
        # simple (not log) per-asset holding-period return, then portfolio log-return
        simple_asset_ret = np.expm1(holding.sum(axis=0).values)
        port_simple_ret = float(w @ simple_asset_ret)
        port_log_ret = np.log1p(port_simple_ret)

        turnover = float(np.abs(w - actual_weights).sum()) if actual_weights is not None else float(np.abs(w).sum())
        cost = turnover * cost_bps / 1e4

        # drift the just-used weights forward through the holding period's
        # realized returns -- this (not `w` itself) is what's actually held
        # going into the next rebalance decision
        drifted = w * (1 + simple_asset_ret)
        drifted_sum = drifted.sum()
        actual_weights = drifted / drifted_sum if drifted_sum != 0 else w

        dates.append(log_returns.index[i])
        weights_list.append(w)
        period_rets.append(port_log_ret)
        turnovers.append(turnover)
        costs.append(cost)

    return BacktestResult(
        method=method_name,
        dates=dates,
        weights=weights_list,
        period_returns=np.array(period_rets),
        turnover=np.array(turnovers),
        cost=np.array(costs),
    )


def block_bootstrap_ci(
    period_returns: np.ndarray,
    *,
    periods_per_year: float,
    n_boot: int = 2000,
    block_size: int = 3,
    ci: float = 0.90,
    seed: int = 0,
) -> dict:
    """Block bootstrap (overlapping blocks of `block_size` consecutive
    periods, to partially preserve autocorrelation) over the realized
    holding-period returns. Returns a CI for annualized return and Sharpe.
    Deterministic given `seed` — recorded so every number here can be
    regenerated exactly.
    """
    rng = np.random.default_rng(seed)
    n = len(period_returns)
    if n < block_size * 3:
        raise ValueError(f"too few periods ({n}) to block-bootstrap with block_size={block_size}")

    n_blocks_needed = int(np.ceil(n / block_size))
    boot_ann_rets = np.empty(n_boot)
    boot_sharpes = np.empty(n_boot)
    for b in range(n_boot):
        starts = rng.integers(0, n - block_size + 1, size=n_blocks_needed)
        sample = np.concatenate([period_returns[s:s + block_size] for s in starts])[:n]
        years = n / periods_per_year
        ann_ret = np.expm1(sample.sum() / years)
        vol = sample.std(ddof=1) * np.sqrt(periods_per_year)
        boot_ann_rets[b] = ann_ret
        boot_sharpes[b] = ann_ret / vol if vol > 0 else np.nan

    alpha = (1 - ci) / 2
    return {
        "ann_return_point": float(np.expm1(period_returns.sum() / (n / periods_per_year))),
        "ann_return_ci": (float(np.nanpercentile(boot_ann_rets, 100 * alpha)),
                          float(np.nanpercentile(boot_ann_rets, 100 * (1 - alpha)))),
        "sharpe_ci": (float(np.nanpercentile(boot_sharpes, 100 * alpha)),
                      float(np.nanpercentile(boot_sharpes, 100 * (1 - alpha)))),
        "n_periods": n,
        "n_boot": n_boot,
        "block_size": block_size,
        "seed": seed,
    }
