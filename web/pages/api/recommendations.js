// Proxies to the "app" service's POST /api/recommendations. See
// pages/api/portfolio.js for why this goes through a server-side route.

export default async function handler(req, res) {
  if (req.method !== "POST") {
    res.status(405).json({ error: "POST only" });
    return;
  }
  const appUrl = process.env.APP_URL;
  if (!appUrl) {
    res.status(503).json({ error: "APP_URL not configured (local dev without the Python service running?)" });
    return;
  }
  try {
    const upstream = await fetch(`${appUrl}/api/recommendations`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req.body),
      signal: AbortSignal.timeout(30_000),
    });
    const json = await upstream.json();
    res.status(upstream.status).json(json);
  } catch (e) {
    console.error(`recommendations fetch failed: ${e}`);
    res.status(502).json({ error: String(e) });
  }
}
