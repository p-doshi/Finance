import numpy as np
import pandas as pd
import pytest
import statsmodels.api as sm

from portfolio_pipeline.research.factor_model import factor_regression, annualized_alpha

RNG = np.random.default_rng(88)


def _synthetic_factors(n=500, k=3, seed=88):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2020-01-02", periods=n)
    cols = ["Mkt-RF", "SMB", "HML"][:k]
    return pd.DataFrame(rng.normal(0.0003, 0.01, size=(n, k)), index=idx, columns=cols)


def test_factor_regression_recovers_exact_coefficients_with_zero_noise():
    factors = _synthetic_factors(n=300, k=3)
    true_alpha, true_betas = 0.0005, np.array([1.2, -0.3, 0.6])
    y = true_alpha + factors.values @ true_betas  # no noise at all
    excess_returns = pd.Series(y, index=factors.index)

    result = factor_regression(excess_returns, factors)
    assert result["coefficients"]["alpha"]["coef"] == pytest.approx(true_alpha, abs=1e-10)
    for name, true_b in zip(factors.columns, true_betas):
        assert result["coefficients"][name]["coef"] == pytest.approx(true_b, abs=1e-8)
    assert result["r_squared"] == pytest.approx(1.0, abs=1e-8)


def test_factor_regression_matches_statsmodels_exactly():
    """Cross-validated against a real, independently-implemented tool --
    same practice that caught the max_drawdown bug via quantstats. Noisy
    (not zero-residual) data this time, so standard errors/t-stats/R^2 are
    all actually exercised, not just the zero-noise closed-form case."""
    factors = _synthetic_factors(n=400, k=3, seed=5)
    true_alpha, true_betas = 0.0003, np.array([0.9, 0.4, -0.5])
    noise = RNG.normal(0, 0.008, size=400)
    y = true_alpha + factors.values @ true_betas + noise
    excess_returns = pd.Series(y, index=factors.index)

    mine = factor_regression(excess_returns, factors)

    X_sm = sm.add_constant(factors.values)
    sm_model = sm.OLS(y, X_sm).fit()

    names = ["alpha"] + list(factors.columns)
    for i, name in enumerate(names):
        assert mine["coefficients"][name]["coef"] == pytest.approx(sm_model.params[i], abs=1e-10)
        assert mine["coefficients"][name]["se"] == pytest.approx(sm_model.bse[i], abs=1e-10)
        assert mine["coefficients"][name]["t"] == pytest.approx(sm_model.tvalues[i], abs=1e-8)
        assert mine["coefficients"][name]["p"] == pytest.approx(sm_model.pvalues[i], abs=1e-6)
    assert mine["r_squared"] == pytest.approx(sm_model.rsquared, abs=1e-10)
    assert mine["dof"] == sm_model.df_resid


def test_factor_regression_matches_statsmodels_five_factor():
    factors = pd.DataFrame(
        RNG.normal(0.0002, 0.009, size=(350, 5)),
        index=pd.bdate_range("2021-01-04", periods=350),
        columns=["Mkt-RF", "SMB", "HML", "RMW", "CMA"],
    )
    true_betas = np.array([1.1, 0.2, -0.1, 0.3, -0.2])
    y = 0.0001 + factors.values @ true_betas + RNG.normal(0, 0.006, size=350)
    excess_returns = pd.Series(y, index=factors.index)

    mine = factor_regression(excess_returns, factors)
    X_sm = sm.add_constant(factors.values)
    sm_model = sm.OLS(y, X_sm).fit()

    for i, name in enumerate(["alpha"] + list(factors.columns)):
        assert mine["coefficients"][name]["coef"] == pytest.approx(sm_model.params[i], abs=1e-10)
    assert mine["r_squared"] == pytest.approx(sm_model.rsquared, abs=1e-10)


def test_factor_regression_aligns_on_common_dates_only():
    factors = _synthetic_factors(n=100, k=3)
    # excess_returns has a different (overlapping but not identical) date range
    shifted_idx = factors.index[20:80]
    excess_returns = pd.Series(RNG.normal(0.001, 0.01, size=60), index=shifted_idx)
    result = factor_regression(excess_returns, factors)
    assert result["n_obs"] == 60


def test_annualized_alpha_known_value():
    result = {"coefficients": {"alpha": {"coef": 0.0003, "se": 0, "t": 0, "p": 0}}}
    expected = (1.0003) ** 252 - 1
    assert annualized_alpha(result, periods_per_year=252) == pytest.approx(expected)
