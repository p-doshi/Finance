#!/usr/bin/env python3
"""Last item on the original roadmap: paper-trade validation. Pulls real
account state from Alpaca's paper-trading API (fake money — see
execution/alpaca_paper.py's docstring on why this is the one place in
this project that submits actual orders), compares it against freshly
recomputed risk-parity targets, and — only with --execute — submits the
resulting trades to the PAPER account. Default is dry-run: print the
ticket, submit nothing.

Needs a free Alpaca paper-trading account and API keys as environment
variables (ALPACA_API_KEY_ID, ALPACA_API_SECRET_KEY) — sign up at
alpaca.markets. Without them, this prints setup instructions and exits
cleanly rather than crashing.

Pricing uses this project's own daily-close data (same source as every
other script here), not Alpaca's live quotes — adequate for a strategy
validated on daily/monthly rebalancing, not meant for intraday precision.

Run: .venv/bin/python scripts/run_paper_trade_sync.py [--execute]
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from portfolio_pipeline.research.optimizers import risk_parity_weight
from portfolio_pipeline.decision.trade_ticket import generate_trade_ticket
from portfolio_pipeline.execution.alpaca_paper import AlpacaPaperClient, AlpacaCredentialsError, AlpacaAPIError

TICKERS = ["NVDA", "JNJ", "KO", "PG", "WMT", "VZ", "XOM", "RY", "ENB", "UL", "NVO", "ASML"]
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
WINDOW_DAYS = 756
DRIFT_BAND = 0.02


def load_log_returns_and_latest_price(ticker: str):
    d = json.load(open(DATA_DIR / f"{ticker}.json"))
    s = pd.Series({r["t"]: r["a"] for r in d["data"]}, name=ticker)
    s.index = pd.to_datetime(s.index)
    s = s.sort_index()
    return np.log(s / s.shift(1)).dropna(), float(s.iloc[-1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true",
                     help="actually submit the resulting trades to the Alpaca PAPER account "
                          "(fake money). Without this flag, only prints what would be done.")
    args = ap.parse_args()

    try:
        client = AlpacaPaperClient()
    except AlpacaCredentialsError as e:
        print(f"{e}\n")
        print("This script can't do anything without a paper account. To set one up:")
        print("  1. Sign up free at https://alpaca.markets")
        print("  2. Generate paper-trading API keys from your dashboard")
        print("  3. export ALPACA_API_KEY_ID=...  and  export ALPACA_API_SECRET_KEY=...")
        print("  4. Re-run this script.")
        sys.exit(0)

    try:
        account = client.get_account()
        positions = client.get_positions()
    except AlpacaAPIError as e:
        print(f"Alpaca API call failed: {e}")
        sys.exit(1)

    print(f"Paper account equity: ${float(account['equity']):,.2f}  "
          f"cash: ${float(account['cash']):,.2f}  buying power: ${float(account['buying_power']):,.2f}")

    holdings = {
        "cash": float(account["cash"]),
        "positions": {p["symbol"]: int(float(p["qty"])) for p in positions if p["symbol"] in TICKERS},
    }

    series, latest_prices = {}, {}
    for t in TICKERS:
        log_ret, price = load_log_returns_and_latest_price(t)
        series[t] = log_ret
        latest_prices[t] = price
    log_ret_df = pd.concat(series, axis=1, join="inner").tail(WINDOW_DAYS)
    target_weights = dict(zip(TICKERS, risk_parity_weight(log_ret_df.cov().values * 252).tolist()))

    ticket = generate_trade_ticket(holdings, target_weights, latest_prices, drift_band=DRIFT_BAND)

    print(f"\nTotal value (paper account): ${ticket['total_value']:,.2f}")
    if not ticket["trades"]:
        print("No trades needed -- every position within the drift band.")
    else:
        for t in ticket["trades"]:
            print(f"  {t.action:4} {t.shares:4} {t.ticker:6} @ ${t.price:>9.2f}  (~${t.est_value:>10,.2f})")

    if not args.execute:
        print("\nDry run -- nothing submitted. Re-run with --execute to actually place these "
              "orders on the PAPER account (still fake money, never real).")
        return

    print("\nSubmitting to Alpaca PAPER account (fake money):")
    for t in ticket["trades"]:
        try:
            order = client.submit_order(t.ticker, qty=t.shares, side=t.action.lower())
            print(f"  {t.action} {t.shares} {t.ticker}: order {order['id']} status={order['status']}")
        except AlpacaAPIError as e:
            print(f"  {t.action} {t.shares} {t.ticker}: FAILED -- {e}")


if __name__ == "__main__":
    main()
