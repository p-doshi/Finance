"""Daily price history for Canadian-exchange-only names (TSX/TSXV/CSE),
via Yahoo Finance's chart API.

Why a second source: stockanalysis.com's history API — used for every US
name and verified directly against the beta/trend figures elsewhere in
this project — has no discoverable equivalent for Canadian-only listings.
The bulk screener and the US history API both revealed themselves as plain
`preload` links in stockanalysis.com's own page HTML; the Canadian history
page has no such link, and its data loads client-side only. Yahoo's chart
API, by contrast, responded correctly for all three Canadian exchange
suffixes when tested directly (ATD.TO, AFM.V, GTII.CN) — confirmed live in
this session, which supersedes an earlier, unverified claim in this
project's history that Yahoo was blocked outright; it was not re-tested
until now.

This is a genuinely different vendor from the US path, so results should
be treated as such: validated the same way (`data.fetch.validate`-style
checks), but not assumed to define "adjusted close" identically to
stockanalysis.com. Good enough for the same screening/ranking purpose;
not a reason to assume the two sources are interchangeable for anything
precision-sensitive.
"""
from __future__ import annotations

import json
import urllib.request
import urllib.error

from .fetch import DataQualityError, PriceRow, USER_AGENT, validate as _validate_rows

YAHOO_SUFFIX = {"TSX": ".TO", "TSXV": ".V", "CSE": ".CN"}
CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range={range_}&interval=1d"


def to_yahoo_symbol(ticker: str, exchange: str) -> str:
    suffix = YAHOO_SUFFIX.get(exchange)
    if suffix is None:
        raise ValueError(f"no Yahoo suffix mapping for exchange {exchange!r}")
    return f"{ticker}{suffix}"


def fetch_raw_yahoo(ticker: str, exchange: str, range_: str = "5y", timeout: float = 15.0) -> dict:
    symbol = to_yahoo_symbol(ticker, exchange)
    url = CHART_URL.format(symbol=symbol, range_=range_)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        raise DataQualityError(f"{ticker}.{exchange}: fetch failed — {e}") from e
    chart = payload.get("chart", {})
    if chart.get("error") is not None:
        raise DataQualityError(f"{ticker}.{exchange}: Yahoo error — {chart['error']}")
    result = chart.get("result")
    if not result:
        raise DataQualityError(f"{ticker}.{exchange}: Yahoo returned no result")
    return result[0]


def to_stockanalysis_shape(yahoo_result: dict) -> dict:
    """Reshape Yahoo's {timestamp[], indicators.quote[0].close[], ...} into
    the same {"status": 200, "data": [{"t","c","a","v"}, ...]} shape used
    everywhere else in this project, so `data.fetch.validate` and every
    downstream consumer work unchanged regardless of which vendor a given
    ticker came from."""
    import datetime as _dt

    timestamps = yahoo_result["timestamp"]
    quote = yahoo_result["indicators"]["quote"][0]
    adj = yahoo_result["indicators"].get("adjclose", [{}])[0].get("adjclose", quote["close"])
    rows = []
    for i, ts in enumerate(timestamps):
        c, a, v = quote["close"][i], adj[i], quote["volume"][i]
        if c is None or a is None:
            continue  # Yahoo leaves holes for missing session data; skip rather than fabricate
        date = _dt.datetime.fromtimestamp(ts, _dt.timezone.utc).strftime("%Y-%m-%d")
        rows.append({"t": date, "c": c, "a": a, "v": v or 0})
    return {"status": 200, "data": rows}


def fetch_and_store_ca(
    ticker: str, exchange: str, data_dir, range_: str = "5y",
    *, max_single_day_move: float = 0.5,
) -> list[PriceRow]:
    """Same contract as `data.fetch.fetch_and_store`, for a Canadian-only
    name. File naming is exchange-qualified (`{exchange}_{ticker}.json`),
    not bare ticker — the screened universe has 39 tickers that collide
    across exchanges with an unrelated company (e.g. US `CMG` = Chipotle
    vs. TSX `CMG` = Computer Modelling Group); a bare-ticker filename would
    silently overwrite one with the other depending on fetch order."""
    from datetime import datetime, timezone
    from pathlib import Path

    yahoo_result = fetch_raw_yahoo(ticker, exchange, range_=range_)
    payload = to_stockanalysis_shape(yahoo_result)
    rows = _validate_rows(f"{exchange}:{ticker}", payload, max_single_day_move=max_single_day_move)

    data_dir = Path(data_dir)
    pulled_at = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    raw_dir = data_dir / "raw" / f"{exchange}_{ticker}"
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / f"{pulled_at}.json").write_text(json.dumps(payload))
    (data_dir / f"{exchange}_{ticker}.json").write_text(json.dumps(payload))
    return rows
