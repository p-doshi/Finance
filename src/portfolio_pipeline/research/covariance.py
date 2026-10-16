"""Covariance estimation. Sample covariance (what every method in
`optimizers.py` has used so far) gets noisier, and optimization against it
gets more unstable, as the number of assets approaches the number of
return observations — exactly the regime of this project's ~4,000-name
universe (Stage B) versus ~750 daily observations in a 3-year window.

Ledoit & Wolf, "Honey, I Shrunk the Sample Covariance Matrix," Journal of
Portfolio Management 30(4), 2004 — shrinks the sample covariance toward a
structured, low-variance target (the constant-correlation target used by
sklearn's `LedoitWolf`) with an analytically-derived optimal shrinkage
intensity, trading a small amount of bias for a large reduction in
estimation variance. Implemented via `sklearn.covariance.LedoitWolf`
rather than re-derived by hand — this is the standard, tested
implementation real portfolio libraries (Riskfolio-Lib, skfolio) use.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.covariance import LedoitWolf


def sample_covariance(log_returns: pd.DataFrame, annualize: bool = True) -> np.ndarray:
    """The baseline this project has used everywhere so far — kept here too
    so callers can switch estimators with one function-name change."""
    cov = log_returns.cov().values
    return cov * 252 if annualize else cov


def shrunk_covariance(log_returns: pd.DataFrame, annualize: bool = True) -> tuple[np.ndarray, float]:
    """Returns (covariance, shrinkage_intensity). Intensity is in [0, 1] —
    0 means no shrinkage was needed (sample covariance already well-behaved),
    1 would mean fully replaced by the structured target; real values are
    typically well inside that range and grow as n_assets/n_obs grows."""
    lw = LedoitWolf().fit(log_returns.values)
    cov = lw.covariance_
    return (cov * 252 if annualize else cov), float(lw.shrinkage_)


def condition_number(cov: np.ndarray) -> float:
    """Ratio of largest to smallest eigenvalue of the correlation matrix
    implied by `cov` — the diagnostic this project has used since Phase 0
    to check whether a covariance matrix is well-conditioned enough to
    invert/optimize against safely."""
    d = np.sqrt(np.diag(cov))
    corr = cov / np.outer(d, d)
    eigvals = np.linalg.eigvalsh(corr)
    return float(eigvals.max() / eigvals.min())
