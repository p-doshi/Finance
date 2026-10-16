import json
from io import BytesIO
from unittest.mock import patch

import pytest

from portfolio_pipeline.data.fetch import DataQualityError
from portfolio_pipeline.data.universe import (
    fetch_us_universe,
    fetch_ca_universe,
    fetch_full_universe,
    screen,
    UniverseRow,
)

COLS = ["s", "n", "marketCap", "price", "change", "industry", "volume", "peRatio"]


class _FakeResponse:
    def __init__(self, payload: dict):
        self._body = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _payload(rows):
    return {"status": 200, "data": {"count": len(rows), "columns": COLS, "rows": rows}}


def test_fetch_us_universe_parses_rows_and_drops_null_price():
    rows = [
        ["AAPL", "Apple Inc.", 3_000_000_000_000, 190.0, 0.5, "Consumer Electronics", 50_000_000, 30.0],
        ["ZZZZ", "Halted Co.", 1_000_000, None, None, "Shell Companies", 0, None],
    ]
    with patch("portfolio_pipeline.data.universe.urllib.request.urlopen", return_value=_FakeResponse(_payload(rows))):
        out = fetch_us_universe()
    assert len(out) == 1
    assert out[0] == UniverseRow(ticker="AAPL", name="Apple Inc.", country="US", exchange="US",
                                   market_cap=3_000_000_000_000, price=190.0, day_change_pct=0.5,
                                   sector="Consumer Electronics", volume=50_000_000, pe_ratio=30.0)


def test_fetch_ca_universe_excludes_cdrs_and_strips_prefix():
    rows = [
        ["tsx/ATD", "Alimentation Couche-Tard Inc.", 75_000_000_000, 81.6, 0.8, "Specialty Retail", 2_000_000, 16.7],
        ["neo/ZNVD", "NVIDIA Corporation", 7_518_074_827_044, 11.48, -1.71, "Semiconductors", 720, 28.1],
        ["tsxv/AFM", "Alphamin Resources Corp.", 1_800_000_000, 1.42, 0.0, "Other Industrial Metals & Mining", 500_000, None],
        ["cse/GTII", "Green Thumb Industries Inc.", 2_000_000_000, 9.05, -1.09, "Drug Manufacturers", 266_446, 11.6],
    ]
    with patch("portfolio_pipeline.data.universe.urllib.request.urlopen", return_value=_FakeResponse(_payload(rows))):
        out = fetch_ca_universe()
    tickers = {r.ticker: r.exchange for r in out}
    assert tickers == {"ATD": "TSX", "AFM": "TSXV", "GTII": "CSE"}
    assert "ZNVD" not in tickers  # CDR excluded


def test_fetch_raw_rejects_row_count_mismatch():
    payload = {"status": 200, "data": {"count": 99, "columns": COLS, "rows": []}}
    with patch("portfolio_pipeline.data.universe.urllib.request.urlopen", return_value=_FakeResponse(payload)):
        with pytest.raises(DataQualityError, match="row-count mismatch"):
            fetch_us_universe()


def test_fetch_raw_rejects_changed_column_layout():
    payload = {"status": 200, "data": {"count": 0, "columns": ["s", "n"], "rows": []}}
    with patch("portfolio_pipeline.data.universe.urllib.request.urlopen", return_value=_FakeResponse(payload)):
        with pytest.raises(DataQualityError, match="column layout changed"):
            fetch_us_universe()


def test_fetch_full_universe_dedupes_across_us_and_ca():
    us_rows = [["RY", "Royal Bank of Canada", 270_000_000_000, 196.0, 1.0, "Banks", 600_000, 17.0]]
    ca_rows = [["tsx/ATD", "Alimentation Couche-Tard Inc.", 75_000_000_000, 81.6, 0.8, "Specialty Retail", 2_000_000, 16.7]]

    responses = [_FakeResponse(_payload(us_rows)), _FakeResponse(_payload(ca_rows))]
    with patch("portfolio_pipeline.data.universe.urllib.request.urlopen", side_effect=responses):
        combined = fetch_full_universe()
    keys = {(r.country, r.exchange, r.ticker) for r in combined}
    assert keys == {("US", "US", "RY"), ("CA", "TSX", "ATD")}


def test_fetch_full_universe_drops_tsx_cdr_with_same_name_as_us_listing():
    """The subtler bug: tsx/NVDA is a CDR with a grossly inconsistent market
    cap vs. the real US NVDA listing, and no prefix convention flags it —
    only the exact name match does."""
    us_rows = [["NVDA", "NVIDIA Corporation", 5_245_452_810_000, 217.23, -1.84, "Semiconductors", 125_510_614, 27.5]]
    ca_rows = [["tsx/NVDA", "NVIDIA Corporation", 7_447_021_808_885, 48.31, -1.99, "Semiconductors", 947_602, 27.4]]

    responses = [_FakeResponse(_payload(us_rows)), _FakeResponse(_payload(ca_rows))]
    with patch("portfolio_pipeline.data.universe.urllib.request.urlopen", side_effect=responses):
        combined = fetch_full_universe()
    assert len(combined) == 1
    assert combined[0].country == "US" and combined[0].market_cap == 5_245_452_810_000


def test_fetch_full_universe_collapses_genuine_dual_listing_to_us_entry():
    """A real dual-listed Canadian company (Royal Bank) appearing in both
    pulls under the same name should be counted once, not twice."""
    us_rows = [["RY", "Royal Bank of Canada", 270_000_000_000, 196.0, 1.0, "Banks", 600_000, 17.0]]
    ca_rows = [["tsx/RY", "Royal Bank of Canada", 271_000_000_000, 196.68, 1.48, "Banks", 602_868, 17.4]]

    responses = [_FakeResponse(_payload(us_rows)), _FakeResponse(_payload(ca_rows))]
    with patch("portfolio_pipeline.data.universe.urllib.request.urlopen", side_effect=responses):
        combined = fetch_full_universe()
    assert len(combined) == 1
    assert combined[0].exchange == "US"


def test_screen_filters_on_market_cap_and_dollar_volume():
    rows = [
        UniverseRow("BIG", "Big Co", "US", "US", market_cap=10_000_000_000, price=100.0, day_change_pct=1.0, sector="Tech", volume=1_000_000, pe_ratio=20.0),
        UniverseRow("TINY", "Tiny Co", "US", "US", market_cap=5_000_000, price=2.0, day_change_pct=0.0, sector="Shell", volume=100, pe_ratio=None),
        UniverseRow("ILLIQUID", "Illiquid Co", "US", "US", market_cap=500_000_000, price=50.0, day_change_pct=0.0, sector="Tech", volume=10, pe_ratio=15.0),
    ]
    out = screen(rows, min_market_cap=100_000_000, min_dollar_volume=500_000)
    assert [r.ticker for r in out] == ["BIG"]
