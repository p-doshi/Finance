"""Portfolio weighting methods: equal-weight, inverse-beta, risk parity,
minimum-variance, and maximum-Sharpe (Markowitz), all long-only and
summing to 1. Deterministic: every solve tries the equal-weight start
first; SLSQP can fail to converge from there on some ill-conditioned
windows (this surfaced for real running the Phase 1 walk-forward backtest
across ~48 real rolling 3-year windows, not a hypothetical), so failures
fall back to a fixed sequence of alternative starting points (seeded, not
true randomness) rather than crashing the whole backtest on one bad
window. Same (covariance, expected returns) in -> same weights out, always.

These are building blocks for the walk-forward backtest (research.backtest)
— they take a covariance matrix and (where needed) an expected-return
vector as plain numpy arrays, with no knowledge of dates, so the same
functions run identically inside a rolling backtest window or against the
latest live window.
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import minimize

_SLSQP_OPTS = {"maxiter": 2000, "ftol": 1e-14}
_RESTART_SEED = 0  # fixed: restarts are deterministic, not genuinely random
_N_RESTARTS = 8


def _robust_minimize(objective, n: int, bounds, cons):
    """Try the equal-weight start first (matches every previously-published
    result exactly when it converges, which is the common case). Only on
    failure, retry from a fixed sequence of seeded Dirichlet-sampled
    long-only starting points and keep the best-objective successful solve.
    Raises only if every attempt fails."""
    rng = np.random.default_rng(_RESTART_SEED)
    starts = [equal_weight(n)] + [rng.dirichlet(np.ones(n)) for _ in range(_N_RESTARTS)]
    best = None
    for x0 in starts:
        res = minimize(objective, x0, method="SLSQP", bounds=bounds, constraints=cons, options=_SLSQP_OPTS)
        if res.success and (best is None or res.fun < best.fun):
            best = res
        if best is not None and x0 is starts[0]:
            break  # equal-weight start converged — no need to try fallbacks
    if best is None:
        raise RuntimeError(f"all {len(starts)} restarts failed to converge")
    return best


def equal_weight(n: int) -> np.ndarray:
    return np.ones(n) / n


def inverse_beta_weight(betas: np.ndarray) -> np.ndarray:
    """weight_i ∝ 1/beta_i. Needs only beta, not a covariance matrix —
    a heuristic, not an optimization; kept as the cheap baseline."""
    inv = 1.0 / np.asarray(betas, dtype=float)
    return inv / inv.sum()


def _risk_contributions(w: np.ndarray, cov: np.ndarray) -> np.ndarray:
    port_var = w @ cov @ w
    marginal = cov @ w
    return w * marginal / port_var


def risk_parity_weight(cov: np.ndarray) -> np.ndarray:
    """Long-only weights such that every asset contributes equally to
    portfolio variance. Needs only the covariance matrix — no expected-return
    assumption, which is what makes it far more stable than Markowitz."""
    n = cov.shape[0]

    def objective(w):
        rc = _risk_contributions(w, cov)
        return np.sum((rc - rc.mean()) ** 2)

    bounds = [(1e-6, 1.0)] * n
    cons = [{"type": "eq", "fun": lambda w: w.sum() - 1.0}]
    res = _robust_minimize(objective, n, bounds, cons)
    return res.x


def min_variance_weight(cov: np.ndarray) -> np.ndarray:
    """Long-only minimum-variance portfolio. Needs only the covariance matrix."""
    n = cov.shape[0]
    bounds = [(0.0, 1.0)] * n
    cons = [{"type": "eq", "fun": lambda w: w.sum() - 1.0}]
    res = _robust_minimize(lambda w: w @ cov @ w, n, bounds, cons)
    return res.x


def max_sharpe_weight(cov: np.ndarray, mu: np.ndarray, rf: float) -> np.ndarray:
    """Long-only tangency (max-Sharpe) portfolio. Needs the expected-return
    vector `mu` in addition to the covariance matrix — this is the input
    that makes max-Sharpe far less stable than risk parity or min-variance;
    see research/backtest.py's window-sensitivity report before trusting it."""
    n = cov.shape[0]
    bounds = [(0.0, 1.0)] * n
    cons = [{"type": "eq", "fun": lambda w: w.sum() - 1.0}]

    def neg_sharpe(w):
        ret = w @ mu
        vol = np.sqrt(w @ cov @ w)
        return -(ret - rf) / vol

    res = _robust_minimize(neg_sharpe, n, bounds, cons)
    return res.x


def portfolio_stats(w: np.ndarray, cov: np.ndarray, mu: np.ndarray, rf: float) -> dict:
    ret = float(w @ mu)
    vol = float(np.sqrt(w @ cov @ w))
    sharpe = (ret - rf) / vol
    n_effective = 1.0 / np.sum(w**2)  # Herfindahl-based effective number of names
    return {"ret": ret, "vol": vol, "sharpe": sharpe, "max_weight": float(w.max()), "n_effective": float(n_effective)}
