#!/usr/bin/env python3
"""Pull 5 years of daily adjusted-close history for the watchlist, with
validation and point-in-time storage. Run from the repo root:

    .venv/bin/python scripts/fetch_prices.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from portfolio_pipeline.data.fetch import DataQualityError, fetch_and_store

TICKERS = ["NVDA", "JNJ", "KO", "PG", "WMT", "VZ", "XOM", "RY", "ENB", "UL", "NVO", "ASML"]

if __name__ == "__main__":
    data_dir = Path(__file__).resolve().parent.parent / "data"
    failures = []
    for t in TICKERS:
        try:
            rows = fetch_and_store(t, data_dir)
            print(f"{t}: {len(rows)} trading days, {rows[0].date} -> {rows[-1].date}")
        except DataQualityError as e:
            print(f"{t}: FAILED — {e}")
            failures.append(t)
        time.sleep(0.5)
    if failures:
        print(f"\n{len(failures)} ticker(s) failed validation: {failures}")
        sys.exit(1)
