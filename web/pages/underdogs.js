import { useEffect, useState } from "react";
import Head from "next/head";
import Link from "next/link";
import Nav from "../components/Nav";
import Card from "../components/Card";
import { fmtCap } from "../lib/format";

const PRESETS = [
  { label: "Micro-cap", min: 50_000_000, max: 300_000_000 },
  { label: "Small-cap", min: 300_000_000, max: 2_000_000_000 },
  { label: "Mid-cap", min: 2_000_000_000, max: 10_000_000_000 },
];

const TOP_PER_SECTOR = 5;
const MAX_SECTORS = 8;
const MAX_NEWS = 2;

// The API's "sector" field is actually a fine-grained industry label (think
// "Marine Shipping", "REIT - Mortgage") -- there's no broader ~11-way GICS
// sector in the underlying data to group by instead. A market-cap band
// commonly spans 40+ of these, so showing every one defeats the point of
// cards over a long list; instead we show the industries with the most
// names passing the screen in this band (richer cards, not a wall of
// one-name cards), each still ranked cheapest-first internally.
function groupBySector(rows) {
  const bySector = new Map();
  for (const r of rows) {
    const key = r.sector || "Unclassified";
    if (!bySector.has(key)) bySector.set(key, []);
    bySector.get(key).push(r);
  }
  const groups = [...bySector.entries()].map(([sector, names]) => ({
    sector,
    total: names.length,
    names: names.slice(0, TOP_PER_SECTOR),
  }));
  const totalSectors = groups.length;
  const top = groups.sort((a, b) => b.total - a.total || a.names[0].pe_ratio - b.names[0].pe_ratio).slice(0, MAX_SECTORS);
  return { top, totalSectors };
}

function TopPickNews({ ticker }) {
  const [news, setNews] = useState(null);

  useEffect(() => {
    let cancelled = false;
    fetch(`/api/news?ticker=${ticker}`)
      .then((r) => r.json())
      .then((json) => !cancelled && Array.isArray(json.items) && setNews(json.items))
      .catch(() => !cancelled && setNews([]));
    return () => {
      cancelled = true;
    };
  }, [ticker]);

  if (news === null) {
    return <div className="skeleton" style={{ height: 12, width: "70%", margin: "2px 0 10px 26px" }} />;
  }
  if (news.length === 0) return null;

  return (
    <ul style={{ listStyle: "none", margin: "2px 0 10px 26px", padding: 0 }}>
      {news.slice(0, MAX_NEWS).map((item) => (
        <li key={item.link} style={{ marginTop: 3, display: "flex", gap: 6, alignItems: "baseline" }}>
          {item.sentiment_label && (
            <span
              className={item.sentiment_label === "positive" ? "up" : item.sentiment_label === "negative" ? "down" : ""}
              style={{ fontSize: 9, fontWeight: 700, textTransform: "uppercase", flexShrink: 0 }}
            >
              {item.sentiment_label === "neutral" ? "·" : item.sentiment_label === "positive" ? "+" : "−"}
            </span>
          )}
          <a
            href={item.link}
            target="_blank"
            rel="noopener noreferrer"
            style={{ fontSize: 11.5, color: "var(--text-secondary)", textDecoration: "none" }}
          >
            {item.title}
          </a>
        </li>
      ))}
    </ul>
  );
}

function SectorCard({ sector, names, delay }) {
  return (
    <Card className="reveal" style={{ "--reveal-delay": `${delay}ms` }}>
      <div className="board-head">
        <div className="eyebrow">{sector}</div>
        <div style={{ fontSize: 11, color: "var(--muted)" }}>{names.length} shown</div>
      </div>
      <ul className="board-list">
        {names.map((r, i) => (
          <li key={`${r.country}-${r.ticker}`}>
            <Link href={`/stock/${r.ticker}`} className="board-row">
              <span className="board-rank">{i + 1}</span>
              <span className="board-id">{r.ticker}</span>
              <span className="board-name">{r.name}</span>
              <span className="board-value">{r.pe_ratio.toFixed(1)}×</span>
            </Link>
            {i === 0 && <TopPickNews ticker={r.ticker} />}
          </li>
        ))}
      </ul>
    </Card>
  );
}

export default function Underdogs() {
  const [minCap, setMinCap] = useState(PRESETS[1].min);
  const [maxCap, setMaxCap] = useState(PRESETS[1].max);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    // limit=100 (the API's ceiling), not the ~25 a flat table would show --
    // grouping by sector needs a wide enough pool that sectors outside the
    // single cheapest handful still get a card.
    fetch(`/api/underdogs?min_cap=${minCap}&max_cap=${maxCap}&limit=100`)
      .then(async (r) => {
        const json = await r.json();
        if (cancelled) return;
        if (!r.ok) setError(json.detail || json.error || `HTTP ${r.status}`);
        else setData(json);
      })
      .catch((e) => !cancelled && setError(String(e)))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [minCap, maxCap]);

  const { top: sectors, totalSectors } = data ? groupBySector(data.rows) : { top: [], totalSectors: 0 };

  return (
    <>
      <Head>
        <title>Underdogs — Live Portfolio Simulator</title>
      </Head>
      <Nav />
      <main id="main-content" className="container">
        <h1 className="page-title reveal">Underdogs</h1>
        <p className="lede reveal" style={{ "--reveal-delay": "60ms" }}>
          A transparent value screen, not a black-box score: within the market-cap band you pick, ranked by lowest
          price-to-earnings among companies that have a usable one, grouped by sector so a cheap pick can&apos;t hide
          a sector-wide problem. Loss-making names, names with no P/E, and P/E below 3 (almost always a data
          artifact or an atypical capital structure like a REIT/trust, not genuine cheapness) are excluded and
          counted separately rather than silently mis-ranked. Each sector&apos;s single cheapest pick carries its
          most recent headlines, linked to the real source, for a first read on why the market has it priced where
          it is.
        </p>

        <div className="reveal" style={{ "--reveal-delay": "100ms", display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 12 }}>
          {PRESETS.map((p) => (
            <button
              key={p.label}
              className={`btn${minCap === p.min && maxCap === p.max ? " active" : ""}`}
              onClick={() => {
                setMinCap(p.min);
                setMaxCap(p.max);
              }}
            >
              {p.label}
            </button>
          ))}
        </div>
        <div className="reveal" style={{ "--reveal-delay": "120ms", display: "flex", gap: 14, flexWrap: "wrap", marginBottom: 20 }}>
          <label className="field">
            Min market cap
            <input
              className="input"
              type="number"
              min="0"
              step="10000000"
              value={minCap}
              onChange={(e) => setMinCap(Math.max(0, Number(e.target.value) || 0))}
              style={{ width: 160 }}
            />
            <span style={{ fontSize: 11, color: "var(--muted)" }}>{fmtCap(minCap)}</span>
          </label>
          <label className="field">
            Max market cap
            <input
              className="input"
              type="number"
              min="0"
              step="10000000"
              value={maxCap}
              onChange={(e) => setMaxCap(Math.max(0, Number(e.target.value) || 0))}
              style={{ width: 160 }}
            />
            <span style={{ fontSize: 11, color: "var(--muted)" }}>{fmtCap(maxCap)}</span>
          </label>
        </div>

        {error && <div className="down" style={{ fontSize: 13, marginBottom: 16 }}>Couldn&apos;t run the screen: {error}</div>}

        {data && !error && (
          <>
            <p style={{ fontSize: 12.5, color: "var(--muted)", marginBottom: 12 }}>
              {data.count_in_band.toLocaleString()} names in this band, {data.count_excluded.toLocaleString()}{" "}
              excluded (no usable P/E), {data.count_ranked.toLocaleString()} pass the screen across {totalSectors}{" "}
              sector{totalSectors === 1 ? "" : "s"} — showing the {sectors.length} with the most names, top{" "}
              {TOP_PER_SECTOR} cheapest in each.
            </p>

            {sectors.length > 0 ? (
              <div className="board-grid">
                {sectors.map((s, i) => (
                  <SectorCard key={s.sector} sector={s.sector} names={s.names} delay={i * 50} />
                ))}
              </div>
            ) : (
              <Card>
                <p style={{ fontSize: 13, color: "var(--muted)", margin: 0 }}>No names in this band pass the screen.</p>
              </Card>
            )}

            <p style={{ fontSize: 11.5, color: "var(--muted)", marginTop: 16 }}>
              A low P/E is a starting point for research, not a buy signal — click a ticker for its price history,
              52-week range, volatility, drawdown, beta, and full recent headlines.
            </p>
          </>
        )}

        {loading && !data && (
          <div className="board-grid">
            {Array.from({ length: 4 }).map((_, i) => (
              <Card key={i}>
                <div className="skeleton" style={{ width: 100, height: 13, marginBottom: 14 }} />
                {Array.from({ length: 4 }).map((_, j) => (
                  <div key={j} className="skeleton" style={{ height: 16, marginTop: j === 0 ? 0 : 12 }} />
                ))}
              </Card>
            ))}
          </div>
        )}
      </main>
    </>
  );
}
