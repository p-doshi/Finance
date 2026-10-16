import json

import pytest

from portfolio_pipeline.decision.trade_ticket import load_holdings, current_weights, generate_trade_ticket


def test_load_holdings_valid_file(tmp_path):
    path = tmp_path / "holdings.json"
    path.write_text(json.dumps({"cash": 100.0, "positions": {"AAA": 10}}))
    data = load_holdings(path)
    assert data["cash"] == 100.0
    assert data["positions"] == {"AAA": 10}


def test_load_holdings_rejects_missing_keys(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"positions": {"AAA": 10}}))  # missing 'cash'
    with pytest.raises(ValueError, match="missing required keys"):
        load_holdings(path)


def test_current_weights_known_case():
    holdings = {"cash": 100.0, "positions": {"AAA": 10, "BBB": 5}}
    prices = {"AAA": 20.0, "BBB": 10.0}
    weights, total = current_weights(holdings, prices)
    # AAA: 200, BBB: 50, cash: 100 -> total 350
    assert total == pytest.approx(350.0)
    assert weights["AAA"] == pytest.approx(200 / 350)
    assert weights["BBB"] == pytest.approx(50 / 350)


def test_current_weights_raises_on_missing_price():
    holdings = {"cash": 0.0, "positions": {"AAA": 10, "ZZZ": 1}}
    prices = {"AAA": 20.0}
    with pytest.raises(ValueError, match="no current price"):
        current_weights(holdings, prices)


def test_generate_trade_ticket_simple_rebalance_with_sufficient_cash():
    holdings = {"cash": 1000.0, "positions": {"AAA": 0, "BBB": 0}}
    prices = {"AAA": 100.0, "BBB": 50.0}
    target = {"AAA": 0.5, "BBB": 0.5}
    ticket = generate_trade_ticket(holdings, target, prices)
    # total value = 1000 (all cash), target AAA = 500 -> 5 shares, BBB = 500 -> 10 shares
    buys = {t.ticker: t.shares for t in ticket["trades"] if t.action == "BUY"}
    assert buys == {"AAA": 5, "BBB": 10}
    assert ticket["cash_after"] >= 0


def test_generate_trade_ticket_sells_a_position_not_in_target():
    holdings = {"cash": 0.0, "positions": {"AAA": 10}}
    prices = {"AAA": 50.0, "BBB": 20.0}
    target = {"BBB": 1.0}  # AAA has an implicit target weight of 0
    ticket = generate_trade_ticket(holdings, target, prices)
    sells = {t.ticker: t.shares for t in ticket["trades"] if t.action == "SELL"}
    assert sells == {"AAA": 10}


def test_generate_trade_ticket_drift_band_suppresses_tiny_trades():
    holdings = {"cash": 0.0, "positions": {"AAA": 50, "BBB": 50}}
    prices = {"AAA": 10.0, "BBB": 10.0}
    # current: 500/500 (50/50) -- target barely different (50.5/49.5) -> trade is tiny relative to $1000 total
    target = {"AAA": 0.505, "BBB": 0.495}
    ticket = generate_trade_ticket(holdings, target, prices, drift_band=0.05)
    assert ticket["trades"] == []


def test_generate_trade_ticket_drift_band_allows_large_trades_through():
    holdings = {"cash": 0.0, "positions": {"AAA": 50, "BBB": 50}}
    prices = {"AAA": 10.0, "BBB": 10.0}
    target = {"AAA": 0.8, "BBB": 0.2}  # a real, large rebalance
    ticket = generate_trade_ticket(holdings, target, prices, drift_band=0.05)
    assert len(ticket["trades"]) > 0


def test_generate_trade_ticket_scales_down_buys_when_cash_insufficient():
    """Target implies buying more than the account can actually afford --
    must scale down proportionally, never produce a ticket assuming money
    that isn't there. total_value = $100 (1 share of AAA) + $50 cash =
    $150; target wants BBB at 80% ($120), but only $50 cash is available
    (AAA isn't being sold here), so the buy must be scaled down."""
    prices = {"AAA": 100.0, "BBB": 100.0}
    holdings = {"cash": 50.0, "positions": {"AAA": 1}}
    target = {"AAA": 0.2, "BBB": 0.8}
    ticket = generate_trade_ticket(holdings, target, prices)
    assert ticket["buy_scale_applied"] <= 1.0
    assert ticket["cash_after"] >= -1e-9


def test_generate_trade_ticket_never_assumes_unavailable_cash_even_when_scaling_needed():
    holdings = {"cash": 10.0, "positions": {}}
    prices = {"AAA": 100.0, "BBB": 100.0, "CCC": 100.0, "DDD": 100.0, "EEE": 100.0}
    # with only $10 cash and a $500 implied total (if it were funded), nothing is affordable --
    # scale should come out at (or very near) 0, and no trade should be created with 0 shares
    target = {"AAA": 0.2, "BBB": 0.2, "CCC": 0.2, "DDD": 0.2, "EEE": 0.2}
    ticket = generate_trade_ticket(holdings, target, prices)
    assert ticket["cash_after"] >= -1e-9
    for t in ticket["trades"]:
        assert t.shares > 0  # never a zero-share trade in the output
