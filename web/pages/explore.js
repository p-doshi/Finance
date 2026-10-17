import { useEffect, useMemo, useState } from "react";
import Head from "next/head";
import Link from "next/link";
import Nav from "../components/Nav";
import Card from "../components/Card";

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
      <main id="main-content" className="container">
        <h1 className="page-title">Explore</h1>
        <p className="lede">
          {universe ? `${universe.count.toLocaleString()} US + Canada listings` : "Loading the market snapshot…"}
          {universe && ` as of ${universe.as_of}`} — liquidity-screened (market cap ≥ $100M, meaningful daily dollar
          volume), not every shell company on the tape.
        </p>

        {error && <div className="down" style={{ fontSize: 13, marginBottom: 16 }}>Couldn&apos;t load the market snapshot: {error}</div>}

        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 16 }}>
          <input
            className="input"
            type="text"
            placeholder="Search ticker or company name…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            style={{ flex: "1 1 240px" }}
          />
          <select className="select" value={country} onChange={(e) => setCountry(e.target.value)}>
            <option value="ALL">US + Canada</option>
            <option value="US">US only</option>
            <option value="CA">Canada only</option>
          </select>
          <select className="select" value={sortKey} onChange={(e) => setSortKey(e.target.value)}>
            <option value="market_cap">Sort: Market cap</option>
            <option value="day_change_pct">Sort: Day change</option>
            <option value="volume">Sort: Volume</option>
          </select>
        </div>

        <Card style={{ padding: "2px 16px" }}>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Ticker</th>
                  <th>Name</th>
                  <th className="num">Price</th>
                  <th className="num">Day change</th>
                  <th className="num">Market cap</th>
                  <th>Sector</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((r) => (
                  <tr key={`${r.country}-${r.ticker}`}>
                    <td style={{ fontWeight: 600 }}>
                      <Link href={`/stock/${r.ticker}`}>{r.ticker}</Link>
                      {r.country === "CA" && <span style={{ color: "var(--muted)", fontSize: 10 }}> {r.exchange}</span>}
                    </td>
                    <td style={{ maxWidth: 240, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.name}</td>
                    <td className="num">${r.price.toFixed(2)}</td>
                    <td className={`num ${(r.day_change_pct ?? 0) >= 0 ? "up" : "down"}`}>
                      {r.day_change_pct != null ? `${r.day_change_pct >= 0 ? "+" : ""}${r.day_change_pct.toFixed(2)}%` : "—"}
                    </td>
                    <td className="num">{fmtCap(r.market_cap)}</td>
                    <td style={{ color: "var(--text-secondary)" }}>{r.sector || "—"}</td>
                  </tr>
                ))}
                {universe && filtered.length === 0 && (
                  <tr>
                    <td colSpan={6} style={{ padding: 20, textAlign: "center", color: "var(--muted)" }}>
                      No matches.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>
        {filtered.length === 200 && (
          <p style={{ fontSize: 11.5, color: "var(--muted)", marginTop: 10 }}>Showing the top 200 matches — narrow your search for more.</p>
        )}
      </main>
    </>
  );
}
