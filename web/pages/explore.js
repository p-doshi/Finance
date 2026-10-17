import { useEffect, useMemo, useState } from "react";
import Head from "next/head";
import Link from "next/link";
import Nav from "../components/Nav";
import Card from "../components/Card";
import { fmtCap, fmtVolume, fmtChange } from "../lib/format";

const TOP_N = 10;

function BoardValue({ metric, row }) {
  if (metric === "cap") return <span className="board-value">{fmtCap(row.market_cap)}</span>;
  if (metric === "volume") return <span className="board-value">{fmtVolume(row.volume)}</span>;
  return (
    <span className={`board-value ${row.day_change_pct >= 0 ? "up" : "down"}`}>{fmtChange(row.day_change_pct)}</span>
  );
}

function LeaderboardCard({ title, rows, metric, delay = 0 }) {
  return (
    <Card className="reveal" style={{ "--reveal-delay": `${delay}ms` }}>
      <div className="board-head">
        <div className="eyebrow">{title}</div>
      </div>
      <ul className="board-list">
        {rows.map((r, i) => (
          <li key={`${r.country}-${r.ticker}`}>
            <Link href={`/stock/${r.ticker}`} className="board-row">
              <span className="board-rank">{i + 1}</span>
              <span className="board-id">{r.ticker}</span>
              <span className="board-name">{r.name}</span>
              <BoardValue metric={metric} row={r} />
            </Link>
          </li>
        ))}
        {rows.length === 0 && (
          <li style={{ padding: "10px 2px", color: "var(--muted)", fontSize: 13 }}>No data.</li>
        )}
      </ul>
    </Card>
  );
}

export default function Explore() {
  const [universe, setUniverse] = useState(null);
  const [error, setError] = useState(null);
  const [query, setQuery] = useState("");
  const [country, setCountry] = useState("ALL");

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

  const scoped = useMemo(() => {
    if (!universe) return [];
    return country === "ALL" ? universe.rows : universe.rows.filter((r) => r.country === country);
  }, [universe, country]);

  const query_ = query.trim().toLowerCase();

  const searchResults = useMemo(() => {
    if (!query_) return [];
    const rows = scoped.filter(
      (r) => r.ticker.toLowerCase().includes(query_) || r.name.toLowerCase().includes(query_)
    );
    return [...rows].sort((a, b) => (b.market_cap ?? -Infinity) - (a.market_cap ?? -Infinity)).slice(0, 50);
  }, [scoped, query_]);

  const leaderboards = useMemo(() => {
    const byCap = [...scoped].sort((a, b) => (b.market_cap ?? -Infinity) - (a.market_cap ?? -Infinity));
    const withChange = scoped.filter((r) => r.day_change_pct != null);
    const gainers = [...withChange].sort((a, b) => b.day_change_pct - a.day_change_pct);
    const losers = [...withChange].sort((a, b) => a.day_change_pct - b.day_change_pct);
    const withVolume = scoped.filter((r) => r.volume != null);
    const active = [...withVolume].sort((a, b) => b.volume - a.volume);
    return [
      { key: "cap", title: "Top market cap", metric: "cap", rows: byCap.slice(0, TOP_N) },
      { key: "gainers", title: "Top gainers", metric: "change", rows: gainers.slice(0, TOP_N) },
      { key: "losers", title: "Top losers", metric: "change", rows: losers.slice(0, TOP_N) },
      { key: "active", title: "Most active", metric: "volume", rows: active.slice(0, TOP_N) },
    ];
  }, [scoped]);

  return (
    <>
      <Head>
        <title>Explore — Live Portfolio Simulator</title>
      </Head>
      <Nav />
      <main id="main-content" className="container">
        <h1 className="page-title reveal">Explore</h1>
        <p className="lede reveal" style={{ "--reveal-delay": "60ms" }}>
          {universe && <span className="live-dot" style={{ marginRight: 7, verticalAlign: "middle" }} />}
          {universe ? `${universe.count.toLocaleString()} US + Canada listings` : "Loading the market snapshot…"}
          {universe && ` as of ${universe.as_of}`} — liquidity-screened (market cap ≥ $100M, meaningful daily dollar
          volume), not every shell company on the tape.
        </p>

        {error && <div className="down" style={{ fontSize: 13, marginBottom: 16 }}>Couldn&apos;t load the market snapshot: {error}</div>}

        <div className="reveal" style={{ "--reveal-delay": "100ms", display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 16 }}>
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
        </div>

        {!universe && !error && (
          <div className="board-grid">
            {Array.from({ length: 4 }).map((_, i) => (
              <Card key={i}>
                <div className="skeleton" style={{ width: 120, height: 13, marginBottom: 14 }} />
                {Array.from({ length: 5 }).map((_, j) => (
                  <div key={j} className="skeleton" style={{ height: 16, marginTop: j === 0 ? 0 : 12 }} />
                ))}
              </Card>
            ))}
          </div>
        )}

        {universe && query_ && (
          <>
            <Card className="reveal" style={{ padding: "2px 16px" }}>
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
                    {searchResults.map((r) => (
                      <tr key={`${r.country}-${r.ticker}`}>
                        <td style={{ fontWeight: 600 }}>
                          <Link href={`/stock/${r.ticker}`}>{r.ticker}</Link>
                          {r.country === "CA" && <span style={{ color: "var(--muted)", fontSize: 10 }}> {r.exchange}</span>}
                        </td>
                        <td style={{ maxWidth: 240, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {r.name}
                        </td>
                        <td className="num">${r.price.toFixed(2)}</td>
                        <td className={`num ${(r.day_change_pct ?? 0) >= 0 ? "up" : "down"}`}>
                          {fmtChange(r.day_change_pct)}
                        </td>
                        <td className="num">{fmtCap(r.market_cap)}</td>
                        <td style={{ color: "var(--text-secondary)" }}>{r.sector || "—"}</td>
                      </tr>
                    ))}
                    {searchResults.length === 0 && (
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
            {searchResults.length === 50 && (
              <p style={{ fontSize: 11.5, color: "var(--muted)", marginTop: 10 }}>
                Showing the top 50 matches — narrow your search for more.
              </p>
            )}
          </>
        )}

        {universe && !query_ && (
          <div className="board-grid">
            {leaderboards.map((board, i) => (
              <LeaderboardCard
                key={board.key}
                title={board.title}
                rows={board.rows}
                metric={board.metric}
                delay={i * 60}
              />
            ))}
          </div>
        )}
      </main>
    </>
  );
}
