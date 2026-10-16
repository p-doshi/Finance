"""Full US + Canada equity universe, from stockanalysis.com's bulk screener
endpoint (`/_api/endpoints/screener/initial`) — one call returns the entire
US common-stock universe (~5,600 names), one more returns every
Canadian-exchange listing. This is a completely different data shape from
`data.fetch`: a wide, shallow snapshot (price, market cap, volume, sector,
P/E — whatever the "initial" view ships with) across thousands of names,
rather than deep daily history for a handful.

Known data-quality issues, handled here rather than left for the caller to
discover:

1. The Canadian query returns `neo/`-prefixed rows, which are Canadian
   Depositary Receipts (CDRs) — synthetic, currency-hedged wrappers on US
   mega-caps (e.g. `neo/ZNVD` is a CDR on NVIDIA), not distinct companies.
   Dropped by prefix.
2. Less obviously, the Canadian query *also* returns CDRs listed directly
   under `tsx/` using the plain US ticker (`tsx/NVDA`, `tsx/AAPL`,
   `tsx/MSFT`, ...) — no prefix convention flags these, and their reported
   market caps are internally inconsistent with the real listing (TSX's
   "NVDA" at $7.4T vs. the actual $5.2T), which is what exposed them: a
   real dual-listing's market cap shouldn't diverge from its US listing by
   40%+. Caught generically rather than by a ticker blocklist: any
   Canadian-side row whose *company name* exactly matches a US-side row is
   dropped, since at that point it's either this kind of CDR or a genuine
   dual-listing (Royal Bank, TD, Enbridge, Shopify, ...) already present
   once from the US pull — either way, the US-side row is kept as the
   single canonical entry.

TSX, TSX Venture, and CSE rows that survive both filters are genuine,
distinct Canadian companies, tagged by exchange so a screen can treat
TSXV/CSE's more speculative, lower-liquidity names differently from the
TSX main board.
"""
from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass

from .fetch import USER_AGENT, DataQualityError

SCREENER_URL = "https://stockanalysis.com/_api/endpoints/screener/initial?type=stock&countryCode={country}&format=compact"

# Canadian-exchange prefixes worth keeping, mapped to a clean label.
# 'neo' is deliberately excluded — see module docstring.
_CA_EXCHANGE_MAP = {"tsx": "TSX", "tsxv": "TSXV", "cse": "CSE"}


@dataclass
class UniverseRow:
    ticker: str
    name: str
    country: str          # "US" or "CA"
    exchange: str          # "US" (undifferentiated NYSE/NASDAQ/AMEX) or "TSX"/"TSXV"/"CSE"
    market_cap: float | None
    price: float
    day_change_pct: float | None
    sector: str | None
    volume: int
    pe_ratio: float | None


def _fetch_raw(country_code: str, timeout: float = 20.0) -> dict:
    url = SCREENER_URL.format(country=country_code)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if payload.get("status") != 200 or "data" not in payload:
        raise DataQualityError(f"screener fetch failed for country={country_code!r}: {payload}")
    data = payload["data"]
    if data["count"] != len(data["rows"]):
        raise DataQualityError(
            f"screener row-count mismatch for country={country_code!r}: "
            f"reported {data['count']}, got {len(data['rows'])}"
        )
    expected_cols = ["s", "n", "marketCap", "price", "change", "industry", "volume", "peRatio"]
    if data["columns"] != expected_cols:
        raise DataQualityError(f"screener column layout changed: {data['columns']} != {expected_cols}")
    return data


def fetch_us_universe() -> list[UniverseRow]:
    data = _fetch_raw("")
    rows = []
    for s, n, mcap, price, chg, industry, vol, pe in data["rows"]:
        if price is None or price <= 0:
            continue  # a handful of halted/delisted-in-transition rows carry null/zero price
        rows.append(UniverseRow(ticker=s, name=n, country="US", exchange="US",
                                  market_cap=mcap, price=price, day_change_pct=chg,
                                  sector=industry, volume=vol or 0, pe_ratio=pe))
    return rows


def fetch_ca_universe() -> list[UniverseRow]:
    data = _fetch_raw("CA")
    rows = []
    for s, n, mcap, price, chg, industry, vol, pe in data["rows"]:
        if "/" not in s:
            continue
        prefix, ticker = s.split("/", 1)
        exchange = _CA_EXCHANGE_MAP.get(prefix)
        if exchange is None:
            continue  # drops 'neo/' CDRs — see module docstring
        if price is None or price <= 0:
            continue
        rows.append(UniverseRow(ticker=ticker, name=n, country="CA", exchange=exchange,
                                  market_cap=mcap, price=price, day_change_pct=chg,
                                  sector=industry, volume=vol or 0, pe_ratio=pe))
    return rows


def fetch_full_universe() -> list[UniverseRow]:
    """US + Canada (TSX/TSXV/CSE), CDRs excluded. Two network calls total,
    not one per ticker — this is a bulk snapshot, not deep history.

    Dedup is name-based, not just ticker-based: a Canadian-side row whose
    company name exactly matches a US-side row is dropped, which is what
    is needed to catch `tsx/`-listed CDRs (see module docstring) and also
    collapses genuine dual-listings (Royal Bank, TD, Enbridge, Shopify...)
    to the single US-side entry rather than double-counting the same real
    company."""
    us = fetch_us_universe()
    ca = fetch_ca_universe()
    us_names = {r.name.strip().lower() for r in us}

    seen = set()
    combined = []
    for row in us:
        key = (row.country, row.exchange, row.ticker)
        if key in seen:
            continue
        seen.add(key)
        combined.append(row)
    for row in ca:
        if row.name.strip().lower() in us_names:
            continue  # CDR or already-counted dual-listing — see docstring
        key = (row.country, row.exchange, row.ticker)
        if key in seen:
            continue
        seen.add(key)
        combined.append(row)
    return combined


def screen(
    rows: list[UniverseRow],
    *,
    min_market_cap: float = 100_000_000,
    min_dollar_volume: float = 500_000,
) -> list[UniverseRow]:
    """Liquidity/size floor. `volume` here is a single day's share volume
    from the snapshot, not a trailing average — a rough proxy, not a
    rigorous liquidity measure; good enough to drop obvious shells and
    illiquid micro-caps, not a substitute for checking actual average daily
    dollar volume before sizing a real position."""
    out = []
    for r in rows:
        if r.market_cap is None or r.market_cap < min_market_cap:
            continue
        if r.price * r.volume < min_dollar_volume:
            continue
        out.append(r)
    return out
