import numpy as np
import pandas as pd
import pytest

from portfolio_pipeline.research.covariance import sample_covariance, shrunk_covariance, condition_number

RNG = np.random.default_rng(7)


def _synthetic_returns(n_obs, n_assets, seed=7):
    rng = np.random.default_rng(seed)
    data = rng.normal(0.0003, 0.01, size=(n_obs, n_assets))
    return pd.DataFrame(data, columns=[f"A{i}" for i in range(n_assets)])


def test_sample_covariance_matches_pandas_annualized():
    df = _synthetic_returns(300, 5)
    cov = sample_covariance(df)
    expected = df.cov().values * 252
    np.testing.assert_allclose(cov, expected)


def test_sample_covariance_not_annualized_option():
    df = _synthetic_returns(300, 5)
    cov = sample_covariance(df, annualize=False)
    np.testing.assert_allclose(cov, df.cov().values)


def test_shrinkage_intensity_in_valid_range():
    df = _synthetic_returns(300, 10)
    _, intensity = shrunk_covariance(df)
    assert 0.0 <= intensity <= 1.0


def test_shrinkage_improves_condition_number_when_assets_approach_observations():
    """The actual claimed benefit, checked directly: when n_assets is close
    to n_obs (the regime that breaks sample covariance, per this project's
    4,000-stock universe), shrinkage should produce a materially better
    (lower) condition number than the raw sample covariance."""
    df = _synthetic_returns(n_obs=60, n_assets=50, seed=11)
    sample_cov = sample_covariance(df)
    shrunk_cov, intensity = shrunk_covariance(df)

    sample_cond = condition_number(sample_cov)
    shrunk_cond = condition_number(shrunk_cov)

    assert shrunk_cond < sample_cond
    assert intensity > 0.05  # meaningful shrinkage should be applied in this hard regime


def _factor_correlated_returns(n_obs, n_assets, seed):
    """Unlike _synthetic_returns' independent columns, this gives assets a
    real common-factor correlation structure — closer to actual equities
    (see the 3-year correlation matrix in docs/methodology.md, values up
    to 0.57) and the right regime to test 'more data -> less shrinkage',
    since that only holds when there's real structure for more data to
    reveal. With truly independent assets, the shrinkage target already
    equals the truth and full shrinkage (intensity=1.0) is correct at any
    sample size — confirmed directly, not assumed, before writing this."""
    rng = np.random.default_rng(seed)
    factor = rng.normal(0, 0.01, size=(n_obs, 1))
    idio = rng.normal(0, 0.008, size=(n_obs, n_assets))
    data = factor @ np.ones((1, n_assets)) * 0.6 + idio
    return pd.DataFrame(data, columns=[f"A{i}" for i in range(n_assets)])


def test_shrinkage_intensity_shrinks_as_data_grows_when_true_structure_exists():
    """With a real correlation structure for more data to reveal, shrinkage
    intensity should decrease as sample size grows — the sample covariance
    becomes trustworthy enough that less correction toward the structured
    target is needed."""
    intensities = []
    for n_obs in [100, 1000, 10000]:
        df = _factor_correlated_returns(n_obs, n_assets=5, seed=13)
        _, intensity = shrunk_covariance(df)
        intensities.append(intensity)
    assert intensities[0] > intensities[1] > intensities[2]


def test_shrinkage_intensity_is_full_when_assets_are_truly_independent():
    """The degenerate case, confirmed empirically rather than assumed: pure
    i.i.d. assets already match Ledoit-Wolf's constant-correlation target,
    so full shrinkage (1.0) is correct regardless of sample size — there's
    no bias cost to paying for a target that's already right."""
    for n_obs in [100, 2000, 50000]:
        df = _synthetic_returns(n_obs, n_assets=5, seed=13)
        _, intensity = shrunk_covariance(df)
        assert intensity == pytest.approx(1.0)


def test_shrunk_covariance_stays_positive_definite():
    df = _synthetic_returns(n_obs=60, n_assets=50, seed=17)
    cov, _ = shrunk_covariance(df)
    eigvals = np.linalg.eigvalsh(cov)
    assert np.all(eigvals > 0)


def test_sample_covariance_breaks_when_assets_exceed_observations():
    """The dramatic real case found running scripts/build_large_portfolio.py
    at K=300 (300 assets, 199 observations after the common-date join):
    sample covariance's condition number came back as roughly -1.26e16 —
    nonsensical, because an N x N sample covariance from fewer than N
    observations is mathematically rank-deficient (singular), and its
    near-zero eigenvalues go slightly negative under floating point,
    flipping the condition-number ratio's sign. Shrunk covariance stays
    well-conditioned and positive-definite throughout. Reproduced here with
    a smaller synthetic N > n_obs case so this doesn't depend on fetched
    market data to catch a regression."""
    df = _factor_correlated_returns(n_obs=30, n_assets=50, seed=19)  # 50 > 30: guaranteed singular
    sample_cov = sample_covariance(df)
    shrunk_cov, _ = shrunk_covariance(df)

    sample_eigvals = np.linalg.eigvalsh(sample_cov)
    assert sample_eigvals.min() < 1e-8  # at or below zero -> singular/near-singular, as expected

    shrunk_eigvals = np.linalg.eigvalsh(shrunk_cov)
    assert shrunk_eigvals.min() > 0  # shrinkage keeps it positive-definite despite N > n_obs
    assert condition_number(shrunk_cov) < 1e6  # stays usable, unlike the sample version


def test_condition_number_known_case_identity_matrix():
    # a correlation matrix of all-independent assets is the identity ->
    # every eigenvalue is 1 -> condition number exactly 1
    cov = np.diag([0.04, 0.09, 0.01])  # diagonal covariance, zero correlation
    assert condition_number(cov) == pytest.approx(1.0)
