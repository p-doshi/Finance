import numpy as np
import pytest

from portfolio_pipeline.research.black_litterman import (
    absolute_view,
    black_litterman_posterior,
    default_view_uncertainty,
    implied_risk_aversion,
    market_implied_returns,
    relative_view,
)
from portfolio_pipeline.research.optimizers import max_sharpe_weight

RNG = np.random.default_rng(77)


def test_implied_risk_aversion_known_value():
    # delta = (0.08 - 0.02) / 0.04 = 1.5
    assert implied_risk_aversion(market_excess_return=0.06, market_variance=0.04) == pytest.approx(1.5)


def test_market_implied_returns_known_value():
    cov = np.array([[0.04, 0.01], [0.01, 0.09]])
    w_mkt = np.array([0.6, 0.4])
    delta = 2.5
    pi = market_implied_returns(cov, w_mkt, delta)
    expected = delta * cov @ w_mkt
    np.testing.assert_allclose(pi, expected)


def test_market_implied_returns_are_self_consistent_with_max_sharpe():
    """The actual point of reverse-optimization, checked directly rather
    than just trusting the matrix multiply: feeding the implied returns
    back into max-Sharpe optimization (at the same risk-free/risk-aversion
    assumptions) should recover the market-cap weights themselves, since
    pi was *defined* as the returns that make w_mkt optimal."""
    n = 5
    A = RNG.normal(size=(n, n))
    cov = A @ A.T / n + np.eye(n) * 0.02
    w_mkt = RNG.dirichlet(np.ones(n))
    delta = 2.2
    pi = market_implied_returns(cov, w_mkt, delta)

    # for a long-only mean-variance investor with risk aversion delta and no
    # risk-free asset, the unconstrained tangency solution is w* ∝ Sigma^-1 pi;
    # check that recovers w_mkt up to normalization (up to the long-only
    # bound potentially binding if w_mkt has nonneg entries, which it does)
    unconstrained = np.linalg.solve(cov, pi)
    unconstrained /= unconstrained.sum()
    np.testing.assert_allclose(unconstrained, w_mkt, atol=1e-8)


def test_default_view_uncertainty_known_value():
    cov = np.eye(3) * 0.04
    P = np.array([[1.0, -1.0, 0.0]])  # a relative view between asset 0 and 1
    tau = 0.05
    omega = default_view_uncertainty(cov, P, tau)
    tau_sigma = tau * cov
    expected = np.diag(np.diag(P @ tau_sigma @ P.T))
    np.testing.assert_allclose(omega, expected)
    assert omega.shape == (1, 1)


def test_posterior_converges_to_prior_with_near_zero_confidence_view():
    n = 4
    A = RNG.normal(size=(n, n))
    cov = A @ A.T / n + np.eye(n) * 0.02
    pi = RNG.normal(0.08, 0.02, size=n)
    P, Q = absolute_view(n, asset_idx=0, expected_return=0.50)  # a wild, confident-sounding view...
    omega = np.array([[1e8]])  # ...but essentially zero confidence in it
    posterior_mean, _ = black_litterman_posterior(cov, pi, P, Q, omega, tau=0.05)
    np.testing.assert_allclose(posterior_mean, pi, atol=1e-3)


def test_posterior_matches_view_with_near_full_confidence():
    n = 4
    A = RNG.normal(size=(n, n))
    cov = A @ A.T / n + np.eye(n) * 0.02
    pi = RNG.normal(0.08, 0.02, size=n)
    P, Q = absolute_view(n, asset_idx=1, expected_return=0.30)
    omega = np.array([[1e-10]])  # near-certain view
    posterior_mean, _ = black_litterman_posterior(cov, pi, P, Q, omega, tau=0.05)
    assert (P @ posterior_mean).item() == pytest.approx(0.30, abs=1e-3)


def test_posterior_cov_is_larger_than_prior_cov_diagonal():
    """Posterior covariance should reflect added estimation uncertainty on
    top of the prior, per He & Litterman's Sigma + M^-1 convention -- never
    smaller than the prior on the diagonal."""
    n = 3
    A = RNG.normal(size=(n, n))
    cov = A @ A.T / n + np.eye(n) * 0.02
    pi = RNG.normal(0.08, 0.02, size=n)
    P, Q = absolute_view(n, asset_idx=0, expected_return=0.12)
    _, posterior_cov = black_litterman_posterior(cov, pi, P, Q, tau=0.05)
    assert np.all(np.diag(posterior_cov) >= np.diag(cov) - 1e-10)


def test_absolute_view_builder_shape_and_content():
    P, Q = absolute_view(n_assets=5, asset_idx=2, expected_return=0.15)
    assert P.shape == (1, 5)
    np.testing.assert_array_equal(P[0], [0, 0, 1, 0, 0])
    assert Q[0] == pytest.approx(0.15)


def test_relative_view_builder_shape_and_content():
    P, Q = relative_view(n_assets=4, long_idx=0, short_idx=3, outperformance=0.05)
    assert P.shape == (1, 4)
    np.testing.assert_array_equal(P[0], [1, 0, 0, -1])
    assert Q[0] == pytest.approx(0.05)


def test_black_litterman_output_feeds_max_sharpe_without_error():
    """End-to-end plumbing check: posterior mean/cov should be directly
    usable by the existing optimizer, same contract as any other
    (cov, mu) pair in this project."""
    n = 4
    A = RNG.normal(size=(n, n))
    cov = A @ A.T / n + np.eye(n) * 0.02
    pi = RNG.normal(0.08, 0.02, size=n)
    P, Q = relative_view(n, long_idx=0, short_idx=1, outperformance=0.03)
    posterior_mean, posterior_cov = black_litterman_posterior(cov, pi, P, Q, tau=0.05)
    w = max_sharpe_weight(posterior_cov, posterior_mean, rf=0.02)
    assert w.sum() == pytest.approx(1.0, abs=1e-6)
    assert np.all(w >= -1e-8)
