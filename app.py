"""Vercel Python service ("app" in vercel.json) backing the live portfolio
simulator in web/. Serves a fresh walk-forward backtest computed on
request from real price data.

Why fetch live instead of reading data/*.json: that directory is
gitignored (.gitignore) so a deployed function has nothing on disk to
read. This reuses the same stateless fetch_raw/validate functions the
rest of this project already uses for price history -- never
fetch_and_store, which writes to disk and has no business running in an
ephemeral serverless function.

GET /api/health
GET /api/portfolio?method=risk_parity
    -> {tickers, as_of_date, last_known_prices, method, equity_curve,
        final_weights, last_curve_value, rf}

Same TICKERS/RF/WINDOW/REBAL_EVERY/COST_BPS as scripts/export_web_data.py
-- this is the live-fetching twin of that script, not a separate design.

Local testing:
    pip install -r requirements.txt uvicorn
    uvicorn app:app --reload
    curl 'http://localhost:8000/api/portfolio?method=risk_parity'
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Response

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from portfolio_pipeline.data.fetch import DataQualityError, fetch_raw, validate  # noqa: E402
from portfolio_pipeline.research.backtest import walk_forward  # noqa: E402
from portfolio_pipeline.research.hrp import hrp_weight  # noqa: E402
from portfolio_pipeline.research.optimizers import (  # noqa: E402
    equal_weight,
    max_sharpe_weight,
    min_variance_weight,
    risk_parity_weight,
)

TICKERS = ["NVDA", "JNJ", "KO", "PG", "WMT", "VZ", "XOM", "RY", "ENB", "UL", "NVO", "ASML"]
RF = 0.0426
WINDOW, REBAL_EVERY, COST_BPS = 756, 21, 10.0

METHODS = {
    "equal_weight": lambda trailing: equal_weight(len(TICKERS)),
    "risk_parity": lambda trailing: risk_parity_weight(trailing.cov().values * 252),
    "hrp": lambda trailing: hrp_weight(trailing.cov().values * 252),
    "min_variance": lambda trailing: min_variance_weight(trailing.cov().values * 252),
    "max_sharpe": lambda trailing: max_sharpe_weight(
        trailing.cov().values * 252, trailing.mean().values * 252, RF
    ),
}

app = FastAPI()


def _load_log_returns_and_latest():
    series, latest_price, latest_date = {}, {}, None
    for ticker in TICKERS:
        payload = fetch_raw(ticker, range_="5Y", period="Daily")
        rows = validate(ticker, payload)
        s = pd.Series({r.date: r.adj_close for r in rows}, name=ticker)
        s.index = pd.to_datetime(s.index)
        s = s.sort_index()
        series[ticker] = s
        latest_price[ticker] = float(s.iloc[-1])
        latest_date = s.index[-1]
    prices = pd.DataFrame(series).dropna(how="any")
    log_ret = np.log(prices / prices.shift(1)).dropna()
    return log_ret, latest_price, str(latest_date.date())


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/portfolio")
def portfolio(method: str = "risk_parity", response: Response = None):
    if method not in METHODS:
        raise HTTPException(status_code=400, detail=f"unknown method, choose one of {list(METHODS)}")
    try:
        log_ret, latest_price, as_of_date = _load_log_returns_and_latest()
    except DataQualityError as e:
        raise HTTPException(status_code=502, detail=f"price data fetch failed: {e}") from e

    res = walk_forward(
        log_ret, METHODS[method], window=WINDOW, rebal_every=REBAL_EVERY, cost_bps=COST_BPS, method_name=method
    )
    equity = 10_000.0 * np.exp(np.cumsum(res.net_period_returns))
    curve = [{"date": str(res.dates[0].date()), "value": 10_000.0}]
    curve += [{"date": str(d.date()), "value": round(float(v), 2)} for d, v in zip(res.dates, equity)]
    final_weights = dict(zip(TICKERS, [round(float(w), 6) for w in res.weights[-1]]))

    # daily-close-based backtest doesn't need recomputing on every request;
    # cache at Vercel's edge so simulator traffic doesn't hammer the upstream
    # price API this reads from.
    if response is not None:
        response.headers["Cache-Control"] = "s-maxage=3600, stale-while-revalidate=7200"

    return {
        "tickers": TICKERS,
        "as_of_date": as_of_date,
        "last_known_prices": latest_price,
        "method": method,
        "equity_curve": curve,
        "final_weights": final_weights,
        "last_curve_value": curve[-1]["value"],
        "rf": RF,
    }
