// Proxies to the "app" Python service's live backtest endpoint.
//
// APP_URL is injected at runtime by the vercel.json "bindings" entry on
// this service -- only server-side functions see it (not middleware, not
// the browser), which is exactly why this lives behind a Next.js API
// route instead of having the browser call the Python service directly:
// the browser never needs to know an internal URL exists, and nothing
// about the service topology is exposed client-side.
//
// Falls back to the static, build-time backtest.json snapshot
// (../../data/backtest.json, from scripts/export_web_data.py) if APP_URL
// isn't set (local `npm run dev` without the Python service running) or
// the live call fails for any reason -- the simulator should degrade to
// last-known-good data, not break.

import staticBacktest from "../../data/backtest.json";

export default async function handler(req, res) {
  const method = typeof req.query.method === "string" ? req.query.method : "risk_parity";
  const tickers = typeof req.query.tickers === "string" ? req.query.tickers : "";
  const appUrl = process.env.APP_URL;

  if (appUrl) {
    try {
      const qs = tickers ? `&tickers=${encodeURIComponent(tickers)}` : "";
      const upstream = await fetch(`${appUrl}/api/portfolio?method=${encodeURIComponent(method)}${qs}`, {
        signal: AbortSignal.timeout(20_000),
      });
      const live = await upstream.json();
      if (!upstream.ok) {
        // for a custom ticker list there's no sensible static fallback (it
        // has data for the fixed watchlist only), so surface the real
        // error (e.g. "need at least 2 tickers") instead of silently
        // falling back to the wrong tickers' data below
        if (tickers) {
          res.status(upstream.status).json(live);
          return;
        }
        throw new Error(`app service returned ${upstream.status}`);
      }
      res.setHeader("Cache-Control", "s-maxage=3600, stale-while-revalidate=7200");
      res.status(200).json({
        tickers: live.tickers,
        as_of_date: live.as_of_date,
        last_known_prices: live.last_known_prices,
        rf: live.rf,
        method,
        window_days: live.window_days,
        data: {
          equity_curve: live.equity_curve,
          final_weights: live.final_weights,
          last_curve_value: live.last_curve_value,
        },
        source: "live",
      });
      return;
    } catch (e) {
      // fall through to the static snapshot below -- but only for the
      // default watchlist; the static snapshot has no data for a custom
      // ticker list, so serving it would silently show the wrong tickers
      if (!tickers) console.error(`live portfolio fetch failed, serving static snapshot: ${e}`);
      else {
        console.error(`live portfolio fetch failed for custom tickers: ${e}`);
        res.status(502).json({ error: `app service unreachable, can't backtest custom tickers right now: ${e}` });
        return;
      }
    }
  } else if (tickers) {
    res.status(503).json({ error: "APP_URL not configured (local dev without the Python service running?)" });
    return;
  }

  if (!staticBacktest.methods[method]) {
    res.status(400).json({ error: `unknown method, choose one of ${Object.keys(staticBacktest.methods)}` });
    return;
  }
  res.setHeader("Cache-Control", "s-maxage=3600, stale-while-revalidate=7200");
  res.status(200).json({
    tickers: staticBacktest.tickers,
    as_of_date: staticBacktest.as_of_date,
    last_known_prices: staticBacktest.last_known_prices,
    rf: staticBacktest.rf,
    method,
    data: staticBacktest.methods[method],
    source: "static",
  });
}
