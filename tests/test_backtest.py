import numpy as np
import pandas as pd
import pytest

from portfolio_pipeline.research.backtest import walk_forward, block_bootstrap_ci
from portfolio_pipeline.research.optimizers import equal_weight, min_variance_weight

RNG = np.random.default_rng(42)
N_ASSETS = 4
N_DAYS = 1000
TICKERS = [f"A{i}" for i in range(N_ASSETS)]


def _synthetic_returns(n_days=N_DAYS, seed=42):
    rng = np.random.default_rng(seed)
    data = rng.normal(loc=0.0003, scale=0.01, size=(n_days, N_ASSETS))
    idx = pd.bdate_range("2020-01-01", periods=n_days)
    return pd.DataFrame(data, index=idx, columns=TICKERS)


def test_no_lookahead_weights_unaffected_by_future_data():
    """The whole point of a walk-forward backtest: a rebalance decision must
    be identical whether or not the future actually happened yet. Corrupt
    everything after day 500 with huge noise and check that every rebalance
    whose estimation window ends before day 500 produces the exact same
    weights either way."""
    base = _synthetic_returns()
    corrupted = base.copy()
    cutoff = 500
    # ~50x the base scale: clearly enough to change weights if it leaked into
    # the estimation window, but not so extreme it makes the covariance
    # matrix numerically pathological for the solver (that would conflate a
    # solver-robustness issue with the lookahead check this test is for).
    corrupted.iloc[cutoff:] = RNG.normal(loc=0.05, scale=0.5, size=corrupted.iloc[cutoff:].shape)

    res_base = walk_forward(base, min_variance_weight_wrapper, window=252, rebal_every=21)
    res_corrupt = walk_forward(corrupted, min_variance_weight_wrapper, window=252, rebal_every=21)

    for i, date in enumerate(res_base.dates):
        day_index = base.index.get_loc(date)
        # window is log_returns.iloc[day_index-252:day_index] -> last day used is
        # day_index-1, so it's untouched by the corruption iff day_index <= cutoff
        if day_index <= cutoff:
            np.testing.assert_allclose(res_base.weights[i], res_corrupt.weights[i], atol=1e-8)


def min_variance_weight_wrapper(trailing_df: pd.DataFrame) -> np.ndarray:
    cov = trailing_df.cov().values * 252
    return min_variance_weight(cov)


def _constant_weight_fn(w):
    def fn(trailing_df):
        return w
    return fn


def test_turnover_zero_after_first_period_when_weights_constant():
    data = _synthetic_returns()
    w = equal_weight(N_ASSETS)
    res = walk_forward(data, _constant_weight_fn(w), window=252, rebal_every=21)
    # first rebalance: turnover vs an implicit all-cash start = sum(|w|) = 1
    assert res.turnover[0] == pytest.approx(1.0, abs=1e-6)
    # every subsequent rebalance: weights didn't change -> zero turnover
    assert np.allclose(res.turnover[1:], 0.0, atol=1e-8)


def test_cost_proportional_to_turnover_and_bps():
    data = _synthetic_returns()
    w = equal_weight(N_ASSETS)
    res_cheap = walk_forward(data, _constant_weight_fn(w), window=252, rebal_every=21, cost_bps=10.0)
    res_pricey = walk_forward(data, _constant_weight_fn(w), window=252, rebal_every=21, cost_bps=50.0)
    # cost is 5x bps -> cost should be exactly 5x at every rebalance
    np.testing.assert_allclose(res_pricey.cost, res_cheap.cost * 5, atol=1e-10)
    # and net return reflects that higher cost
    assert res_pricey.net_period_returns.sum() < res_cheap.net_period_returns.sum()


def test_weights_must_sum_to_one():
    data = _synthetic_returns()
    bad_fn = lambda trailing_df: np.array([0.5, 0.5, 0.5, 0.5])  # sums to 2
    with pytest.raises(AssertionError):
        walk_forward(data, bad_fn, window=252, rebal_every=21)


def test_equity_curve_matches_manual_compounding():
    data = _synthetic_returns()
    w = equal_weight(N_ASSETS)
    res = walk_forward(data, _constant_weight_fn(w), window=252, rebal_every=21, cost_bps=0.0)
    curve = res.equity_curve()
    manual = np.exp(np.cumsum(res.net_period_returns))
    np.testing.assert_allclose(curve, manual)
    assert curve[-1] == pytest.approx(np.exp(res.net_period_returns.sum()))


def test_not_enough_history_raises():
    data = _synthetic_returns(n_days=100)
    with pytest.raises(ValueError, match="not enough history"):
        walk_forward(data, _constant_weight_fn(equal_weight(N_ASSETS)), window=252, rebal_every=21)


def test_block_bootstrap_ci_reproducible_and_contains_point_estimate():
    period_returns = RNG.normal(loc=0.01, scale=0.03, size=48)
    r1 = block_bootstrap_ci(period_returns, periods_per_year=12, seed=7, n_boot=500)
    r2 = block_bootstrap_ci(period_returns, periods_per_year=12, seed=7, n_boot=500)
    assert r1 == r2  # same seed -> identical result
    lo, hi = r1["ann_return_ci"]
    assert lo < hi
    # point estimate should typically fall within or very near its own bootstrap CI
    assert lo - 0.5 < r1["ann_return_point"] < hi + 0.5


def test_block_bootstrap_rejects_too_few_periods():
    with pytest.raises(ValueError, match="too few periods"):
        block_bootstrap_ci(np.array([0.01, 0.02]), periods_per_year=12, block_size=3)
