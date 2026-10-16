import numpy as np
import pytest

from portfolio_pipeline.research.backtest import BacktestResult


def _result(period_returns):
    period_returns = np.array(period_returns)
    n = len(period_returns)
    return BacktestResult(
        method="test",
        dates=list(range(n)),
        weights=[np.array([1.0])] * n,
        period_returns=period_returns,
        turnover=np.zeros(n),
        cost=np.zeros(n),
    )


def test_sortino_ignores_pure_upside_volatility():
    """All returns at or above the minimum acceptable return (0) -> zero
    downside deviation -> Sortino is undefined (nan), not infinite or
    zero-division-wrong — this is the point of Sortino vs Sharpe: upside
    swings alone should never register as risk."""
    res = _result([0.05, 0.10, 0.0, 0.08, 0.02])
    assert np.isnan(res.sortino_ratio(rf=0.0, periods_per_year=12))


def test_sortino_known_value():
    # returns: +10%, -5%, +10%, -5% (log-ish, small enough to treat ~linearly for a hand check)
    rets = [0.10, -0.05, 0.10, -0.05]
    res = _result(rets)
    downside = np.minimum(np.array(rets) - 0.0, 0.0)
    expected_downside_dev = np.sqrt(np.mean(downside ** 2)) * np.sqrt(12)
    expected_ann_ret = res.annualized_return(12)
    expected_sortino = (expected_ann_ret - 0.0) / expected_downside_dev
    assert res.sortino_ratio(rf=0.0, periods_per_year=12) == pytest.approx(expected_sortino)


def test_sortino_respects_custom_mar():
    """A higher minimum-acceptable-return should count more periods as
    'downside' and therefore produce a lower (or equal) Sortino ratio."""
    rets = [0.03, 0.01, -0.02, 0.04, 0.0]
    res = _result(rets)
    s_mar0 = res.sortino_ratio(rf=0.0, periods_per_year=12, mar=0.0)
    s_mar_high = res.sortino_ratio(rf=0.0, periods_per_year=12, mar=0.02)
    assert s_mar_high < s_mar0


def test_calmar_known_value():
    # +20% then -50% then +10%: drawdown trough is well below the first peak
    rets = [np.log(1.20), np.log(0.50), np.log(1.10)]
    res = _result(rets)
    ann_ret = res.annualized_return(12)
    mdd = res.max_drawdown()
    assert res.calmar_ratio(periods_per_year=12) == pytest.approx(ann_ret / abs(mdd))
    assert mdd < 0  # sanity: a drawdown is recorded as negative


def test_calmar_nan_when_no_drawdown():
    rets = [0.01, 0.02, 0.01, 0.03]  # monotonically up -> max_drawdown == 0
    res = _result(rets)
    assert res.max_drawdown() == pytest.approx(0.0)
    assert np.isnan(res.calmar_ratio(periods_per_year=12))


def test_historical_var_known_percentile():
    rets = np.array([-0.10, -0.05, -0.02, 0.0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06])
    res = _result(rets)
    var95 = res.historical_var(alpha=0.95)
    assert var95 == pytest.approx(np.percentile(rets, 5))


def test_cvar_is_at_least_as_extreme_as_var():
    rng = np.random.default_rng(5)
    rets = rng.normal(0.0, 0.03, size=100)
    res = _result(rets)
    var95 = res.historical_var(alpha=0.95)
    cvar95 = res.cvar(alpha=0.95)
    assert cvar95 <= var95  # average of the tail beyond VaR must be at least as bad


def test_cvar_known_value_averages_the_tail():
    rets = np.array([-0.20, -0.15, -0.10, 0.0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06])
    res = _result(rets)
    var95 = res.historical_var(alpha=0.95)
    expected_tail_mean = rets[rets <= var95].mean()
    assert res.cvar(alpha=0.95) == pytest.approx(expected_tail_mean)
