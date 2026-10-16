import { useEffect, useState } from "react";
import Head from "next/head";
import { useRouter } from "next/router";
import Nav from "../../components/Nav";
import PriceChart from "../../components/PriceChart";

const RANGES = ["3M", "1Y", "5Y"];

export default function StockDetail() {
  const router = useRouter();
  const { ticker } = router.query;
  const [range, setRange] = useState("1Y");
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!ticker) return;
    let cancelled = false;
    setData(null);
    setError(null);
    fetch(`/api/stock/${ticker}?range=${range}`)
      .then(async (r) => {
        const json = await r.json();
        if (cancelled) return;
        if (!r.ok) setError(json.detail || json.error || `HTTP ${r.status}`);
        else setData(json);
      })
      .catch((e) => !cancelled && setError(String(e)));
    return () => {
      cancelled = true;
    };
  }, [ticker, range]);

  return (
    <>
      <Head>
        <title>{ticker ? `${ticker} — Live Portfolio Simulator` : "Stock — Live Portfolio Simulator"}</title>
      </Head>
      <Nav />
      <main style={{ maxWidth: 820, margin: "0 auto", padding: "20px 16px 48px" }}>
        <h1 style={{ fontSize: 22, fontWeight: 650, margin: "0 0 4px" }}>{ticker}</h1>

        {error && (
          <div style={{ color: "var(--critical)", fontSize: 13, margin: "8px 0" }}>
            Couldn&apos;t load {ticker}: {error}
          </div>
        )}

        {data && (
          <>
            <div style={{ display: "flex", alignItems: "baseline", gap: 12, margin: "4px 0 16px" }}>
              <span style={{ fontSize: 32, fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>${data.price.toFixed(2)}</span>
              {data.day_change_pct != null && (
                <span style={{ fontSize: 15, color: data.day_change_pct >= 0 ? "var(--good)" : "var(--critical)" }}>
                  {data.day_change_pct >= 0 ? "+" : ""}
                  {data.day_change_pct.toFixed(2)}%
                </span>
              )}
              <span style={{ fontSize: 12, color: "var(--muted)" }}>as of {data.as_of}</span>
            </div>

            <div style={{ display: "flex", gap: 6, marginBottom: 12 }}>
              {RANGES.map((r) => (
                <button
                  key={r}
                  onClick={() => setRange(r)}
                  style={{
                    fontSize: 12,
                    padding: "4px 10px",
                    borderRadius: 6,
                    border: "1px solid var(--border)",
                    background: r === range ? "var(--text-primary)" : "var(--surface-1)",
                    color: r === range ? "var(--surface-1)" : "var(--text-primary)",
                    cursor: "pointer",
                  }}
                >
                  {r}
                </button>
              ))}
            </div>

            <div style={{ background: "var(--surface-1)", border: "1px solid var(--border)", borderRadius: 12, padding: 16, marginBottom: 16 }}>
              <PriceChart series={data.series} color="auto" />
            </div>

            <div style={{ display: "flex", gap: 24, fontSize: 13 }}>
              <div>
                <div style={{ color: "var(--muted)", fontSize: 11, textTransform: "uppercase" }}>52-week low</div>
                <div style={{ fontVariantNumeric: "tabular-nums" }}>${data.low_52w.toFixed(2)}</div>
              </div>
              <div>
                <div style={{ color: "var(--muted)", fontSize: 11, textTransform: "uppercase" }}>52-week high</div>
                <div style={{ fontVariantNumeric: "tabular-nums" }}>${data.high_52w.toFixed(2)}</div>
              </div>
            </div>
          </>
        )}

        {!data && !error && <p style={{ color: "var(--muted)", fontSize: 13 }}>Loading…</p>}
      </main>
    </>
  );
}
