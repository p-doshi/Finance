import { useEffect, useState } from "react";
import Head from "next/head";
import { useRouter } from "next/router";
import Nav from "../../components/Nav";
import PriceChart from "../../components/PriceChart";
import Card from "../../components/Card";

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
      <main id="main-content" className="container">
        <h1 className="page-title reveal" style={{ fontSize: 24 }}>{ticker}</h1>

        {error && (
          <div className="down" style={{ fontSize: 13, margin: "10px 0" }}>
            Couldn&apos;t load {ticker}: {error}
          </div>
        )}

        {data && (
          <>
            <div className="reveal" style={{ display: "flex", alignItems: "center", gap: 12, margin: "10px 0 18px" }}>
              <span className="hero-figure" style={{ fontSize: 32 }}>${data.price.toFixed(2)}</span>
              {data.day_change_pct != null && (
                <span className={data.day_change_pct >= 0 ? "up" : "down"} style={{ fontSize: 15, fontWeight: 600 }}>
                  {data.day_change_pct >= 0 ? "+" : ""}
                  {data.day_change_pct.toFixed(2)}%
                </span>
              )}
              <span style={{ fontSize: 12, color: "var(--muted)" }}>
                <span className="live-dot" style={{ marginRight: 6, verticalAlign: "middle" }} />
                as of {data.as_of}
              </span>
            </div>

            <div className="reveal" style={{ "--reveal-delay": "60ms", display: "flex", gap: 6, marginBottom: 14 }}>
              {RANGES.map((r) => (
                <button
                  key={r}
                  className={`btn${r === range ? " active" : ""}`}
                  onClick={() => setRange(r)}
                >
                  {r}
                </button>
              ))}
            </div>

            <Card className="reveal" style={{ "--reveal-delay": "120ms", marginBottom: 18 }}>
              <PriceChart series={data.series} color="auto" />
            </Card>

            <div className="reveal" style={{ "--reveal-delay": "180ms", display: "flex", gap: 28, fontSize: 13 }}>
              <div>
                <div className="eyebrow">52-week low</div>
                <div style={{ fontVariantNumeric: "tabular-nums", marginTop: 2 }}>${data.low_52w.toFixed(2)}</div>
              </div>
              <div>
                <div className="eyebrow">52-week high</div>
                <div style={{ fontVariantNumeric: "tabular-nums", marginTop: 2 }}>${data.high_52w.toFixed(2)}</div>
              </div>
            </div>
          </>
        )}

        {!data && !error && (
          <div style={{ marginTop: 10 }}>
            <div className="skeleton" style={{ width: 160, height: 38, marginBottom: 18 }} />
            <div className="skeleton" style={{ width: "100%", height: 280, borderRadius: 14 }} />
          </div>
        )}
      </main>
    </>
  );
}
