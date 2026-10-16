#!/usr/bin/env python3
"""Stage C: build an actual portfolio from Stage B's ranked universe —
top-K names by composite momentum rank, N large enough that sample
covariance starts to strain (unlike the 12-stock case, where Phase 0 found
condition number 8.2, already fine). Demonstrates Ledoit-Wolf shrinkage's
real value directly rather than asserting it: same K names, same window,
sample vs. shrunk covariance, compared on condition number and on the
resulting risk-parity weights.

Run after scripts/rank_universe.py: .venv/bin/python scripts/build_large_portfolio.py
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from portfolio_pipeline.research.covariance import sample_covariance, shrunk_covariance, condition_number
from portfolio_pipeline.research.optimizers import risk_parity_weight, portfolio_stats
from portfolio_pipeline.research.hrp import hrp_weight

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
RESULTS_DIR = ROOT / "results"
WINDOW_DAYS = 252  # 1y — chosen deliberately so N approaches the observation
                   # count at the larger K values tested below, which is the
                   # regime shrinkage is actually for (see research/covariance.py)


def data_path(ticker: str, country: str, exchange: str) -> Path:
    return DATA_DIR / f"{ticker}.json" if country == "US" else DATA_DIR / f"{exchange}_{ticker}.json"


def load_log_returns(path: Path) -> pd.Series:
    d = json.load(open(path))
    s = pd.Series({r["t"]: r["a"] for r in d["data"]})
    s.index = pd.to_datetime(s.index)
    return np.log(s.sort_index() / s.sort_index().shift(1)).dropna()


def build_for_k(ranked: list[dict], k: int):
    top_k = ranked[:k]
    series = {}
    for entry in top_k:
        path = data_path(entry["ticker"], entry["country"], entry["exchange"])
        if not path.exists():
            continue
        series[entry["ticker"]] = load_log_returns(path)
    df = pd.DataFrame(series).dropna(how="any").tail(WINDOW_DAYS)
    n_assets, n_obs = df.shape[1], len(df)

    cov_sample = sample_covariance(df)
    cov_shrunk, intensity = shrunk_covariance(df)
    cond_sample = condition_number(cov_sample)
    cond_shrunk = condition_number(cov_shrunk)

    w_sample = risk_parity_weight(cov_sample)
    w_shrunk = risk_parity_weight(cov_shrunk)
    weight_diff = np.abs(w_sample - w_shrunk)

    # HRP never inverts the covariance matrix at all (research/hrp.py), so it's
    # run here on the raw sample covariance even where that matrix is singular
    # (K=300) — exactly the case min_variance/max_sharpe would hard-fail on.
    w_hrp = hrp_weight(cov_sample)

    mu = df.mean().values * 252  # only used for the return side of portfolio_stats, not the optimization itself
    stats_sample = portfolio_stats(w_sample, cov_sample, mu, rf=0.0426)
    stats_shrunk = portfolio_stats(w_shrunk, cov_shrunk, mu, rf=0.0426)
    stats_hrp = portfolio_stats(w_hrp, cov_shrunk, mu, rf=0.0426)  # evaluated on the stable (shrunk) cov either way

    return {
        "k_requested": k, "n_assets": n_assets, "n_obs": n_obs,
        "shrinkage_intensity": intensity,
        "condition_number_sample": cond_sample, "condition_number_shrunk": cond_shrunk,
        "max_weight_diff_pp": float(weight_diff.max() * 100),
        "mean_weight_diff_pp": float(weight_diff.mean() * 100),
        "vol_sample": stats_sample["vol"], "vol_shrunk": stats_shrunk["vol"],
        "vol_hrp": stats_hrp["vol"], "n_eff_hrp": stats_hrp["n_effective"],
        "n_eff_sample_rp": stats_sample["n_effective"], "n_eff_shrunk_rp": stats_shrunk["n_effective"],
    }


def main():
    ranked = json.load(open(RESULTS_DIR / "universe_rankings.json"))
    ranked = [r for r in ranked if r.get("n_horizons_used") == 3]
    ranked.sort(key=lambda r: -r["composite_rank"])

    print(f"Ranked universe available: {len(ranked)} names with full 3/6/12mo history.\n")
    print(f"{'K':>5}{'n_assets':>10}{'n_obs':>8}{'shrink%':>9}{'cond(sample)':>14}{'cond(shrunk)':>14}"
          f"{'max Δw(pp)':>12}{'vol(sample)%':>14}{'vol(shrunk)%':>14}{'vol(hrp)%':>12}{'n_eff(hrp)':>12}")

    results = []
    for k in [20, 50, 100, 200, 300]:
        if k > len(ranked):
            continue
        r = build_for_k(ranked, k)
        results.append(r)
        print(f"{r['k_requested']:>5}{r['n_assets']:>10}{r['n_obs']:>8}{r['shrinkage_intensity']*100:>8.1f}%"
              f"{r['condition_number_sample']:>14.1f}{r['condition_number_shrunk']:>14.1f}"
              f"{r['max_weight_diff_pp']:>11.2f}pp{r['vol_sample']*100:>13.1f}%{r['vol_shrunk']*100:>13.1f}%"
              f"{r['vol_hrp']*100:>11.1f}%{r['n_eff_hrp']:>12.1f}")

    RESULTS_DIR.mkdir(exist_ok=True)
    with open(RESULTS_DIR / "large_portfolio_shrinkage_comparison.json", "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved {RESULTS_DIR / 'large_portfolio_shrinkage_comparison.json'}")


if __name__ == "__main__":
    main()
