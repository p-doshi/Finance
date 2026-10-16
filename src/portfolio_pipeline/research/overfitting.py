"""Deflated Sharpe Ratio and Probability of Backtest Overfitting — López
de Prado's corrections for exactly the situation this project is already
in: 5 weighting methods compared on the same 24-period backtest is 5
trials, and picking whichever looks best in-sample (Phase 0 picked
max-Sharpe) is a textbook multiple-testing/selection-bias setup.

Deflated Sharpe Ratio: Bailey & López de Prado, "The Deflated Sharpe
Ratio: Correcting for Selection Bias, Backtest Overfitting, and
Non-Normality," J. Portfolio Management 40(5), 2014, 94-107.

Probability of Backtest Overfitting (via Combinatorially Symmetric
Cross-Validation): Bailey, Borwein, López de Prado & Zhu, "The
Probability of Backtest Overfitting," J. Computational Finance 20(4),
2017, 39-69.
"""
from __future__ import annotations

from itertools import combinations

import numpy as np
import pandas as pd
from scipy.stats import norm, skew as _skew, kurtosis as _kurtosis

EULER_MASCHERONI = 0.5772156649015329


def probabilistic_sharpe_ratio(sr_hat: float, sr_benchmark: float, n_obs: int,
                                skewness: float, kurtosis_raw: float) -> float:
    """PSR(SR*): probability that the TRUE Sharpe ratio exceeds `sr_benchmark`,
    given an observed (per-period, not annualized) Sharpe `sr_hat` estimated
    from `n_obs` observations with the given skewness and *raw* kurtosis
    (3.0 for a normal distribution — not excess kurtosis). Bailey & López
    de Prado (2012), "The Sharpe Ratio Efficient Frontier."
    """
    denom = np.sqrt(max(1e-12, 1 - skewness * sr_hat + ((kurtosis_raw - 1) / 4) * sr_hat ** 2))
    z = (sr_hat - sr_benchmark) * np.sqrt(n_obs - 1) / denom
    return float(norm.cdf(z))


def expected_max_sharpe_under_null(n_trials: int, sharpe_variance: float) -> float:
    """E[max_n SR_n] under the null of no true skill across `n_trials`
    independent trials whose Sharpe ratios have variance `sharpe_variance`
    — the benchmark DSR measures the observed best Sharpe against, instead
    of 0. Returns 0.0 for n_trials <= 1 (no multiple-testing correction
    needed/well-defined with a single trial)."""
    if n_trials <= 1:
        return 0.0
    a = norm.ppf(1 - 1.0 / n_trials)
    b = norm.ppf(1 - 1.0 / (n_trials * np.e))
    return float(np.sqrt(max(0.0, sharpe_variance)) * ((1 - EULER_MASCHERONI) * a + EULER_MASCHERONI * b))


def deflated_sharpe_ratio(
    period_returns_by_trial: dict[str, np.ndarray], best_trial: str,
) -> dict:
    """DSR for `best_trial` (e.g. the method that looked best in-sample),
    given the per-period returns of every trial actually run (the
    selection pool — this is what the deflation needs to know about: how
    many trials, how spread out their Sharpes were). All trials must share
    the same number of periods and period length (no annualization here —
    `period_returns_by_trial` should hold whatever raw per-period returns
    the Sharpe/skew/kurtosis are computed consistently from).
    """
    sharpes = {}
    for name, rets in period_returns_by_trial.items():
        rets = np.asarray(rets)
        sharpes[name] = rets.mean() / rets.std(ddof=1) if rets.std(ddof=1) > 0 else np.nan
    sr_values = np.array([v for v in sharpes.values() if not np.isnan(v)])
    n_trials = len(sr_values)
    sharpe_variance = float(sr_values.var(ddof=1)) if n_trials > 1 else 0.0

    best_rets = np.asarray(period_returns_by_trial[best_trial])
    sr_hat = sharpes[best_trial]
    n_obs = len(best_rets)
    skewness = float(_skew(best_rets))
    kurt_raw = float(_kurtosis(best_rets, fisher=False))  # raw (not excess) kurtosis — 3.0 for normal

    sr_benchmark = expected_max_sharpe_under_null(n_trials, sharpe_variance)
    dsr = probabilistic_sharpe_ratio(sr_hat, sr_benchmark, n_obs, skewness, kurt_raw)

    return {
        "best_trial": best_trial, "sr_hat": float(sr_hat), "n_trials": n_trials,
        "sharpe_variance_across_trials": sharpe_variance, "sr_benchmark_expected_max_under_null": sr_benchmark,
        "skewness": skewness, "kurtosis_raw": kurt_raw, "n_obs": n_obs, "dsr": dsr,
        "trial_sharpes": sharpes,
    }


def probability_of_backtest_overfitting(returns: pd.DataFrame, n_splits: int = 8) -> dict:
    """Combinatorially Symmetric Cross-Validation. `returns`: T periods
    (rows) x N trials/strategies (columns), all evaluated over the SAME
    time periods — exactly this project's 5-method, 24-period backtest.

    Splits the T periods into `n_splits` contiguous, equal-sized blocks.
    For every way of choosing half the blocks as "in-sample" (IS) and the
    rest as "out-of-sample" (OOS) — C(n_splits, n_splits/2) combinations —
    finds whichever strategy has the best IS Sharpe, then checks that same
    strategy's OOS rank among all strategies. PBO = the fraction of
    combinations where the IS-best strategy fell at or below the OOS
    median — i.e., how often picking the in-sample winner would have been
    the wrong call. 0.5 is what pure noise (no real skill differences)
    looks like; well below 0.5 means the selection is actually finding
    real, transferable skill.
    """
    if n_splits % 2 != 0:
        raise ValueError("n_splits must be even (need to split into two equal halves)")
    t, n = returns.shape
    if t % n_splits != 0:
        raise ValueError(f"{t} periods not evenly divisible by n_splits={n_splits}")
    block_size = t // n_splits
    blocks = [returns.iloc[i * block_size:(i + 1) * block_size] for i in range(n_splits)]

    def sharpe(df_slice: pd.DataFrame) -> pd.Series:
        std = df_slice.std(ddof=1)
        return df_slice.mean() / std.replace(0, np.nan)

    logits = []
    half = n_splits // 2
    for is_idx in combinations(range(n_splits), half):
        oos_idx = [i for i in range(n_splits) if i not in is_idx]
        is_data = pd.concat([blocks[i] for i in is_idx])
        oos_data = pd.concat([blocks[i] for i in oos_idx])

        is_sharpe = sharpe(is_data)
        best = is_sharpe.idxmax()
        if pd.isna(is_sharpe[best]):
            continue

        oos_sharpe = sharpe(oos_data)
        rank = oos_sharpe.rank(pct=True)[best]  # in (0, 1]; 1.0 = best OOS performer
        rank = min(max(rank, 1e-6), 1 - 1e-6)    # keep logit finite
        logit = np.log(rank / (1 - rank))
        logits.append(logit)

    logits = np.array(logits)
    pbo = float(np.mean(logits < 0)) if len(logits) else float("nan")
    return {"pbo": pbo, "n_combinations": len(logits), "n_splits": n_splits,
            "logits_mean": float(logits.mean()) if len(logits) else float("nan")}
