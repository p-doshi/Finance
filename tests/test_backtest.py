import numpy as np
import pandas as pd
import pytest

from portfolio_pipeline.research.backtest import walk_forward, block_bootstrap_ci, BacktestResult
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


def test_turnover_reflects_real_drift_even_with_a_constant_target():
    """A constant equal-weight TARGET still has real turnover every period:
    the portfolio drifts away from equal-weight during each holding period
    (different assets have different returns), and rebalancing back to the
    target requires actually trading that drift away. Turnover is
    computed against the drifted holdings, not the stale prior target --
    verified directly against a hand-computed drift for period 2, not just
    'it's nonzero'."""
    data = _synthetic_returns()
    w = equal_weight(N_ASSETS)
    res = walk_forward(data, _constant_weight_fn(w), window=252, rebal_every=21)
    assert res.turnover[0] == pytest.approx(1.0, abs=1e-6)  # period 0: vs. implicit all-cash start
    assert np.all(res.turnover[1:] > 0)  # real drift every period after -> real turnover

    # hand-check period 1's turnover: drift period 0's equal weights through
    # period 0's realized per-asset returns, compare to period 1's target (= w again)
    i0 = res.dates[0]
    idx0 = data.index.get_loc(i0)
    idx1 = data.index.get_loc(res.dates[1])
    holding0 = data.iloc[idx0:idx1]
    simple_ret0 = np.expm1(holding0.sum(axis=0).values)
    drifted = w * (1 + simple_ret0)
    drifted /= drifted.sum()
    expected_turnover1 = np.abs(w - drifted).sum()
    assert res.turnover[1] == pytest.approx(expected_turnover1, abs=1e-8)


def test_drift_band_suppresses_rebalancing_within_the_band():
    """The actual point of drift_band: if the drifted holdings haven't
    moved far from the (constant) target, don't trade at all -- turnover
    should drop to zero once the band is wide enough to tolerate the real
    drift this data produces."""
    data = _synthetic_returns()
    w = equal_weight(N_ASSETS)
    no_band = walk_forward(data, _constant_weight_fn(w), window=252, rebal_every=21)
    max_drift_seen = no_band.turnover[1:].max()  # generous upper bound on any single period's drift

    wide_band = walk_forward(data, _constant_weight_fn(w), window=252, rebal_every=21,
                              drift_band=max_drift_seen + 1.0)
    assert wide_band.turnover[0] == pytest.approx(1.0, abs=1e-6)  # still must enter the position initially
    assert np.allclose(wide_band.turnover[1:], 0.0, atol=1e-8)  # never worth trading given the band
    # holding the drifted (not reset) weights should change the realized returns
    # versus always-rebalance -- a real, checkable difference, not just zero turnover
    assert not np.allclose(wide_band.period_returns, no_band.period_returns)


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


def _result(period_returns):
    period_returns = np.array(period_returns)
    n = len(period_returns)
    return BacktestResult(method="test", dates=list(range(n)), weights=[np.array([1.0])] * n,
                           period_returns=period_returns, turnover=np.zeros(n), cost=np.zeros(n))


def test_max_drawdown_counts_a_loss_in_the_very_first_period():
    """The actual bug found cross-checking against quantstats on real
    data (docs/methodology.md): a loss in the first period must register
    as a drawdown from the implicit starting equity of 1.0, not get
    silently absorbed because `np.maximum.accumulate` starting from the
    post-first-period value took that value as its own peak. Here, the
    only loss is period 1 (-10%); if it isn't counted, max_drawdown would
    wrongly come back as 0 once the series recovers above its start."""
    rets = [np.log(0.90), np.log(1.02), np.log(1.03), np.log(1.01)]  # -10%, then all gains
    res = _result(rets)
    assert res.max_drawdown() == pytest.approx(-0.10, abs=1e-9)


def test_max_drawdown_known_multi_period_case():
    # +20%, -30%, +10%: trough is 1.20 * 0.70 = 0.84 -> drawdown from peak 1.20 is (0.84/1.20 - 1) = -30%
    rets = [np.log(1.20), np.log(0.70), np.log(1.10)]
    res = _result(rets)
    assert res.max_drawdown() == pytest.approx(-0.30, abs=1e-9)


def test_max_drawdown_matches_quantstats_on_identical_series():
    """Pinned to the exact real discrepancy found: quantstats computed
    -0.055637515839061846 on this project's actual risk-parity walk-forward
    log-returns, where this project's own max_drawdown() was returning
    -0.0433 before the fix. Hardcoding the real log-return series here
    (res.net_period_returns, not the simple/expm1-converted values shown
    in the tearsheet) so this doesn't silently regress without needing
    live data or quantstats installed."""
    rets = [-0.041746820561121764, -0.009294543513022238, -0.0062038350081886125,
            0.04354710127074744, -0.014681588213113, -0.007334379667662257,
            0.026198768329029943, 0.01378992119057157, 0.019230172100709444,
            0.016856516153524542, 0.016752116672622372, 0.011477621328044828,
            0.0013560601707369156, 0.015060993563746862, 0.0696044914138206,
            0.07933732334643695, -0.04428407304629001, 0.012026654560575858,
            0.026902602855007646, 0.012101898965234583, 0.02783418995412101,
            0.02022563391329936, -0.025755446467769613, 0.01353223501623073]
    res = _result(rets)
    assert res.max_drawdown() == pytest.approx(-0.055637515839061846, abs=1e-9)


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
