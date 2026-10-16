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
GET /api/universe
    -> {as_of, count, rows: [{ticker, name, country, exchange, market_cap,
        price, day_change_pct, sector, volume, pe_ratio}, ...]} -- the full
       US+Canada liquid-equity universe (data.universe), for the Explore
       page's search/browse. One snapshot, edge-cached for 30 min; the
       frontend searches/filters it client-side rather than round-tripping
       per keystroke.
GET /api/stock/{ticker}
    -> {ticker, as_of, price, day_change_pct, high_52w, low_52w, series}
       -- works for any ticker stockanalysis.com covers, not just the
       12-name watchlist above.

Same TICKERS/RF/WINDOW/REBAL_EVERY/COST_BPS as scripts/export_web_data.py
-- this is the live-fetching twin of that script, not a separate design.

Local testing:
    pip install -e . uvicorn
    uvicorn app:app --reload
    curl 'http://localhost:8000/api/portfolio?method=risk_parity'
"""
from __future__ import annotations

import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Response

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from portfolio_pipeline.data.fetch import DataQualityError, fetch_raw, validate  # noqa: E402
from portfolio_pipeline.data.universe import fetch_full_universe, screen  # noqa: E402
from portfolio_pipeline.research.backtest import walk_forward  # noqa: E402
from portfolio_pipeline.research.hrp import hrp_weight  # noqa: E402
from portfolio_pipeline.research.optimizers import (  # noqa: E402
    equal_weight,
    max_sharpe_weight,
    min_variance_weight,
    risk_parity_weight,
)

# Real tickers look like AAPL, BRK.B, RY (TSX); this is a permissive but
# closed charset, not a format spec -- it exists only to stop arbitrary
# user input from reaching fetch_raw's unescaped URL format string, not to
# validate real ticker syntax.
_TICKER_RE = re.compile(r"^[A-Za-z0-9.\-]{1,10}$")

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


@app.get("/api/universe")
def universe(response: Response = None):
    try:
        rows = screen(fetch_full_universe())
    except DataQualityError as e:
        raise HTTPException(status_code=502, detail=f"universe fetch failed: {e}") from e

    if response is not None:
        # a full-market snapshot, not a per-user value -- cache hard at the
        # edge so search-page traffic doesn't refetch ~7,000 names per visitor
        response.headers["Cache-Control"] = "s-maxage=1800, stale-while-revalidate=3600"

    return {
        "as_of": datetime.now(timezone.utc).date().isoformat(),
        "count": len(rows),
        "rows": [
            {
                "ticker": r.ticker,
                "name": r.name,
                "country": r.country,
                "exchange": r.exchange,
                "market_cap": r.market_cap,
                "price": r.price,
                "day_change_pct": r.day_change_pct,
                "sector": r.sector,
                "volume": r.volume,
                "pe_ratio": r.pe_ratio,
            }
            for r in rows
        ],
    }


@app.get("/api/stock/{ticker}")
def stock_detail(ticker: str, range_: str = "1Y", response: Response = None):
    ticker = ticker.upper()
    if not _TICKER_RE.match(ticker):
        raise HTTPException(status_code=400, detail="invalid ticker format")
    try:
        payload = fetch_raw(ticker, range_=range_, period="Daily")
        # min_rows relaxed from validate()'s 200-day default -- this serves
        # any ticker a visitor searches for, including recent IPOs, not just
        # the curated mega-cap watchlist the default was calibrated for.
        # max_single_day_move relaxed too: this is a display chart, not an
        # input to a covariance matrix, so a real (if wild) move shouldn't
        # 404 the page -- see validate()'s docstring on that threshold.
        rows = validate(ticker, payload, min_rows=5, max_single_day_move=0.95)
    except DataQualityError as e:
        raise HTTPException(status_code=404, detail=f"{ticker}: {e}") from e

    latest = rows[-1]
    prev = rows[-2] if len(rows) > 1 else latest
    window_1y = rows[-252:] if len(rows) >= 252 else rows

    if response is not None:
        response.headers["Cache-Control"] = "s-maxage=300, stale-while-revalidate=900"

    return {
        "ticker": ticker,
        "as_of": latest.date,
        "price": latest.adj_close,
        "day_change_pct": round((latest.adj_close / prev.adj_close - 1) * 100, 4) if prev.adj_close else None,
        "high_52w": max(r.adj_close for r in window_1y),
        "low_52w": min(r.adj_close for r in window_1y),
        "series": [{"date": r.date, "close": r.adj_close, "volume": r.volume} for r in rows],
    }
