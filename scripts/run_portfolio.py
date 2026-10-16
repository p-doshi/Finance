#!/usr/bin/env python3
"""Load the watchlist's price history, build the 1y/3y/5y covariance
matrices, and report all five weighting methods plus the window-sensitivity
check, using the shared optimizer functions in portfolio_pipeline.research.
Run after scripts/fetch_prices.py. Risk-free rate and data-source details:
docs/methodology.md.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import jarque_bera, kurtosis, skew

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from portfolio_pipeline.research.optimizers import (
    equal_weight,
    inverse_beta_weight,
    risk_parity_weight,
    min_variance_weight,
    max_sharpe_weight,
    portfolio_stats,
)

TICKERS = ["NVDA", "JNJ", "KO", "PG", "WMT", "VZ", "XOM", "RY", "ENB", "UL", "NVO", "ASML"]
BETAS = np.array([2.22, 0.21, 0.32, 0.38, 0.58, 0.25, 0.21, 0.91, 0.80, 0.46, 0.38, 1.30])
RF = 0.0426  # 3-month Treasury, constant maturity, Fed H.15, 2026-10-13 — see docs/methodology.md
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"


def load_prices():
    series = {}
    for t in TICKERS:
        d = json.load(open(DATA_DIR / f"{t}.json"))
        s = pd.Series({r["t"]: r["a"] for r in d["data"]}, name=t)
        s.index = pd.to_datetime(s.index)
        series[t] = s.sort_index()
    prices = pd.DataFrame(series).dropna(how="any")
    return prices


def main():
    prices = load_prices()
    log_ret = np.log(prices / prices.shift(1)).dropna()
    print(f"Common trading days: {len(prices)} ({prices.index.min().date()} -> {prices.index.max().date()})")

    print("\n--- Return distribution checks (full history) ---")
    for t in TICKERS:
        r = log_ret[t].values
        _, p = jarque_bera(r)
        print(f"{t:6} skew={skew(r):+.2f}  excess_kurt={kurtosis(r):+.2f}  JB p={p:.4f}")

    windows = {"1y": 252, "3y": 756, "5y": len(log_ret)}
    cov_w, mu_w = {}, {}
    print("\n--- Covariance conditioning across windows ---")
    for tag, nd in windows.items():
        r = log_ret.tail(nd)
        cov = r.cov().values * 252
        corr = r.corr().values
        eig = np.linalg.eigvalsh(corr)
        cov_w[tag] = cov
        mu_w[tag] = r.mean().values * 252
        print(f"{tag}: n={nd}  cond={eig.max()/eig.min():.1f}  min_eig={eig.min():.3f}")

    n = len(TICKERS)
    cov3, mu3 = cov_w["3y"], mu_w["3y"]
    methods = {
        "equal_weight": equal_weight(n),
        "inverse_beta": inverse_beta_weight(BETAS),
        "risk_parity": risk_parity_weight(cov3),
        "min_variance": min_variance_weight(cov3),
        "max_sharpe": max_sharpe_weight(cov3, mu3, RF),
    }

    print("\n--- Weights by method (3y base case) ---")
    print(f"{'Ticker':7}" + "".join(f"{m:>14}" for m in methods))
    for i, t in enumerate(TICKERS):
        print(f"{t:7}" + "".join(f"{methods[m][i]*100:13.1f}%" for m in methods))

    print("\n--- Portfolio stats (evaluated on 3y window) ---")
    stats = {}
    for m, w in methods.items():
        s = portfolio_stats(w, cov3, mu3, RF)
        stats[m] = s
        print(f"{m:14} ret={s['ret']*100:6.2f}%  vol={s['vol']*100:6.2f}%  "
              f"sharpe={s['sharpe']:5.2f}  n_eff={s['n_effective']:4.1f}")

    print("\n--- Max-Sharpe window sensitivity ---")
    ms_w = {tag: max_sharpe_weight(cov_w[tag], mu_w[tag], RF) for tag in windows}
    print(f"{'Ticker':7}" + "".join(f"{tag:>10}" for tag in windows))
    for i, t in enumerate(TICKERS):
        print(f"{t:7}" + "".join(f"{ms_w[tag][i]*100:9.1f}%" for tag in windows))

    RESULTS_DIR.mkdir(exist_ok=True)
    out = {
        "tickers": TICKERS,
        "weights": {m: w.tolist() for m, w in methods.items()},
        "stats": stats,
        "maxsharpe_window_sensitivity": {tag: w.tolist() for tag, w in ms_w.items()},
    }
    with open(RESULTS_DIR / "run_portfolio_output.json", "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nSaved {RESULTS_DIR / 'run_portfolio_output.json'}")


if __name__ == "__main__":
    main()
