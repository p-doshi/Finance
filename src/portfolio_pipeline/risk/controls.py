"""Position-level risk controls: a cap on any single name's weight, and
volatility targeting that scales exposure down (never up — see docstring)
toward cash when realized volatility runs hot.

Neither of these improves expected return; both exist to bound how badly
a single bad name or a single bad regime can hurt, which is a different
job from anything research/optimizers.py or research/hrp.py do.
"""
from __future__ import annotations

import numpy as np


def cap_weights(weights: np.ndarray, max_weight: float, max_iter: int = 50) -> np.ndarray:
    """Caps any weight above `max_weight`, redistributing the excess
    proportionally among the names still under the cap, iterating because
    redistribution can push a previously-fine name over the cap too.
    Raises if `max_weight` is too small for `len(weights)` names to even
    sum to 1 (e.g. max_weight=0.05 with 10 names can reach at most 50%).

    Once a name is capped it stays capped for every later iteration (a
    monotonically-growing "capped" set, never reconsidered for more
    redistributed weight) — the first version of this function instead
    recomputed "under the cap" as just "not currently over" on every pass,
    which let a name sitting exactly at the cap from an earlier iteration
    receive more weight in a later one and go over again. Caught by
    `tests/test_risk_controls.py::test_cap_weights_requires_iteration_when_redistribution_creates_new_breach`."""
    n = len(weights)
    if max_weight * n < 1.0 - 1e-9:
        raise ValueError(f"max_weight={max_weight} is infeasible for {n} names "
                          f"(max possible total = {max_weight * n:.3f} < 1.0)")
    w = np.asarray(weights, dtype=float).copy()
    capped = np.zeros(n, dtype=bool)
    for _ in range(max_iter):
        newly_over = (~capped) & (w > max_weight + 1e-12)
        if not newly_over.any():
            break
        excess = (w[newly_over] - max_weight).sum()
        w[newly_over] = max_weight
        capped |= newly_over
        free = ~capped
        free_sum = w[free].sum()
        if free_sum <= 0:
            # every name is now at the cap -- nothing left to redistribute into
            break
        w[free] += excess * (w[free] / free_sum)
    return w


def volatility_target_scale(realized_vol: float, target_vol: float, max_leverage: float = 1.0) -> float:
    """Fraction of the portfolio to hold in the risky weights (the rest
    sits in cash, 0 return, 0 vol) to bring realized volatility toward
    `target_vol`. Capped at `max_leverage` (1.0 by default) because a real
    retail brokerage account has no margin to scale risky exposure above
    100% the way a levered institutional risk-parity fund can (AQR's own
    "Understanding Risk Parity" white paper, docs/methodology.md §7,
    explicitly leverages up in calm regimes — this project deliberately
    does not, since that isn't available to the account this is built for).
    Floored at 0 (never short cash)."""
    if realized_vol <= 0:
        return max_leverage
    scale = target_vol / realized_vol
    return float(np.clip(scale, 0.0, max_leverage))
