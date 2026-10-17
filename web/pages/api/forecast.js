// Proxies to the "app" service's POST /api/forecast. See
// pages/api/portfolio.js for why this goes through a server-side route:
// APP_URL (injected by the vercel.json binding) is only visible
// server-side. No static fallback here -- this is a live, per-request
// simulation over whatever holdings the visitor entered, not a shared
// snapshot with a sensible cached substitute.

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
    const upstream = await fetch(`${appUrl}/api/forecast`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req.body),
      signal: AbortSignal.timeout(30_000),
    });
    const json = await upstream.json();
    res.status(upstream.status).json(json);
  } catch (e) {
    console.error(`forecast fetch failed: ${e}`);
    res.status(502).json({ error: String(e) });
  }
}
