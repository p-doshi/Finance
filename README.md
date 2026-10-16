# Portfolio Pipeline

Two related tracks: (1) a risk-aware portfolio construction and monitoring
pipeline for a 12-stock watchlist (NVDA, JNJ, KO, PG, WMT, VZ, XOM, RY, ENB,
UL, NVO, ASML), built to be used against a real Wealthsimple account, and
(2) a full US + Canada market screener — which stocks are performing well
or badly across the ~8,000+ listed names, independent of that watchlist.
Both built to hold up as a serious research project, not just a personal
dashboard.

**Execution boundary, by design:** this pipeline computes target weights and
trade tickets. It never submits an order anywhere. Wealthsimple Trade's terms
of service prohibit API-based order submission (and actively detect it), and
IIROC does not permit electronic order submission through an unofficial API
for Canadian self-directed accounts. So the system's job ends at "here is
exactly what to buy or sell" — a human reads that and enters it manually.

**Live dashboard (beta/trend + risk-parity/Markowitz charts):**
https://claude.ai/artifact/P2j9A38vV7haiYe3AiCS3w

**Full methodology, data sources, assumption checks, and results:**
[docs/methodology.md](docs/methodology.md)

## Architecture

```
Data layer → Research/backtest layer → Risk layer → Decision layer → Monitor/alert layer
(validated,   (risk parity, Markowitz,  (position     (drift vs.       (live dashboard;
 point-in-     walk-forward backtest     limits, vol    target,         you execute the
 time pulls)   — Phase 1)                targeting)     trade ticket)   trade manually)
```

Status: **Phases 0–1 complete** (12-stock track). Phase 1's walk-forward
backtest found that the method which looked best in-sample (max-Sharpe) is
the *worst* performer out-of-sample, and that no method is statistically
distinguishable from the others given ~2 years of out-of-sample data — see
[docs/methodology.md § 5](docs/methodology.md#5-phase-1--walk-forward-out-of-sample-backtest).

**Market-wide screener track: Stages A–B complete.** 8,356 US+Canada
companies scanned, 3,954 survive a liquidity screen, 3,734 (94%) ranked by
momentum with 5 years of real daily history — see
[docs/methodology.md § 6](docs/methodology.md#6-market-wide-screener-us--canada-all-listed-common-stocks)
for the two data-source bugs found and fixed along the way, and the
honest caveat that this ranking is pure momentum, not risk-adjusted.

**Stage C (shrinkage vs. sample covariance) also done** — Ledoit-Wolf
shrinkage keeps a 300-name portfolio's covariance matrix usable even where
sample covariance mathematically breaks (more assets than observations);
see [§ 7](docs/methodology.md#7-beyond-markowitz--benchmarking-against-real-tools-and-practice).

Remaining phases/stages are scoped in [§ 8 Roadmap](docs/methodology.md#8-roadmap).

## Repo layout

```
src/portfolio_pipeline/
  data/fetch.py          — validated, point-in-time price ingestion for the watchlist
  data/universe.py       — bulk US+Canada market snapshot (2 calls, ~8,000+ names)
  research/optimizers.py — equal-weight, inverse-beta, risk parity, min-variance, max-Sharpe
  research/backtest.py   — walk-forward engine + block-bootstrap confidence intervals
tests/                    — pytest: optimizer math, data validation, no-lookahead, universe dedup
scripts/
  fetch_prices.py         — pulls + validates 5y daily history for the watchlist
  inverse_beta.py         — beta/52-week heuristic baseline
  run_portfolio.py        — in-sample risk-parity / Markowitz run (Phase 0)
  run_backtest.py         — walk-forward, out-of-sample backtest (Phase 1)
  generate_tearsheet.py   — quantstats HTML tearsheet per method (results/tearsheet_*.html)
  scan_universe.py        — full US+Canada market scan + liquidity screen (Stage A)
docs/methodology.md       — data sources, assumptions tested, full results, roadmap
results/                  — JSON output of the scripts above
.github/workflows/ci.yml  — runs the test suite on every push
```

## Quickstart

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m pytest -q              # 34 tests, no network needed
.venv/bin/python scripts/fetch_prices.py   # needs network; pulls 5y history for the watchlist
.venv/bin/python scripts/run_portfolio.py  # Phase 0: in-sample
.venv/bin/python scripts/run_backtest.py   # Phase 1: walk-forward, out-of-sample
.venv/bin/python scripts/generate_tearsheet.py  # HTML tearsheets (results/tearsheet_*.html)
.venv/bin/python scripts/scan_universe.py  # Stage A: full US+Canada market scan
```
