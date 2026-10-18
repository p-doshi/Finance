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
GET /api/news/{ticker}?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD&limit=20
    -> {source_errors, items: [{title, link, source, published_at,
        sentiment_compound, sentiment_label}]} -- three independent free
       sources (data.news.get_news): Yahoo RSS, Google News RSS (real
       historical search), SEC EDGAR (official per-company 8-K history).
       Sentiment is computed locally (VADER + a finance lexicon patch),
       not a vendor score -- see data/news.py's module docstring.
POST /api/forecast {holdings: {ticker: shares}, add_amount, distributions,
                     horizon_days}
    -> {as_of, current_value, current_weights, total_initial, dates,
        scenarios: {<distribution>: {weights, p10, p50, p90}}} -- a
       block-bootstrap forward simulation (research.forecast), not a
       backtest and not a prediction. See that module's docstring for what
       it does and does not establish.
POST /api/add-funds {holdings: {ticker: shares}, add_amount}
    -> {current_value, add_amount, total_value_after, current_weights,
        trades: [{ticker, action, shares, price, est_value}], cash_after}
       -- a concrete whole-share buy plan that puts new cash into your
       existing positions in their current proportions (decision.
       trade_ticket, already used/tested elsewhere in this project).
       Deliberately not a what-if comparison -- that's /api/forecast;
       this always targets "same split", the Wealthsimple-style
       auto-invest behavior.
GET /api/underdogs?min_cap=...&max_cap=...&limit=25
    -> {count_in_band, count_ranked, count_excluded, rows: [...]} --
       a transparent, rule-based value screen (ascending P/E) within a
       chosen market-cap band, same universe data as /api/universe.
POST /api/recommendations {holdings: {ticker: shares}}
    -> {current_value, current_weights, sector_weights, annualized_vol,
        flags: [{severity, title, detail}]} -- fixed-threshold concentration
       and volatility checks against real holdings, not a trained model
       (see the threshold constants' docstring for why not, for now).

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
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from portfolio_pipeline.data.fetch import DataQualityError, fetch_raw, validate  # noqa: E402
from portfolio_pipeline.data.news import get_news, news_item_to_dict  # noqa: E402
from portfolio_pipeline.data.universe import fetch_full_universe, screen  # noqa: E402
from portfolio_pipeline.decision.trade_ticket import current_weights as ticket_current_weights  # noqa: E402
from portfolio_pipeline.decision.trade_ticket import generate_trade_ticket  # noqa: E402
from portfolio_pipeline.research.backtest import walk_forward  # noqa: E402
from portfolio_pipeline.research.forecast import simulate_forward  # noqa: E402
from portfolio_pipeline.research.hrp import hrp_weight  # noqa: E402
from portfolio_pipeline.research.optimizers import (  # noqa: E402
    equal_weight,
    max_sharpe_weight,
    min_variance_weight,
    risk_parity_weight,
)
from portfolio_pipeline.research.screen import annualized_vol, compute_beta, max_drawdown  # noqa: E402

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

# Same optimizers as METHODS above, but parametrized by n (the holder's own
# number of positions) instead of closing over the fixed 12-name TICKERS --
# /api/forecast runs these against whatever tickers a visitor actually
# holds, not the curated watchlist.
FORECAST_METHOD_FNS = {
    "equal_weight": lambda trailing, n: equal_weight(n),
    "risk_parity": lambda trailing, n: risk_parity_weight(trailing.cov().values * 252),
    "hrp": lambda trailing, n: hrp_weight(trailing.cov().values * 252),
    "min_variance": lambda trailing, n: min_variance_weight(trailing.cov().values * 252),
    "max_sharpe": lambda trailing, n: max_sharpe_weight(
        trailing.cov().values * 252, trailing.mean().values * 252, RF
    ),
}


class ForecastRequest(BaseModel):
    holdings: dict[str, float]  # ticker -> shares (fractional allowed)
    add_amount: float = 0.0
    distributions: list[str] = ["same"]
    horizon_days: int = 252


class AddFundsRequest(BaseModel):
    holdings: dict[str, float]  # ticker -> shares
    add_amount: float


class RecommendationsRequest(BaseModel):
    holdings: dict[str, float]  # ticker -> shares


app = FastAPI()


def _load_log_returns_and_latest(tickers=TICKERS, *, min_rows=200, max_single_day_move=0.5):
    # defaults match validate()'s own, calibrated for the curated 12-name
    # watchlist; the custom-ticker path below passes the same relaxed
    # values used for /api/stock and /api/forecast instead, since an
    # arbitrary visitor-chosen name may be newly listed or more volatile
    # than this mega-cap watchlist.
    series, latest_price, latest_date = {}, {}, None
    for ticker in tickers:
        payload = fetch_raw(ticker, range_="5Y", period="Daily")
        rows = validate(ticker, payload, min_rows=min_rows, max_single_day_move=max_single_day_move)
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


MAX_CUSTOM_TICKERS = 20


@app.get("/api/portfolio")
def portfolio(method: str = "risk_parity", tickers: str = "", response: Response = None):
    if method not in METHODS:
        raise HTTPException(status_code=400, detail=f"unknown method, choose one of {list(METHODS)}")

    custom = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    if custom:
        if len(custom) < 2:
            raise HTTPException(status_code=400, detail="need at least 2 tickers to backtest a portfolio")
        if len(custom) > MAX_CUSTOM_TICKERS:
            raise HTTPException(status_code=400, detail=f"too many tickers (max {MAX_CUSTOM_TICKERS})")
        for t in custom:
            if not _TICKER_RE.match(t):
                raise HTTPException(status_code=400, detail=f"invalid ticker format: {t}")
        use_tickers = custom
        n = len(custom)
        weight_fn = {
            "equal_weight": lambda trailing: equal_weight(n),
            "risk_parity": lambda trailing: risk_parity_weight(trailing.cov().values * 252),
            "hrp": lambda trailing: hrp_weight(trailing.cov().values * 252),
            "min_variance": lambda trailing: min_variance_weight(trailing.cov().values * 252),
            "max_sharpe": lambda trailing: max_sharpe_weight(trailing.cov().values * 252, trailing.mean().values * 252, RF),
        }[method]
    else:
        use_tickers = TICKERS
        weight_fn = METHODS[method]

    try:
        if custom:
            # relaxed vs. the curated watchlist's defaults -- an arbitrary
            # visitor-chosen name may be newly listed or more volatile than
            # this project's mega-cap research watchlist (same reasoning as
            # /api/stock/{ticker} and /api/forecast).
            log_ret, latest_price, as_of_date = _load_log_returns_and_latest(
                use_tickers, min_rows=60, max_single_day_move=0.95
            )
        else:
            log_ret, latest_price, as_of_date = _load_log_returns_and_latest(use_tickers)
    except DataQualityError as e:
        raise HTTPException(status_code=502, detail=f"price data fetch failed: {e}") from e

    n_days = len(log_ret)
    effective_window = WINDOW if not custom else min(WINDOW, max(126, (n_days - REBAL_EVERY) // 2))
    try:
        res = walk_forward(
            log_ret, weight_fn, window=effective_window, rebal_every=REBAL_EVERY, cost_bps=COST_BPS, method_name=method
        )
    except ValueError as e:
        raise HTTPException(
            status_code=422,
            detail=f"not enough overlapping history across these tickers to backtest ({e})",
        ) from e

    equity = 10_000.0 * np.exp(np.cumsum(res.net_period_returns))
    curve = [{"date": str(res.dates[0].date()), "value": 10_000.0}]
    curve += [{"date": str(d.date()), "value": round(float(v), 2)} for d, v in zip(res.dates, equity)]
    final_weights = dict(zip(use_tickers, [round(float(w), 6) for w in res.weights[-1]]))

    # daily-close-based backtest doesn't need recomputing on every request;
    # cache at Vercel's edge so simulator traffic doesn't hammer the upstream
    # price API this reads from.
    if response is not None:
        response.headers["Cache-Control"] = "s-maxage=3600, stale-while-revalidate=7200"

    return {
        "tickers": use_tickers,
        "as_of_date": as_of_date,
        "last_known_prices": latest_price,
        "method": method,
        "window_days": effective_window,
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


_RISK_BENCHMARK = "SPY"
# A P/E this low on a real operating company is vanishingly rare -- in
# practice it almost always means a trust/REIT unit (FFO-based valuation,
# not GAAP-earnings-based, so a GAAP P/E on one is close to meaningless),
# a one-time gain, or a data error, not genuine cheapness. Checked
# directly: without this floor the top of an unfiltered scan was REIT and
# trust units at P/E 0.2-0.9, not real bargains. Excluding them is a
# scope limitation (sector-aware valuation, e.g. FFO multiples for REITs,
# is out of scope here), stated plainly rather than silently producing a
# list that looks broken.
MIN_PE_RATIO = 3.0


@app.get("/api/underdogs")
def underdogs(
    min_cap: float = 100_000_000,
    max_cap: float = 5_000_000_000,
    limit: int = 25,
    response: Response = None,
):
    """A transparent value screen within a user-chosen market-cap band --
    "underdog" here means cheap relative to earnings, not a black-box
    score. Ranks by ascending P/E among names with a P/E above MIN_PE_RATIO;
    loss-making, no-P/E, or implausibly-low-P/E names in the band aren't
    force-ranked into a list where "cheap" has no reliable meaning for
    them, they're just counted separately so nothing about the band is
    hidden.
    """
    if min_cap < 0 or max_cap <= min_cap:
        raise HTTPException(status_code=400, detail="max_cap must be greater than min_cap, both >= 0")
    if not (1 <= limit <= 100):
        raise HTTPException(status_code=400, detail="limit must be between 1 and 100")

    try:
        rows = screen(fetch_full_universe())
    except DataQualityError as e:
        raise HTTPException(status_code=502, detail=f"universe fetch failed: {e}") from e

    in_band = [r for r in rows if r.market_cap is not None and min_cap <= r.market_cap <= max_cap]
    valued = sorted(
        (r for r in in_band if r.pe_ratio is not None and r.pe_ratio > MIN_PE_RATIO),
        key=lambda r: r.pe_ratio,
    )
    excluded_count = len(in_band) - len(valued)

    if response is not None:
        response.headers["Cache-Control"] = "s-maxage=1800, stale-while-revalidate=3600"

    return {
        "as_of": datetime.now(timezone.utc).date().isoformat(),
        "min_cap": min_cap,
        "max_cap": max_cap,
        "count_in_band": len(in_band),
        "count_ranked": len(valued),
        "count_excluded": excluded_count,
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
            for r in valued[:limit]
        ],
    }


_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@app.get("/api/news/{ticker}")
def news(ticker: str, start_date: str | None = None, end_date: str | None = None, limit: int = 20, response: Response = None):
    """Three independent sources (data.news.get_news): Yahoo RSS, Google
    News RSS (real date-range search via after:/before:), SEC EDGAR
    (official per-company 8-K history). Each gets a locally-computed
    sentiment score -- see data/news.py's module docstring on why that's
    VADER plus a small finance-specific lexicon patch, not a vendor score
    or a trained model."""
    ticker = ticker.upper()
    if not _TICKER_RE.match(ticker):
        raise HTTPException(status_code=400, detail="invalid ticker format")
    for label, d in (("start_date", start_date), ("end_date", end_date)):
        if d is not None and not _DATE_RE.match(d):
            raise HTTPException(status_code=400, detail=f"{label} must be YYYY-MM-DD")
    if not (1 <= limit <= 50):
        raise HTTPException(status_code=400, detail="limit must be between 1 and 50")

    items, errors = get_news(ticker, start_date=start_date, end_date=end_date, limit=limit)

    if response is not None:
        response.headers["Cache-Control"] = "s-maxage=900, stale-while-revalidate=3600"

    return {
        "ticker": ticker,
        "start_date": start_date,
        "end_date": end_date,
        "sources_queried": ["yahoo", "google_news", "sec_edgar"],
        "source_errors": errors,
        "items": [news_item_to_dict(it) for it in items],
    }


@app.get("/api/stock/{ticker}")
def stock_detail(ticker: str, range_: str = "1Y", risk: bool = False, response: Response = None):
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

    result = {
        "ticker": ticker,
        "as_of": latest.date,
        "price": latest.adj_close,
        "day_change_pct": round((latest.adj_close / prev.adj_close - 1) * 100, 4) if prev.adj_close else None,
        "high_52w": max(r.adj_close for r in window_1y),
        "low_52w": min(r.adj_close for r in window_1y),
        "series": [{"date": r.date, "close": r.adj_close, "volume": r.volume} for r in rows],
    }

    # Opt-in: Explore's plain stock-detail view doesn't need this on every
    # load, but Underdogs' risk analysis does -- compute_beta/annualized_vol/
    # max_drawdown are the same functions research/screen.py uses to rank
    # the broader universe, not a separate metric just for this view.
    if risk:
        s = pd.Series({r.date: r.adj_close for r in rows})
        s.index = pd.to_datetime(s.index)
        log_ret = np.log(s.sort_index() / s.sort_index().shift(1)).dropna()

        beta = None
        try:
            bench_payload = fetch_raw(_RISK_BENCHMARK, range_=range_, period="Daily")
            bench_rows = validate(_RISK_BENCHMARK, bench_payload, min_rows=5, max_single_day_move=0.95)
            bench_s = pd.Series({r.date: r.adj_close for r in bench_rows})
            bench_s.index = pd.to_datetime(bench_s.index)
            bench_log_ret = np.log(bench_s.sort_index() / bench_s.sort_index().shift(1)).dropna()
            beta = compute_beta(log_ret, bench_log_ret)
        except DataQualityError:
            pass  # beta is a bonus field here -- a benchmark fetch failure shouldn't 404 the whole page

        result["risk"] = {
            "annualized_vol": annualized_vol(log_ret, window_days=min(252, len(log_ret))),
            "max_drawdown": max_drawdown(log_ret, window_days=min(252, len(log_ret))),
            "beta_vs_spy": beta,
        }

    return result


@app.post("/api/forecast")
def forecast(req: ForecastRequest):
    if not req.holdings:
        raise HTTPException(status_code=400, detail="holdings must include at least one position")
    tickers = [t.upper() for t in req.holdings]
    for t in tickers:
        if not _TICKER_RE.match(t):
            raise HTTPException(status_code=400, detail=f"invalid ticker format: {t}")
    shares = {t.upper(): s for t, s in req.holdings.items()}
    if any(s < 0 for s in shares.values()):
        raise HTTPException(status_code=400, detail="share counts must be >= 0")
    if req.add_amount < 0:
        raise HTTPException(status_code=400, detail="add_amount must be >= 0")
    if not (5 <= req.horizon_days <= 756):
        raise HTTPException(status_code=400, detail="horizon_days must be between 5 and 756 (3 trading years)")
    bad = [d for d in req.distributions if d != "same" and d not in FORECAST_METHOD_FNS]
    if bad:
        raise HTTPException(
            status_code=400,
            detail=f"unknown distribution(s) {bad}; choose from ['same', {list(FORECAST_METHOD_FNS)}]",
        )

    series, latest_price = {}, {}
    try:
        for t in tickers:
            payload = fetch_raw(t, range_="2Y", period="Daily")
            # min_rows relaxed vs. the curated watchlist's 200-day default --
            # this serves whatever a visitor actually holds, which may
            # include recent listings; max_single_day_move relaxed for the
            # same reason /api/stock/{ticker} relaxes it.
            rows = validate(t, payload, min_rows=60, max_single_day_move=0.95)
            s = pd.Series({r.date: r.adj_close for r in rows}, name=t)
            s.index = pd.to_datetime(s.index)
            series[t] = s.sort_index()
            latest_price[t] = float(series[t].iloc[-1])
    except DataQualityError as e:
        raise HTTPException(status_code=502, detail=f"price data fetch failed: {e}") from e

    prices = pd.DataFrame(series).dropna(how="any")
    if len(prices) < 60:
        raise HTTPException(
            status_code=422,
            detail="not enough overlapping price history across these tickers to forecast (need 60+ trading days)",
        )
    log_ret = np.log(prices / prices.shift(1)).dropna()

    current_value = sum(shares[t] * latest_price[t] for t in tickers)
    if current_value <= 0:
        raise HTTPException(
            status_code=400, detail="current holdings value must be > 0 -- enter at least one position with shares > 0"
        )
    current_weights = {t: shares[t] * latest_price[t] / current_value for t in tickers}
    total_initial = current_value + req.add_amount

    last_date = prices.index[-1]
    future_dates = pd.bdate_range(start=last_date, periods=req.horizon_days + 1)[1:]

    n = len(tickers)
    scenarios = {}
    for dist in req.distributions:
        if dist == "same":
            weights = dict(current_weights)
        else:
            w = FORECAST_METHOD_FNS[dist](log_ret[tickers], n)
            weights = dict(zip(tickers, (float(x) for x in w)))
        w_series = pd.Series(weights).reindex(tickers).fillna(0.0)
        portfolio_daily_ret = log_ret[tickers].dot(w_series)
        try:
            result = simulate_forward(
                portfolio_daily_ret, initial_value=total_initial, horizon_days=req.horizon_days, n_sims=2000, seed=0
            )
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e
        scenarios[dist] = {
            "weights": {t: round(weights[t], 6) for t in tickers},
            "p10": [round(float(v), 2) for v in result.p10],
            "p50": [round(float(v), 2) for v in result.p50],
            "p90": [round(float(v), 2) for v in result.p90],
        }

    return {
        "as_of": str(last_date.date()),
        "tickers": tickers,
        "current_value": round(current_value, 2),
        "current_weights": {t: round(current_weights[t], 6) for t in tickers},
        "add_amount": req.add_amount,
        "total_initial": round(total_initial, 2),
        "horizon_days": req.horizon_days,
        "dates": [str(d.date()) for d in future_dates],
        "n_sims": 2000,
        "block_size": 5,
        "scenarios": scenarios,
    }


@app.post("/api/add-funds")
def add_funds(req: AddFundsRequest):
    if not req.holdings:
        raise HTTPException(status_code=400, detail="holdings must include at least one position")
    tickers = [t.upper() for t in req.holdings]
    for t in tickers:
        if not _TICKER_RE.match(t):
            raise HTTPException(status_code=400, detail=f"invalid ticker format: {t}")
    if req.add_amount < 0:
        raise HTTPException(status_code=400, detail="add_amount must be >= 0")

    latest_price = {}
    try:
        for t in tickers:
            payload = fetch_raw(t, range_="1M", period="Daily")
            rows = validate(t, payload, min_rows=1, max_single_day_move=0.95)
            latest_price[t] = float(rows[-1].adj_close)
    except DataQualityError as e:
        raise HTTPException(status_code=502, detail=f"price data fetch failed: {e}") from e

    # trade_ticket.py's whole-share contract predates this project's
    # forecast feature, which allows fractional shares -- floor to whole
    # shares only for this ticket computation, never for what's displayed
    # or stored elsewhere.
    positions = {t.upper(): int(s) for t, s in req.holdings.items()}
    held_only = {"cash": 0.0, "positions": positions}
    target_weights, current_value = ticket_current_weights(held_only, latest_price)
    if not target_weights or current_value <= 0:
        raise HTTPException(
            status_code=400, detail="current holdings value must be > 0 -- enter at least one position with shares > 0"
        )

    with_new_cash = {"cash": req.add_amount, "positions": positions}
    ticket = generate_trade_ticket(with_new_cash, target_weights, latest_price, drift_band=0.0)

    return {
        "as_of": datetime.now(timezone.utc).date().isoformat(),
        "latest_prices": latest_price,
        "current_value": round(current_value, 2),
        "current_weights": {t: round(w, 6) for t, w in target_weights.items()},
        "add_amount": req.add_amount,
        "total_value_after": round(ticket["total_value"], 2),
        "trades": [
            {"ticker": t.ticker, "action": t.action, "shares": t.shares, "price": t.price, "est_value": t.est_value}
            for t in ticket["trades"]
        ],
        "cash_after": ticket["cash_after"],
    }


# Thresholds below are stated, fixed rules, not a trained or fit model --
# a rule-based first pass per the project's current scope. Each is a round,
# defensible number (a single name or sector above 30%/50% of a portfolio
# is concentration risk by any standard definition; 3 names is the point
# single-company news starts to dominate the whole account's return), not
# backtested or optimized against this project's own data -- doing that
# would risk fitting the thresholds to look good on a tiny number of
# example portfolios, the same overfitting trap research/overfitting.py
# exists to catch elsewhere in this project.
MAX_POSITION_WEIGHT = 0.30
MAX_SECTOR_WEIGHT = 0.50
MIN_POSITIONS = 3
HIGH_VOL_THRESHOLD = 0.35  # annualized


@app.post("/api/recommendations")
def recommendations(req: RecommendationsRequest):
    if not req.holdings:
        raise HTTPException(status_code=400, detail="holdings must include at least one position")
    tickers = [t.upper() for t in req.holdings]
    for t in tickers:
        if not _TICKER_RE.match(t):
            raise HTTPException(status_code=400, detail=f"invalid ticker format: {t}")
    shares = {t.upper(): s for t, s in req.holdings.items()}

    series, latest_price = {}, {}
    try:
        for t in tickers:
            payload = fetch_raw(t, range_="2Y", period="Daily")
            rows = validate(t, payload, min_rows=60, max_single_day_move=0.95)
            s = pd.Series({r.date: r.adj_close for r in rows}, name=t)
            s.index = pd.to_datetime(s.index)
            series[t] = s.sort_index()
            latest_price[t] = float(series[t].iloc[-1])
    except DataQualityError as e:
        raise HTTPException(status_code=502, detail=f"price data fetch failed: {e}") from e

    current_value = sum(shares[t] * latest_price[t] for t in tickers)
    if current_value <= 0:
        raise HTTPException(
            status_code=400, detail="current holdings value must be > 0 -- enter at least one position with shares > 0"
        )
    weights = {t: shares[t] * latest_price[t] / current_value for t in tickers}

    try:
        universe_rows = fetch_full_universe()
    except DataQualityError as e:
        raise HTTPException(status_code=502, detail=f"universe fetch failed: {e}") from e
    sector_by_ticker = {r.ticker: (r.sector or "Unknown") for r in universe_rows}

    sector_weights: dict[str, float] = {}
    for t in tickers:
        sec = sector_by_ticker.get(t, "Unknown")
        sector_weights[sec] = sector_weights.get(sec, 0.0) + weights[t]

    prices = pd.DataFrame(series).dropna(how="any")
    log_ret = np.log(prices / prices.shift(1)).dropna()
    w_series = pd.Series(weights).reindex(tickers).fillna(0.0)
    portfolio_daily_ret = log_ret[tickers].dot(w_series)
    port_vol = annualized_vol(portfolio_daily_ret, window_days=min(252, len(portfolio_daily_ret)))

    flags = []
    worst_position = max(weights.items(), key=lambda kv: kv[1])
    if worst_position[1] > MAX_POSITION_WEIGHT:
        flags.append(
            {
                "severity": "warning",
                "title": f"{worst_position[0]} is {worst_position[1] * 100:.0f}% of your portfolio",
                "detail": f"A single name above {MAX_POSITION_WEIGHT * 100:.0f}% concentrates risk in one "
                "company's outcome. Consider trimming it or adding other positions to dilute it.",
            }
        )
    worst_sector = max(sector_weights.items(), key=lambda kv: kv[1])
    if worst_sector[1] > MAX_SECTOR_WEIGHT:
        flags.append(
            {
                "severity": "warning",
                "title": f"{worst_sector[1] * 100:.0f}% of your portfolio is in {worst_sector[0]}",
                "detail": f"A single sector above {MAX_SECTOR_WEIGHT * 100:.0f}% means a sector-wide shock hits "
                f"most of your money at once. Explore or Underdogs can help find names outside {worst_sector[0]}.",
            }
        )
    if len(tickers) < MIN_POSITIONS:
        flags.append(
            {
                "severity": "info",
                "title": f"Only {len(tickers)} position{'s' if len(tickers) != 1 else ''} held",
                "detail": f"Fewer than {MIN_POSITIONS} names means any one company's news can swing your whole "
                "portfolio. More positions, even small ones, reduce single-name risk.",
            }
        )
    if port_vol is not None and port_vol > HIGH_VOL_THRESHOLD:
        flags.append(
            {
                "severity": "warning",
                "title": f"Realized volatility is high ({port_vol * 100:.0f}% annualized)",
                "detail": "Your portfolio has swung more than a typical diversified mix over the last year. "
                "Strategy Lab's Min-Variance or Risk Parity methods are built specifically to reduce this.",
            }
        )
    if not flags:
        flags.append(
            {
                "severity": "info",
                "title": "No concentration or volatility flags from this check",
                "detail": "Position sizes, sector mix, and realized volatility are all within the thresholds this "
                "rule-based check looks for. That doesn't mean there's no risk -- only that none of the specific, "
                "measurable kinds this check screens for were triggered.",
            }
        )

    return {
        "as_of": datetime.now(timezone.utc).date().isoformat(),
        "current_value": round(current_value, 2),
        "current_weights": {t: round(w, 6) for t, w in weights.items()},
        "sector_weights": {s: round(w, 6) for s, w in sorted(sector_weights.items(), key=lambda kv: -kv[1])},
        "annualized_vol": port_vol,
        "flags": flags,
    }
