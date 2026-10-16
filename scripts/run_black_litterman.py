#!/usr/bin/env python3
"""Black-Litterman on the 12-stock watchlist: market-cap-implied
equilibrium returns (reverse-optimized from real market caps, Stage A
scan) blended with one illustrative view, then fed into the existing
optimizers.

Honest framing, stated once here and not hidden: the view below is
value-premium-grounded (cheapest vs. priciest P/E in the group) rather
than reusing Stage B's momentum signal, because research/ic_analysis.py
already found that signal has no demonstrated out-of-sample predictive
skill — it would be dishonest to launder a signal just shown not to work
into a "view" and call the result an improvement. The value view itself
also has NOT been validated with its own IC study here; it's included to
demonstrate the Black-Litterman machinery correctly, not as a claim this
project has found a working signal. Market caps for delta/view inputs:
results/screened_universe.json (Stage A, verified real data, not assumed).

Run: .venv/bin/python scripts/run_black_litterman.py
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from portfolio_pipeline.research.black_litterman import (
    implied_risk_aversion, market_implied_returns, black_litterman_posterior, relative_view,
)
from portfolio_pipeline.research.optimizers import max_sharpe_weight, risk_parity_weight, portfolio_stats

TICKERS = ["NVDA", "JNJ", "KO", "PG", "WMT", "VZ", "XOM", "RY", "ENB", "UL", "NVO", "ASML"]
RF = 0.0426
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"
WINDOW_DAYS = 756  # 3y, same base case as Phase 0


def load_log_returns(tickers):
    series = {}
    for t in tickers:
        d = json.load(open(DATA_DIR / f"{t}.json"))
        s = pd.Series({r["t"]: r["a"] for r in d["data"]}, name=t)
        s.index = pd.to_datetime(s.index)
        series[t] = s.sort_index()
    prices = pd.DataFrame(series).dropna(how="any")
    return np.log(prices / prices.shift(1)).dropna()


def main():
    log_ret = load_log_returns(TICKERS).tail(WINDOW_DAYS)
    cov = log_ret.cov().values * 252

    universe = json.load(open(RESULTS_DIR / "screened_universe.json"))
    by_ticker = {e["ticker"]: e for e in universe}
    market_caps = np.array([by_ticker[t]["market_cap"] for t in TICKERS], dtype=float)
    w_mkt = market_caps / market_caps.sum()
    print("Market-cap weights (Stage A scan, real data):")
    for t, w in zip(TICKERS, w_mkt):
        print(f"  {t:6} {w*100:5.1f}%  (mktcap ${market_caps[list(TICKERS).index(t)]/1e9:.1f}B, "
              f"P/E {by_ticker[t]['pe_ratio']:.1f})")

    spy_log_ret = load_log_returns(["SPY"])["SPY"].tail(WINDOW_DAYS)
    market_excess = spy_log_ret.mean() * 252 - RF
    market_var = spy_log_ret.var() * 252
    delta = implied_risk_aversion(market_excess, market_var)
    print(f"\nImplied risk aversion (delta) from SPY's own 3y Sharpe-like ratio: {delta:.2f}")

    pi = market_implied_returns(cov, w_mkt, delta)
    print(f"\nEquilibrium (implied) returns:")
    for t, p in zip(TICKERS, pi):
        print(f"  {t:6} {p*100:+6.1f}%")

    # Illustrative view: cheapest P/E (NVO, 9.5x) outperforms priciest (ASML, 53.8x)
    # by 5%/yr -- value-premium-grounded, modest confidence, NOT a validated signal
    # (see module/script docstrings).
    pe = {t: by_ticker[t]["pe_ratio"] for t in TICKERS}
    cheap, expensive = min(pe, key=pe.get), max(pe, key=pe.get)
    print(f"\nIllustrative view: {cheap} (P/E {pe[cheap]:.1f}) outperforms {expensive} "
          f"(P/E {pe[expensive]:.1f}) by 5%/yr (value-premium-grounded, NOT IC-validated here, "
          "modest confidence via the default He-Litterman uncertainty)")
    P, Q = relative_view(len(TICKERS), TICKERS.index(cheap), TICKERS.index(expensive), outperformance=0.05)

    posterior_mean, posterior_cov = black_litterman_posterior(cov, pi, P, Q, tau=0.05)
    print(f"\nPosterior returns (equilibrium blended with the one view above):")
    for t, p_prior, p_post in zip(TICKERS, pi, posterior_mean):
        shift = p_post - p_prior
        print(f"  {t:6} prior {p_prior*100:+6.1f}%  ->  posterior {p_post*100:+6.1f}%  (shift {shift*100:+.2f}pp)")

    w_bl_sharpe = max_sharpe_weight(posterior_cov, posterior_mean, RF)
    w_bl_rp = risk_parity_weight(posterior_cov)  # risk parity doesn't use the view's return at all, only cov -- included for contrast
    stats_bl_sharpe = portfolio_stats(w_bl_sharpe, posterior_cov, posterior_mean, RF)

    print(f"\n--- Weights: market-cap vs. BL-max-Sharpe vs. BL-risk-parity ---")
    print(f"{'Ticker':7}{'Mkt-cap wt':>12}{'BL max-Sharpe':>15}{'BL risk-parity':>16}")
    for i, t in enumerate(TICKERS):
        print(f"{t:7}{w_mkt[i]*100:11.1f}%{w_bl_sharpe[i]*100:14.1f}%{w_bl_rp[i]*100:15.1f}%")

    print(f"\nBL max-Sharpe portfolio: ret={stats_bl_sharpe['ret']*100:.2f}%  "
          f"vol={stats_bl_sharpe['vol']*100:.2f}%  sharpe={stats_bl_sharpe['sharpe']:.2f}")
    print(f"NVO weight moved from market-cap {w_mkt[TICKERS.index('NVO')]*100:.1f}% to "
          f"BL max-Sharpe {w_bl_sharpe[TICKERS.index('NVO')]*100:.1f}% -- the view's direct effect, "
          f"traceable rather than a black box.")

    RESULTS_DIR.mkdir(exist_ok=True)
    out = {
        "market_cap_weights": dict(zip(TICKERS, w_mkt.tolist())),
        "implied_risk_aversion": float(delta),
        "equilibrium_returns": dict(zip(TICKERS, pi.tolist())),
        "view": {"long": cheap, "short": expensive, "outperformance": 0.05},
        "posterior_returns": dict(zip(TICKERS, posterior_mean.tolist())),
        "weights": {
            "market_cap": dict(zip(TICKERS, w_mkt.tolist())),
            "bl_max_sharpe": dict(zip(TICKERS, w_bl_sharpe.tolist())),
            "bl_risk_parity": dict(zip(TICKERS, w_bl_rp.tolist())),
        },
        "bl_max_sharpe_stats": stats_bl_sharpe,
    }
    with open(RESULTS_DIR / "black_litterman_output.json", "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nSaved {RESULTS_DIR / 'black_litterman_output.json'}")


if __name__ == "__main__":
    main()
