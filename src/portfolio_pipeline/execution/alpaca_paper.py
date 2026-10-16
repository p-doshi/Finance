"""Alpaca paper-trading client — the one place in this project that
submits actual orders, and only ever to Alpaca's fake-money paper
endpoint. This is a deliberate, narrow exception: every other part of
this project (decision/trade_ticket.py, the monitor dashboard) stops at
"here's what to do," specifically because Wealthsimple's ToS and IIROC
forbid API order submission for a real self-directed Canadian account
(docs/methodology.md §0). Alpaca's PAPER account is fake money with no
such restriction, and is the standard free way to validate a strategy's
actual order-submission mechanics before ever trusting it for a real
manual trade.

**Hard safety gate, not just a convention:** this client refuses to
construct with any base URL other than Alpaca's paper endpoint. There is
no parameter, flag, or environment variable anywhere in this file that
can point it at the live-trading endpoint — if you genuinely want live
Alpaca trading, that is a deliberate decision outside this project's
scope and should not go through this class.

Setup (free, does this project no good without it): sign up at
alpaca.markets, generate paper-trading API keys, and set
ALPACA_API_KEY_ID / ALPACA_API_SECRET_KEY as environment variables.
Nothing in this file asks for or stores a credential anywhere else.

Endpoints verified directly against Alpaca's current API docs (not
assumed from memory) on 2026-10-16:
  GET  /v2/account    -> cash, equity, buying_power
  GET  /v2/positions  -> list of {symbol, qty, market_value, ...}
  POST /v2/orders     -> {symbol, qty, side, type, time_in_force} -> order object
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

PAPER_BASE_URL = "https://paper-api.alpaca.markets"


class AlpacaCredentialsError(RuntimeError):
    pass


class AlpacaAPIError(RuntimeError):
    pass


class AlpacaPaperClient:
    def __init__(self, api_key_id: str | None = None, api_secret_key: str | None = None,
                 base_url: str = PAPER_BASE_URL, timeout: float = 15.0):
        if base_url != PAPER_BASE_URL:
            raise ValueError(
                f"This client is deliberately hard-locked to Alpaca's PAPER endpoint "
                f"({PAPER_BASE_URL}) and refuses base_url={base_url!r}. See this module's "
                f"docstring — live trading is intentionally out of scope here."
            )
        self.base_url = base_url
        self.timeout = timeout
        self.api_key_id = api_key_id or os.environ.get("ALPACA_API_KEY_ID")
        self.api_secret_key = api_secret_key or os.environ.get("ALPACA_API_SECRET_KEY")
        if not self.api_key_id or not self.api_secret_key:
            raise AlpacaCredentialsError(
                "No Alpaca API credentials found. Set ALPACA_API_KEY_ID and "
                "ALPACA_API_SECRET_KEY environment variables (free paper-trading "
                "account: sign up at alpaca.markets, generate paper API keys)."
            )

    def _headers(self) -> dict:
        return {"APCA-API-KEY-ID": self.api_key_id, "APCA-API-SECRET-KEY": self.api_secret_key,
                "Content-Type": "application/json"}

    def _request(self, method: str, path: str, body: dict | None = None):
        url = f"{self.base_url}{path}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, headers=self._headers(), method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise AlpacaAPIError(f"Alpaca API error {e.code} on {method} {path}: {e.read().decode('utf-8', 'replace')}") from e
        except urllib.error.URLError as e:
            raise AlpacaAPIError(f"Alpaca API request failed on {method} {path}: {e}") from e

    def get_account(self) -> dict:
        return self._request("GET", "/v2/account")

    def get_positions(self) -> list[dict]:
        return self._request("GET", "/v2/positions")

    def submit_order(self, symbol: str, qty: int, side: str, order_type: str = "market",
                      time_in_force: str = "day") -> dict:
        if side not in ("buy", "sell"):
            raise ValueError(f"side must be 'buy' or 'sell', got {side!r}")
        if qty <= 0:
            raise ValueError(f"qty must be positive, got {qty}")
        body = {"symbol": symbol, "qty": str(qty), "side": side, "type": order_type,
                "time_in_force": time_in_force}
        return self._request("POST", "/v2/orders", body)
