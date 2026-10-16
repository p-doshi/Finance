import numpy as np
import pytest

from portfolio_pipeline.research.hrp import hrp_weight, correlation_distance
from portfolio_pipeline.research.covariance import sample_covariance
import pandas as pd

RNG = np.random.default_rng(31)


def test_correlation_distance_known_values():
    corr = np.array([[1.0, 1.0], [1.0, 1.0]])  # perfectly correlated -> distance 0
    d = correlation_distance(corr)
    np.testing.assert_allclose(d, np.zeros((2, 2)), atol=1e-12)

    corr = np.array([[1.0, -1.0], [-1.0, 1.0]])  # perfectly anti-correlated -> distance 1 off-diag
    d = correlation_distance(corr)
    assert d[0, 1] == pytest.approx(1.0)
    assert d[0, 0] == pytest.approx(0.0)


def test_hrp_single_asset():
    cov = np.array([[0.04]])
    w = hrp_weight(cov)
    assert w == pytest.approx([1.0])


def test_hrp_two_assets_matches_inverse_variance_closed_form():
    """For exactly 2 assets, HRP's recursive bisection reduces to splitting
    inversely to each asset's own variance — a known closed form, checked
    directly rather than just trusting the recursion."""
    cov = np.array([[0.04, 0.01], [0.01, 0.09]])  # var0=0.04, var1=0.09
    w = hrp_weight(cov)
    expected_w0 = (1 / 0.04) / (1 / 0.04 + 1 / 0.09)
    assert w[0] == pytest.approx(expected_w0, abs=1e-9)
    assert w.sum() == pytest.approx(1.0)


def test_hrp_sums_to_one_and_long_only_random_cov():
    n = 8
    A = RNG.normal(size=(n, n))
    cov = A @ A.T / n + np.eye(n) * 0.01
    w = hrp_weight(cov)
    assert w.sum() == pytest.approx(1.0, abs=1e-8)
    assert np.all(w >= 0)


def test_hrp_diversifies_across_correlated_blocks_not_within():
    """The actual point of HRP, checked directly: two blocks of two
    highly-correlated assets each, with the blocks uncorrelated with each
    other. HRP should split roughly evenly ACROSS the two blocks (~50/50)
    rather than concentrating in whichever single asset has lowest
    variance — a naive (non-hierarchical) inverse-variance scheme would
    ignore the block structure entirely and could easily overweight one
    block because two of its assets happen to look individually safe."""
    # block A: assets 0,1 correlated 0.95, var ~0.04; block B: assets 2,3 correlated 0.95, var ~0.04
    rho_in, rho_out = 0.95, 0.0
    corr = np.array([
        [1.0, rho_in, rho_out, rho_out],
        [rho_in, 1.0, rho_out, rho_out],
        [rho_out, rho_out, 1.0, rho_in],
        [rho_out, rho_out, rho_in, 1.0],
    ])
    std = np.array([0.2, 0.2, 0.2, 0.2])
    cov = corr * np.outer(std, std)
    w = hrp_weight(cov)
    block_a = w[0] + w[1]
    block_b = w[2] + w[3]
    assert block_a == pytest.approx(0.5, abs=0.05)
    assert block_b == pytest.approx(0.5, abs=0.05)
    # within each block, equal variance -> equal split
    assert w[0] == pytest.approx(w[1], abs=1e-6)
    assert w[2] == pytest.approx(w[3], abs=1e-6)


def test_hrp_deterministic():
    n = 10
    A = RNG.normal(size=(n, n))
    cov = A @ A.T / n + np.eye(n) * 0.01
    w1 = hrp_weight(cov)
    w2 = hrp_weight(cov)
    np.testing.assert_array_equal(w1, w2)


def test_hrp_handles_singular_covariance_where_matrix_inversion_would_fail():
    """The actual advertised benefit, checked directly rather than just
    asserted: N > n_obs guarantees a singular sample covariance (see
    test_covariance.py's matching test), which would break any method
    needing to invert it. HRP never inverts anything, so it should still
    produce valid long-only weights summing to 1 here."""
    rng = np.random.default_rng(41)
    n_obs, n_assets = 30, 50
    factor = rng.normal(0, 0.01, size=(n_obs, 1))
    data = factor @ np.ones((1, n_assets)) * 0.6 + rng.normal(0, 0.008, size=(n_obs, n_assets))
    df = pd.DataFrame(data)
    cov = sample_covariance(df, annualize=False)

    eigvals = np.linalg.eigvalsh(cov)
    assert eigvals.min() < 1e-8  # confirm it's actually singular/near-singular first

    w = hrp_weight(cov)
    assert w.sum() == pytest.approx(1.0, abs=1e-6)
    assert np.all(w >= 0)
    assert len(w) == n_assets
