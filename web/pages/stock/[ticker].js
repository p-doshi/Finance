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
  const [risk, setRisk] = useState(null);
  const [news, setNews] = useState(null);

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

  useEffect(() => {
    if (!ticker) return;
    let cancelled = false;
    setRisk(null);
    setNews(null);
    // fixed at 1Y regardless of the chart's own range toggle -- vol/drawdown
    // need ~252 trading days to be meaningful, which a 3M chart view doesn't have
    fetch(`/api/stock/${ticker}?range=1Y&risk=true`)
      .then((r) => r.json())
      .then((json) => !cancelled && json.risk && setRisk(json.risk))
      .catch((e) => console.error(`risk fetch failed for ${ticker}: ${e}`));
    fetch(`/api/news?ticker=${ticker}`)
      .then((r) => r.json())
      .then((json) => !cancelled && Array.isArray(json.items) && setNews(json.items))
      .catch((e) => console.error(`news fetch failed for ${ticker}: ${e}`));
    return () => {
      cancelled = true;
    };
  }, [ticker]);

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

            <div className="reveal" style={{ "--reveal-delay": "180ms", display: "flex", gap: 28, fontSize: 13, marginBottom: 24 }}>
              <div>
                <div className="eyebrow">52-week low</div>
                <div style={{ fontVariantNumeric: "tabular-nums", marginTop: 2 }}>${data.low_52w.toFixed(2)}</div>
              </div>
              <div>
                <div className="eyebrow">52-week high</div>
                <div style={{ fontVariantNumeric: "tabular-nums", marginTop: 2 }}>${data.high_52w.toFixed(2)}</div>
              </div>
            </div>

            <h2 style={{ fontSize: 15, fontWeight: 650, margin: "0 0 10px" }}>Risk (trailing 1 year)</h2>
            {risk ? (
              <Card className="reveal" style={{ marginBottom: 24 }}>
                <div style={{ display: "flex", gap: 28, flexWrap: "wrap", fontSize: 13 }}>
                  <div>
                    <div className="eyebrow">Annualized volatility</div>
                    <div style={{ fontVariantNumeric: "tabular-nums", marginTop: 2 }}>
                      {risk.annualized_vol != null ? `${(risk.annualized_vol * 100).toFixed(1)}%` : "—"}
                    </div>
                  </div>
                  <div>
                    <div className="eyebrow">Max drawdown</div>
                    <div className={risk.max_drawdown != null && risk.max_drawdown < 0 ? "down" : ""} style={{ fontVariantNumeric: "tabular-nums", marginTop: 2 }}>
                      {risk.max_drawdown != null ? `${(risk.max_drawdown * 100).toFixed(1)}%` : "—"}
                    </div>
                  </div>
                  <div>
                    <div className="eyebrow">Beta vs S&amp;P 500</div>
                    <div style={{ fontVariantNumeric: "tabular-nums", marginTop: 2 }}>
                      {risk.beta_vs_spy != null ? risk.beta_vs_spy.toFixed(2) : "—"}
                    </div>
                  </div>
                </div>
                <p style={{ fontSize: 11, color: "var(--muted)", marginTop: 10 }}>
                  Computed the same way this project ranks its broader universe (research.screen), not a vendor
                  figure. Needs ~1 year of history; null if {ticker} doesn&apos;t have enough yet.
                </p>
              </Card>
            ) : (
              <Card style={{ marginBottom: 24 }}>
                <div className="skeleton" style={{ height: 40 }} />
              </Card>
            )}

            <h2 style={{ fontSize: 15, fontWeight: 650, margin: "0 0 10px" }}>Recent news</h2>
            {news ? (
              news.length > 0 ? (
                <Card className="reveal" style={{ padding: "4px 16px" }}>
                  <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
                    {news.map((item, i) => (
                      <li key={item.link} style={{ padding: "12px 0", borderTop: i === 0 ? "none" : "1px solid var(--grid)" }}>
                        <a href={item.link} target="_blank" rel="noopener noreferrer" style={{ fontSize: 13.5, fontWeight: 600, textDecoration: "none" }}>
                          {item.title}
                        </a>
                        {item.pubDate && (
                          <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 4 }}>
                            {new Date(item.pubDate).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })}
                          </div>
                        )}
                      </li>
                    ))}
                  </ul>
                </Card>
              ) : (
                <p style={{ fontSize: 13, color: "var(--muted)" }}>No recent headlines found for {ticker}.</p>
              )
            ) : (
              <Card>
                <div className="skeleton" style={{ height: 18, marginBottom: 10 }} />
                <div className="skeleton" style={{ height: 18, marginBottom: 10 }} />
                <div className="skeleton" style={{ height: 18 }} />
              </Card>
            )}
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
