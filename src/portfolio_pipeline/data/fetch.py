"""Price-history ingestion with validation, and an append-only point-in-time
store: every pull is saved under its own timestamp rather than overwritten,
so a later backtest can never accidentally see a revision that didn't exist
on the date being simulated.

Source: stockanalysis.com's own chart API — same vendor used (and
cross-checked) for the beta/52-week figures in docs/methodology.md, so there
is no cross-source identity-mismatch risk for price history either. This is
a convenience source, not a point-in-time, survivorship-bias-free vendor
(delisted/acquired names simply disappear rather than being preserved) —
acceptable for a fixed watchlist of currently-listed large caps, explicitly
not acceptable for backtesting a broad historical universe screen.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

API_URL = "https://stockanalysis.com/api/symbol/s/{ticker}/history?range={range_}&period={period}"
USER_AGENT = "portfolio-pipeline/0.1 (personal research use)"


class DataQualityError(ValueError):
    """Raised when a pulled price series fails a validation check."""


@dataclass
class PriceRow:
    date: str
    close: float
    adj_close: float
    volume: int


def fetch_raw(ticker: str, range_: str = "5Y", period: str = "Daily", timeout: float = 15.0) -> dict:
    """Hit the history API directly and return the parsed JSON. Raises on
    non-200 status or a network error rather than silently returning stale
    or empty data."""
    url = API_URL.format(ticker=ticker, range_=range_, period=period)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        raise DataQualityError(f"{ticker}: fetch failed — {e}") from e
    if payload.get("status") != 200:
        raise DataQualityError(f"{ticker}: API returned status {payload.get('status')!r}")
    if not payload.get("data"):
        raise DataQualityError(f"{ticker}: API returned no rows")
    return payload


def validate(ticker: str, payload: dict, *, min_rows: int = 200, max_single_day_move: float = 0.5) -> list[PriceRow]:
    """Structural + sanity checks on a raw pull. Raises DataQualityError on
    failure rather than returning partially-bad data — a failed pull should
    stop the pipeline, not feed a quietly-corrupted covariance matrix.

    Checks:
      - enough rows to be usable (default: at least ~200 trading days)
      - dates strictly increasing, no duplicates
      - no non-positive prices
      - no single-day adjusted-close move bigger than `max_single_day_move`
        (50% default) that isn't flagged as a stock split in the source data —
        meant to catch data errors, not real crashes (several of these names
        have had genuine >20% single-day moves on earnings, which is not an
        error). The 50% default was calibrated against a 12-name mega-cap
        watchlist; running the full market screen (Stage B,
        docs/methodology.md) against ~4,000 names at the default threshold
        flagged 473 tickers, most of which turned out to be genuine —
        BMNR (+695%) and DFDV (+843%) are real, documented single-day moves
        from crypto-treasury-strategy pivot announcements, not bad data. A
        caller working with a broader, more volatile universe than a
        mega-cap watchlist should pass a higher threshold rather than trust
        this default.
    """
    rows_raw = sorted(payload["data"], key=lambda r: r["t"])
    if len(rows_raw) < min_rows:
        raise DataQualityError(f"{ticker}: only {len(rows_raw)} rows, expected >= {min_rows}")

    rows: list[PriceRow] = []
    seen_dates = set()
    prev_adj = None
    for r in rows_raw:
        date = r["t"]
        if date in seen_dates:
            raise DataQualityError(f"{ticker}: duplicate date {date}")
        seen_dates.add(date)
        close, adj = r["c"], r["a"]
        if close <= 0 or adj <= 0:
            raise DataQualityError(f"{ticker}: non-positive price on {date}")
        if prev_adj is not None:
            move = abs(adj - prev_adj) / prev_adj
            if move > max_single_day_move:
                raise DataQualityError(
                    f"{ticker}: {move:.0%} single-day adjusted-close move on {date} "
                    f"exceeds {max_single_day_move:.0%} threshold — verify manually before trusting this pull"
                )
        prev_adj = adj
        rows.append(PriceRow(date=date, close=close, adj_close=adj, volume=r.get("v", 0)))
    return rows


def save_point_in_time(ticker: str, payload: dict, data_dir: Path) -> Path:
    """Append-only: writes data/raw/<TICKER>/<pulled_at_utc_iso>.json and
    refreshes data/<TICKER>.json as a convenience "latest" copy. The raw
    per-pull file is never overwritten, so re-running the pipeline can never
    erase what an earlier backtest run actually saw."""
    data_dir = Path(data_dir)
    pulled_at = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    raw_dir = data_dir / "raw" / ticker
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / f"{pulled_at}.json"
    raw_path.write_text(json.dumps(payload))

    latest_path = data_dir / f"{ticker}.json"
    latest_path.write_text(json.dumps(payload))
    return raw_path


def fetch_and_store(
    ticker: str, data_dir: Path, range_: str = "5Y", period: str = "Daily",
    *, max_single_day_move: float = 0.5,
) -> list[PriceRow]:
    payload = fetch_raw(ticker, range_=range_, period=period)
    rows = validate(ticker, payload, max_single_day_move=max_single_day_move)
    save_point_in_time(ticker, payload, data_dir)
    return rows
