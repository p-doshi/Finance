// Proxies to the "app" service's GET /api/news/{ticker}. See
// pages/api/portfolio.js for why this goes through a server-side route.
//
// This used to be a standalone Yahoo-RSS-only fetch+parse implemented
// entirely here in JS. It's now a thin proxy: the real work (three
// independent sources, date-range filtering, sentiment scoring) moved to
// Python (data/news.py) once it needed VADER, which has no equivalent
// here without adding an npm dependency this project doesn't otherwise
// need.

export default async function handler(req, res) {
  const ticker = typeof req.query.ticker === "string" ? req.query.ticker : "";
  const appUrl = process.env.APP_URL;
  if (!appUrl) {
    res.status(503).json({ error: "APP_URL not configured (local dev without the Python service running?)" });
    return;
  }
  try {
    const params = new URLSearchParams();
    for (const key of ["start_date", "end_date", "limit"]) {
      if (req.query[key]) params.set(key, req.query[key]);
    }
    const qs = params.toString() ? `?${params.toString()}` : "";
    const upstream = await fetch(`${appUrl}/api/news/${encodeURIComponent(ticker)}${qs}`, {
      signal: AbortSignal.timeout(25_000),
    });
    const json = await upstream.json();
    if (!upstream.ok) {
      res.status(upstream.status).json(json);
      return;
    }
    res.setHeader("Cache-Control", "s-maxage=900, stale-while-revalidate=3600");
    res.status(200).json(json);
  } catch (e) {
    console.error(`news fetch failed for ${ticker}: ${e}`);
    res.status(502).json({ error: String(e) });
  }
}
