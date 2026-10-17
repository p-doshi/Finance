// Live quotes, fetched server-side (Vercel serverless function) from
// Yahoo Finance's chart API -- the same endpoint already validated and
// used throughout the Python side of this project
// (portfolio_pipeline.data.fetch_ca), confirmed live during this session
// to return genuinely current prices (today's regularMarketPrice/Time).
//
// Not Yahoo's v7 multi-symbol quote endpoint -- that now requires an API
// key (`"Unauthorized"` when tried anonymously, checked directly before
// building this). One request per ticker instead, in parallel, server-side
// only (never exposed to the browser, which only ever calls this route).
//
// Cached at the edge for 30s (`Cache-Control`) so a page full of visitors
// polling this route doesn't turn into N Yahoo requests per visitor per
// poll -- Vercel's CDN serves the cached response to everyone else within
// that window. Pass ?tickers=A,B,C for an arbitrary list (the My Holdings
// panel, which can hold anything); no param keeps the original fixed
// watchlist behaviour the strategy simulator relies on.

const DEFAULT_TICKERS = ["NVDA", "JNJ", "KO", "PG", "WMT", "VZ", "XOM", "RY", "ENB", "UL", "NVO", "ASML"];
const TICKER_RE = /^[A-Za-z0-9.-]{1,10}$/;
const MAX_TICKERS = 40;

async function fetchOne(ticker) {
  const url = `https://query1.finance.yahoo.com/v8/finance/chart/${ticker}?range=1d&interval=1d`;
  const res = await fetch(url, { headers: { "User-Agent": "Mozilla/5.0" } });
  if (!res.ok) throw new Error(`${ticker}: ${res.status}`);
  const json = await res.json();
  const meta = json?.chart?.result?.[0]?.meta;
  if (!meta || typeof meta.regularMarketPrice !== "number") {
    throw new Error(`${ticker}: no price in response`);
  }
  const prevClose = meta.previousClose ?? meta.chartPreviousClose ?? null;
  return {
    ticker,
    price: meta.regularMarketPrice,
    previousClose: prevClose,
    dayChangePct: prevClose ? (meta.regularMarketPrice / prevClose - 1) * 100 : null,
    asOf: meta.regularMarketTime ? new Date(meta.regularMarketTime * 1000).toISOString() : null,
  };
}

export default async function handler(req, res) {
  let tickers = DEFAULT_TICKERS;
  if (typeof req.query.tickers === "string" && req.query.tickers.length > 0) {
    const requested = [...new Set(req.query.tickers.split(",").map((t) => t.trim().toUpperCase()).filter(Boolean))];
    const invalid = requested.filter((t) => !TICKER_RE.test(t));
    if (invalid.length > 0) {
      res.status(400).json({ error: `invalid ticker format: ${invalid.join(", ")}` });
      return;
    }
    if (requested.length > MAX_TICKERS) {
      res.status(400).json({ error: `too many tickers (max ${MAX_TICKERS})` });
      return;
    }
    tickers = requested;
  }

  const settled = await Promise.allSettled(tickers.map(fetchOne));
  const quotes = {};
  const errors = {};
  settled.forEach((r, i) => {
    const ticker = tickers[i];
    if (r.status === "fulfilled") {
      quotes[ticker] = r.value;
    } else {
      errors[ticker] = String(r.reason);
    }
  });

  res.setHeader("Cache-Control", "s-maxage=30, stale-while-revalidate=60");
  res.status(200).json({ quotes, errors, fetchedAt: new Date().toISOString() });
}
