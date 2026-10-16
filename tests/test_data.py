from datetime import date, timedelta
from unittest.mock import patch

import pytest

from portfolio_pipeline.data.fetch import DataQualityError, save_point_in_time, validate


def _payload(rows):
    return {"status": 200, "data": rows}


def _good_rows(n=250, start_price=100.0):
    rows = []
    price = start_price
    d = date(2024, 1, 1)
    for _ in range(n):
        price *= 1.001  # gentle upward drift, no single-day shocks
        rows.append({"t": d.isoformat(), "c": price, "a": price, "v": 1_000_000})
        d += timedelta(days=1)
    return rows


def test_validate_accepts_well_formed_series():
    rows = validate("TEST", _payload(_good_rows()))
    assert len(rows) == 250
    assert rows[0].adj_close < rows[-1].adj_close  # drift preserved


def test_validate_rejects_too_few_rows():
    with pytest.raises(DataQualityError, match="only"):
        validate("TEST", _payload(_good_rows(n=10)), min_rows=200)


def test_validate_rejects_duplicate_dates():
    rows = _good_rows()
    rows.append(rows[-1])
    with pytest.raises(DataQualityError, match="duplicate"):
        validate("TEST", _payload(rows))


def test_validate_rejects_non_positive_price():
    rows = _good_rows()
    rows[5]["a"] = 0.0
    with pytest.raises(DataQualityError, match="non-positive"):
        validate("TEST", _payload(rows))


def test_validate_rejects_extreme_single_day_move():
    rows = _good_rows()
    rows[10]["a"] = rows[9]["a"] * 3.0  # +200% in a day, not a plausible organic move
    with pytest.raises(DataQualityError, match="single-day"):
        validate("TEST", _payload(rows))


def test_validate_accepts_large_but_plausible_move_under_threshold():
    rows = _good_rows()
    rows[10]["a"] = rows[9]["a"] * 1.35  # +35% move (e.g. a real earnings pop) clears the 50% default
    validate("TEST", _payload(rows))  # should not raise


def test_fetch_and_store_passes_through_max_single_day_move(tmp_path):
    """A 300% move would fail the 50% default but should be accepted (and
    not silently ignored elsewhere) when the caller explicitly raises the
    threshold for a more volatile universe — see Stage B's BMNR/DFDV finding
    in docs/methodology.md."""
    from portfolio_pipeline.data.fetch import fetch_and_store

    rows = _good_rows()
    rows[10]["a"] = rows[9]["a"] * 4.0  # +300%
    payload = _payload(rows)

    with patch("portfolio_pipeline.data.fetch.fetch_raw", return_value=payload):
        with pytest.raises(DataQualityError, match="single-day"):
            fetch_and_store("TEST", tmp_path)  # default threshold still rejects it
        got = fetch_and_store("TEST", tmp_path, max_single_day_move=5.0)  # explicit override accepts it
    assert len(got) == len(rows)


def test_save_point_in_time_accepts_plain_string_path(tmp_path):
    """Regression test: save_point_in_time used to crash with a plain
    string data_dir (str / str is a TypeError) — only caught because
    scripts pass Path objects in every other call site. Coerce internally
    instead of relying on every future caller remembering to wrap it."""
    save_point_in_time("TEST", _payload(_good_rows()), str(tmp_path))
    assert (tmp_path / "TEST.json").exists()
    raw_files = list((tmp_path / "raw" / "TEST").glob("*.json"))
    assert len(raw_files) == 1
