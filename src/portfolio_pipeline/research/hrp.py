"""Hierarchical Risk Parity — López de Prado, "Building Diversified
Portfolios that Outperform Out-of-Sample," Journal of Portfolio Management
42(4), 2016, pp. 59-69.

Targets the exact failure mode this project's own Phase 1 backtest already
found empirically: Markowitz-style quadratic optimizers are unstable to
small changes in their inputs and concentrate hard whenever the covariance
matrix is poorly conditioned (docs/methodology.md §5's window-sensitivity
finding — up to 30 percentage point swings in max-Sharpe weights). HRP
never inverts the covariance matrix at all, so it doesn't require it to be
positive-definite — the exact property that breaks sample covariance once
assets outnumber observations (research/covariance.py).

Three steps, each a plain function so the algorithm is auditable rather
than one opaque call:
  1. tree clustering  — hierarchical clustering on a correlation distance
  2. quasi-diagonalization — reorder assets so similar ones sit adjacent
  3. recursive bisection — split the ordered list in two repeatedly,
     allocating weight between each pair of halves inversely to their
     own (inverse-variance-portfolio) cluster variance
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import dendrogram, linkage
from scipy.spatial.distance import squareform


def correlation_distance(corr: np.ndarray) -> np.ndarray:
    """d(i,j) = sqrt(0.5 * (1 - corr(i,j))) — a proper metric distance
    (unlike 1 - corr itself), 0 for perfectly correlated assets, 1 for
    perfectly anti-correlated ones."""
    d = np.sqrt(np.clip(0.5 * (1 - corr), 0, None))
    np.fill_diagonal(d, 0.0)
    return d


def quasi_diagonal_order(link: np.ndarray) -> list[int]:
    """Leaf order from a linkage matrix — the permutation that puts
    similar assets next to each other, read off scipy's own dendrogram
    computation rather than re-implemented by hand."""
    return dendrogram(link, no_plot=True)["leaves"]


def _cluster_variance(cov: np.ndarray, items: list[int]) -> float:
    sub_cov = cov[np.ix_(items, items)]
    ivp = 1.0 / np.diag(sub_cov)
    ivp /= ivp.sum()
    return float(ivp @ sub_cov @ ivp)


def _recursive_bisection(cov: np.ndarray, sort_ix: list[int]) -> pd.Series:
    weights = pd.Series(1.0, index=sort_ix)
    clusters = [sort_ix]
    while clusters:
        next_clusters = []
        for cluster in clusters:
            if len(cluster) <= 1:
                continue
            split = len(cluster) // 2
            left, right = cluster[:split], cluster[split:]
            var_left = _cluster_variance(cov, left)
            var_right = _cluster_variance(cov, right)
            alpha = 1.0 - var_left / (var_left + var_right)
            weights[left] *= alpha
            weights[right] *= (1.0 - alpha)
            next_clusters += [left, right]
        clusters = next_clusters
    return weights


def hrp_weight(cov: np.ndarray, *, linkage_method: str = "single") -> np.ndarray:
    """Long-only weights summing to 1, by construction (every step splits
    a positive weight into two non-negative pieces — no explicit
    long-only constraint needs to be imposed, unlike the SLSQP-based
    methods in optimizers.py). Never inverts `cov`, so it tolerates a
    singular or near-singular covariance matrix that would make
    min_variance_weight/max_sharpe_weight fail outright."""
    n = cov.shape[0]
    if n == 1:
        return np.array([1.0])

    std = np.sqrt(np.diag(cov))
    corr = cov / np.outer(std, std)
    corr = np.clip(corr, -1.0, 1.0)

    dist = correlation_distance(corr)
    condensed = squareform(dist, checks=False)
    link = linkage(condensed, method=linkage_method)
    sort_ix = quasi_diagonal_order(link)

    weights = _recursive_bisection(cov, sort_ix)
    return weights.sort_index().values
