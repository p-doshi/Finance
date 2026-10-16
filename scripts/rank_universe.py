#!/usr/bin/env python3
"""Stage B: rank every screened-universe ticker that has price history on
disk (run scripts/fetch_universe_history.py first — this script only uses
whatever has already been fetched, so it's safe to run against a partial
pull too). Computes momentum (3/6/12mo), volatility, max drawdown, and beta
vs. SPY for each name, then a rank-based composite — see
portfolio_pipeline.research.screen for why rank-based, not raw-return.

Run: .venv/bin/python scripts/rank_universe.py
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from portfolio_pipeline.research.screen import score_one, rank_universe

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
RESULTS_DIR = ROOT / "results"


def data_path(ticker: str, country: str, exchange: str) -> Path:
    if country == "US":
        return DATA_DIR / f"{ticker}.json"
    return DATA_DIR / f"{exchange}_{ticker}.json"


def load_log_returns(path: Path) -> pd.Series:
    d = json.load(open(path))
    s = pd.Series({r["t"]: r["a"] for r in d["data"]})
    s.index = pd.to_datetime(s.index)
    s = s.sort_index()
    return np.log(s / s.shift(1)).dropna()


def main():
    spy_path = DATA_DIR / "SPY.json"
    if not spy_path.exists():
        print("SPY.json not found — fetch it first: "
              ".venv/bin/python -c \"from portfolio_pipeline.data.fetch import fetch_and_store; "
              "fetch_and_store('SPY', 'data')\"")
        sys.exit(1)
    market_returns = load_log_returns(spy_path)

    universe = json.load(open(RESULTS_DIR / "screened_universe.json"))
    records, missing = [], 0
    for entry in universe:
        ticker, country, exchange = entry["ticker"], entry["country"], entry["exchange"]
        path = data_path(ticker, country, exchange)
        if not path.exists():
            missing += 1
            continue
        try:
            log_ret = load_log_returns(path)
        except Exception:
            missing += 1
            continue
        scores = score_one(log_ret, market_returns)
        records.append({**entry, **scores})

    print(f"Ranking {len(records)} names with price history on disk ({missing} not yet fetched / unreadable).")
    df = rank_universe(records)

    RESULTS_DIR.mkdir(exist_ok=True)
    df.to_json(RESULTS_DIR / "universe_rankings.json", orient="records", indent=2)

    cols = ["ticker", "exchange", "name", "sector", "mom_3m", "mom_6m", "mom_12m",
            "ann_vol", "beta_vs_spy", "max_drawdown_1y", "n_horizons_used", "composite_rank"]
    full_history_only = df[df["n_horizons_used"] == 3]

    print(f"\n--- Top 20 by composite rank (full 3/6/12mo history only, n={len(full_history_only)}) ---")
    for _, r in full_history_only.head(20).iterrows():
        print(f"  {r.ticker:8} {r.exchange:5} rank={r.composite_rank:5.1f}  "
              f"3m={r.mom_3m*100:+6.1f}%  6m={r.mom_6m*100:+6.1f}%  12m={r.mom_12m*100:+6.1f}%  "
              f"vol={r.ann_vol*100:5.1f}%  beta={r.beta_vs_spy:+.2f}  {str(r['name'])[:35]}")

    print(f"\n--- Bottom 20 by composite rank ---")
    for _, r in full_history_only.tail(20).iterrows():
        print(f"  {r.ticker:8} {r.exchange:5} rank={r.composite_rank:5.1f}  "
              f"3m={r.mom_3m*100:+6.1f}%  6m={r.mom_6m*100:+6.1f}%  12m={r.mom_12m*100:+6.1f}%  "
              f"vol={r.ann_vol*100:5.1f}%  beta={r.beta_vs_spy:+.2f}  {str(r['name'])[:35]}")

    print(f"\nSaved {RESULTS_DIR / 'universe_rankings.json'} ({len(df)} total ranked names)")


if __name__ == "__main__":
    main()
