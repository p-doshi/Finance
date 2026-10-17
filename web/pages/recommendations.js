import { useEffect, useState } from "react";
import Head from "next/head";
import Nav from "../components/Nav";
import Card from "../components/Card";
import { loadHoldings } from "../components/HoldingsEditor";

// Rule-based, not a trained model -- fixed concentration/volatility
// thresholds checked against your real holdings (app.py's
// MAX_POSITION_WEIGHT/MAX_SECTOR_WEIGHT/MIN_POSITIONS/HIGH_VOL_THRESHOLD).
// See that module for why this stays rule-based for now rather than
// fitting thresholds to this project's own small set of example
// portfolios, which would risk the same overfitting research/overfitting.py
// exists elsewhere in this project to catch.
export default function Recommendations() {
  const [holdings, setHoldings] = useState([]);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setHoldings(loadHoldings());
  }, []);

  const holdingsKey = holdings.map((h) => `${h.ticker}:${h.shares}`).join(",");

  useEffect(() => {
    if (holdings.length === 0) {
      setData(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetch("/api/recommendations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ holdings: Object.fromEntries(holdings.map((h) => [h.ticker, h.shares])) }),
    })
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [holdingsKey]);

  return (
    <>
      <Head>
        <title>Recommendations — Live Portfolio Simulator</title>
      </Head>
      <Nav />
      <main id="main-content" className="container">
        <h1 className="page-title reveal">Recommendations</h1>
        <p className="lede reveal" style={{ "--reveal-delay": "60ms" }}>
          Fixed-threshold checks against your real holdings from{" "}
          <a href="/" style={{ fontWeight: 600, textDecoration: "underline" }}>
            My Portfolio
          </a>
          : position concentration, sector concentration, position count, and realized volatility. Rule-based by
          design for now, not a trained or fitted model — see the note below each flag for the actual threshold.
        </p>

        {holdings.length === 0 && (
          <Card className="reveal">
            <p style={{ fontSize: 13, color: "var(--muted)", margin: 0 }}>
              No holdings saved in this browser yet. Add positions on{" "}
              <a href="/" style={{ fontWeight: 600, textDecoration: "underline" }}>
                My Portfolio
              </a>{" "}
              first.
            </p>
          </Card>
        )}

        {error && <div className="down" style={{ fontSize: 13, marginBottom: 16 }}>Couldn&apos;t run the check: {error}</div>}

        {data && !error && (
          <>
            <div className="reveal" style={{ display: "flex", gap: 28, marginBottom: 20 }}>
              <div>
                <div className="eyebrow">Current value</div>
                <div className="hero-figure" style={{ fontSize: 28 }}>
                  ${data.current_value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </div>
              </div>
              <div>
                <div className="eyebrow">Realized volatility (1Y annualized)</div>
                <div className="hero-figure" style={{ fontSize: 28 }}>
                  {data.annualized_vol != null ? `${(data.annualized_vol * 100).toFixed(1)}%` : "—"}
                </div>
              </div>
            </div>

            <div className="card-stack reveal" style={{ "--reveal-delay": "100ms", marginBottom: 28 }}>
              {data.flags.map((f, i) => (
                <Card
                  key={i}
                  style={{
                    borderLeft: `3px solid ${f.severity === "warning" ? "var(--critical)" : "var(--border)"}`,
                  }}
                >
                  <div style={{ fontSize: 13.5, fontWeight: 650, marginBottom: 4 }}>
                    {f.severity === "warning" && <span className="down">⚠ </span>}
                    {f.title}
                  </div>
                  <div style={{ fontSize: 12.5, color: "var(--text-secondary)" }}>{f.detail}</div>
                </Card>
              ))}
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: 16 }}>
              <div>
                <h2 className="eyebrow" style={{ marginBottom: 8 }}>
                  By position
                </h2>
                <Card className="reveal" style={{ padding: "4px 16px" }}>
                  <table className="table">
                    <tbody>
                      {Object.entries(data.current_weights)
                        .sort((a, b) => b[1] - a[1])
                        .map(([ticker, w]) => (
                          <tr key={ticker}>
                            <td style={{ fontWeight: 600 }}>{ticker}</td>
                            <td className="num">{(w * 100).toFixed(1)}%</td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </Card>
              </div>
              <div>
                <h2 className="eyebrow" style={{ marginBottom: 8 }}>
                  By sector
                </h2>
                <Card className="reveal" style={{ padding: "4px 16px" }}>
                  <table className="table">
                    <tbody>
                      {Object.entries(data.sector_weights).map(([sector, w]) => (
                        <tr key={sector}>
                          <td>{sector}</td>
                          <td className="num">{(w * 100).toFixed(1)}%</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </Card>
              </div>
            </div>
          </>
        )}

        {loading && !data && (
          <Card>
            <div className="skeleton" style={{ height: 18, marginBottom: 10 }} />
            <div className="skeleton" style={{ height: 18, marginBottom: 10 }} />
            <div className="skeleton" style={{ height: 18 }} />
          </Card>
        )}
      </main>
    </>
  );
}
