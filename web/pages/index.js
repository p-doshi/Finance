import { useEffect, useMemo, useState } from "react";
import Head from "next/head";
import backtest from "../data/backtest.json";
import EquityChart from "../components/EquityChart";

const METHOD_LABELS = {
  equal_weight: "Equal Weight",
  risk_parity: "Risk Parity",
  hrp: "Hierarchical Risk Parity",
  min_variance: "Min Variance",
  max_sharpe: "Max Sharpe",
};

const POLL_MS = 30_000;

export default function Home() {
  const [method, setMethod] = useState("risk_parity");
  const [amount, setAmount] = useState(10_000);
  const [quotes, setQuotes] = useState(null);
  const [fetchedAt, setFetchedAt] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    async function poll() {
      try {
        const res = await fetch("/api/quotes");
        const json = await res.json();
        if (cancelled) return;
        setQuotes(json.quotes);
        setFetchedAt(json.fetchedAt);
        setError(Object.keys(json.errors || {}).length > 0 ? json.errors : null);
      } catch (e) {
        if (!cancelled) setError({ _fetch: String(e) });
      }
    }
    poll();
    const id = setInterval(poll, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  const data = backtest.methods[method];
  const scale = amount / 10_000;
  const scaledCurve = useMemo(
    () => data.equity_curve.map((p) => ({ date: p.date, value: p.value * scale })),
    [data, scale]
  );
  const baseValue = data.last_curve_value * scale;

  const liveMultiplier = useMemo(() => {
    if (!quotes) return null;
    let mult = 0;
    let missing = false;
    for (const ticker of backtest.tickers) {
      const w = data.final_weights[ticker] || 0;
      const lastKnown = backtest.last_known_prices[ticker];
      const live = quotes[ticker]?.price;
      if (live == null) {
        missing = true;
        continue;
      }
      mult += w * (live / lastKnown);
    }
    return missing ? null : mult;
  }, [quotes, data]);

  const liveValue = liveMultiplier != null ? baseValue * liveMultiplier : null;
  const dollarChange = liveValue != null ? liveValue - baseValue : null;
  const pctChangeSinceBacktest = liveValue != null ? (liveValue / baseValue - 1) * 100 : null;
  const totalGainPct = liveValue != null ? (liveValue / amount - 1) * 100 : null;

  return (
    <>
      <Head>
        <title>Live Portfolio Simulator</title>
      </Head>
      <main style={{ maxWidth: 820, margin: "0 auto", padding: "24px 16px 48px" }}>
        <h1 style={{ fontSize: 20, fontWeight: 650, margin: "0 0 4px" }}>Live Portfolio Simulator</h1>
        <p style={{ color: "var(--text-secondary)", fontSize: 13, margin: "0 0 20px", maxWidth: "64ch" }}>
          The curve is a real, walk-forward out-of-sample backtest ({backtest.methods.risk_parity.equity_curve[0].date}{" "}
          to {backtest.as_of_date}) — see the methodology write-up for how it was built and validated. The{" "}
          <b style={{ color: "var(--critical)" }}>LIVE</b> point extends it using real-time quotes applied against the
          strategy&apos;s last-rebalanced weights, polled every 30s. Simulated money, not a real brokerage position —
          this project never submits an order anywhere.
        </p>

        <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginBottom: 20 }}>
          <label style={{ fontSize: 13 }}>
            Strategy{" "}
            <select
              value={method}
              onChange={(e) => setMethod(e.target.value)}
              style={{ fontSize: 13, padding: "4px 8px", borderRadius: 6 }}
            >
              {Object.keys(METHOD_LABELS).map((m) => (
                <option key={m} value={m}>
                  {METHOD_LABELS[m]}
                </option>
              ))}
            </select>
          </label>
          <label style={{ fontSize: 13 }}>
            Initial investment{" "}
            <input
              type="number"
              min="100"
              step="100"
              value={amount}
              onChange={(e) => setAmount(Math.max(100, Number(e.target.value) || 0))}
              style={{ fontSize: 13, padding: "4px 8px", borderRadius: 6, width: 110 }}
            />
          </label>
        </div>

        <div
          style={{
            background: "var(--surface-1)",
            border: "1px solid var(--border)",
            borderRadius: 12,
            padding: "18px 20px",
            marginBottom: 20,
          }}
        >
          <div style={{ fontSize: 11, color: "var(--muted)", textTransform: "uppercase" }}>Live value</div>
          <div style={{ fontSize: 32, fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>
            {liveValue != null
              ? `$${liveValue.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
              : "loading…"}
          </div>
          {liveValue != null && (
            <div style={{ fontSize: 13, color: dollarChange >= 0 ? "var(--good)" : "var(--critical)" }}>
              {dollarChange >= 0 ? "+" : ""}
              {dollarChange.toLocaleString(undefined, { maximumFractionDigits: 2 })} ({pctChangeSinceBacktest >= 0 ? "+" : ""}
              {pctChangeSinceBacktest.toFixed(2)}% since {backtest.as_of_date}) · total gain {totalGainPct >= 0 ? "+" : ""}
              {totalGainPct.toFixed(1)}% since {backtest.methods.risk_parity.equity_curve[0].date}
            </div>
          )}
          <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 6 }}>
            {fetchedAt ? `Quotes as of ${new Date(fetchedAt).toLocaleTimeString()}` : "Fetching live quotes…"}
            {error && <span style={{ color: "var(--critical)" }}> · some quotes unavailable</span>}
          </div>
        </div>

        <div
          style={{
            background: "var(--surface-1)",
            border: "1px solid var(--border)",
            borderRadius: 12,
            padding: 16,
            marginBottom: 20,
          }}
        >
          <EquityChart curve={scaledCurve} liveValue={liveValue} color={`var(--m-${method})`} />
        </div>

        <div style={{ background: "var(--surface-1)", border: "1px solid var(--border)", borderRadius: 12, padding: "8px 16px" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12.5 }}>
            <thead>
              <tr style={{ color: "var(--muted)", textTransform: "uppercase", fontSize: 11 }}>
                <th style={{ textAlign: "left", padding: "8px 4px" }}>Ticker</th>
                <th style={{ textAlign: "right", padding: "8px 4px" }}>Weight</th>
                <th style={{ textAlign: "right", padding: "8px 4px" }}>Live price</th>
                <th style={{ textAlign: "right", padding: "8px 4px" }}>Day change</th>
              </tr>
            </thead>
            <tbody>
              {backtest.tickers.map((t) => {
                const q = quotes?.[t];
                return (
                  <tr key={t} style={{ borderTop: "1px solid var(--grid)" }}>
                    <td style={{ padding: "8px 4px", fontWeight: 600 }}>{t}</td>
                    <td style={{ padding: "8px 4px", textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                      {((data.final_weights[t] || 0) * 100).toFixed(1)}%
                    </td>
                    <td style={{ padding: "8px 4px", textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                      {q ? `$${q.price.toFixed(2)}` : "…"}
                    </td>
                    <td
                      style={{
                        padding: "8px 4px",
                        textAlign: "right",
                        fontVariantNumeric: "tabular-nums",
                        color: q && q.dayChangePct >= 0 ? "var(--good)" : "var(--critical)",
                      }}
                    >
                      {q && q.dayChangePct != null ? `${q.dayChangePct >= 0 ? "+" : ""}${q.dayChangePct.toFixed(2)}%` : "…"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </main>
    </>
  );
}
