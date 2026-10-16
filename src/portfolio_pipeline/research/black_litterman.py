"""Black-Litterman: Black & Litterman, "Global Portfolio Optimization,"
Financial Analysts Journal, Sept-Oct 1992, pp. 28-43 (developed at Goldman
Sachs). Starts from CAPM-implied equilibrium returns (reverse-optimized
from market-cap weights) and Bayesian-updates them with the investor's own
views, each carrying its own confidence — directly targets the "garbage
in, garbage out" problem already found empirically in this project's
Phase 1 backtest: max-Sharpe's instability comes entirely from how noisy
a plain historical-mean expected-return estimate is, and Black-Litterman
exists specifically to replace that estimate with something better-anchored.

Honest framing for how this project actually uses it (see
scripts/run_black_litterman.py and docs/methodology.md): a view is only as
good as the process that generated it, and Stage B's IC study
(research/ic_analysis.py) already found the momentum ranking has no
demonstrated out-of-sample predictive skill. So this isn't wired up to
secretly launder an unvalidated signal into a "view" — it's demonstrated
with explicit, small, clearly-labeled illustrative views instead, with the
machinery itself verified against known closed-form limiting cases.
"""
from __future__ import annotations

import numpy as np


def implied_risk_aversion(market_excess_return: float, market_variance: float) -> float:
    """delta = (E[R_m] - Rf) / Var(R_m) -- standard CAPM reverse-engineering
    of the risk-aversion coefficient from the market portfolio's own
    historical Sharpe-like ratio."""
    return market_excess_return / market_variance


def market_implied_returns(cov: np.ndarray, market_weights: np.ndarray, risk_aversion: float) -> np.ndarray:
    """pi = delta * Sigma * w_mkt -- the equilibrium expected-return vector
    that would make the market-cap-weighted portfolio the optimal
    mean-variance portfolio, given `cov` and `risk_aversion`. This is the
    *prior*, replacing noisy historical sample means as the starting point."""
    return risk_aversion * cov @ market_weights


def default_view_uncertainty(cov: np.ndarray, P: np.ndarray, tau: float) -> np.ndarray:
    """He & Litterman's common default when the investor doesn't specify
    view confidence directly: Omega = diag(P (tau*Sigma) P'), i.e. each
    view's uncertainty scales with the variance of the portfolio that view
    is actually about."""
    tau_sigma = tau * cov
    diag_vals = np.diag(P @ tau_sigma @ P.T)
    return np.diag(diag_vals)


def black_litterman_posterior(
    cov: np.ndarray, pi: np.ndarray, P: np.ndarray, Q: np.ndarray,
    omega: np.ndarray | None = None, tau: float = 0.05,
) -> tuple[np.ndarray, np.ndarray]:
    """Combines the equilibrium prior (`pi`, `cov`) with `P`-`Q` views
    (each row of `P` is a portfolio the investor has a view on; `Q` is
    the expected return of that view-portfolio; `omega`'s diagonal is
    each view's uncertainty — lower means more confident) via the
    standard Bayesian update. `omega` defaults to `default_view_uncertainty`
    if not given. Returns (posterior_mean, posterior_cov) — the posterior
    covariance already includes both prior and estimation uncertainty
    (He & Litterman's Sigma + M^-1 convention), ready to feed into any of
    optimizers.py's methods."""
    if omega is None:
        omega = default_view_uncertainty(cov, P, tau)

    tau_sigma_inv = np.linalg.inv(tau * cov)
    omega_inv = np.linalg.inv(omega)

    m_inv = np.linalg.inv(tau_sigma_inv + P.T @ omega_inv @ P)
    posterior_mean = m_inv @ (tau_sigma_inv @ pi + P.T @ omega_inv @ Q)
    posterior_cov = cov + m_inv

    return posterior_mean, posterior_cov


def absolute_view(n_assets: int, asset_idx: int, expected_return: float) -> tuple[np.ndarray, np.ndarray]:
    """Convenience builder: 'asset i will return Q', as a single-row (P, Q)."""
    p_row = np.zeros(n_assets)
    p_row[asset_idx] = 1.0
    return p_row.reshape(1, -1), np.array([expected_return])


def relative_view(n_assets: int, long_idx: int, short_idx: int, outperformance: float) -> tuple[np.ndarray, np.ndarray]:
    """Convenience builder: 'asset `long_idx` will outperform asset
    `short_idx` by `outperformance`', as a single-row (P, Q)."""
    p_row = np.zeros(n_assets)
    p_row[long_idx] = 1.0
    p_row[short_idx] = -1.0
    return p_row.reshape(1, -1), np.array([outperformance])
