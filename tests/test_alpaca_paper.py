import json
import urllib.error
from unittest.mock import patch, MagicMock

import pytest

from portfolio_pipeline.execution.alpaca_paper import (
    AlpacaPaperClient, AlpacaCredentialsError, AlpacaAPIError, PAPER_BASE_URL,
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


def test_raises_without_any_credentials(monkeypatch):
    monkeypatch.delenv("ALPACA_API_KEY_ID", raising=False)
    monkeypatch.delenv("ALPACA_API_SECRET_KEY", raising=False)
    with pytest.raises(AlpacaCredentialsError, match="No Alpaca API credentials"):
        AlpacaPaperClient()


def test_reads_credentials_from_env_vars(monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY_ID", "key123")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "secret456")
    client = AlpacaPaperClient()
    assert client.api_key_id == "key123"
    assert client.api_secret_key == "secret456"


def test_explicit_credentials_do_not_need_env_vars(monkeypatch):
    monkeypatch.delenv("ALPACA_API_KEY_ID", raising=False)
    monkeypatch.delenv("ALPACA_API_SECRET_KEY", raising=False)
    client = AlpacaPaperClient(api_key_id="a", api_secret_key="b")
    assert client.api_key_id == "a"


def test_refuses_any_non_paper_base_url():
    with pytest.raises(ValueError, match="hard-locked to Alpaca's PAPER endpoint"):
        AlpacaPaperClient(api_key_id="a", api_secret_key="b", base_url="https://api.alpaca.markets")


def test_get_account_parses_response_and_uses_correct_headers():
    client = AlpacaPaperClient(api_key_id="key123", api_secret_key="secret456")
    payload = {"cash": "1000.00", "equity": "1000.00", "buying_power": "2000.00"}
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["method"] = req.get_method()
        captured["headers"] = {k: v for k, v in req.header_items()}
        return _FakeResponse(payload)

    with patch("portfolio_pipeline.execution.alpaca_paper.urllib.request.urlopen", side_effect=fake_urlopen):
        result = client.get_account()

    assert result == payload
    assert captured["url"] == f"{PAPER_BASE_URL}/v2/account"
    assert captured["method"] == "GET"
    assert captured["headers"]["Apca-api-key-id"] == "key123"
    assert captured["headers"]["Apca-api-secret-key"] == "secret456"


def test_get_positions_returns_list():
    client = AlpacaPaperClient(api_key_id="a", api_secret_key="b")
    payload = [{"symbol": "AAPL", "qty": "10", "market_value": "1900.00"}]
    with patch("portfolio_pipeline.execution.alpaca_paper.urllib.request.urlopen",
               return_value=_FakeResponse(payload)):
        result = client.get_positions()
    assert result == payload


def test_submit_order_builds_correct_request_body():
    client = AlpacaPaperClient(api_key_id="a", api_secret_key="b")
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["body"] = json.loads(req.data.decode("utf-8"))
        captured["method"] = req.get_method()
        return _FakeResponse({"id": "abc-123", "status": "accepted", "filled_qty": "0"})

    with patch("portfolio_pipeline.execution.alpaca_paper.urllib.request.urlopen", side_effect=fake_urlopen):
        result = client.submit_order("NVDA", qty=3, side="buy")

    assert captured["method"] == "POST"
    assert captured["body"] == {"symbol": "NVDA", "qty": "3", "side": "buy",
                                  "type": "market", "time_in_force": "day"}
    assert result["status"] == "accepted"


def test_submit_order_rejects_invalid_side_without_any_network_call():
    client = AlpacaPaperClient(api_key_id="a", api_secret_key="b")
    with patch("portfolio_pipeline.execution.alpaca_paper.urllib.request.urlopen") as mock_urlopen:
        with pytest.raises(ValueError, match="side must be"):
            client.submit_order("NVDA", qty=1, side="hold")
    mock_urlopen.assert_not_called()


def test_submit_order_rejects_non_positive_qty_without_any_network_call():
    client = AlpacaPaperClient(api_key_id="a", api_secret_key="b")
    with patch("portfolio_pipeline.execution.alpaca_paper.urllib.request.urlopen") as mock_urlopen:
        with pytest.raises(ValueError, match="qty must be positive"):
            client.submit_order("NVDA", qty=0, side="buy")
    mock_urlopen.assert_not_called()


def test_http_error_wrapped_as_alpaca_api_error():
    client = AlpacaPaperClient(api_key_id="a", api_secret_key="b")
    err = urllib.error.HTTPError(url="x", code=403, msg="Forbidden", hdrs=None, fp=MagicMock(
        read=lambda: b'{"message": "insufficient buying power"}'))
    with patch("portfolio_pipeline.execution.alpaca_paper.urllib.request.urlopen", side_effect=err):
        with pytest.raises(AlpacaAPIError, match="403"):
            client.get_account()


def test_url_error_wrapped_as_alpaca_api_error():
    client = AlpacaPaperClient(api_key_id="a", api_secret_key="b")
    with patch("portfolio_pipeline.execution.alpaca_paper.urllib.request.urlopen",
               side_effect=urllib.error.URLError("network down")):
        with pytest.raises(AlpacaAPIError, match="request failed"):
            client.get_positions()
