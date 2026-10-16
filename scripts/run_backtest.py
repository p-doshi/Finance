#!/usr/bin/env python3
"""Walk-forward, out-of-sample backtest of the four data-driven weighting
methods (equal-weight, risk parity, min-variance, max-Sharpe) over the full
5-year history, with transaction costs and block-bootstrap confidence
intervals. Inverse-beta is excluded here: it's driven by a live beta
snapshot, not something re-estimable from the trailing price window at each
rebalance date, so it has no walk-forward analog in this framework.

Run after scripts/fetch_prices.py:
    .venv/bin/python scripts/run_backtest.py
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from portfolio_pipeline.research.optimizers import (
    equal_weight,
    risk_parity_weight,
    min_variance_weight,
    max_sharpe_weight,
)
from portfolio_pipeline.research.backtest import walk_forward, block_bootstrap_ci

TICKERS = ["NVDA", "JNJ", "KO", "PG", "WMT", "VZ", "XOM", "RY", "ENB", "UL", "NVO", "ASML"]
RF = 0.0426
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"

WINDOW = 756          # 3y trailing estimation window, same base case as Phase 0
REBAL_EVERY = 21       # ~monthly
COST_BPS = 10.0        # assumed one-way cost; sensitivity checked separately below
PERIODS_PER_YEAR = 252 / REBAL_EVERY
BOOTSTRAP_SEED = 20261015  # fixed, so every CI here is exactly reproducible


def load_log_returns():
    series = {}
    for t in TICKERS:
        d = json.load(open(DATA_DIR / f"{t}.json"))
        s = pd.Series({r["t"]: r["a"] for r in d["data"]}, name=t)
        s.index = pd.to_datetime(s.index)
        series[t] = s.sort_index()
    prices = pd.DataFrame(series).dropna(how="any")
    return np.log(prices / prices.shift(1)).dropna()


def eq_fn(trailing):
    return equal_weight(len(TICKERS))


def rp_fn(trailing):
    cov = trailing.cov().values * 252
    return risk_parity_weight(cov)


def mv_fn(trailing):
    cov = trailing.cov().values * 252
    return min_variance_weight(cov)


def ms_fn(trailing):
    cov = trailing.cov().values * 252
    mu = trailing.mean().values * 252
    return max_sharpe_weight(cov, mu, RF)


def main():
    log_ret = load_log_returns()
    print(f"History: {len(log_ret)} trading days ({log_ret.index.min().date()} -> {log_ret.index.max().date()})")
    print(f"Window={WINDOW}d  rebal_every={REBAL_EVERY}d (~monthly)  cost={COST_BPS}bps one-way\n")

    methods = {"equal_weight": eq_fn, "risk_parity": rp_fn, "min_variance": mv_fn, "max_sharpe": ms_fn}
    results = {}
    for name, fn in methods.items():
        res = walk_forward(log_ret, fn, window=WINDOW, rebal_every=REBAL_EVERY, cost_bps=COST_BPS, method_name=name)
        results[name] = res

    n_periods = len(next(iter(results.values())).period_returns)
    print(f"Out-of-sample holding periods: {n_periods} (~{n_periods / 12:.1f} years)\n")

    print(f"{'Method':14}{'Ann.ret(net)':>14}{'Ann.vol':>10}{'Sharpe':>9}{'MaxDD':>9}{'AvgTurnover':>13}")
    summary = {}
    for name, res in results.items():
        ann_ret = res.annualized_return(PERIODS_PER_YEAR)
        ann_vol = res.annualized_vol(PERIODS_PER_YEAR)
        sharpe = res.sharpe(RF, PERIODS_PER_YEAR)
        mdd = res.max_drawdown()
        turn = res.avg_turnover()
        summary[name] = {"ann_return_net": ann_ret, "ann_vol": ann_vol, "sharpe": sharpe,
                          "max_drawdown": mdd, "avg_turnover": turn}
        print(f"{name:14}{ann_ret*100:13.2f}%{ann_vol*100:9.2f}%{sharpe:9.2f}{mdd*100:8.2f}%{turn*100:12.1f}%")

    print(f"\n--- Block-bootstrap {90}% CIs (seed={BOOTSTRAP_SEED}, {n_periods} periods, block=3 months) ---")
    print("Small sample (one historical regime) — treat these as wide, honest uncertainty bands, not tight estimates.")
    cis = {}
    for name, res in results.items():
        ci = block_bootstrap_ci(res.period_returns, periods_per_year=PERIODS_PER_YEAR,
                                 seed=BOOTSTRAP_SEED, block_size=3, ci=0.90)
        cis[name] = ci
        lo, hi = ci["ann_return_ci"]
        slo, shi = ci["sharpe_ci"]
        print(f"{name:14} ann.return {lo*100:6.1f}% to {hi*100:6.1f}%   Sharpe {slo:5.2f} to {shi:5.2f}")

    # Pairwise overlap check: are any two methods' CIs actually distinguishable?
    print("\n--- Sharpe CI overlap between methods (non-overlap = distinguishable at ~90%) ---")
    names = list(results.keys())
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = cis[names[i]]["sharpe_ci"], cis[names[j]]["sharpe_ci"]
            overlap = not (a[1] < b[0] or b[1] < a[0])
            print(f"{names[i]:14} vs {names[j]:14} {'OVERLAP (not distinguishable)' if overlap else 'no overlap'}")

    # Transaction-cost sensitivity for the two methods people would actually consider trading
    print("\n--- Transaction-cost sensitivity (risk_parity, max_sharpe) ---")
    for name in ["risk_parity", "max_sharpe"]:
        print(f"{name}:")
        for bps in [0.0, 10.0, 25.0, 50.0]:
            fn = methods[name]
            r = walk_forward(log_ret, fn, window=WINDOW, rebal_every=REBAL_EVERY, cost_bps=bps, method_name=name)
            print(f"  cost={bps:5.1f}bps  ann.return(net)={r.annualized_return(PERIODS_PER_YEAR)*100:6.2f}%  "
                  f"Sharpe={r.sharpe(RF, PERIODS_PER_YEAR):5.2f}")

    # Estimation-window robustness check: 756d leaves only ~24 out-of-sample
    # periods from 5y of history, which is a real small-sample limitation.
    # A shorter window trades noisier covariance/return estimates for more
    # out-of-sample periods (more statistical power) — report both rather
    # than picking whichever looks better.
    print("\n--- Window sensitivity: 2y (504d) estimation window instead of 3y (756d) ---")
    window_sensitivity = {}
    for w_days, w_label in [(504, "2y"), (756, "3y")]:
        row = {}
        for name, fn in methods.items():
            r = walk_forward(log_ret, fn, window=w_days, rebal_every=REBAL_EVERY, cost_bps=COST_BPS, method_name=name)
            row[name] = {"ann_return_net": r.annualized_return(PERIODS_PER_YEAR), "sharpe": r.sharpe(RF, PERIODS_PER_YEAR),
                         "n_periods": len(r.period_returns)}
        window_sensitivity[w_label] = row
        print(f"{w_label} window ({row['equal_weight']['n_periods']} periods):")
        for name, s in row.items():
            print(f"  {name:14} ann.return={s['ann_return_net']*100:6.2f}%  Sharpe={s['sharpe']:5.2f}")

    RESULTS_DIR.mkdir(exist_ok=True)
    out = {
        "params": {"window": WINDOW, "rebal_every": REBAL_EVERY, "cost_bps": COST_BPS,
                    "periods_per_year": PERIODS_PER_YEAR, "rf": RF, "bootstrap_seed": BOOTSTRAP_SEED,
                    "n_periods": n_periods},
        "summary": summary,
        "bootstrap_ci": cis,
        "window_sensitivity": window_sensitivity,
    }
    with open(RESULTS_DIR / "backtest_output.json", "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nSaved {RESULTS_DIR / 'backtest_output.json'}")


if __name__ == "__main__":
    main()
