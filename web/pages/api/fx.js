// USD->CAD spot rate, from the same Yahoo Finance chart endpoint already
// used for equity quotes (pages/api/quotes.js) -- FX pairs work on the
// identical v8/finance/chart route with a "USDCAD=X" symbol, no separate
// provider needed. Cached at the edge for 10 minutes: unlike an equity
// quote this never needs to be fresher than that for a display-currency
// toggle, and it keeps this from adding a Yahoo request to every poll of
// every visitor.

export default async function handler(req, res) {
  try {
    const url = "https://query1.finance.yahoo.com/v8/finance/chart/USDCAD=X?range=1d&interval=1d";
    const upstream = await fetch(url, { headers: { "User-Agent": "Mozilla/5.0" } });
    if (!upstream.ok) throw new Error(`USDCAD=X: ${upstream.status}`);
    const json = await upstream.json();
    const meta = json?.chart?.result?.[0]?.meta;
    const rate = meta?.regularMarketPrice;
    if (typeof rate !== "number") throw new Error("no rate in response");
    res.setHeader("Cache-Control", "s-maxage=600, stale-while-revalidate=1800");
    res.status(200).json({ pair: "USDCAD", rate, asOf: new Date().toISOString() });
  } catch (e) {
    console.error(`fx fetch failed: ${e}`);
    res.status(502).json({ error: String(e) });
  }
}
