#!/usr/bin/env python3
"""Full US + Canada market scan: two bulk API calls, no per-ticker looping.
Reports the whole-market picture (counts, sectors, today's biggest movers)
and the screened (liquid, non-shell) subset that Stage B would rank further.

Run: .venv/bin/python scripts/scan_universe.py
"""
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from portfolio_pipeline.data.universe import fetch_full_universe, screen

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"


def main():
    rows = fetch_full_universe()
    by_country = Counter(r.country for r in rows)
    by_exchange = Counter(r.exchange for r in rows)
    print(f"Full universe: {len(rows)} names")
    print(f"  by country:  {dict(by_country)}")
    print(f"  by exchange: {dict(by_exchange)}")

    screened = screen(rows, min_market_cap=100_000_000, min_dollar_volume=500_000)
    print(f"\nAfter liquidity/size screen (mkt cap >= $100M, day $ volume >= $500k): {len(screened)} names "
          f"({len(screened) / len(rows):.1%} of full universe)")

    sector_counts = Counter(r.sector for r in screened if r.sector)
    print(f"\nTop 10 sectors/industries in screened universe:")
    for sector, n in sector_counts.most_common(10):
        print(f"  {sector:40} {n:5}")

    with_change = [r for r in screened if r.day_change_pct is not None]
    gainers = sorted(with_change, key=lambda r: r.day_change_pct, reverse=True)[:15]
    losers = sorted(with_change, key=lambda r: r.day_change_pct)[:15]

    print(f"\nTop 15 gainers today (screened universe):")
    for r in gainers:
        print(f"  {r.ticker:8} {r.exchange:5} {r.day_change_pct:+6.2f}%  {r.name[:40]:40} mktcap=${r.market_cap/1e9:7.2f}B")

    print(f"\nTop 15 losers today (screened universe):")
    for r in losers:
        print(f"  {r.ticker:8} {r.exchange:5} {r.day_change_pct:+6.2f}%  {r.name[:40]:40} mktcap=${r.market_cap/1e9:7.2f}B")

    by_mcap = sorted(screened, key=lambda r: r.market_cap or 0, reverse=True)[:15]
    print(f"\nTop 15 by market cap:")
    for r in by_mcap:
        print(f"  {r.ticker:8} {r.exchange:5} ${r.market_cap/1e9:9.1f}B  {r.name[:40]}")

    RESULTS_DIR.mkdir(exist_ok=True)
    out = {
        "full_universe_count": len(rows),
        "by_country": dict(by_country),
        "by_exchange": dict(by_exchange),
        "screened_count": len(screened),
        "screen_params": {"min_market_cap": 100_000_000, "min_dollar_volume": 500_000},
        "sector_counts": dict(sector_counts),
        "top_gainers": [{"ticker": r.ticker, "exchange": r.exchange, "name": r.name,
                          "day_change_pct": r.day_change_pct, "market_cap": r.market_cap} for r in gainers],
        "top_losers": [{"ticker": r.ticker, "exchange": r.exchange, "name": r.name,
                         "day_change_pct": r.day_change_pct, "market_cap": r.market_cap} for r in losers],
        "top_by_market_cap": [{"ticker": r.ticker, "exchange": r.exchange, "name": r.name,
                                "market_cap": r.market_cap} for r in by_mcap],
    }
    with open(RESULTS_DIR / "universe_scan.json", "w") as f:
        json.dump(out, f, indent=2)

    # Full screened list saved separately — this is the Stage B input, not just a summary.
    screened_full = [{"ticker": r.ticker, "country": r.country, "exchange": r.exchange, "name": r.name,
                       "market_cap": r.market_cap, "price": r.price, "day_change_pct": r.day_change_pct,
                       "sector": r.sector, "volume": r.volume, "pe_ratio": r.pe_ratio} for r in screened]
    with open(RESULTS_DIR / "screened_universe.json", "w") as f:
        json.dump(screened_full, f, indent=2)
    print(f"\nSaved results/universe_scan.json (summary) and results/screened_universe.json "
          f"({len(screened_full)} names, full records for Stage B)")


if __name__ == "__main__":
    main()
