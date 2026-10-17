// Proxies to the "app" service's /api/stock/{ticker} -- works for any
// ticker stockanalysis.com covers, not just the 12-name watchlist. See
// pages/api/portfolio.js for why this goes through a server-side route.

export default async function handler(req, res) {
  const { ticker, range: range_, risk } = req.query;
  const appUrl = process.env.APP_URL;
  if (!appUrl) {
    res.status(503).json({ error: "APP_URL not configured (local dev without the Python service running?)" });
    return;
  }
  try {
    const params = new URLSearchParams();
    if (range_) params.set("range_", range_);
    if (risk) params.set("risk", "true");
    const qs = params.toString() ? `?${params.toString()}` : "";
    const upstream = await fetch(`${appUrl}/api/stock/${encodeURIComponent(ticker)}${qs}`, {
      signal: AbortSignal.timeout(20_000),
    });
    const json = await upstream.json();
    if (!upstream.ok) {
      res.status(upstream.status).json(json);
      return;
    }
    res.setHeader("Cache-Control", "s-maxage=300, stale-while-revalidate=900");
    res.status(200).json(json);
  } catch (e) {
    console.error(`stock detail fetch failed for ${ticker}: ${e}`);
    res.status(502).json({ error: String(e) });
  }
}
