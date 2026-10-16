#!/usr/bin/env python3
"""Beta/52-week heuristic baseline. Figures verified manually against each
ticker's stockanalysis.com statistics page (and cross-checked for XOM's name
against three further sources) — see docs/methodology.md for the full
verification note and date.
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from portfolio_pipeline.research.optimizers import inverse_beta_weight

DATA = {
    "NVDA": {"beta": 2.22, "chg52w": 20.79, "price": 217.39},
    "JNJ":  {"beta": 0.21, "chg52w": 34.06, "price": 255.67},
    "KO":   {"beta": 0.32, "chg52w": 37.00, "price": 92.43},
    "PG":   {"beta": 0.38, "chg52w": 5.83,  "price": 158.01},
    "WMT":  {"beta": 0.58, "chg52w": 10.61, "price": 118.60},
    "VZ":   {"beta": 0.25, "chg52w": 11.07, "price": 44.84},
    "XOM":  {"beta": 0.21, "chg52w": 55.56, "price": 174.63},
    "RY":   {"beta": 0.91, "chg52w": 34.76, "price": 196.19},
    "ENB":  {"beta": 0.80, "chg52w": -1.60, "price": 46.82},
    "UL":   {"beta": 0.46, "chg52w": -5.37, "price": 64.94},
    "NVO":  {"beta": 0.38, "chg52w": -30.17,"price": 39.53},
    "ASML": {"beta": 1.30, "chg52w": 66.65, "price": 1638.39},
}

if __name__ == "__main__":
    tickers = list(DATA.keys())
    betas = np.array([DATA[t]["beta"] for t in tickers])
    weights = inverse_beta_weight(betas)

    print(f"{'Ticker':6}{'Beta':>7}{'52wChg%':>10}{'InvBetaWt%':>12}")
    for t, w in zip(tickers, weights):
        print(f"{t:6}{DATA[t]['beta']:>7.2f}{DATA[t]['chg52w']:>10.2f}{w*100:>12.1f}")
    print("\nSum of weights:", round(float(weights.sum()) * 100, 2))

    results_dir = Path(__file__).resolve().parent.parent / "results"
    results_dir.mkdir(exist_ok=True)
    with open(results_dir / "inverse_beta_weights.json", "w") as f:
        json.dump({"data": DATA, "weights": {t: round(float(w) * 100, 1) for t, w in zip(tickers, weights)}}, f, indent=2)
