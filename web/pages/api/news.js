// Per-ticker news, from Yahoo Finance's long-standing public RSS feed --
// same vendor already used for quotes/FX in this project, no API key, no
// Cloudflare challenge (unlike a couple of stockanalysis.com paths tried
// and rejected during research for this feature). Hand-rolled RSS
// extraction rather than pulling in an XML parser dependency: the feed's
// <item> shape is simple and stable, and this project already avoids
// dependencies where a short, tested parser does the job (see
// EquityChart.js/PriceChart.js on not using a charting library).
//
// Cached at the edge for 15 minutes -- headlines don't need to be fresher
// than that for this use, and it keeps a popular ticker from hammering
// Yahoo on every visitor's page load.

const TICKER_RE = /^[A-Za-z0-9.-]{1,10}$/;
const MAX_ITEMS = 8;

function decodeEntities(s) {
  return s
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, "$1");
}

function extractTag(block, tag) {
  const m = block.match(new RegExp(`<${tag}>([\\s\\S]*?)</${tag}>`));
  return m ? decodeEntities(m[1]).trim() : null;
}

function parseRssItems(xml) {
  const items = [];
  const blocks = xml.match(/<item>[\s\S]*?<\/item>/g) || [];
  for (const block of blocks.slice(0, MAX_ITEMS)) {
    const title = extractTag(block, "title");
    const link = extractTag(block, "link");
    const pubDate = extractTag(block, "pubDate");
    if (title && link) items.push({ title, link, pubDate });
  }
  return items;
}

export default async function handler(req, res) {
  const ticker = typeof req.query.ticker === "string" ? req.query.ticker.toUpperCase() : "";
  if (!TICKER_RE.test(ticker)) {
    res.status(400).json({ error: "invalid ticker format" });
    return;
  }
  try {
    const url = `https://feeds.finance.yahoo.com/rss/2.0/headline?s=${encodeURIComponent(ticker)}&region=US&lang=en-US`;
    const upstream = await fetch(url, { headers: { "User-Agent": "Mozilla/5.0" } });
    if (!upstream.ok) throw new Error(`feed returned ${upstream.status}`);
    const xml = await upstream.text();
    const items = parseRssItems(xml);
    res.setHeader("Cache-Control", "s-maxage=900, stale-while-revalidate=3600");
    res.status(200).json({ ticker, items });
  } catch (e) {
    console.error(`news fetch failed for ${ticker}: ${e}`);
    res.status(502).json({ error: String(e) });
  }
}
