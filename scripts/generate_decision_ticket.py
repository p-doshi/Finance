#!/usr/bin/env python3
"""Phase 3: the decision layer. Reads your actual holdings (entered by
hand in portfolio_state.json -- no safe programmatic read path into
Wealthsimple either, see docs/methodology.md §0), computes fresh risk-
parity target weights from the latest data, and prints exactly what to
buy/sell in whole shares. Prints a trade ticket. Submits nothing, ever.

First run: copy portfolio_state.example.json to portfolio_state.json
(gitignored -- it's your real account data) and fill in your real cash
and share counts. Until you do, this runs against the all-zero template
so the script itself is still checkable -- the output will clearly show
it's not real.

Run: .venv/bin/python scripts/generate_decision_ticket.py
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from portfolio_pipeline.research.optimizers import risk_parity_weight
from portfolio_pipeline.decision.trade_ticket import load_holdings, generate_trade_ticket

TICKERS = ["NVDA", "JNJ", "KO", "PG", "WMT", "VZ", "XOM", "RY", "ENB", "UL", "NVO", "ASML"]
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ROOT = Path(__file__).resolve().parent.parent
WINDOW_DAYS = 756
DRIFT_BAND = 0.02  # don't bother trading a name whose dollar drift is under 2% of total portfolio value


def load_log_returns_and_latest_price(ticker: str) -> tuple[pd.Series, float]:
    d = json.load(open(DATA_DIR / f"{ticker}.json"))
    s = pd.Series({r["t"]: r["a"] for r in d["data"]}, name=ticker)
    s.index = pd.to_datetime(s.index)
    s = s.sort_index()
    latest_price = float(s.iloc[-1])
    log_ret = np.log(s / s.shift(1)).dropna()
    return log_ret, latest_price


def main():
    holdings_path = ROOT / "portfolio_state.json"
    if not holdings_path.exists():
        print("No portfolio_state.json found -- using the all-zero template (portfolio_state.example.json).")
        print("Copy it to portfolio_state.json and fill in your real holdings/cash for a real ticket.\n")
        holdings_path = ROOT / "portfolio_state.example.json"
    holdings = load_holdings(holdings_path)

    series, latest_prices = {}, {}
    for t in TICKERS:
        log_ret, price = load_log_returns_and_latest_price(t)
        series[t] = log_ret
        latest_prices[t] = price
    log_ret_df = pd.concat(series, axis=1, join="inner").tail(WINDOW_DAYS)
    cov = log_ret_df.cov().values * 252
    target_w = risk_parity_weight(cov)
    target_weights = dict(zip(TICKERS, target_w.tolist()))

    print(f"Latest prices (most recent close on file):")
    for t in TICKERS:
        print(f"  {t:6} ${latest_prices[t]:>9.2f}")

    print(f"\nFresh risk-parity target weights (3y window, recomputed now, not a stale table):")
    for t in TICKERS:
        print(f"  {t:6} {target_weights[t]*100:5.1f}%")

    ticket = generate_trade_ticket(holdings, target_weights, latest_prices, drift_band=DRIFT_BAND)

    print(f"\nTotal portfolio value (holdings + cash): ${ticket['total_value']:,.2f}")
    print(f"\nCurrent weights vs. target (drift_band={DRIFT_BAND*100:.0f}% of total value):")
    print(f"{'Ticker':8}{'Current':>10}{'Target':>10}{'Drift':>10}")
    for t in TICKERS:
        cur = ticket["current_weights"].get(t, 0.0)
        tgt = target_weights.get(t, 0.0)
        print(f"{t:8}{cur*100:9.1f}%{tgt*100:9.1f}%{(cur-tgt)*100:+9.1f}pp")

    print(f"\n--- TRADE TICKET (enter manually in Wealthsimple -- this script submits nothing) ---")
    if not ticket["trades"]:
        print("No trades needed: every position is within the drift band of its target.")
    else:
        for t in ticket["trades"]:
            print(f"  {t.action:4} {t.shares:4} {t.ticker:6} @ ${t.price:>9.2f}  (~${t.est_value:>10,.2f})")
    if ticket["buy_scale_applied"] < 1.0:
        print(f"\nNote: buys were scaled to {ticket['buy_scale_applied']*100:.0f}% of the target-implied size "
              f"-- available cash wasn't enough to fund the full rebalance.")
    print(f"\nCash before: ${ticket['cash_before']:,.2f}  ->  estimated cash after: ${ticket['cash_after']:,.2f}")
    print("\nThis is a decision, not an order. Nothing was submitted anywhere.")


if __name__ == "__main__":
    main()
