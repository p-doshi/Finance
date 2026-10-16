import numpy as np
import pandas as pd
import pytest

from portfolio_pipeline.research.screen import (
    compute_beta,
    trailing_simple_return,
    annualized_vol,
    max_drawdown,
    rank_universe,
)

RNG = np.random.default_rng(123)


def test_compute_beta_recovers_known_value():
    n = 500
    market = pd.Series(RNG.normal(0.0003, 0.01, n))
    true_beta = 1.7
    noise = RNG.normal(0, 0.002, n)
    stock = true_beta * market + noise
    beta = compute_beta(stock, market)
    assert beta == pytest.approx(true_beta, abs=0.1)


def test_compute_beta_none_with_too_few_overlapping_observations():
    stock = pd.Series(RNG.normal(0, 0.01, 30), index=pd.RangeIndex(30))
    market = pd.Series(RNG.normal(0, 0.01, 30), index=pd.RangeIndex(30))
    assert compute_beta(stock, market) is None


def test_compute_beta_none_with_zero_variance_market():
    n = 200
    stock = pd.Series(RNG.normal(0, 0.01, n))
    market = pd.Series(np.zeros(n))
    assert compute_beta(stock, market) is None


def test_trailing_simple_return_known_value():
    # three days of +1% log return each -> simple return = exp(0.03) - 1
    log_rets = pd.Series([0.01, 0.01, 0.01])
    r = trailing_simple_return(log_rets, window_days=3)
    assert r == pytest.approx(np.expm1(0.03))


def test_trailing_simple_return_none_if_insufficient_history():
    log_rets = pd.Series([0.01, 0.01])
    assert trailing_simple_return(log_rets, window_days=5) is None


def test_annualized_vol_known_value():
    log_rets = pd.Series(np.full(252, 0.01))  # zero variance -> vol should be 0
    assert annualized_vol(log_rets, window_days=252) == pytest.approx(0.0, abs=1e-9)


def test_annualized_vol_none_if_insufficient_history():
    assert annualized_vol(pd.Series([0.01] * 10), window_days=252) is None


def test_max_drawdown_known_case():
    # +10%, then -20%, then +5% (log returns) -> compute expected curve/drawdown directly
    log_rets = pd.Series([np.log(1.10), np.log(0.80), np.log(1.05)])
    dd = max_drawdown(log_rets, window_days=3)
    curve = np.exp(np.cumsum(log_rets.values))
    expected = (curve / np.maximum.accumulate(curve) - 1.0).min()
    assert dd == pytest.approx(expected)


def test_max_drawdown_none_if_insufficient_history():
    assert max_drawdown(pd.Series([0.01] * 10), window_days=252) is None


def test_rank_universe_orders_by_composite_and_counts_horizons():
    records = [
        {"ticker": "HIGH", "mom_3m": 0.10, "mom_6m": 0.20, "mom_12m": 0.30},
        {"ticker": "LOW", "mom_3m": -0.10, "mom_6m": -0.20, "mom_12m": -0.30},
        {"ticker": "PARTIAL", "mom_3m": 0.05, "mom_6m": None, "mom_12m": None},
    ]
    df = rank_universe(records)
    assert list(df["ticker"]) == ["HIGH", "PARTIAL", "LOW"]
    assert df.loc[df["ticker"] == "HIGH", "n_horizons_used"].iloc[0] == 3
    assert df.loc[df["ticker"] == "PARTIAL", "n_horizons_used"].iloc[0] == 1
