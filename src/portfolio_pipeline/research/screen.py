"""Stage B: rank the Stage A screened universe using the deep history
Stage C's fetch step pulled. Every signal here is computed from the same
daily adjusted-close series the rest of this project uses — no second,
undocumented data source for the ranking itself.

Composite ranking is deliberately rank-based, not a raw-return or z-score
average: every return series in this project's 12-stock watchlist rejected
normality (Phase 1, docs/methodology.md), and nothing suggests the other
~4,000 names in this universe are better-behaved. A percentile-rank
composite doesn't assume a distribution shape and isn't dominated by a
handful of fat-tailed outliers the way an average of raw returns would be.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def compute_beta(stock_log_returns: pd.Series, market_log_returns: pd.Series) -> float | None:
    """OLS beta against the market series, computed transparently here
    rather than taken from a vendor — see docs/methodology.md on vendor
    beta's undisclosed methodology. Aligns on overlapping dates only;
    returns None if fewer than 60 overlapping observations (too little to
    trust a covariance estimate)."""
    aligned = pd.concat([stock_log_returns, market_log_returns], axis=1, join="inner").dropna()
    if len(aligned) < 60:
        return None
    s, m = aligned.iloc[:, 0].values, aligned.iloc[:, 1].values
    var_m = m.var(ddof=1)
    if var_m == 0:
        return None
    return float(np.cov(s, m, ddof=1)[0, 1] / var_m)


def trailing_simple_return(log_returns: pd.Series, window_days: int) -> float | None:
    if len(log_returns) < window_days:
        return None
    return float(np.expm1(log_returns.tail(window_days).sum()))


def annualized_vol(log_returns: pd.Series, window_days: int = 252) -> float | None:
    if len(log_returns) < window_days:
        return None
    return float(log_returns.tail(window_days).std(ddof=1) * np.sqrt(252))


def max_drawdown(log_returns: pd.Series, window_days: int = 252) -> float | None:
    if len(log_returns) < window_days:
        return None
    tail = log_returns.tail(window_days)
    curve = np.exp(np.cumsum(tail.values))
    running_max = np.maximum.accumulate(curve)
    return float((curve / running_max - 1.0).min())


def score_one(log_returns: pd.Series, market_log_returns: pd.Series) -> dict:
    return {
        "mom_3m": trailing_simple_return(log_returns, 63),
        "mom_6m": trailing_simple_return(log_returns, 126),
        "mom_12m": trailing_simple_return(log_returns, 252),
        "ann_vol": annualized_vol(log_returns, 252),
        "beta_vs_spy": compute_beta(log_returns, market_log_returns),
        "max_drawdown_1y": max_drawdown(log_returns, 252),
        "n_days": len(log_returns),
    }


def rank_universe(records: list[dict]) -> pd.DataFrame:
    """records: list of per-ticker dicts already containing the raw score_one()
    output plus identifying fields (ticker, country, exchange, name, sector).
    Composite = equal-weighted average percentile rank (0-100) across the
    three momentum horizons; a name missing a horizon (e.g. a recent IPO
    with <252 days of history) is ranked on whichever horizons it has
    rather than dropped outright, and `n_horizons_used` records how many —
    treat a composite built on 1 horizon as much weaker evidence than one
    built on 3."""
    df = pd.DataFrame(records)
    pct_cols = []
    for col in ["mom_3m", "mom_6m", "mom_12m"]:
        pct_col = f"{col}_pct"
        df[pct_col] = df[col].rank(pct=True, na_option="keep") * 100
        pct_cols.append(pct_col)
    df["n_horizons_used"] = df[pct_cols].notna().sum(axis=1)
    df["composite_rank"] = df[pct_cols].mean(axis=1, skipna=True)
    return df.sort_values("composite_rank", ascending=False, na_position="last").reset_index(drop=True)
