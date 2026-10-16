import json
from unittest.mock import patch

import pytest

from portfolio_pipeline.data.fetch import DataQualityError
from portfolio_pipeline.data.fetch_ca import (
    fetch_and_store_ca,
    fetch_raw_yahoo,
    to_stockanalysis_shape,
    to_yahoo_symbol,
)


class _FakeResponse:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_to_yahoo_symbol_mapping():
    assert to_yahoo_symbol("ATD", "TSX") == "ATD.TO"
    assert to_yahoo_symbol("AFM", "TSXV") == "AFM.V"
    assert to_yahoo_symbol("GTII", "CSE") == "GTII.CN"
    with pytest.raises(ValueError, match="no Yahoo suffix mapping"):
        to_yahoo_symbol("XXX", "US")


def _yahoo_chart_payload(n=5, start_ts=1700000000):
    timestamps = [start_ts + i * 86400 for i in range(n)]
    closes = [100.0 + i for i in range(n)]
    return {
        "chart": {
            "error": None,
            "result": [{
                "timestamp": timestamps,
                "indicators": {
                    "quote": [{"close": closes, "volume": [1000 + i for i in range(n)]}],
                    "adjclose": [{"adjclose": closes}],
                },
            }],
        }
    }


def test_fetch_raw_yahoo_success():
    payload = _yahoo_chart_payload()
    with patch("portfolio_pipeline.data.fetch_ca.urllib.request.urlopen", return_value=_FakeResponse(payload)):
        result = fetch_raw_yahoo("ATD", "TSX")
    assert len(result["timestamp"]) == 5


def test_fetch_raw_yahoo_raises_on_chart_error():
    payload = {"chart": {"error": {"code": "Not Found"}, "result": None}}
    with patch("portfolio_pipeline.data.fetch_ca.urllib.request.urlopen", return_value=_FakeResponse(payload)), \
            pytest.raises(DataQualityError, match="Yahoo error"):
        fetch_raw_yahoo("FAKE", "TSX")


def test_fetch_raw_yahoo_raises_on_empty_result():
    payload = {"chart": {"error": None, "result": []}}
    with patch("portfolio_pipeline.data.fetch_ca.urllib.request.urlopen", return_value=_FakeResponse(payload)), \
            pytest.raises(DataQualityError, match="no result"):
        fetch_raw_yahoo("FAKE", "TSX")


def test_to_stockanalysis_shape_converts_and_skips_null_sessions():
    yahoo_result = {
        "timestamp": [1700000000, 1700086400, 1700172800],
        "indicators": {
            "quote": [{"close": [100.0, None, 102.0], "volume": [1000, 0, 1200]}],
            "adjclose": [{"adjclose": [100.0, None, 102.0]}],
        },
    }
    shaped = to_stockanalysis_shape(yahoo_result)
    assert shaped["status"] == 200
    assert len(shaped["data"]) == 2  # the None session is dropped
    assert shaped["data"][0]["c"] == 100.0
    assert shaped["data"][1]["c"] == 102.0


def test_fetch_and_store_ca_writes_exchange_qualified_files(tmp_path):
    payload = _yahoo_chart_payload(n=250)  # clears validate()'s min_rows default
    with patch("portfolio_pipeline.data.fetch_ca.urllib.request.urlopen", return_value=_FakeResponse(payload)):
        rows = fetch_and_store_ca("ATD", "TSX", tmp_path)
    assert len(rows) == 250
    assert (tmp_path / "TSX_ATD.json").exists()
    raw_files = list((tmp_path / "raw" / "TSX_ATD").glob("*.json"))
    assert len(raw_files) == 1


def test_fetch_and_store_ca_does_not_collide_with_us_ticker_of_same_symbol(tmp_path):
    """The real bug this guards against: US CMG (Chipotle) and TSX CMG
    (Computer Modelling Group) must never write to the same file."""
    (tmp_path / "CMG.json").write_text(json.dumps({"marker": "us-chipotle"}))
    payload = _yahoo_chart_payload(n=250)
    with patch("portfolio_pipeline.data.fetch_ca.urllib.request.urlopen", return_value=_FakeResponse(payload)):
        fetch_and_store_ca("CMG", "TSX", tmp_path)
    assert json.loads((tmp_path / "CMG.json").read_text()) == {"marker": "us-chipotle"}
    assert (tmp_path / "TSX_CMG.json").exists()
