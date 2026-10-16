// Proxies to the "app" service's /api/universe -- the full US+Canada
// liquid-equity snapshot backing the Explore page's search/browse. See
// pages/api/portfolio.js for why this goes through a server-side route
// instead of the browser calling the internal service directly: APP_URL
// (injected by the vercel.json binding) is only visible server-side.
//
// Unlike /api/portfolio there's no static build-time snapshot to fall
// back to here -- a stale universe listing a year old would be actively
// misleading for a "search any company" feature, so a failure surfaces
// as an error to the page instead of silently serving old data.

export default async function handler(req, res) {
  const appUrl = process.env.APP_URL;
  if (!appUrl) {
    res.status(503).json({ error: "APP_URL not configured (local dev without the Python service running?)" });
    return;
  }
  try {
    const upstream = await fetch(`${appUrl}/api/universe`, { signal: AbortSignal.timeout(25_000) });
    if (!upstream.ok) throw new Error(`app service returned ${upstream.status}`);
    const json = await upstream.json();
    res.setHeader("Cache-Control", "s-maxage=1800, stale-while-revalidate=3600");
    res.status(200).json(json);
  } catch (e) {
    console.error(`universe fetch failed: ${e}`);
    res.status(502).json({ error: String(e) });
  }
}
