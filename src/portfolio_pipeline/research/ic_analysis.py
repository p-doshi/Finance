"""Information Coefficient validation of a cross-sectional ranking signal
— Alphalens-style (§7's tool survey), checking whether Stage B's momentum
composite actually predicts forward returns, rather than just producing an
ordering and trusting it.

IC = the cross-sectional Spearman rank correlation between a signal
computed as of date T and the realized forward return from T to T+horizon.
Grinold & Kahn's Fundamental Law of Active Management: IR ≈ IC × sqrt(breadth)
— a signal's usefulness is its per-period skill (IC) times how many
roughly-independent times it can be applied (breadth). Practitioner
benchmark: IC ≈ 0.05 is considered good, 0.10 very good (both from the
research behind docs/methodology.md §7).

Every window used here requires a *complete* (no-gap) slice — `skipna=False`
on the sum, not pandas' default — because a partial window silently summed
around a gap (e.g. a ticker's pre-IPO NaNs) would produce a number that
looks like a return but isn't one.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import spearmanr


def trailing_window_return(log_returns: pd.DataFrame, as_of_idx: int, window: int) -> pd.Series:
    """Per-ticker simple return over `log_returns.iloc[as_of_idx-window+1 : as_of_idx+1]`
    — the `window` days up to and including `as_of_idx`. NaN for any ticker
    missing even one day in that span (see module docstring)."""
    start = as_of_idx - window + 1
    if start < 0:
        return pd.Series(np.nan, index=log_returns.columns)
    window_slice = log_returns.iloc[start:as_of_idx + 1]
    log_sum = window_slice.sum(skipna=False)
    return np.expm1(log_sum)


def forward_window_return(log_returns: pd.DataFrame, as_of_idx: int, horizon: int) -> pd.Series:
    """Per-ticker simple return over the `horizon` days strictly after
    `as_of_idx` — the realized forward return the signal is checked against."""
    start, end = as_of_idx + 1, as_of_idx + 1 + horizon
    if end > len(log_returns):
        return pd.Series(np.nan, index=log_returns.columns)
    window_slice = log_returns.iloc[start:end]
    log_sum = window_slice.sum(skipna=False)
    return np.expm1(log_sum)


def composite_momentum_signal(log_returns: pd.DataFrame, as_of_idx: int,
                               windows: tuple[int, ...] = (63, 126, 252)) -> pd.Series:
    """Same construction as `research.screen.rank_universe`'s composite —
    equal-weighted average percentile rank across the given trailing
    windows — but evaluated as of an arbitrary historical index rather
    than always 'today', so it can be checked against what actually
    happened next."""
    pct_ranks = []
    for w in windows:
        raw = trailing_window_return(log_returns, as_of_idx, w)
        pct_ranks.append(raw.rank(pct=True, na_option="keep") * 100)
    return pd.concat(pct_ranks, axis=1).mean(axis=1, skipna=True)


def information_coefficient(signal: pd.Series, forward_return: pd.Series) -> tuple[float, int]:
    """Spearman rank correlation between signal and forward return, over
    tickers where both are non-null. Returns (ic, n_names); ic is NaN if
    fewer than 10 names have both — too few for a cross-sectional
    correlation to mean anything."""
    aligned = pd.concat([signal, forward_return], axis=1, join="inner").dropna()
    if len(aligned) < 10:
        return float("nan"), len(aligned)
    ic, _ = spearmanr(aligned.iloc[:, 0], aligned.iloc[:, 1])
    return float(ic), len(aligned)


def run_ic_study(
    log_returns: pd.DataFrame, *, signal_windows=(63, 126, 252), horizon: int = 21,
    snapshot_every: int = 63, min_lookback: int = 252,
) -> pd.DataFrame:
    """Walks forward through `log_returns`' date index at `snapshot_every`-day
    intervals (quarterly by default), computing the composite signal and
    the realized forward return at each snapshot, strictly separated in
    time (the signal at index i only uses data up to i; the forward return
    only uses data after i) — the same no-lookahead discipline as
    `research.backtest.walk_forward`.
    """
    n = len(log_returns)
    rows = []
    for as_of_idx in range(min_lookback, n - horizon, snapshot_every):
        signal = composite_momentum_signal(log_returns, as_of_idx, signal_windows)
        fwd = forward_window_return(log_returns, as_of_idx, horizon)
        ic, n_names = information_coefficient(signal, fwd)
        rows.append({"date": log_returns.index[as_of_idx], "ic": ic, "n_names": n_names})
    return pd.DataFrame(rows)


def summarize_ic(ic_df: pd.DataFrame) -> dict:
    """Mean IC, its standard error (treating snapshots as independent,
    which is an approximation — see docs/methodology.md, quarterly
    momentum snapshots are not fully independent bets), a t-stat, and the
    Grinold-Kahn IR approximation IC * sqrt(breadth)."""
    valid = ic_df["ic"].dropna()
    n = len(valid)
    if n < 2:
        return {"mean_ic": float("nan"), "se_ic": float("nan"), "t_stat": float("nan"),
                "ir_approx": float("nan"), "n_snapshots": n}
    mean_ic = float(valid.mean())
    se_ic = float(valid.std(ddof=1) / np.sqrt(n))
    t_stat = mean_ic / se_ic if se_ic > 0 else float("nan")
    ir_approx = mean_ic * np.sqrt(n)
    return {"mean_ic": mean_ic, "se_ic": se_ic, "t_stat": t_stat, "ir_approx": ir_approx, "n_snapshots": n}
