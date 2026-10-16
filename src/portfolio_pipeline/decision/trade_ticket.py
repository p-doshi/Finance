"""Phase 3, the decision layer: compares manually-entered current holdings
against target weights and produces a trade ticket in whole shares. Never
submits anything — see `portfolio_pipeline/__init__.py`'s module docstring
on why (Wealthsimple Trade's ToS prohibits API order submission; IIROC
doesn't permit it for self-directed Canadian accounts either). Holdings
are entered by hand in `portfolio_state.json` (gitignored — see
`.gitignore` and `portfolio_state.example.json`) because there's no safe
programmatic *read* path into the brokerage either, only no safe *write*
path.
"""
from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass
class Trade:
    ticker: str
    action: str  # "BUY" or "SELL"
    shares: int
    price: float
    est_value: float


def load_holdings(path) -> dict:
    data = json.load(open(path))
    required = {"cash", "positions"}
    missing = required - data.keys()
    if missing:
        raise ValueError(f"holdings file missing required keys: {missing}")
    return data


def current_weights(holdings: dict, latest_prices: dict) -> tuple[dict, float]:
    """Returns (weights_by_ticker, total_portfolio_value). Cash counts
    toward total value but has no entry in the returned weights dict,
    matching how target weights (which also don't carry a 'cash' entry)
    are expressed."""
    missing = set(holdings["positions"]) - set(latest_prices)
    if missing:
        raise ValueError(f"no current price available for held tickers: {missing}")
    position_values = {t: shares * latest_prices[t] for t, shares in holdings["positions"].items()}
    total_value = sum(position_values.values()) + holdings["cash"]
    weights = {t: v / total_value for t, v in position_values.items()} if total_value > 0 else {}
    return weights, total_value


def generate_trade_ticket(holdings: dict, target_weights: dict, latest_prices: dict,
                           drift_band: float = 0.0) -> dict:
    """For every ticker in `target_weights` or currently held, computes
    the whole-share trade that moves toward the target. Skips any trade
    whose dollar size is below `drift_band` of total portfolio value
    (don't trade on noise — same idea as `research.backtest`'s
    `drift_band`). If the naive target-implied buys would cost more than
    the account actually has (existing cash + this ticket's own sell
    proceeds), scales every buy down proportionally rather than producing
    a ticket that assumes money the account doesn't have. Target share
    counts are floored, never rounded up, for the same reason — never plan
    to spend more than the target implies.
    """
    current_w, total_value = current_weights(holdings, latest_prices)
    all_tickers = set(target_weights) | set(holdings["positions"])
    missing_prices = all_tickers - set(latest_prices)
    if missing_prices:
        raise ValueError(f"no current price available for: {missing_prices}")

    current_shares = {t: holdings["positions"].get(t, 0) for t in all_tickers}
    target_shares = {
        t: int((target_weights.get(t, 0.0) * total_value) // latest_prices[t])
        for t in all_tickers
    }
    raw_trade_shares = {t: target_shares[t] - current_shares[t] for t in all_tickers}

    for t in list(raw_trade_shares):
        trade_value = abs(raw_trade_shares[t]) * latest_prices[t]
        if trade_value < drift_band * total_value:
            raw_trade_shares[t] = 0

    sells = {t: -n for t, n in raw_trade_shares.items() if n < 0}
    buys = {t: n for t, n in raw_trade_shares.items() if n > 0}
    sell_proceeds = sum(n * latest_prices[t] for t, n in sells.items())
    available_cash = holdings["cash"] + sell_proceeds
    buy_cost = sum(n * latest_prices[t] for t, n in buys.items())

    scale = 1.0 if buy_cost <= available_cash or buy_cost == 0 else available_cash / buy_cost
    scaled_buys = {t: int(n * scale) for t, n in buys.items()}

    trades = [Trade(t, "SELL", n, latest_prices[t], round(n * latest_prices[t], 2)) for t, n in sells.items()]
    trades += [Trade(t, "BUY", n, latest_prices[t], round(n * latest_prices[t], 2))
               for t, n in scaled_buys.items() if n > 0]

    final_buy_cost = sum(t.est_value for t in trades if t.action == "BUY")
    final_sell_proceeds = sum(t.est_value for t in trades if t.action == "SELL")

    return {
        "total_value": total_value,
        "current_weights": current_w,
        "target_weights": target_weights,
        "trades": trades,
        "cash_before": holdings["cash"],
        "cash_after": round(holdings["cash"] + final_sell_proceeds - final_buy_cost, 2),
        "buy_scale_applied": scale,
    }
