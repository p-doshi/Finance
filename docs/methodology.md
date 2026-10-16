# Methodology

Full record of data sources, assumptions, statistical checks, and results for
the 12-candidate watchlist (NVDA, JNJ, KO, PG, WMT, VZ, XOM, RY, ENB, UL, NVO,
ASML). Written so every number here can be checked against a real source or
regenerated with `scripts/`, not taken on faith.

## 0. Why this exists, and why it isn't a trading bot

An earlier pass pulled beta and 52-week price change from macrotrends using
guessed URL slugs. At least two of those slugs pointed at the wrong company —
caught by cross-checking against confirmed current prices. This project
redoes that work against a self-verifying source and extends it into a real
risk-parity / Markowitz pipeline with real history.

**Execution boundary:** this pipeline computes target weights and trade
tickets. It never submits an order. Wealthsimple Trade's terms of service
explicitly prohibit API-based order submission and detect it; IIROC does not
permit electronic order submission through an unofficial API for Canadian
self-directed accounts either. So every decision this system produces is
meant to be read by a human and entered into the brokerage manually — see
`src/portfolio_pipeline/__init__.py` for where this is enforced in code (by
omission: there is no order-submission code path anywhere in this repo).

## 1. Data sources

- **Beta / 52-week change:** `stockanalysis.com/stocks/<TICKER>/statistics/`,
  one fetch per ticker. Company name on each page checked against the
  expected company for that ticker before using any number.
  - XOM's page names the company "ExxonMobil Holdings Corporation," not
    "Exxon Mobil Corporation." Cross-checked against Yahoo Finance, Google
    Finance, and GuruFocus — all four agree, so treated as a 2026
    holding-company restructuring rather than a wrong ticker.
  - Pulled Oct 15, 2026, ~1:27–1:30 PM EDT.
- **Daily price history:** `stockanalysis.com`'s own chart API
  (`/api/symbol/s/<TICKER>/history`), same vendor as above — no cross-source
  identity-mismatch risk. `scripts/fetch_prices.py` pulls 5 years of daily
  split/dividend-adjusted closes per ticker, validates each pull
  (`portfolio_pipeline.data.fetch.validate`: row count, duplicate/non-monotonic
  dates, non-positive prices, implausible single-day moves), and stores it
  point-in-time (`data/raw/<TICKER>/<pulled_at_utc>.json`, never overwritten)
  so a later backtest can't accidentally see a revision that didn't exist on
  the date being simulated.
  - This is a convenience source, not a point-in-time, survivorship-bias-free
    vendor — delisted/acquired names simply disappear rather than being
    preserved. Acceptable for a fixed watchlist of currently-listed large
    caps (none of these 12 was at risk of delisting over the lookback
    window); **not** acceptable for backtesting a broad historical universe
    screen without a proper vendor (e.g. CRSP).
- **Risk-free rate:** 4.26%, the 3-month Treasury constant-maturity yield
  from the Federal Reserve's H.15 release dated Oct 14, 2026 (reporting
  Oct 13, 2026 data) — looked up directly, not assumed.

## 2. Verified beta / 52-week figures

| Ticker | Beta, 5y | 52-wk change % | Price (USD) |
|---|---|---|---|
| NVDA | 2.22 | +20.79 | 217.39 |
| JNJ  | 0.21 | +34.06 | 255.67 |
| KO   | 0.32 | +37.00 | 92.43 |
| PG   | 0.38 | +5.83  | 158.01 |
| WMT  | 0.58 | +10.61 | 118.60 |
| VZ   | 0.25 | +11.07 | 44.84 |
| XOM  | 0.21 | +55.56 | 174.63 |
| RY   | 0.91 | +34.76 | 196.19 |
| ENB  | 0.80 | -1.60  | 46.82 |
| UL   | 0.46 | -5.37  | 64.94 |
| NVO  | 0.38 | -30.17 | 39.53 |
| ASML | 1.30 | +66.65 | 1638.39 |

Beta (long-run co-movement with the market) and 52-week return (current
trend) show no visible relationship to each other. Several trend numbers
bundle in one-off events that don't extrapolate cleanly: JNJ's talc-settlement
overhang clearing, XOM's strong oil year, NVO's GLP-1 competition.

## 3. Portfolio construction methods

All long-only, weights sum to 1, deterministic (every solver starts from the
equal-weight point via `scipy.optimize.minimize(method="SLSQP")` — no
randomness). Implementations: `src/portfolio_pipeline/research/optimizers.py`,
unit-tested in `tests/test_optimizers.py`.

- **Equal weight** — no inputs beyond the universe size.
- **Inverse beta** — `w_i ∝ 1/beta_i`. A heuristic, not an optimization.
- **Risk parity** — equalizes each asset's contribution to portfolio
  variance. Needs only the covariance matrix.
- **Minimum variance** — minimizes portfolio variance. Needs only the
  covariance matrix.
- **Max Sharpe (tangency)** — maximizes `(return - rf) / vol`. Needs the
  covariance matrix **and** an expected-return estimate (historical mean
  daily log return, annualized) — the noisiest input in the pipeline.

### Assumption checks (run before trusting any of the above)

- **Normality:** all 12 return series reject normality at p < 0.0001
  (Jarque-Bera). Worst fat tails: UL (excess kurtosis +19.7), NVO (+15.9),
  WMT (+10.8). Mean-variance's implicit "variance captures risk" assumption
  understates tail risk across the board.
- **Covariance conditioning:** 3-year correlation matrix condition number
  8.2, min eigenvalue 0.39 — well-conditioned at 756 observations for 12
  assets; no shrinkage estimator needed.
- **Temporal structure respected:** all windows are trailing (1y/3y/5y ending
  on the latest pull date), never shuffled or resampled out of order.

### Weights by method (3-year covariance/return window, base case)

| Ticker | Equal wt % | Inverse beta % | Risk parity % | Min variance % | Max Sharpe % |
|---|---|---|---|---|---|
| NVDA | 8.3 | 1.5 | 6.2 | 6.0 | 12.1 |
| JNJ | 8.3 | 16.2 | 10.6 | 15.0 | 12.2 |
| KO | 8.3 | 10.6 | 10.2 | 16.8 | 22.6 |
| PG | 8.3 | 9.0 | 9.2 | 9.9 | 0.0 |
| WMT | 8.3 | 5.9 | 7.9 | 4.5 | 10.9 |
| VZ | 8.3 | 13.6 | 8.8 | 5.8 | 3.1 |
| XOM | 8.3 | 16.2 | 10.0 | 10.5 | 7.0 |
| RY | 8.3 | 3.7 | 9.0 | 14.1 | 32.2 |
| ENB | 8.3 | 4.3 | 9.5 | 10.7 | 0.0 |
| UL | 8.3 | 7.4 | 8.2 | 2.9 | 0.0 |
| NVO | 8.3 | 9.0 | 4.8 | 0.7 | 0.0 |
| ASML | 8.3 | 2.6 | 5.7 | 3.3 | 0.0 |

| Method | Ann. return | Ann. vol | Sharpe |
|---|---|---|---|
| Equal weight | 18.95% | 11.49% | 1.28 |
| Inverse beta | 14.66% | 11.28% | 0.92 |
| Risk parity | 19.37% | 10.48% | 1.44 |
| Min variance | 21.72% | 10.10% | 1.73 |
| Max Sharpe | 28.19% | 11.20% | 2.14 |

**Max Sharpe's Sharpe ratio is not a forecast.** It is definitionally the
best Sharpe achievable on this exact historical sample, because that is what
the solver was pointed at maximizing. None of these numbers are a backtest of
forward performance (that's Phase 1 — see Roadmap).

### Instability finding

Re-solving max-Sharpe on three trailing windows (1y / 3y / 5y), same
optimizer, same equal-weight start:

| Ticker | 1-year | 3-year | 5-year |
|---|---|---|---|
| RY | 30.1% | 32.2% | 3.2% |
| WMT | 0.0% | 10.9% | 21.5% |
| XOM | 22.5% | 7.0% | 25.7% |
| ASML | 8.9% | 0.0% | 0.0% |

Weights swing by up to ~30 percentage points depending on which window
estimated the expected-return input. **Risk parity, solved the same way
across the same three windows, moves at most ~4 percentage points** per
stock, because it depends only on the covariance matrix, which is far more
stable than the historical-mean-return estimate.

### Recommended distribution (risk parity, whole percent)

| Ticker | % |
|---|---|
| JNJ | 11 |
| KO | 10 |
| XOM | 10 |
| ENB | 9 |
| PG | 9 |
| RY | 9 |
| VZ | 9 |
| UL | 8 |
| WMT | 8 |
| ASML | 6 |
| NVDA | 6 |
| NVO | 5 |

Largest-remainder rounding from the exact risk-parity weights so it still
sums to 100.

## 4. What this does and doesn't establish

- Five-year beta from a single vendor is noisy and backward-looking;
  individual-stock betas are known to drift toward 1 over time (Blume, 1975)
  rather than staying fixed.
- All 12 return series reject normality — tail risk is understated by any
  method that only looks at mean and variance, risk parity and Markowitz
  included.
- Max-Sharpe's in-sample Sharpe ratio is circular by construction, not
  evidence of future outperformance.
- Everything above is in-sample optimization on one realized historical
  window, not a backtest of forward returns — that gap is Phase 1 of the
  roadmap (walk-forward, out-of-sample, bootstrap confidence intervals
  across folds).
- Nothing here says anything about valuation (PG at ~24x earnings vs. NVO at
  ~9x are treated identically by methods that only see risk and historical
  return).

## 5. Phase 1 — walk-forward, out-of-sample backtest

Everything in §3 is in-sample: one covariance/return estimate, evaluated on
the same data it was estimated from. Phase 1 (`portfolio_pipeline.research.backtest`,
`scripts/run_backtest.py`) fixes that: at every rebalance date, the
estimation window (`log_returns.iloc[i-window:i]`) ends *strictly before*
that date — verified directly by `tests/test_backtest.py::test_no_lookahead_weights_unaffected_by_future_data`,
which corrupts all data after a cutoff and checks that every rebalance whose
window ends before the cutoff produces bit-identical weights either way.
Each holding period charges a transaction cost on turnover; confidence
intervals come from a block bootstrap (not a single point estimate) over
the realized out-of-sample holding-period returns.

**Base case:** 756-day (3y) trailing window, ~monthly rebalancing (21
trading days), 10bps one-way cost, risk-free rate 4.26%, bootstrap seed
20261015 (fixed — every number below is exactly reproducible).

### A real, honest small-sample problem

A 756-day estimation window eats three of the five years of history, leaving
only **24 out-of-sample holding periods (~2 years)** to evaluate on. That is
not enough data to draw a confident conclusion, and the results below should
be read that way — wide bands, not a verdict.

| Method | Ann. return (net) | Ann. vol | Sharpe | Max drawdown | Avg turnover |
|---|---|---|---|---|---|
| Equal weight | 15.45% | 10.40% | 1.08 | -4.40% | 4.2% |
| Risk parity | 14.83% | 10.00% | 1.06 | -4.33% | 5.6% |
| Min variance | 15.82% | 11.44% | 1.01 | -4.62% | 11.4% |
| Max Sharpe | 11.70% | 10.19% | 0.73 | -7.18% | 28.9% |

**The method that looked best in-sample (Phase 0: max-Sharpe, Sharpe 2.14) is
the worst performer out-of-sample** — lowest return, worst drawdown, and by
far the highest turnover (28.9% average, vs. 4–11% for the others), which
also means it eats the most transaction-cost drag. This is overfitting shown
directly: the expected-return estimate max-Sharpe leans on is noisy enough
that optimizing hard against it in-sample doesn't transfer forward.

**None of the four methods are statistically distinguishable from each
other** at a 90% block-bootstrap confidence level — every pairwise Sharpe CI
overlaps the others. With 24 periods, that's the honest conclusion; claiming
"risk parity beats max-Sharpe" from this sample alone would be overstating
what 2 years of monthly data can support.

| Method | Ann. return 90% CI | Sharpe 90% CI |
|---|---|---|
| Equal weight | 7.8% – 31.7% | 0.84 – 3.41 |
| Risk parity | 7.5% – 30.0% | 0.84 – 3.48 |
| Min variance | 8.0% – 32.4% | 0.73 – 3.28 |
| Max Sharpe | 1.6% – 29.3% | 0.16 – 3.68 |

### Transaction costs matter most for the method that needed them least

| Cost (bps, one-way) | Risk parity ann. return | Max Sharpe ann. return |
|---|---|---|
| 0 | 14.90% | 12.09% |
| 10 | 14.83% | 11.70% |
| 25 | 14.71% | 11.12% |
| 50 | 14.52% | 10.16% |

Risk parity's low turnover (5.6% average) makes it nearly cost-insensitive;
max-Sharpe's high turnover (28.9%) means realistic trading costs erode almost
2 full points of annual return between 0 and 50bps.

### Window-length sensitivity: the ranking itself isn't stable

Shortening the estimation window to 504 days (2y) — noisier covariance
estimates, but 36 out-of-sample periods instead of 24 — **flips the
result**: over that (more AI-rally-weighted) sub-period, max-Sharpe's
26.96% return is the highest of the four, though its Sharpe (1.48) still
trails risk parity's (1.92) because of higher volatility.

| Window | Equal wt | Risk parity | Min variance | Max Sharpe |
|---|---|---|---|---|
| 2y (36 periods) | 24.63% / Sharpe 1.90 | 22.66% / Sharpe 1.92 | 21.53% / Sharpe 1.75 | 26.96% / Sharpe 1.48 |
| 3y (24 periods) | 15.45% / Sharpe 1.08 | 14.83% / Sharpe 1.06 | 15.82% / Sharpe 1.01 | 11.70% / Sharpe 0.73 |

**Which method "wins" depends on which historical window you test over as
much as it depends on the method itself.** That's a real finding, not a
failure of the backtest — surfacing it is the point of doing this properly
rather than reporting whichever window happens to make one method look best.

### A solver robustness issue the backtest surfaced for real

Running max-Sharpe across ~48 real rolling windows hit a genuine SLSQP
convergence failure on one window (not a hypothetical edge case) —
`"Positive directional derivative for linesearch"` from the equal-weight
starting point. Fixed with a deterministic (fixed-seed, not truly random)
restart sequence in `optimizers._robust_minimize`, tested in
`tests/test_optimizers.py` via a mocked solver that fails on the first
attempt and succeeds on a fallback, confirming the retry path and the
all-attempts-fail path both behave correctly.

## 6. Market-wide screener (US + Canada, all listed common stocks)

A second, related track: not just the 12-stock watchlist, but a scan of the
entire US + Canadian market — "which stocks are performing well, which
aren't, which might be worth a closer look" — built as a funnel rather than
one flat pipeline, because a sample covariance matrix stops being
meaningful once the number of assets isn't small relative to the number of
trading days available, and pulling 5 years of daily history one ticker at
a time for thousands of names isn't practical (time, and real rate-limit
risk — see the earlier Yahoo/stooq blocks).

```
Stage A: universe scan  →  Stage B: screen + rank  →  Stage C: deep dive
(bulk snapshot, 2 calls)   (liquidity/size filter,     (full 5y history,
                            momentum/signal rank)        existing optimizers —
                                                          only for a narrowed
                                                          candidate list)
```

### Stage A (done): `portfolio_pipeline.data.universe`, `scripts/scan_universe.py`

Source: stockanalysis.com's bulk screener snapshot endpoint
(`/_api/endpoints/screener/initial`) — found by inspecting the public
screener page's own preloaded request, not a documented API. One call
returns the *entire* US common-stock universe; a second (`countryCode=CA`)
returns every Canadian-exchange listing. Two network calls total, not
thousands — this is a wide/shallow snapshot (ticker, name, market cap,
price, today's % change, sector, volume, P/E), not deep history.

**Two real data-quality bugs found and fixed, not just assumed absent:**

1. `neo/`-prefixed rows are Canadian Depositary Receipts (CDRs) — synthetic
   wrappers on US mega-caps (`neo/ZNVD` = a CDR on NVIDIA), not distinct
   companies. Dropped by prefix.
2. Less obviously: `tsx/`-prefixed rows *also* include CDRs, listed under
   the plain US ticker with no naming convention to flag them —
   `tsx/NVDA` reported a $7.4T market cap against the real listing's
   $5.2T, a 40%+ divergence that is itself the signal something was wrong
   (a genuine dual-listing's market cap shouldn't diverge that much from
   its primary listing). Fixed generically rather than with a ticker
   blocklist: any Canadian-side row whose company name exactly matches a
   US-side row is dropped — this catches the `tsx/` CDRs and, as a side
   effect, correctly collapses genuine dual-listings (Royal Bank, TD,
   Enbridge, Shopify) to a single entry instead of double-counting them.
   Covered by `tests/test_universe.py::test_fetch_full_universe_drops_tsx_cdr_with_same_name_as_us_listing`
   and `...collapses_genuine_dual_listing_to_us_entry`.

**Results, run live Oct 15, 2026:**

- Full universe after both fixes: **8,356 names** (US 5,612; TSX 511; TSXV
  1,548; CSE 685).
- After a liquidity/size screen (market cap ≥ $100M, today's dollar volume
  ≥ $500k): **3,954 names** (47.3% of the full universe) — the other ~53%
  is shells, halted names, and illiquid micro-caps that aren't realistically
  tradeable regardless of what any ranking says about them.
- Top sectors in the screened universe: Biotechnology (328), Banks -
  Regional (275), Software - Application (151) — a reminder that "the
  market" is heavily weighted toward a few sectors, not evenly spread.
- Full screened list (3,954 records) saved to `results/screened_universe.json`
  — this is the actual input Stage B works from, not just the summary.

**What this snapshot doesn't give, by design:** no beta, no 52-week return,
no multi-day momentum — the bulk endpoint only ships today's price and
change. Getting those for the full screened universe is Stage B's job.

### Stage B: deep history + ranking — a second real data-source problem

Fetching 5y daily history for all 3,954 screened survivors surfaced another
gap: stockanalysis.com's history API — solid for every US name — has no
discoverable equivalent for Canadian-only listings (TSX/TSXV/CSE). Unlike
the US history API and the bulk screener, both found as plain `preload`
links in the page's own HTML, the Canadian history page loads its data
client-side with no such link to follow.

**Fix:** `portfolio_pipeline.data.fetch_ca` uses Yahoo Finance's chart API
instead for Canadian names (`ATD.TO`, `AFM.V`, `GTII.CN` — confirmed
working live in this session for all three exchange suffixes, which
corrects an earlier, untested assumption in this project that Yahoo was
blocked outright). A second vendor means results aren't assumed
interchangeable with the US data — same validation checks, documented as a
separate source.

**A second, subtler collision risk, found before it caused damage:** 39
tickers in the screened universe share a symbol with an unrelated company
on a different exchange — e.g. US `CMG` is Chipotle, TSX `CMG` is Computer
Modelling Group; US `L` is Loews Corporation, TSX `L` is Loblaw. Storing by
bare ticker would silently let one overwrite the other depending on fetch
order. Fixed with exchange-qualified filenames for every non-US name
(`TSX_ATD.json`, not `ATD.json`), tested directly in
`tests/test_fetch_ca.py::test_fetch_and_store_ca_does_not_collide_with_us_ticker_of_same_symbol`.

**Fetching at this scale needed different engineering than the 12-stock
case:** `scripts/fetch_universe_history.py` is resumable (skips tickers
whose output file already exists, so an interrupted run picks up where it
left off), never lets one bad ticker (recent IPO with <200 days of
history, a delisted name, a transient network error) kill a multi-thousand-
ticker run, and backs off if it sees too many consecutive failures in a
row rather than hammering a source that may be rate-limiting it.

**Ranking (`portfolio_pipeline.research.screen`, `scripts/rank_universe.py`):**
for every name with history on disk, computes 3/6/12-month momentum,
trailing annualized volatility, max 1-year drawdown, and beta — the last
one computed directly via OLS against SPY's own daily returns rather than
taken from a vendor, which sidesteps the "undisclosed methodology" problem
noted for vendor beta in §3. The composite rank is an equal-weighted
average of each momentum horizon's **percentile rank**, not raw return or a
z-score average — chosen because every return series examined in this
project (Phase 1, §5) rejected normality, so there's no reason to expect
the other ~4,000 names to be better-behaved, and a rank-based composite
isn't distorted by fat-tailed outliers the way an average of raw returns
would be. A name missing a horizon (recent IPO) is ranked on whichever
horizons it has, with `n_horizons_used` recording how many — a composite
built on one horizon is weaker evidence than one built on three, and is
reported as such rather than hidden.

### Results, run live Oct 15, 2026

**Coverage:** 3,734 of 3,954 screened names (94.4%) have usable 5-year (or
shorter, for recent IPOs) daily history. The 220 excluded, by reason:

| Reason | Count | Disposition |
|---|---|---|
| Too few trading days (recent IPO) | 149 | Correctly excluded — not enough history for even a 12-month lookback |
| Symbol unresolvable at either vendor | 37 | Retried once, failed identically both times — likely delisted/renamed since the Stage A snapshot |
| Single-day move exceeds even a 300% threshold | 32 | Left excluded, documented — see below |

**A real validation bug found and fixed mid-run:** the single-day-move
check (§3) was calibrated against the 12-name mega-cap watchlist at a 50%
threshold. Run against this far more volatile 3,954-name universe, it
flagged 473 names — most turned out to be genuine. Spot-checking the
largest, **BMNR (+695%, 2025-06-30) and DFDV (+843%, 2025-04-07) are real,
documented single-day moves from crypto-treasury-strategy pivot
announcements**, not data errors. Fixed properly (a `max_single_day_move`
parameter on `fetch_and_store`/`fetch_and_store_ca`, not a one-off patch),
re-ran at a 300% threshold, and recovered 441 of the 473 (93%). The
remaining 32 — mostly micro-cap biotechs with >300%, in a few cases
>1,000%, single-day moves (plausible for a binary clinical-trial-readout
stock, but not individually confirmed) — are left excluded rather than
guessed at further; chasing the last 0.8% of the universe by repeatedly
loosening a safety check stops being validation and starts being
wishful thinking.

**Composite ranking is pure momentum, not risk-adjusted — worth being
direct about what this is and isn't.** The composite score is a percentile
rank of trailing return only; nothing in it divides by volatility. That
shows up clearly in the data: average annualized volatility is 66.8% for
the top 100 names, 92.8% for the *bottom* 100, and 41.7% for the names in
the middle. **Both tails of a pure momentum ranking are more volatile than
the middle** — extreme winners and extreme losers are both disproportionately
the same kind of speculative, high-beta names; steady, unremarkable
performance clusters in the middle. A ranking built to surface "good risk-
adjusted bets" would need to divide momentum by volatility explicitly
(a Sharpe-style score), which this one does not do, by design, in order to
keep "performing well vs. badly" legible as its own question. Top-100
sectors: Biotechnology (15), Oil & Gas Midstream (8), Software -
Infrastructure (7), Oil & Gas Refining & Marketing (7) — energy's strong
showing in Oct 2026 tracks Phase 0/1's XOM finding; biotech's volatility
profile is the same pattern described above.

## 7. Beyond Markowitz — benchmarking against real tools and practice

Researched real open-source quant tooling (PyPortfolioOpt, Riskfolio-Lib,
skfolio, quantstats, Microsoft's Qlib) and the published methodology behind
what quant firms actually target and measure (Sharpe/Sortino/Calmar/
Information Ratio, CVaR, the Grinold-Kahn Fundamental Law of IR ≈ IC ×
√Breadth, López de Prado's deflated Sharpe ratio and probability-of-
backtest-overfitting corrections). Full source list available on request;
summary finding: HRP, Black-Litterman, and Ledoit-Wolf shrinkage are
standard options in every real portfolio library checked, not exotic
additions — treating them as a priority list to close that gap.

### Ledoit-Wolf covariance shrinkage (`research/covariance.py`)

Sample covariance — what every method here has used since Phase 0 — gets
noisier as the number of assets approaches the number of return
observations, and is mathematically guaranteed singular once assets
*exceed* observations. This project's 12-stock watchlist never hit that
problem (3y window: condition number 8.2, Phase 0). Stage B's momentum-
ranked universe does, directly, once a real portfolio is built from the
top-K names (`scripts/build_large_portfolio.py`), 1-year (252-day) window:

| K | n_assets | n_obs | shrinkage | cond# (sample) | cond# (shrunk) | vol (sample) | vol (shrunk) |
|---|---|---|---|---|---|---|---|
| 20 | 20 | 252 | 37.5% | 11.0 | 4.0 | 24.4% | 24.9% |
| 50 | 50 | 252 | 26.2% | 70.2 | 9.5 | 17.6% | 16.8% |
| 100 | 100 | 233 | 26.5% | 227.2 | 23.9 | 15.9% | 14.5% |
| 200 | 200 | 233 | 26.4% | 11,477.5 | 59.8 | 14.2% | 12.5% |
| 300 | 300 | 199 | 26.0% | **−1.26×10¹⁶** | 137.9 | 12.8% | 11.5% |

At K=300 there are more assets (300) than trading-day observations (199)
after the common-date join — the sample covariance matrix is mathematically
rank-deficient (singular), and its near-zero eigenvalues go slightly
negative under floating point, which is exactly what that nonsensical
condition number is reporting: not a bug, a direct symptom of trying to
invert something that isn't invertible. Shrunk covariance stays positive-
definite and usable throughout, confirmed in
`tests/test_covariance.py::test_sample_covariance_breaks_when_assets_exceed_observations`
with a synthetic reproduction that doesn't depend on live market data.
Implemented via `sklearn.covariance.LedoitWolf` (the same implementation
Riskfolio-Lib and skfolio use), not re-derived by hand.

### Hierarchical Risk Parity (`research/hrp.py`)

López de Prado, "Building Diversified Portfolios that Outperform
Out-of-Sample," *J. Portfolio Management* 42(4), 2016. Three steps
(correlation-distance clustering → quasi-diagonalization → recursive
bisection), implemented as separate, auditable functions rather than one
opaque call. The actual claimed benefit — HRP never inverts the covariance
matrix, so it doesn't need it to be positive-definite — checked directly
on real data at K=300 (`scripts/build_large_portfolio.py`, same run as the
shrinkage table above, where sample covariance is singular): HRP still
produces a valid long-only portfolio, volatility 11.4% (vs. shrunk risk
parity's 11.5% — close agreement) and effective N=120.6 of 300 names
(healthy diversification, not a degenerate corner solution). A synthetic
regression test
(`tests/test_hrp.py::test_hrp_handles_singular_covariance_where_matrix_inversion_would_fail`)
locks this in without depending on live data.

**Honest negative finding at small N:** added to the 12-stock walk-forward
backtest (§5) too, where the result is the opposite of a sales pitch — HRP
underperforms plain risk parity out-of-sample (Sharpe 0.98 vs. 1.06) with
*higher* turnover (13.6% vs. 5.6%), not lower. This tracks the theory
rather than contradicting it: HRP's advantage is specifically about
robustness under a noisy or ill-conditioned covariance matrix, and 12
assets with 756 observations was already well-conditioned in Phase 0
(condition number 8.2) — there's no instability problem here for HRP to
fix, and its extra clustering machinery just adds turnover without buying
anything. The benefit shows up exactly where the theory says it should
(large N, poorly-conditioned covariance), not as a universal upgrade.

## 8. Roadmap

0. **Foundations** (done) — package, tests, CI, validated + point-in-time
   data ingestion.
1. **Walk-forward backtest** (done) — out-of-sample weights, transaction
   costs, block-bootstrap CIs, window-sensitivity check. See above.
2. **Transaction-cost / turnover modeling** (done as part of Phase 1 — cost
   sensitivity table above) — could still extend to a market-impact model
   for larger position sizes, not needed at retail scale.
3. **Risk management layer** — position caps, volatility targeting,
   rebalance bands (don't trade on noise-level drift).
4. **Decision layer** — compares manually-entered current holdings against
   target weights, outputs a trade ticket in whole shares. (No safe
   programmatic read path into Wealthsimple either, by the same ToS/IIROC
   constraint — holdings are entered by hand.)
5. **Real-time monitor** — live prices/risk on a dashboard; alert fires when
   drift crosses threshold. Rebalancing decisions themselves stay periodic
   (weekly/monthly), not continuous.
6. **Paper-trade validation + write-up** — run in parallel against a free
   Alpaca/IBKR paper account before trusting it for manual real trades.

## 9. Reproducing this

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m pytest -q              # 34 tests, pure math + synthetic data, no network
.venv/bin/python scripts/fetch_prices.py   # pulls + validates 5y history, needs network
.venv/bin/python scripts/inverse_beta.py
.venv/bin/python scripts/run_portfolio.py  # Phase 0: in-sample weights
.venv/bin/python scripts/run_backtest.py   # Phase 1: walk-forward, out-of-sample
.venv/bin/python scripts/scan_universe.py  # Stage A: full US+Canada market scan
.venv/bin/python scripts/fetch_universe_history.py  # Stage B data: ~40min, resumable
.venv/bin/python scripts/rank_universe.py  # Stage B: momentum ranking
.venv/bin/python scripts/build_large_portfolio.py  # Stage C: shrinkage-vs-sample comparison
```
