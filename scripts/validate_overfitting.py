#!/usr/bin/env python3
"""Deflated Sharpe Ratio and Probability of Backtest Overfitting, applied
to the actual situation this project is in: 5 weighting methods, each
walk-forward backtested over the same 24 out-of-sample periods (Phase 1).
Comparing 5 methods and reporting whichever looks best is a multiple-
comparison problem even when (as here) the comparison is already properly
out-of-sample -- picking the best-of-5 after the fact is still a form of
selection, and DSR/PBO are the standard corrections for exactly that.

Run after scripts/run_backtest.py (reuses the same walk-forward setup):
    .venv/bin/python scripts/validate_overfitting.py
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from portfolio_pipeline.research.backtest import walk_forward
from portfolio_pipeline.research.hrp import hrp_weight
from portfolio_pipeline.research.optimizers import (
    equal_weight,
    max_sharpe_weight,
    min_variance_weight,
    risk_parity_weight,
)
from portfolio_pipeline.research.overfitting import deflated_sharpe_ratio, probability_of_backtest_overfitting

TICKERS = ["NVDA", "JNJ", "KO", "PG", "WMT", "VZ", "XOM", "RY", "ENB", "UL", "NVO", "ASML"]
RF = 0.0426
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"
WINDOW, REBAL_EVERY, COST_BPS = 756, 21, 10.0


def load_log_returns():
    series = {}
    for t in TICKERS:
        with open(DATA_DIR / f"{t}.json") as f:
            d = json.load(f)
        s = pd.Series({r["t"]: r["a"] for r in d["data"]}, name=t)
        s.index = pd.to_datetime(s.index)
        series[t] = s.sort_index()
    prices = pd.DataFrame(series).dropna(how="any")
    return np.log(prices / prices.shift(1)).dropna()


def main():
    log_ret = load_log_returns()
    n = len(TICKERS)
    methods = {
        "equal_weight": lambda trailing: equal_weight(n),
        "risk_parity": lambda trailing: risk_parity_weight(trailing.cov().values * 252),
        "hrp": lambda trailing: hrp_weight(trailing.cov().values * 252),
        "min_variance": lambda trailing: min_variance_weight(trailing.cov().values * 252),
        "max_sharpe": lambda trailing: max_sharpe_weight(
            trailing.cov().values * 252, trailing.mean().values * 252, RF),
    }

    period_returns = {}
    for name, fn in methods.items():
        res = walk_forward(log_ret, fn, window=WINDOW, rebal_every=REBAL_EVERY, cost_bps=COST_BPS, method_name=name)
        period_returns[name] = res.net_period_returns

    returns_df = pd.DataFrame(period_returns)
    n_periods = len(returns_df)
    print(f"{n_periods} out-of-sample periods x {len(methods)} methods (5 trials, same evaluation set)\n")

    sharpes = {m: r.mean() / r.std(ddof=1) for m, r in period_returns.items()}
    best_method = max(sharpes, key=sharpes.get)
    print("Out-of-sample per-period Sharpe by method (un-annualized, raw period Sharpe):")
    for m, s in sorted(sharpes.items(), key=lambda kv: -kv[1]):
        marker = "  <- best observed" if m == best_method else ""
        print(f"  {m:14} {s:6.3f}{marker}")

    print(f"\n--- Deflated Sharpe Ratio for '{best_method}' (the observed best of 5 trials) ---")
    dsr_result = deflated_sharpe_ratio(period_returns, best_trial=best_method)
    print(f"Observed (per-period) Sharpe: {dsr_result['sr_hat']:.3f}")
    print(f"Expected max Sharpe under the null, given {dsr_result['n_trials']} trials "
          f"with Sharpe variance {dsr_result['sharpe_variance_across_trials']:.5f}: "
          f"{dsr_result['sr_benchmark_expected_max_under_null']:.3f}")
    print(f"Skew={dsr_result['skewness']:+.2f}  raw kurtosis={dsr_result['kurtosis_raw']:.2f} "
          f"(non-normality both adjusted for, not assumed away)")
    print(f"Deflated Sharpe Ratio: {dsr_result['dsr']:.3f}  "
          f"(probability the TRUE Sharpe exceeds the expected-best-of-{dsr_result['n_trials']}-trials "
          f"benchmark under the null of no real skill)")
    print("Rule of thumb: DSR > 0.95 is often treated as a reasonable bar given the correction; "
          f"{dsr_result['dsr']:.3f} should be read against that, not against the uncorrected Sharpe.")

    print("\n--- Probability of Backtest Overfitting (CSCV) ---")
    for n_splits in [8, 12] if n_periods % 12 == 0 else [8]:
        if n_periods % n_splits != 0:
            continue
        pbo_result = probability_of_backtest_overfitting(returns_df, n_splits=n_splits)
        block_size = n_periods // n_splits
        print(f"n_splits={n_splits} (block size {block_size} periods, {pbo_result['n_combinations']} "
              f"IS/OOS combinations): PBO = {pbo_result['pbo']:.3f}")
    print("0.5 = indistinguishable from picking the in-sample winner at random; well below 0.5 means "
          "the method-selection process is finding real, transferable skill, not noise.")
    print(f"Honest caveat: block size here is only {n_periods // 8}-{n_periods // 12} periods — a very "
          f"small sample to estimate each split's Sharpe from. Treat this as indicative given the data "
          f"available, not a precise estimate.")

    RESULTS_DIR.mkdir(exist_ok=True)
    out = {
        "n_periods": n_periods, "sharpes_by_method": sharpes, "best_method": best_method,
        "deflated_sharpe": dsr_result,
        "pbo": {n_splits: probability_of_backtest_overfitting(returns_df, n_splits=n_splits)
                for n_splits in [8, 12] if n_periods % n_splits == 0},
    }
    with open(RESULTS_DIR / "overfitting_validation.json", "w") as f:
        json.dump(out, f, indent=2, default=float)
    print(f"\nSaved {RESULTS_DIR / 'overfitting_validation.json'}")


if __name__ == "__main__":
    main()
