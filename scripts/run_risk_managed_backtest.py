#!/usr/bin/env python3
"""Phase 2: risk management layer, demonstrated on the real 12-stock
walk-forward backtest rather than left as untested library functions.
Three controls, each checked for a real, measurable effect:

  1. Position caps (risk/controls.cap_weights) -- bounds single-name risk.
  2. Rebalance band (research.backtest.walk_forward's drift_band) -- skips
     trading on noise-level drift, reducing turnover/cost.
  3. Volatility targeting (risk/controls.volatility_target_scale) -- scales
     exposure toward cash when ex-ante risk runs hot, capped at 100% risky
     exposure (no leverage -- see risk/controls.py's docstring on why,
     unlike AQR's levered risk-parity funds, a retail account can't do this).

Run after scripts/run_backtest.py: .venv/bin/python scripts/run_risk_managed_backtest.py
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from portfolio_pipeline.research.optimizers import risk_parity_weight
from portfolio_pipeline.research.backtest import walk_forward
from portfolio_pipeline.risk.controls import cap_weights, volatility_target_scale

TICKERS = ["NVDA", "JNJ", "KO", "PG", "WMT", "VZ", "XOM", "RY", "ENB", "UL", "NVO", "ASML"]
RF = 0.0426
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"
WINDOW, REBAL_EVERY, COST_BPS = 756, 21, 10.0
PERIODS_PER_YEAR = 252 / REBAL_EVERY
CAP = 0.095           # feasible for 12 names (0.095*12=1.14>=1.0) and still binds for risk parity's
                       # higher-weight names (Phase 0 showed up to ~10.6%)
TARGET_VOL = 0.09      # below risk parity's own realized 10.0% (Phase 1), so this should actually bind sometimes


def load_log_returns():
    series = {}
    for t in TICKERS:
        d = json.load(open(DATA_DIR / f"{t}.json"))
        s = pd.Series({r["t"]: r["a"] for r in d["data"]}, name=t)
        s.index = pd.to_datetime(s.index)
        series[t] = s.sort_index()
    prices = pd.DataFrame(series).dropna(how="any")
    return np.log(prices / prices.shift(1)).dropna()


def main():
    log_ret = load_log_returns()

    def rp_fn(trailing):
        return risk_parity_weight(trailing.cov().values * 252)

    def rp_capped_fn(trailing):
        return cap_weights(risk_parity_weight(trailing.cov().values * 252), max_weight=CAP)

    print(f"--- 1. Position cap at {CAP*100:.0f}% ---")
    baseline = walk_forward(log_ret, rp_fn, window=WINDOW, rebal_every=REBAL_EVERY, cost_bps=COST_BPS)
    capped = walk_forward(log_ret, rp_capped_fn, window=WINDOW, rebal_every=REBAL_EVERY, cost_bps=COST_BPS)
    max_w_baseline = max(w.max() for w in baseline.weights)
    max_w_capped = max(w.max() for w in capped.weights)
    print(f"Max single-name weight ever held: baseline {max_w_baseline*100:.1f}% -> capped {max_w_capped*100:.1f}%")
    print(f"Ann. return: baseline {baseline.annualized_return(PERIODS_PER_YEAR)*100:.2f}% -> "
          f"capped {capped.annualized_return(PERIODS_PER_YEAR)*100:.2f}%")
    print(f"Ann. vol:    baseline {baseline.annualized_vol(PERIODS_PER_YEAR)*100:.2f}% -> "
          f"capped {capped.annualized_vol(PERIODS_PER_YEAR)*100:.2f}%")

    print(f"\n--- 2. Rebalance band (drift_band=3pp) ---")
    banded = walk_forward(log_ret, rp_fn, window=WINDOW, rebal_every=REBAL_EVERY, cost_bps=COST_BPS,
                           drift_band=0.03)
    print(f"Avg turnover:  no band {baseline.avg_turnover()*100:.1f}%  ->  banded {banded.avg_turnover()*100:.1f}%")
    print(f"Periods actually rebalanced (nonzero turnover after period 0): "
          f"no band {int(np.sum(baseline.turnover[1:] > 1e-9))}/{len(baseline.turnover)-1}  ->  "
          f"banded {int(np.sum(banded.turnover[1:] > 1e-9))}/{len(banded.turnover)-1}")
    print(f"Ann. return(net): no band {baseline.annualized_return(PERIODS_PER_YEAR)*100:.2f}%  ->  "
          f"banded {banded.annualized_return(PERIODS_PER_YEAR)*100:.2f}%  "
          f"(fewer trades -> lower cost drag, at the price of drifting further from target between rebalances)")

    print(f"\n--- 3. Volatility targeting (target {TARGET_VOL*100:.0f}%, max_leverage=1.0 -- no margin) ---")
    rebal_idx = list(range(WINDOW, len(log_ret), REBAL_EVERY))
    scales = []
    scaled_period_returns = []
    for k, i in enumerate(rebal_idx[:len(baseline.period_returns)]):
        trailing = log_ret.iloc[i - WINDOW:i]
        cov = trailing.cov().values * 252
        w = baseline.weights[k]
        ex_ante_vol = float(np.sqrt(w @ cov @ w))
        scale = volatility_target_scale(ex_ante_vol, TARGET_VOL, max_leverage=1.0)
        scales.append(scale)
        scaled_period_returns.append(scale * baseline.period_returns[k])
    scales = np.array(scales)
    scaled_period_returns = np.array(scaled_period_returns)

    realized_vol_before = baseline.net_period_returns.std(ddof=1) * np.sqrt(PERIODS_PER_YEAR)
    realized_vol_after = pd.Series(scaled_period_returns).std(ddof=1) * np.sqrt(PERIODS_PER_YEAR)
    ann_return_after = np.expm1(scaled_period_returns.sum() / (len(scaled_period_returns) / PERIODS_PER_YEAR))
    print(f"Scale factor: mean {scales.mean():.2f}, range [{scales.min():.2f}, {scales.max():.2f}] "
          f"across {len(scales)} periods")
    print(f"Realized ann. vol: {realized_vol_before*100:.2f}% -> {realized_vol_after*100:.2f}% "
          f"(target was {TARGET_VOL*100:.0f}%)")
    print(f"Ann. return: {baseline.annualized_return(PERIODS_PER_YEAR)*100:.2f}% -> {ann_return_after*100:.2f}% "
          f"(de-risking also gives up some return -- that's the actual trade this control makes, not a free lunch)")
    print("Caveat: this scales realized returns by an ex-ante (trailing-covariance-implied) vol estimate, not a "
          "fully re-costed cash/risky rebalancing simulation -- the cash leg's own transaction cost isn't modeled.")

    RESULTS_DIR.mkdir(exist_ok=True)
    out = {
        "position_cap": {"cap": CAP, "max_weight_baseline": max_w_baseline, "max_weight_capped": max_w_capped,
                          "ann_return_baseline": baseline.annualized_return(PERIODS_PER_YEAR),
                          "ann_return_capped": capped.annualized_return(PERIODS_PER_YEAR)},
        "rebalance_band": {"band": 0.03, "avg_turnover_baseline": baseline.avg_turnover(),
                            "avg_turnover_banded": banded.avg_turnover(),
                            "ann_return_baseline": baseline.annualized_return(PERIODS_PER_YEAR),
                            "ann_return_banded": banded.annualized_return(PERIODS_PER_YEAR)},
        "vol_targeting": {"target_vol": TARGET_VOL, "scale_mean": float(scales.mean()),
                           "scale_min": float(scales.min()), "scale_max": float(scales.max()),
                           "realized_vol_before": float(realized_vol_before), "realized_vol_after": float(realized_vol_after),
                           "ann_return_before": baseline.annualized_return(PERIODS_PER_YEAR),
                           "ann_return_after": float(ann_return_after)},
    }
    with open(RESULTS_DIR / "risk_management_output.json", "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nSaved {RESULTS_DIR / 'risk_management_output.json'}")


if __name__ == "__main__":
    main()
