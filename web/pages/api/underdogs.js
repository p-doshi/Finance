// Proxies to the "app" service's /api/underdogs. See
// pages/api/portfolio.js for why this goes through a server-side route.

export default async function handler(req, res) {
  const appUrl = process.env.APP_URL;
  if (!appUrl) {
    res.status(503).json({ error: "APP_URL not configured (local dev without the Python service running?)" });
    return;
  }
  try {
    const params = new URLSearchParams();
    for (const key of ["min_cap", "max_cap", "limit"]) {
      if (req.query[key]) params.set(key, req.query[key]);
    }
    const upstream = await fetch(`${appUrl}/api/underdogs?${params.toString()}`, {
      signal: AbortSignal.timeout(25_000),
    });
    const json = await upstream.json();
    if (!upstream.ok) {
      res.status(upstream.status).json(json);
      return;
    }
    res.setHeader("Cache-Control", "s-maxage=1800, stale-while-revalidate=3600");
    res.status(200).json(json);
  } catch (e) {
    console.error(`underdogs fetch failed: ${e}`);
    res.status(502).json({ error: String(e) });
  }
}
