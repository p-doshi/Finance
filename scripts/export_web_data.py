#!/usr/bin/env python3
"""Exports everything the live web simulator (web/) needs: the real
walk-forward equity curve per method (not currently saved anywhere —
backtest_output.json only keeps summary stats), each method's final
(most-recently-rebalanced) weights, and the last known close price per
ticker as of this data pull. The web app's live-quotes API applies live
price *ratios* against these last-known prices to extend each method's
curve in real time, so the historical part is exactly the already-
validated backtest and the live part is a transparent, checkable
extension of it — never a separately-fabricated number.

Run after scripts/run_backtest.py (reuses the same setup):
    .venv/bin/python scripts/export_web_data.py
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

TICKERS = ["NVDA", "JNJ", "KO", "PG", "WMT", "VZ", "XOM", "RY", "ENB", "UL", "NVO", "ASML"]
RF = 0.0426
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
WEB_DATA_DIR = Path(__file__).resolve().parent.parent / "web" / "data"
WINDOW, REBAL_EVERY, COST_BPS = 756, 21, 10.0


def load_log_returns_and_latest():
    series, latest_price, latest_date = {}, {}, None
    for t in TICKERS:
        with open(DATA_DIR / f"{t}.json") as f:
            d = json.load(f)
        s = pd.Series({r["t"]: r["a"] for r in d["data"]}, name=t)
        s.index = pd.to_datetime(s.index)
        s = s.sort_index()
        series[t] = s
        latest_price[t] = float(s.iloc[-1])
        latest_date = s.index[-1]
    prices = pd.DataFrame(series).dropna(how="any")
    log_ret = np.log(prices / prices.shift(1)).dropna()
    return log_ret, latest_price, str(latest_date.date())


def main():
    log_ret, latest_price, latest_date = load_log_returns_and_latest()
    n = len(TICKERS)

    methods = {
        "equal_weight": lambda trailing: equal_weight(n),
        "risk_parity": lambda trailing: risk_parity_weight(trailing.cov().values * 252),
        "hrp": lambda trailing: hrp_weight(trailing.cov().values * 252),
        "min_variance": lambda trailing: min_variance_weight(trailing.cov().values * 252),
        "max_sharpe": lambda trailing: max_sharpe_weight(
            trailing.cov().values * 252, trailing.mean().values * 252, RF),
    }

    out_methods = {}
    for name, fn in methods.items():
        res = walk_forward(log_ret, fn, window=WINDOW, rebal_every=REBAL_EVERY, cost_bps=COST_BPS, method_name=name)
        equity = 10_000.0 * np.exp(np.cumsum(res.net_period_returns))  # $10k baseline, frontend rescales linearly
        curve = [{"date": str(d.date()), "value": round(float(v), 2)}
                 for d, v in zip(res.dates, equity)]
        # prepend the actual start (t=0, before the first period's return) so the
        # chart's first point is genuinely $10,000, not already-grown
        curve = [{"date": str(res.dates[0].date()), "value": 10_000.0}] + curve
        final_weights = dict(zip(TICKERS, [round(float(w), 6) for w in res.weights[-1]]))
        out_methods[name] = {
            "equity_curve": curve,
            "final_weights": final_weights,
            "last_curve_value": curve[-1]["value"],
        }
        print(f"{name}: {len(curve)} curve points, final value ${curve[-1]['value']:,.2f}, "
              f"final weights sum={sum(final_weights.values()):.4f}")

    out = {
        "tickers": TICKERS,
        "as_of_date": latest_date,
        "last_known_prices": latest_price,
        "methods": out_methods,
        "rf": RF,
    }

    WEB_DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_path = WEB_DATA_DIR / "backtest.json"
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nSaved {out_path}")


if __name__ == "__main__":
    main()
