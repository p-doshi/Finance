"""Factor regression against Kenneth French's published factors
(data.fetch_factors) — a stock or portfolio's excess returns regressed on
Mkt-RF, SMB, HML (3-factor) or additionally RMW, CMA (5-factor):

    R_i - RF = alpha + sum_k(beta_k * factor_k) + epsilon

`alpha` here is exactly Jensen's alpha from the metrics research
(docs/methodology.md §7) generalized from a single market factor to
several — return unexplained by factor exposure. This is the standard way
real multi-factor risk models (Barra/Axioma) are used for both expected-
return and covariance decomposition at scale: regress against a small set
of factors instead of estimating a full N x N asset covariance matrix
directly, which is exactly the problem research/covariance.py's shrinkage
exists for at this project's ~4,000-name universe (though a full
production factor-risk model needs licensed fundamentals/industry data
beyond this project's scope — see docs/methodology.md).

OLS implemented directly (no statsmodels dependency at runtime) and
cross-checked against statsmodels.OLS in tests/test_factor_model.py —
coefficients, standard errors, t-stats, and R^2 all verified to match a
real, independently-implemented tool, continuing the practice that caught
the max_drawdown bug via quantstats.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import t as t_dist


def factor_regression(excess_returns: pd.Series, factors: pd.DataFrame) -> dict:
    """excess_returns: a Series of RETURNS ALREADY IN EXCESS OF THE
    RISK-FREE RATE (i.e. already had `factors['RF']` subtracted, since RF
    is a factor-file column, not a regressor). factors: a DataFrame of the
    regressor columns only (e.g. ['Mkt-RF','SMB','HML'] or
    ['Mkt-RF','SMB','HML','RMW','CMA'] — do not pass 'RF' itself as a
    regressor). Aligned on their common dates (inner join); raises nothing
    special on a mismatch, just uses whatever overlaps -- callers should
    check `n_obs` in the result if they need a minimum.
    """
    aligned = pd.concat([excess_returns, factors], axis=1, join="inner").dropna()
    y = aligned.iloc[:, 0].values
    X_factors = aligned.iloc[:, 1:].values
    factor_names = list(factors.columns)
    n = len(y)
    X = np.column_stack([np.ones(n), X_factors])

    beta_hat, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
    y_hat = X @ beta_hat
    resid = y - y_hat
    rss = float(np.sum(resid ** 2))
    tss = float(np.sum((y - y.mean()) ** 2))
    r_squared = 1 - rss / tss if tss > 0 else float("nan")
    dof = n - X.shape[1]
    sigma2 = rss / dof if dof > 0 else float("nan")
    cov_beta = sigma2 * np.linalg.inv(X.T @ X)
    se = np.sqrt(np.diag(cov_beta))
    t_stats = beta_hat / se
    p_values = 2 * (1 - t_dist.cdf(np.abs(t_stats), dof))

    names = ["alpha"] + factor_names
    coefficients = {
        name: {"coef": float(b), "se": float(s), "t": float(tv), "p": float(pv)}
        for name, b, s, tv, pv in zip(names, beta_hat, se, t_stats, p_values)
    }
    return {
        "coefficients": coefficients, "r_squared": r_squared,
        "n_obs": n, "dof": dof, "residual_std": float(np.sqrt(sigma2)) if dof > 0 else float("nan"),
    }


def annualized_alpha(regression_result: dict, periods_per_year: float = 252) -> float:
    """The regression's daily alpha, annualized by simple compounding --
    the part of the return this factor set cannot explain, scaled to a
    yearly figure comparable to the Sharpe/Sortino/Calmar metrics
    elsewhere in this project."""
    daily_alpha = regression_result["coefficients"]["alpha"]["coef"]
    return float((1 + daily_alpha) ** periods_per_year - 1)
