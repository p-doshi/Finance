#!/usr/bin/env python3
"""Does Stage B's momentum ranking actually predict forward returns, or
just reorder history? Alphalens-style Information Coefficient study
(research/ic_analysis.py) across every ticker with price history on disk,
quarterly snapshots over the full 5y window, 1-month forward returns.

No new network calls — uses exactly the data scripts/fetch_universe_history.py
already pulled. Run after that script (and after rank_universe.py, though
this recomputes the signal itself rather than reading its output, so it
can evaluate the signal at historical dates rank_universe.py never looked at).

Run: .venv/bin/python scripts/validate_ranker_ic.py
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from portfolio_pipeline.research.ic_analysis import (
    composite_momentum_signal,
    forward_window_return,
    run_ic_study,
    summarize_ic,
)

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
RESULTS_DIR = ROOT / "results"
HORIZON = 21          # ~1 month forward return
SNAPSHOT_EVERY = 63    # ~quarterly
MIN_LOOKBACK = 252     # need a full 12-month trailing window for the longest signal horizon


def data_path(ticker: str, country: str, exchange: str) -> Path:
    return DATA_DIR / f"{ticker}.json" if country == "US" else DATA_DIR / f"{exchange}_{ticker}.json"


def load_adj_close(path: Path) -> pd.Series:
    with open(path) as f:
        d = json.load(f)
    s = pd.Series({r["t"]: r["a"] for r in d["data"]})
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def main():
    with open(RESULTS_DIR / "screened_universe.json") as f:
        universe = json.load(f)
    # US-only: mixing US and Canadian tickers in one outer-joined panel means
    # every US-market holiday (Thanksgiving, July 4th, MLK Day, ...) becomes a
    # row where literally every US ticker is NaN (because TSX traded that day),
    # which poisons any window requiring completeness. Confirmed directly: 27
    # such dates in this history, each flipping every US ticker's forward
    # return to NaN for any quarterly snapshot whose window straddles one —
    # exactly the alternating all-or-nothing IC pattern this surfaced on the
    # first run. US names are 94% of the screened universe (3,494 of 3,734
    # with history on disk), so restricting to them loses little coverage
    # while keeping the complete-window discipline meaningful.
    universe = [e for e in universe if e["country"] == "US"]
    print(f"Loading price history for {len(universe)} US-only screened names "
          f"(Canada excluded here — see comment above on why mixing calendars breaks this).")

    series = {}
    for entry in universe:
        path = data_path(entry["ticker"], entry["country"], entry["exchange"])
        if not path.exists():
            continue
        series[entry["ticker"]] = load_adj_close(path)

    prices = pd.concat(series, axis=1)  # outer join by construction
    log_ret = np.log(prices / prices.shift(1))
    # the very first row is NaN for everyone (nothing to take a log-return against) — drop it,
    # but otherwise keep per-ticker NaN gaps (pre-IPO, delistings) rather than dropping rows/cols
    log_ret = log_ret.iloc[1:]
    print(f"{len(series)} tickers loaded, {len(log_ret)} trading days "
          f"({log_ret.index.min().date()} -> {log_ret.index.max().date()})")

    study = run_ic_study(log_ret, horizon=HORIZON, snapshot_every=SNAPSHOT_EVERY, min_lookback=MIN_LOOKBACK)
    print(f"\n--- IC per snapshot ({HORIZON}d forward return, ~{SNAPSHOT_EVERY}d apart) ---")
    for _, row in study.iterrows():
        ic_str = f"{row['ic']:+.3f}" if not np.isnan(row["ic"]) else "  n/a"
        print(f"  {row['date'].date()}  IC={ic_str}  n_names={row['n_names']}")

    summary = summarize_ic(study)
    print(f"\n--- Summary (primary horizon: {HORIZON}d) ---")
    print(f"Snapshots: {summary['n_snapshots']}")
    print(f"Mean IC: {summary['mean_ic']:.4f}  (SE {summary['se_ic']:.4f}, t={summary['t_stat']:.2f})")
    print(f"Grinold-Kahn IR approx (IC * sqrt(breadth), breadth=snapshots): {summary['ir_approx']:.3f}")
    print("Practitioner benchmark: IC ~ 0.05 is 'good', ~ 0.10 is 'very good' (docs/methodology.md §7).")
    print(f"Caveat: {summary['n_snapshots']} quarterly snapshots over one 5-year window are not "
          f"independent bets in the Fundamental Law's strict sense (autocorrelated momentum regime) — "
          f"treat the t-stat/IR here as indicative, not a rigorous significance test.")

    # Fair test needs more than one horizon: academic momentum literature (Jegadeesh-Titman) documents
    # a well-known SHORT-TERM REVERSAL effect that can swamp momentum at 1-month forward horizons,
    # with the classic positive-momentum regime more associated with 3-12 month formation/holding.
    # Testing only 21d and calling it done would risk testing the wrong regime, not a null result.
    print("\n--- IC by forward horizon (fair test — momentum literature flags 1mo short-term reversal) ---")
    horizon_summaries = {}
    for h, label in [(21, "1mo"), (63, "3mo"), (126, "6mo")]:
        s = run_ic_study(log_ret, horizon=h, snapshot_every=SNAPSHOT_EVERY, min_lookback=MIN_LOOKBACK)
        summ = summarize_ic(s)
        horizon_summaries[label] = summ
        print(f"  {label:4} (horizon={h:3}d): mean_ic={summ['mean_ic']:+.4f}  "
              f"se={summ['se_ic']:.4f}  t={summ['t_stat']:+.2f}  n_snapshots={summ['n_snapshots']}")

    # Decile analysis: does average forward return increase monotonically with signal decile?
    print("\n--- Decile analysis (pooled across all snapshots) ---")
    pooled = []
    for as_of_idx in range(MIN_LOOKBACK, len(log_ret) - HORIZON, SNAPSHOT_EVERY):
        signal = composite_momentum_signal(log_ret, as_of_idx)
        fwd = forward_window_return(log_ret, as_of_idx, HORIZON)
        aligned = pd.concat([signal, fwd], axis=1, join="inner").dropna()
        aligned.columns = ["signal", "fwd_return"]
        if len(aligned) >= 10:
            aligned["decile"] = pd.qcut(aligned["signal"], 10, labels=False, duplicates="drop")
            pooled.append(aligned)
    pooled_df = pd.concat(pooled)
    decile_means = pooled_df.groupby("decile")["fwd_return"].mean().sort_index()
    for decile, mean_ret in decile_means.items():
        print(f"  decile {int(decile)+1:2}: avg {HORIZON}d forward return = {mean_ret*100:+.2f}%")
    monotonic = all(decile_means.values[i] <= decile_means.values[i + 1] + 1e-9
                     for i in range(len(decile_means) - 1))
    print(f"Monotonically increasing decile 1->10: {monotonic}")

    RESULTS_DIR.mkdir(exist_ok=True)
    out = {
        "params": {"horizon": HORIZON, "snapshot_every": SNAPSHOT_EVERY, "min_lookback": MIN_LOOKBACK},
        "per_snapshot": study.assign(date=study["date"].astype(str)).to_dict(orient="records"),
        "summary": summary,
        "horizon_summaries": horizon_summaries,
        "decile_means": {int(k): float(v) for k, v in decile_means.items()},
    }
    with open(RESULTS_DIR / "ic_validation.json", "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nSaved {RESULTS_DIR / 'ic_validation.json'}")


if __name__ == "__main__":
    main()
