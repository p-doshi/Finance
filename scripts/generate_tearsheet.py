#!/usr/bin/env python3
"""HTML tearsheets via quantstats — the real, standard tool for this
(docs/methodology.md §7's tool survey), not a reimplementation. One
tearsheet per method: cumulative return, drawdown underwater plot, rolling
Sharpe/Sortino, monthly-return heatmap, and SPY-benchmark comparison
(alpha/beta/tracking error), all in one file.

quantstats expects a pandas Series indexed by date; this project's
walk-forward periods are ~monthly (21 trading days), not daily, so the
series built here is monthly, with `periods_per_year` passed explicitly
wherever quantstats needs the annualization factor rather than letting it
assume daily data.

Run after scripts/run_backtest.py (reuses the same walk-forward setup):
    .venv/bin/python scripts/generate_tearsheet.py
"""
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless — no display backend available/needed

import numpy as np
import pandas as pd
import quantstats as qs

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from portfolio_pipeline.research.backtest import walk_forward
from portfolio_pipeline.research.optimizers import equal_weight, max_sharpe_weight, risk_parity_weight

TICKERS = ["NVDA", "JNJ", "KO", "PG", "WMT", "VZ", "XOM", "RY", "ENB", "UL", "NVO", "ASML"]
RF = 0.0426
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"
WINDOW, REBAL_EVERY, COST_BPS = 756, 21, 10.0
PERIODS_PER_YEAR = 252 / REBAL_EVERY


def load_log_returns(tickers):
    series = {}
    for t in tickers:
        with open(DATA_DIR / f"{t}.json") as f:
            d = json.load(f)
        s = pd.Series({r["t"]: r["a"] for r in d["data"]}, name=t)
        s.index = pd.to_datetime(s.index)
        series[t] = s.sort_index()
    prices = pd.DataFrame(series).dropna(how="any")
    return np.log(prices / prices.shift(1)).dropna()


def to_series(result) -> pd.Series:
    return pd.Series(np.expm1(result.net_period_returns), index=pd.to_datetime(result.dates))


def main():
    log_ret = load_log_returns(TICKERS)
    spy_log_ret = load_log_returns(["SPY"])["SPY"]

    methods = {
        "equal_weight": lambda trailing: equal_weight(len(TICKERS)),
        "risk_parity": lambda trailing: risk_parity_weight(trailing.cov().values * 252),
        "max_sharpe": lambda trailing: max_sharpe_weight(
            trailing.cov().values * 252, trailing.mean().values * 252, RF),
    }

    RESULTS_DIR.mkdir(exist_ok=True)
    for name, fn in methods.items():
        res = walk_forward(log_ret, fn, window=WINDOW, rebal_every=REBAL_EVERY, cost_bps=COST_BPS, method_name=name)
        returns = to_series(res)

        # benchmark: SPY's simple return over the same holding periods, same dates
        bench_vals = []
        for i, d in enumerate(res.dates):
            idx = spy_log_ret.index.get_loc(d)
            j = spy_log_ret.index.get_loc(res.dates[i + 1]) if i + 1 < len(res.dates) else len(spy_log_ret)
            bench_vals.append(np.expm1(spy_log_ret.iloc[idx:j].sum()))
        benchmark = pd.Series(bench_vals, index=returns.index)

        out_path = RESULTS_DIR / f"tearsheet_{name}.html"
        qs.reports.html(
            returns, benchmark=benchmark, output=str(out_path),
            title=f"{name} — walk-forward, {WINDOW}d window, {COST_BPS}bps cost (monthly periods, not daily)",
            periods_per_year=PERIODS_PER_YEAR,
        )
        print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
