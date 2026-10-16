# Portfolio Pipeline

[![CI](https://github.com/p-doshi/portfolio-pipeline/actions/workflows/ci.yml/badge.svg)](https://github.com/p-doshi/portfolio-pipeline/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)

A portfolio construction, backtesting, and risk-management engine for
systematic equity strategies — the machinery a quant desk uses to decide
*what* to hold and *how much*, pressure-tested for overfitting before you
trust it, stopping at a trade ticket instead of touching your brokerage
account.

Most retail portfolio tools show you a pie chart. This one builds the pie
chart from real optimization (risk parity, Black-Litterman, Markowitz),
checks whether the backtest behind it would survive a professional
quant's objections (walk-forward validation, Deflated Sharpe Ratio,
Probability of Backtest Overfitting), and manages risk the way a desk
would (position caps, volatility targeting, rebalance bands) — without
ever placing an order on your behalf.

**Who this is for:** systematic/quant traders who want to validate a
strategy before risking capital; day traders who want risk controls
instead of gut-feel position sizing; retail investors who want
institutional portfolio construction without a Bloomberg terminal.

## Features

**Portfolio construction**
- Equal-Weight, Inverse-Beta, Risk Parity, Hierarchical Risk Parity (HRP),
  Minimum-Variance, Max-Sharpe (Markowitz), and Black-Litterman
- Ledoit-Wolf covariance shrinkage for universes where sample covariance
  breaks down (more assets than observations)
- Fama-French 3/5-factor regression for return attribution

**Backtesting & validation**
- Walk-forward, out-of-sample engine — no lookahead, enforced by tests
- Transaction costs, turnover tracking, configurable no-trade bands
- Block-bootstrap confidence intervals instead of single-run point estimates
- Deflated Sharpe Ratio and Probability of Backtest Overfitting (CSCV) —
  the same corrections quant funds use before trusting a backtest
- One-command [quantstats](https://github.com/ranaroussi/quantstats) HTML tearsheets

**Market screening**
- Full US + Canada equity universe scan (8,000+ tickers) in two API calls
- Liquidity/size filtering and momentum ranking
- Information-Coefficient validation — checks whether a ranking signal
  actually predicts forward returns before you trust it

**Risk management**
- Position concentration caps
- Volatility targeting (no-margin, long-only)
- Rebalance bands to cut unnecessary turnover

**Execution — safe by design**
- Generates whole-share trade tickets from real holdings vs. target
  weights, for any brokerage, because it never calls a trading API
- Optional Alpaca paper-trading integration (fake money) for pre-live validation
- Regenerate-on-demand monitoring dashboard with drift alerts

**Live simulator**
- A Next.js app (deployable to Vercel): pick a strategy and a dollar
  amount, watch a real backtest equity curve extend with a live,
  real-time market-data tail. See [web/](web/).

## Quickstart

```bash
git clone https://github.com/p-doshi/portfolio-pipeline
cd portfolio-pipeline
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

python scripts/fetch_prices.py         # pull price history for your watchlist
python scripts/run_backtest.py         # walk-forward backtest, all methods
python scripts/generate_tearsheet.py   # HTML performance report
```

Point it at your own tickers by editing the `TICKERS` list at the top of
each script in `scripts/`.

## Architecture

```
Data layer → Research/backtest layer → Risk layer → Decision layer → Monitor layer
(validated,   (risk parity, Markowitz,  (position     (drift vs.       (live dashboard;
 point-in-     walk-forward backtest,    limits, vol    target,         you execute the
 time pulls)   factor models)            targeting)     trade ticket)   trade manually)
```

## Project layout

```
src/portfolio_pipeline/
  data/            — price ingestion, universe scanning, Fama-French factors
  research/        — optimizers, HRP, shrinkage, Black-Litterman, factor
                      regression, backtesting, overfitting detection
  risk/            — position caps, volatility targeting
  decision/        — holdings vs. target weights -> trade ticket
  execution/       — Alpaca paper-trading client
tests/             — pytest, 96%+ coverage
scripts/           — one script per capability above; see --help or the
                      docstring at the top of each
web/               — live simulator (Next.js, Vercel-ready)
docs/methodology.md — full research methodology, data sources, and validation
```

## Documentation

For data sources, every assumption tested, and the full validation
record — see [docs/methodology.md](docs/methodology.md).

## License

[MIT](LICENSE)
