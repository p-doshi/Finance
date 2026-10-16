import { useEffect, useMemo, useState } from "react";
import Head from "next/head";
import Link from "next/link";
import Nav from "../components/Nav";

const fmtCap = (n) => {
  if (n == null) return "—";
  if (n >= 1e12) return `$${(n / 1e12).toFixed(2)}T`;
  if (n >= 1e9) return `$${(n / 1e9).toFixed(2)}B`;
  if (n >= 1e6) return `$${(n / 1e6).toFixed(0)}M`;
  return `$${n.toLocaleString()}`;
};

export default function Explore() {
  const [universe, setUniverse] = useState(null);
  const [error, setError] = useState(null);
  const [query, setQuery] = useState("");
  const [country, setCountry] = useState("ALL");
  const [sortKey, setSortKey] = useState("market_cap");

  useEffect(() => {
    let cancelled = false;
    fetch("/api/universe")
      .then((r) => r.json())
      .then((json) => {
        if (cancelled) return;
        if (json.error) setError(json.error);
        else setUniverse(json);
      })
      .catch((e) => !cancelled && setError(String(e)));
    return () => {
      cancelled = true;
    };
  }, []);

  const filtered = useMemo(() => {
    if (!universe) return [];
    const q = query.trim().toLowerCase();
    let rows = universe.rows;
    if (country !== "ALL") rows = rows.filter((r) => r.country === country);
    if (q) rows = rows.filter((r) => r.ticker.toLowerCase().includes(q) || r.name.toLowerCase().includes(q));
    const sorted = [...rows].sort((a, b) => (b[sortKey] ?? -Infinity) - (a[sortKey] ?? -Infinity));
    return sorted.slice(0, 200);
  }, [universe, query, country, sortKey]);

  return (
    <>
      <Head>
        <title>Explore — Live Portfolio Simulator</title>
      </Head>
      <Nav />
      <main style={{ maxWidth: 820, margin: "0 auto", padding: "20px 16px 48px" }}>
        <h1 style={{ fontSize: 20, fontWeight: 650, margin: "0 0 4px" }}>Explore</h1>
        <p style={{ color: "var(--text-secondary)", fontSize: 13, margin: "0 0 16px", maxWidth: "64ch" }}>
          {universe ? `${universe.count.toLocaleString()} US + Canada listings` : "Loading the market snapshot…"}
          {universe && ` as of ${universe.as_of}`} — liquidity-screened (market cap ≥ $100M, meaningful daily dollar
          volume), not every shell company on the tape.
        </p>

        {error && (
          <div style={{ color: "var(--critical)", fontSize: 13, marginBottom: 16 }}>Couldn&apos;t load the market snapshot: {error}</div>
        )}

        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 16 }}>
          <input
            type="text"
            placeholder="Search ticker or company name…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            style={{ fontSize: 13, padding: "6px 10px", borderRadius: 6, border: "1px solid var(--border)", flex: "1 1 240px", background: "var(--surface-1)", color: "var(--text-primary)" }}
          />
          <select
            value={country}
            onChange={(e) => setCountry(e.target.value)}
            style={{ fontSize: 13, padding: "6px 10px", borderRadius: 6 }}
          >
            <option value="ALL">US + Canada</option>
            <option value="US">US only</option>
            <option value="CA">Canada only</option>
          </select>
          <select
            value={sortKey}
            onChange={(e) => setSortKey(e.target.value)}
            style={{ fontSize: 13, padding: "6px 10px", borderRadius: 6 }}
          >
            <option value="market_cap">Sort: Market cap</option>
            <option value="day_change_pct">Sort: Day change</option>
            <option value="volume">Sort: Volume</option>
          </select>
        </div>

        <div style={{ background: "var(--surface-1)", border: "1px solid var(--border)", borderRadius: 12, padding: "4px 16px" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12.5 }}>
            <thead>
              <tr style={{ color: "var(--muted)", textTransform: "uppercase", fontSize: 11 }}>
                <th style={{ textAlign: "left", padding: "8px 4px" }}>Ticker</th>
                <th style={{ textAlign: "left", padding: "8px 4px" }}>Name</th>
                <th style={{ textAlign: "right", padding: "8px 4px" }}>Price</th>
                <th style={{ textAlign: "right", padding: "8px 4px" }}>Day change</th>
                <th style={{ textAlign: "right", padding: "8px 4px" }}>Market cap</th>
                <th style={{ textAlign: "left", padding: "8px 4px" }}>Sector</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((r) => (
                <tr key={`${r.country}-${r.ticker}`} style={{ borderTop: "1px solid var(--grid)" }}>
                  <td style={{ padding: "8px 4px", fontWeight: 600 }}>
                    <Link href={`/stock/${r.ticker}`} style={{ textDecoration: "none" }}>
                      {r.ticker}
                    </Link>
                    {r.country === "CA" && <span style={{ color: "var(--muted)", fontSize: 10 }}> {r.exchange}</span>}
                  </td>
                  <td style={{ padding: "8px 4px", maxWidth: 220, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {r.name}
                  </td>
                  <td style={{ padding: "8px 4px", textAlign: "right", fontVariantNumeric: "tabular-nums" }}>${r.price.toFixed(2)}</td>
                  <td
                    style={{
                      padding: "8px 4px",
                      textAlign: "right",
                      fontVariantNumeric: "tabular-nums",
                      color: (r.day_change_pct ?? 0) >= 0 ? "var(--good)" : "var(--critical)",
                    }}
                  >
                    {r.day_change_pct != null ? `${r.day_change_pct >= 0 ? "+" : ""}${r.day_change_pct.toFixed(2)}%` : "—"}
                  </td>
                  <td style={{ padding: "8px 4px", textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{fmtCap(r.market_cap)}</td>
                  <td style={{ padding: "8px 4px", color: "var(--text-secondary)" }}>{r.sector || "—"}</td>
                </tr>
              ))}
              {universe && filtered.length === 0 && (
                <tr>
                  <td colSpan={6} style={{ padding: 16, textAlign: "center", color: "var(--muted)" }}>
                    No matches.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        {filtered.length === 200 && (
          <p style={{ fontSize: 11, color: "var(--muted)", marginTop: 8 }}>Showing the top 200 matches — narrow your search for more.</p>
        )}
      </main>
    </>
  );
}
