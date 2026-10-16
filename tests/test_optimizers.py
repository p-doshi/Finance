from unittest.mock import patch

import numpy as np
import pytest
from scipy.optimize import OptimizeResult

from portfolio_pipeline.research.optimizers import (
    equal_weight,
    inverse_beta_weight,
    risk_parity_weight,
    min_variance_weight,
    max_sharpe_weight,
    portfolio_stats,
    _risk_contributions,
    _robust_minimize,
)

N = 6
RNG = np.random.default_rng(0)


def _random_cov(n=N):
    """A random but valid (positive-definite) covariance matrix."""
    A = RNG.normal(size=(n, n))
    cov = A @ A.T / n + np.eye(n) * 0.01  # ridge term keeps it well-conditioned
    return cov


@pytest.fixture
def cov():
    return _random_cov()


@pytest.fixture
def mu():
    return RNG.normal(loc=0.08, scale=0.05, size=N)


def test_equal_weight_sums_to_one_and_is_uniform():
    w = equal_weight(N)
    assert w.sum() == pytest.approx(1.0)
    assert np.allclose(w, 1.0 / N)


def test_inverse_beta_weight_known_case():
    # beta=1 and beta=2 -> inverse weights 1 and 0.5 -> normalized 2/3, 1/3
    w = inverse_beta_weight(np.array([1.0, 2.0]))
    assert w.sum() == pytest.approx(1.0)
    assert w[0] == pytest.approx(2 / 3)
    assert w[1] == pytest.approx(1 / 3)


def test_risk_parity_sums_to_one_and_long_only(cov):
    w = risk_parity_weight(cov)
    assert w.sum() == pytest.approx(1.0, abs=1e-6)
    assert np.all(w >= -1e-8)


def test_risk_parity_contributions_are_actually_equal(cov):
    w = risk_parity_weight(cov)
    rc = _risk_contributions(w, cov)
    # every asset should contribute (1/N) of total portfolio variance
    assert np.allclose(rc, rc.mean(), atol=1e-4)


def test_risk_parity_deterministic(cov):
    w1 = risk_parity_weight(cov)
    w2 = risk_parity_weight(cov)
    assert np.allclose(w1, w2)


def test_min_variance_sums_to_one_and_long_only(cov):
    w = min_variance_weight(cov)
    assert w.sum() == pytest.approx(1.0, abs=1e-6)
    assert np.all(w >= -1e-8)


def test_min_variance_has_lower_or_equal_variance_than_equal_weight(cov):
    w_mv = min_variance_weight(cov)
    w_eq = equal_weight(N)
    var_mv = w_mv @ cov @ w_mv
    var_eq = w_eq @ cov @ w_eq
    assert var_mv <= var_eq + 1e-9


def test_max_sharpe_sums_to_one_and_long_only(cov, mu):
    w = max_sharpe_weight(cov, mu, rf=0.04)
    assert w.sum() == pytest.approx(1.0, abs=1e-6)
    assert np.all(w >= -1e-8)


def test_max_sharpe_beats_equal_weight_sharpe_in_sample(cov, mu):
    # max-Sharpe is solved to maximize exactly this ratio on this exact
    # (cov, mu) — it must weakly beat every other long-only portfolio
    # in-sample. This is NOT evidence of forward performance (see
    # docs/methodology.md); it is a solver-correctness check.
    w_ms = max_sharpe_weight(cov, mu, rf=0.04)
    w_eq = equal_weight(N)
    stats_ms = portfolio_stats(w_ms, cov, mu, rf=0.04)
    stats_eq = portfolio_stats(w_eq, cov, mu, rf=0.04)
    assert stats_ms["sharpe"] >= stats_eq["sharpe"] - 1e-6


def test_robust_minimize_falls_back_when_equal_weight_start_fails():
    """This is the exact failure mode that surfaced running the real
    walk-forward backtest (scripts/run_backtest.py) on window ~23/48:
    SLSQP failed to converge from the equal-weight start. Simulate that
    here deterministically rather than relying on hitting it again by luck."""
    n = 4
    bounds = [(0.0, 1.0)] * n
    cons = [{"type": "eq", "fun": lambda w: w.sum() - 1.0}]
    fail = OptimizeResult(x=equal_weight(n), success=False, fun=np.nan, message="forced failure")
    ok = OptimizeResult(x=np.array([0.4, 0.3, 0.2, 0.1]), success=True, fun=-1.0, message="ok")
    # equal-weight start fails, every fallback restart succeeds with the same
    # objective value -> first successful fallback wins (all tied on `fun`)
    with patch("portfolio_pipeline.research.optimizers.minimize", side_effect=[fail] + [ok] * 8):
        res = _robust_minimize(lambda w: w @ w, n, bounds, cons)
    assert res.success
    np.testing.assert_allclose(res.x, [0.4, 0.3, 0.2, 0.1])


def test_robust_minimize_raises_if_every_attempt_fails():
    n = 3
    bounds = [(0.0, 1.0)] * n
    cons = [{"type": "eq", "fun": lambda w: w.sum() - 1.0}]
    always_fail = OptimizeResult(x=equal_weight(n), success=False, fun=np.nan, message="nope")
    with patch("portfolio_pipeline.research.optimizers.minimize", return_value=always_fail):
        with pytest.raises(RuntimeError, match="all .* restarts failed"):
            _robust_minimize(lambda w: w @ w, n, bounds, cons)


def test_portfolio_stats_n_effective_bounds(cov, mu):
    w_eq = equal_weight(N)
    assert portfolio_stats(w_eq, cov, mu, rf=0.0)["n_effective"] == pytest.approx(N)
    concentrated = np.zeros(N)
    concentrated[0] = 1.0
    assert portfolio_stats(concentrated, cov, mu, rf=0.0)["n_effective"] == pytest.approx(1.0)
