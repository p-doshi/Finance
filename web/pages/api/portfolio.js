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
  const appUrl = process.env.APP_URL;

  if (appUrl) {
    try {
      const upstream = await fetch(`${appUrl}/api/portfolio?method=${encodeURIComponent(method)}`, {
        signal: AbortSignal.timeout(20_000),
      });
      if (!upstream.ok) throw new Error(`app service returned ${upstream.status}`);
      const live = await upstream.json();
      res.setHeader("Cache-Control", "s-maxage=3600, stale-while-revalidate=7200");
      res.status(200).json({
        tickers: live.tickers,
        as_of_date: live.as_of_date,
        last_known_prices: live.last_known_prices,
        rf: live.rf,
        method,
        data: {
          equity_curve: live.equity_curve,
          final_weights: live.final_weights,
          last_curve_value: live.last_curve_value,
        },
        source: "live",
      });
      return;
    } catch (e) {
      // fall through to the static snapshot below
      console.error(`live portfolio fetch failed, serving static snapshot: ${e}`);
    }
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
