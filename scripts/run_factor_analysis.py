#!/usr/bin/env python3
"""Fama-French 3- and 5-factor regression for the 12-stock watchlist,
using Kenneth French's real published factor returns (data.fetch_factors),
not reconstructed from fundamentals this project doesn't have.

Run: .venv/bin/python scripts/run_factor_analysis.py
"""
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from portfolio_pipeline.data.fetch_factors import fetch_ff3_daily, fetch_ff5_daily
from portfolio_pipeline.research.factor_model import annualized_alpha, factor_regression

TICKERS = ["NVDA", "JNJ", "KO", "PG", "WMT", "VZ", "XOM", "RY", "ENB", "UL", "NVO", "ASML"]
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"
WINDOW_DAYS = 756  # 3y, same base case as Phase 0


def load_simple_returns(ticker: str) -> pd.Series:
    with open(DATA_DIR / f"{ticker}.json") as f:
        d = json.load(f)
    s = pd.Series({r["t"]: r["a"] for r in d["data"]}, name=ticker)
    s.index = pd.to_datetime(s.index)
    s = s.sort_index()
    return s.pct_change().dropna()  # simple returns, matching the Fama-French factors' own convention


def run_for(ticker: str, factors_only: pd.DataFrame, rf: pd.Series, label: str) -> dict:
    stock_ret = load_simple_returns(ticker).tail(WINDOW_DAYS)
    aligned_rf = rf.reindex(stock_ret.index).dropna()
    excess = (stock_ret - aligned_rf).dropna()
    result = factor_regression(excess, factors_only)
    result["annualized_alpha"] = annualized_alpha(result)
    return result


def main():
    print("Fetching real Fama-French factor data (Dartmouth, Kenneth French Data Library)...")
    ff3 = fetch_ff3_daily()
    ff5 = fetch_ff5_daily()
    print(f"FF3: {len(ff3)} days through {ff3.index.max().date()}")
    print(f"FF5: {len(ff5)} days through {ff5.index.max().date()}  "
          f"(both lag 'today' by the source's own update cadence -- not a bug, a real data-availability caveat)")

    RESULTS_DIR.mkdir(exist_ok=True)
    factors_dir = DATA_DIR / "factors"
    factors_dir.mkdir(exist_ok=True)
    ff3.to_csv(factors_dir / "ff3_daily.csv")
    ff5.to_csv(factors_dir / "ff5_daily.csv")

    all_results = {}
    for model_name, factors in [("FF3", ff3), ("FF5", ff5)]:
        rf = factors["RF"]
        factors_only = factors.drop(columns=["RF"])
        print(f"\n=== {model_name} regression (3y window, ending wherever ticker and factor history overlap) ===")
        print(f"{'Ticker':7}{'alpha(ann)':>11}{'Mkt-RF':>9}" +
              "".join(f"{c:>9}" for c in factors_only.columns[1:]) + f"{'R2':>7}{'n':>6}")
        model_results = {}
        for t in TICKERS:
            r = run_for(t, factors_only, rf, model_name)
            model_results[t] = r
            betas = r["coefficients"]
            beta_str = "".join(f"{betas[c]['coef']:9.2f}" for c in factors_only.columns)
            sig = "*" if betas["alpha"]["p"] < 0.05 else " "
            print(f"{t:7}{r['annualized_alpha']*100:10.1f}%{sig}{beta_str}{r['r_squared']:7.2f}{r['n_obs']:6}")
        all_results[model_name] = model_results

    print("\n* = alpha significant at p<0.05 (unadjusted for the 12-way multiple comparison -- "
          "see docs/methodology.md's Deflated Sharpe/PBO section for why that correction matters "
          "when scanning many names for a 'significant' result).")

    out = {}
    for model_name, model_results in all_results.items():
        out[model_name] = {t: {"coefficients": r["coefficients"], "r_squared": r["r_squared"],
                                 "n_obs": r["n_obs"], "annualized_alpha": r["annualized_alpha"]}
                             for t, r in model_results.items()}
    with open(RESULTS_DIR / "factor_analysis.json", "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nSaved {RESULTS_DIR / 'factor_analysis.json'}")


if __name__ == "__main__":
    main()
