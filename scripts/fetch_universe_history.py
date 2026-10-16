#!/usr/bin/env python3
"""Pull 5y daily history for every name in results/screened_universe.json
(US via stockanalysis.com, Canada via Yahoo — see
portfolio_pipeline.data.fetch_ca for why two vendors). Built for ~4,000
tickers, not 12: resumable (skips tickers whose output file already
exists), tolerant of individual failures (a delisted/recent-IPO/bad-data
ticker is logged and skipped, never kills the run), and backs off if it
starts seeing consecutive network-ish failures that look like rate
limiting rather than hammering through them.

Usage:
    .venv/bin/python scripts/fetch_universe_history.py [--limit N] [--force]
    .venv/bin/python scripts/fetch_universe_history.py --retry-reason "single-day" --max-move 3.0
        (retries only tickers whose last failure reason contains the given
        substring, e.g. recovering genuine-but-volatile names that tripped
        the default 50% single-day-move check — see docs/methodology.md on
        BMNR/DFDV, real >500% moves that aren't data errors.)
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from portfolio_pipeline.data.fetch import fetch_and_store, DataQualityError
from portfolio_pipeline.data.fetch_ca import fetch_and_store_ca

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
RESULTS_DIR = ROOT / "results"
REPORT_PATH = RESULTS_DIR / "fetch_universe_history_report.json"
SLEEP_BETWEEN = 0.3
CONSECUTIVE_FAILURE_THRESHOLD = 15
BACKOFF_SECONDS = 30
MAX_BACKOFFS = 5


def output_path(ticker: str, exchange: str) -> Path:
    if exchange == "US":
        return DATA_DIR / f"{ticker}.json"
    return DATA_DIR / f"{exchange}_{ticker}.json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="only process the first N entries (for a quick sanity check)")
    ap.add_argument("--force", action="store_true", help="re-fetch even if the output file already exists")
    ap.add_argument("--max-move", type=float, default=0.5, help="max_single_day_move passed to validate() (fraction, e.g. 3.0 = 300%%)")
    ap.add_argument("--retry-reason", type=str, default=None,
                     help="only retry tickers whose previous failure reason (from the saved report) contains this substring")
    args = ap.parse_args()

    universe = json.load(open(RESULTS_DIR / "screened_universe.json"))

    prior = {"ok": [], "skipped_existing": [], "failed": []}
    if REPORT_PATH.exists():
        prior = json.load(open(REPORT_PATH))

    if args.retry_reason:
        wanted = {(f["ticker"], f["exchange"]) for f in prior["failed"] if args.retry_reason in f["reason"]}
        universe = [e for e in universe if (e["ticker"], e["exchange"]) in wanted]
        args.force = True  # the whole point of a retry is to overwrite the failed attempt
        print(f"Retrying {len(universe)} previously-failed tickers matching reason*='{args.retry_reason}' "
              f"with max_single_day_move={args.max_move}")

    if args.limit:
        universe = universe[: args.limit]

    # Start from the prior report so a retry merges into history instead of discarding it
    results = {
        "ok": list(prior["ok"]),
        "skipped_existing": [],
        "failed": [f for f in prior["failed"] if (f["ticker"], f["exchange"]) not in
                   {(e["ticker"], e["exchange"]) for e in universe}],
    }
    consecutive_failures = 0
    backoffs_used = 0
    start = time.time()

    for i, entry in enumerate(universe):
        ticker, country, exchange = entry["ticker"], entry["country"], entry["exchange"]
        out_path = output_path(ticker, exchange)

        if out_path.exists() and not args.force:
            results["skipped_existing"].append(ticker)
            continue

        try:
            if country == "US":
                rows = fetch_and_store(ticker, DATA_DIR, max_single_day_move=args.max_move)
            else:
                rows = fetch_and_store_ca(ticker, exchange, DATA_DIR, max_single_day_move=args.max_move)
            results["ok"].append({"ticker": ticker, "exchange": exchange, "n_rows": len(rows)})
            consecutive_failures = 0
        except DataQualityError as e:
            results["failed"].append({"ticker": ticker, "exchange": exchange, "reason": str(e)})
            consecutive_failures += 1
        except Exception as e:  # noqa: BLE001 — a single bad ticker must never kill a 3,954-ticker run
            results["failed"].append({"ticker": ticker, "exchange": exchange, "reason": f"unexpected: {e!r}"})
            consecutive_failures += 1

        if consecutive_failures >= CONSECUTIVE_FAILURE_THRESHOLD:
            backoffs_used += 1
            print(f"\n{consecutive_failures} consecutive failures — possible rate limiting. "
                  f"Backing off {BACKOFF_SECONDS}s (backoff {backoffs_used}/{MAX_BACKOFFS}).")
            if backoffs_used > MAX_BACKOFFS:
                print("Too many backoffs — stopping early. Re-run the script later to resume (already-fetched tickers are skipped).")
                break
            time.sleep(BACKOFF_SECONDS)
            consecutive_failures = 0

        if (i + 1) % 50 == 0:
            elapsed = time.time() - start
            rate = (i + 1) / elapsed
            remaining = (len(universe) - i - 1) / rate if rate > 0 else float("nan")
            print(f"[{i+1}/{len(universe)}] ok={len(results['ok'])} skipped={len(results['skipped_existing'])} "
                  f"failed={len(results['failed'])}  elapsed={elapsed/60:.1f}m  est.remaining={remaining/60:.1f}m")

        time.sleep(SLEEP_BETWEEN)

    elapsed = time.time() - start
    print(f"\nDone in {elapsed/60:.1f} minutes.")
    print(f"  ok (cumulative):  {len(results['ok'])}")
    print(f"  skipped (exists): {len(results['skipped_existing'])}")
    print(f"  failed (cumulative): {len(results['failed'])}")

    with open(REPORT_PATH, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Saved {REPORT_PATH}")


if __name__ == "__main__":
    main()
