import numpy as np
import pandas as pd
import pytest

from portfolio_pipeline.research.forecast import simulate_forward


def _synthetic_log_returns(n_days=500, mean=0.0004, scale=0.012, seed=7):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2023-01-01", periods=n_days)
    return pd.Series(rng.normal(loc=mean, scale=scale, size=n_days), index=idx)


def test_deterministic_given_seed():
    r = _synthetic_log_returns()
    a = simulate_forward(r, initial_value=1000.0, horizon_days=60, n_sims=500, seed=3)
    b = simulate_forward(r, initial_value=1000.0, horizon_days=60, n_sims=500, seed=3)
    np.testing.assert_array_equal(a.p50, b.p50)
    np.testing.assert_array_equal(a.p10, b.p10)
    np.testing.assert_array_equal(a.p90, b.p90)


def test_different_seed_gives_different_path():
    r = _synthetic_log_returns()
    a = simulate_forward(r, initial_value=1000.0, horizon_days=60, n_sims=500, seed=1)
    b = simulate_forward(r, initial_value=1000.0, horizon_days=60, n_sims=500, seed=2)
    assert not np.array_equal(a.p50, b.p50)


def test_percentiles_are_ordered_at_every_step():
    r = _synthetic_log_returns()
    res = simulate_forward(r, initial_value=500.0, horizon_days=120, n_sims=1000, seed=0)
    assert np.all(res.p10 <= res.p50 + 1e-9)
    assert np.all(res.p50 <= res.p90 + 1e-9)


def test_output_length_matches_horizon():
    r = _synthetic_log_returns()
    res = simulate_forward(r, initial_value=100.0, horizon_days=90, n_sims=200, seed=0)
    assert len(res.p10) == len(res.p50) == len(res.p90) == 90


def test_initial_value_scales_every_percentile_linearly():
    """Compounding is multiplicative: doubling the starting dollar amount
    must exactly double every simulated path and therefore every
    percentile, for the identical return draws (same seed)."""
    r = _synthetic_log_returns()
    res_1x = simulate_forward(r, initial_value=1000.0, horizon_days=80, n_sims=500, seed=11)
    res_2x = simulate_forward(r, initial_value=2000.0, horizon_days=80, n_sims=500, seed=11)
    np.testing.assert_allclose(res_2x.p50, res_1x.p50 * 2)
    np.testing.assert_allclose(res_2x.p10, res_1x.p10 * 2)
    np.testing.assert_allclose(res_2x.p90, res_1x.p90 * 2)


def test_zero_return_series_stays_flat():
    idx = pd.bdate_range("2023-01-01", periods=200)
    zero_returns = pd.Series(0.0, index=idx)
    res = simulate_forward(zero_returns, initial_value=777.0, horizon_days=50, n_sims=100, seed=0)
    np.testing.assert_allclose(res.p10, 777.0)
    np.testing.assert_allclose(res.p50, 777.0)
    np.testing.assert_allclose(res.p90, 777.0)


def test_too_few_observations_raises():
    r = _synthetic_log_returns(n_days=10)
    with pytest.raises(ValueError, match="too few"):
        simulate_forward(r, initial_value=100.0, horizon_days=30, block_size=5)


def test_nan_returns_are_dropped_not_propagated():
    r = _synthetic_log_returns()
    r.iloc[5:10] = np.nan
    res = simulate_forward(r, initial_value=100.0, horizon_days=30, n_sims=100, seed=0)
    assert np.all(np.isfinite(res.p50))
