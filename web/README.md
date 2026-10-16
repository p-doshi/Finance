# Live Portfolio Simulator (web)

A small Next.js app: pick one of the 5 weighting methods from the Python
project's real walk-forward backtest, pick an investment amount, and watch
a live value — the real historical equity curve extended with real-time
quotes applied against that strategy's last-rebalanced weights. Never
submits an order anywhere; same execution boundary as the rest of this
project (`../docs/methodology.md` §0).

## What's real here and what isn't

- **The curve itself**: the actual `research.backtest.walk_forward` results
  (`../scripts/export_web_data.py` exports it) — same data as
  `../docs/methodology.md` §5, not a separate or prettier number.
- **The live point**: real quotes from Yahoo Finance's chart API
  (`pages/api/quotes.js`), applied against the strategy's final (most-
  recently-rebalanced) weights as of the backtest's data cutoff. It is a
  transparent extension of the real curve, not a separately-fabricated
  value — the exact formula is in `pages/index.js`.
- **What it is not**: a real brokerage position. This is a simulator.
  Nothing here ever submits an order, to Wealthsimple, Alpaca, or anywhere
  else.

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

This is a standard Next.js app — Vercel auto-detects it with zero config.
Two ways to actually put it live (both need your own free Vercel account;
that part can't be done on your behalf):

**Option A — Vercel CLI (fastest for a one-off deploy):**
```bash
npm install -g vercel   # one-time
cd web
vercel                  # first run asks you to log in (browser/GitHub), then deploys
vercel --prod           # promote to your production URL
```

**Option B — Connect the GitHub repo (recommended if you want every push
to auto-deploy):**
1. Push this repo to GitHub (if not already).
2. At vercel.com → "Add New Project" → import the repo.
3. Set the project's **Root Directory** to `web/` (this is the one
   non-default setting needed, since the Next.js app isn't at the repo
   root) — Vercel detects everything else (framework, build command)
   automatically.
4. Deploy. Every push to `main` redeploys automatically after that.

## Data freshness

- The historical curve is static (baked in at build time from
  `data/backtest.json`) — re-run `export_web_data.py` and redeploy to
  refresh it with a newer backtest run.
- Live quotes are fetched on each page load and every 30s after
  (`pages/index.js`), cached at Vercel's edge for 30s
  (`Cache-Control: s-maxage=30` in `pages/api/quotes.js`) so many
  simultaneous visitors don't turn into many times as many requests to
  Yahoo Finance.
