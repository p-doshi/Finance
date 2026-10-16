# Live Portfolio Simulator (web)

A small Next.js app: pick one of the 5 weighting methods from the Python
project's real walk-forward backtest, pick an investment amount, and watch
a live value — the real historical equity curve extended with real-time
quotes applied against that strategy's last-rebalanced weights. Never
submits an order anywhere; same execution boundary as the rest of this
project (`../docs/methodology.md` §0).

## What's real here and what isn't

- **The curve itself**: the actual `research.backtest.walk_forward` results,
  same code as `../docs/methodology.md` §5, not a separate or prettier
  number. Recomputed on request from live price data by the `app` service
  (`../app.py`) when it's reachable; otherwise served from the static
  snapshot baked in at build time (`data/backtest.json`, from
  `../scripts/export_web_data.py`). `pages/api/portfolio.js` tries the
  former and falls back to the latter — the page shows which one you're
  looking at.
- **The live point**: real quotes from Yahoo Finance's chart API
  (`pages/api/quotes.js`), applied against the strategy's final (most-
  recently-rebalanced) weights as of the backtest's data cutoff. It is a
  transparent extension of the real curve, not a separately-fabricated
  value — the exact formula is in `pages/index.js`.
- **What it is not**: a real brokerage position. This is a simulator.
  Nothing here ever submits an order, to Wealthsimple, Alpaca, or anywhere
  else.

## Architecture

Two Vercel services, defined in `../vercel.json`:

- **`web`** (this directory) — the public Next.js site. Everything (the
  page, `/api/quotes`, `/api/portfolio`) is served from here.
- **`app`** (`../app.py`, root of the repo) — an internal-only FastAPI
  service. Not publicly routable; `web` reaches it at request time through
  a service *binding*, which injects its URL into `web`'s server-side
  functions as `process.env.APP_URL` (never into the browser bundle).
  `pages/api/portfolio.js` is the only thing that reads `APP_URL` — it
  proxies to `app`'s `/api/portfolio?method=...` and falls back to the
  static snapshot if that call fails or `APP_URL` isn't set (e.g. local
  `npm run dev` without the Python service running alongside it).

`app` fetches price history live (stockanalysis.com) rather than reading
`../data/*.json` — that directory is gitignored, so none of it exists in
the deployed function in the first place.

Local development with the live path:
```bash
# terminal 1, from the repo root
.venv/bin/python -m uvicorn app:app --reload --port 8099

# terminal 2
cd web
APP_URL=http://127.0.0.1:8099 npm run dev
```
Without `APP_URL` set, `npm run dev` still works — it just serves the
static snapshot for every method.

## Local development

```bash
cd web
npm install
npm run dev
# http://localhost:3000
```

Re-export fresh backtest data (after re-running the Python backtest) with:

```bash
cd ..
.venv/bin/python scripts/export_web_data.py
```

## Deploying to Vercel

This is now a two-service project (see Architecture above), configured by
`../vercel.json` at the **repo root** — unlike a plain Next.js deploy, the
project's Root Directory should be the repo root, not `web/`, so Vercel
sees `vercel.json` and sets up both services. Needs your own free Vercel
account; that part can't be done on your behalf.

1. Push this repo to GitHub (if not already).
2. At vercel.com → "Add New Project" → import the repo. Vercel reads
   `vercel.json`'s `services` block and should detect both `web`
   (Next.js) and `app` (Python) automatically — leave Root Directory as
   `.` (the repo root).
3. Deploy. Only `web` is publicly routable (the `rewrites` entry in
   `vercel.json` sends every path to it); `app` is reachable only from
   `web`'s server-side code, via the injected `APP_URL` binding.
4. Every push to `main` redeploys both services automatically after that.

## Data freshness

- The historical curve is static (baked in at build time from
  `data/backtest.json`) — re-run `export_web_data.py` and redeploy to
  refresh it with a newer backtest run.
- Live quotes are fetched on each page load and every 30s after
  (`pages/index.js`), cached at Vercel's edge for 30s
  (`Cache-Control: s-maxage=30` in `pages/api/quotes.js`) so many
  simultaneous visitors don't turn into many times as many requests to
  Yahoo Finance.
