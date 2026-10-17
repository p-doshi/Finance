import { useEffect, useState } from "react";
import Head from "next/head";
import Link from "next/link";
import Nav from "../components/Nav";
import Card from "../components/Card";
import { fmtCap, fmtChange } from "../lib/format";

const PRESETS = [
  { label: "Micro-cap", min: 50_000_000, max: 300_000_000 },
  { label: "Small-cap", min: 300_000_000, max: 2_000_000_000 },
  { label: "Mid-cap", min: 2_000_000_000, max: 10_000_000_000 },
];

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
    fetch(`/api/underdogs?min_cap=${minCap}&max_cap=${maxCap}&limit=25`)
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
          price-to-earnings among companies that have a usable one. Loss-making names, names with no P/E, and P/E
          below 3 (almost always a data artifact or an atypical capital structure like a REIT/trust, not genuine
          cheapness) are excluded and counted separately rather than silently mis-ranked.
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
          </label>
        </div>

        {error && <div className="down" style={{ fontSize: 13, marginBottom: 16 }}>Couldn&apos;t run the screen: {error}</div>}

        {data && !error && (
          <>
            <p style={{ fontSize: 12.5, color: "var(--muted)", marginBottom: 12 }}>
              {data.count_in_band.toLocaleString()} names in this band, {data.count_excluded.toLocaleString()}{" "}
              excluded (no usable P/E), {data.rows.length} shown.
            </p>
            <Card className="reveal" style={{ padding: "2px 16px" }}>
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Ticker</th>
                      <th>Name</th>
                      <th className="num">P/E</th>
                      <th className="num">Price</th>
                      <th className="num">Day change</th>
                      <th className="num">Market cap</th>
                      <th>Sector</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.rows.map((r) => (
                      <tr key={`${r.country}-${r.ticker}`}>
                        <td style={{ fontWeight: 600 }}>
                          <Link href={`/stock/${r.ticker}`}>{r.ticker}</Link>
                          {r.country === "CA" && <span style={{ color: "var(--muted)", fontSize: 10 }}> {r.exchange}</span>}
                        </td>
                        <td style={{ maxWidth: 220, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {r.name}
                        </td>
                        <td className="num">{r.pe_ratio.toFixed(1)}</td>
                        <td className="num">${r.price.toFixed(2)}</td>
                        <td className={`num ${(r.day_change_pct ?? 0) >= 0 ? "up" : "down"}`}>{fmtChange(r.day_change_pct)}</td>
                        <td className="num">{fmtCap(r.market_cap)}</td>
                        <td style={{ color: "var(--text-secondary)" }}>{r.sector || "—"}</td>
                      </tr>
                    ))}
                    {data.rows.length === 0 && (
                      <tr>
                        <td colSpan={7} style={{ padding: 20, textAlign: "center", color: "var(--muted)" }}>
                          No names in this band pass the screen.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </Card>
            <p style={{ fontSize: 11.5, color: "var(--muted)", marginTop: 10 }}>
              A low P/E is a starting point for research, not a buy signal — click a ticker for its price history,
              52-week range, volatility, drawdown, beta, and recent headlines.
            </p>
          </>
        )}

        {loading && !data && (
          <Card>
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="skeleton" style={{ height: 18, marginTop: i === 0 ? 0 : 10 }} />
            ))}
          </Card>
        )}
      </main>
    </>
  );
}
