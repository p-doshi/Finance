"""Forward-looking contribution forecasts via block-bootstrap resampling of
historical daily portfolio returns.

This is explicitly not a backtest and not a prediction. A backtest asks "how
would this allocation have performed over history" using history exactly
once, in order. This asks "if the next `horizon_days` statistically
resembles the trailing window of history, what range of outcomes is
plausible for this amount, under this allocation" -- by resampling
overlapping blocks of real historical daily returns (preserving their
autocorrelation and volatility clustering, same block-bootstrap approach
as backtest.block_bootstrap_ci) thousands of times and compounding each
path forward. The spread across simulated paths is the entire point: a
single point estimate would hide exactly the uncertainty this exists to
show, and nothing here should ever be collapsed to one number without its
band.

What this does not establish: that the next `horizon_days` will resemble
the trailing window at all. A regime change (rate shock, sector-specific
shift) invalidates the resampled distribution same as it would any
historical estimate -- this is a statement about the recent past's return
distribution, not a guarantee about the future.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class ForecastResult:
    horizon_days: int
    p10: np.ndarray
    p50: np.ndarray
    p90: np.ndarray
    n_sims: int
    block_size: int
    seed: int


def simulate_forward(
    daily_log_returns: pd.Series,
    *,
    initial_value: float,
    horizon_days: int = 252,
    n_sims: int = 2000,
    block_size: int = 5,
    seed: int = 0,
) -> ForecastResult:
    """Block-bootstrap `n_sims` forward paths of `horizon_days` trading days
    from `daily_log_returns` (a single, already portfolio-weighted daily log
    return series), compound `initial_value` through each path, and return
    the 10th/50th/90th percentile portfolio value at every day along the
    horizon. Deterministic given `seed`.
    """
    r = daily_log_returns.dropna().to_numpy()
    n = len(r)
    if n < block_size * 3:
        raise ValueError(f"too few return observations ({n}) to block-bootstrap with block_size={block_size}")

    rng = np.random.default_rng(seed)
    n_blocks_needed = int(np.ceil(horizon_days / block_size))
    paths = np.empty((n_sims, horizon_days))
    for s in range(n_sims):
        starts = rng.integers(0, n - block_size + 1, size=n_blocks_needed)
        sample = np.concatenate([r[st : st + block_size] for st in starts])[:horizon_days]
        paths[s] = initial_value * np.exp(np.cumsum(sample))

    return ForecastResult(
        horizon_days=horizon_days,
        p10=np.percentile(paths, 10, axis=0),
        p50=np.percentile(paths, 50, axis=0),
        p90=np.percentile(paths, 90, axis=0),
        n_sims=n_sims,
        block_size=block_size,
        seed=seed,
    )
