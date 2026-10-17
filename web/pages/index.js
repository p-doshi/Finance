import { useEffect, useMemo, useState } from "react";
import Head from "next/head";
import staticBacktest from "../data/backtest.json";
import EquityChart from "../components/EquityChart";
import Nav from "../components/Nav";
import Card from "../components/Card";
import HoldingsEditor, { loadHoldings } from "../components/HoldingsEditor";
import ForecastPanel from "../components/ForecastPanel";

const METHOD_LABELS = {
  equal_weight: "Equal Weight",
  risk_parity: "Risk Parity",
  hrp: "Hierarchical Risk Parity",
  min_variance: "Min Variance",
  max_sharpe: "Max Sharpe",
};

const POLL_MS = 30_000;

// Seed state from the static build-time snapshot so the page paints
// instantly; /api/portfolio (proxied to the "app" service, falling back
// to this same snapshot if that call fails) then refreshes it per method.
const INITIAL_PORTFOLIO = {
  tickers: staticBacktest.tickers,
  as_of_date: staticBacktest.as_of_date,
  last_known_prices: staticBacktest.last_known_prices,
  rf: staticBacktest.rf,
  method: "risk_parity",
  data: staticBacktest.methods.risk_parity,
  source: "static",
};

export default function Home() {
  const [method, setMethod] = useState("risk_parity");
  const [amount, setAmount] = useState(10_000);
  const [portfolio, setPortfolio] = useState(INITIAL_PORTFOLIO);
  const [quotes, setQuotes] = useState(null);
  const [fetchedAt, setFetchedAt] = useState(null);
  const [error, setError] = useState(null);

  const [holdings, setHoldings] = useState([]);
  const [holdingsQuotes, setHoldingsQuotes] = useState(null);
  const [holdingsQuotesLoading, setHoldingsQuotesLoading] = useState(false);

  useEffect(() => {
    setHoldings(loadHoldings());
  }, []);

  useEffect(() => {
    if (holdings.length === 0) {
      setHoldingsQuotes(null);
      return;
    }
    let cancelled = false;
    async function poll() {
      setHoldingsQuotesLoading(true);
      try {
        const tickers = holdings.map((h) => h.ticker).join(",");
        const res = await fetch(`/api/quotes?tickers=${encodeURIComponent(tickers)}`);
        const json = await res.json();
        if (!cancelled) setHoldingsQuotes(json.quotes);
      } catch (e) {
        console.error(`holdings quotes fetch failed: ${e}`);
      } finally {
        if (!cancelled) setHoldingsQuotesLoading(false);
      }
    }
    poll();
    const id = setInterval(poll, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [holdings]);

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

  useEffect(() => {
    let cancelled = false;
    async function loadMethod() {
      try {
        const res = await fetch(`/api/portfolio?method=${method}`);
        const json = await res.json();
        if (!cancelled) setPortfolio(json);
      } catch (e) {
        // keep whatever we already had (static seed or a prior method's
        // live data) rather than blanking the page
        console.error(`portfolio fetch failed for ${method}: ${e}`);
      }
    }
    loadMethod();
    return () => {
      cancelled = true;
    };
  }, [method]);

  const data = portfolio.data;
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
    for (const ticker of portfolio.tickers) {
      const w = data.final_weights[ticker] || 0;
      const lastKnown = portfolio.last_known_prices[ticker];
      const live = quotes[ticker]?.price;
      if (live == null) {
        missing = true;
        continue;
      }
      mult += w * (live / lastKnown);
    }
    return missing ? null : mult;
  }, [quotes, data, portfolio]);

  const liveValue = liveMultiplier != null ? baseValue * liveMultiplier : null;
  const dollarChange = liveValue != null ? liveValue - baseValue : null;
  const pctChangeSinceBacktest = liveValue != null ? (liveValue / baseValue - 1) * 100 : null;
  const totalGainPct = liveValue != null ? (liveValue / amount - 1) * 100 : null;

  return (
    <>
      <Head>
        <title>Live Portfolio Simulator</title>
      </Head>
      <Nav />
      <main id="main-content" className="container">
        <h1 className="page-title">My Portfolio</h1>
        <p className="lede">
          Your real positions, priced live from this browser&apos;s saved holdings — not a brokerage connection, and
          nothing here ever places an order. The strategy backtest further down is reference material from this
          project&apos;s research watchlist, shown for context, not your actual holdings.
        </p>

        <Card style={{ marginBottom: 16 }}>
          <HoldingsEditor
            rows={holdings}
            onChange={setHoldings}
            quotes={holdingsQuotes}
            quotesLoading={holdingsQuotesLoading}
          />
        </Card>

        <h2 style={{ fontSize: 16, fontWeight: 650, margin: "32px 0 2px" }}>Forecast a new contribution</h2>
        <p className="lede" style={{ marginTop: 4, marginBottom: 14 }}>
          If you add money next month, does keeping today&apos;s split or re-optimizing it change the outcome enough
          to matter?
        </p>
        <Card style={{ marginBottom: 32 }}>
          <ForecastPanel holdings={holdings} />
        </Card>

        <h2 style={{ fontSize: 16, fontWeight: 650, margin: "0 0 2px" }}>Strategy backtest (reference)</h2>
        <p className="lede" style={{ marginTop: 4 }}>
          The curve is a real, walk-forward out-of-sample backtest ({data.equity_curve[0].date}{" "}
          to {portfolio.as_of_date}) over this project&apos;s 12-name research watchlist — see the methodology
          write-up for how it was built and validated. The <b className="down">LIVE</b> point extends it using
          real-time quotes applied against the strategy&apos;s last-rebalanced weights, polled every 30s. Simulated
          money against a fixed watchlist, not your holdings above.
        </p>

        <div style={{ display: "flex", gap: 14, flexWrap: "wrap", marginBottom: 20 }}>
          <label className="field">
            Strategy
            <select className="select" value={method} onChange={(e) => setMethod(e.target.value)}>
              {Object.keys(METHOD_LABELS).map((m) => (
                <option key={m} value={m}>
                  {METHOD_LABELS[m]}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            Initial investment
            <input
              className="input"
              type="number"
              min="100"
              step="100"
              value={amount}
              onChange={(e) => setAmount(Math.max(100, Number(e.target.value) || 0))}
              style={{ width: 130 }}
            />
          </label>
        </div>

        <Card style={{ marginBottom: 16 }}>
          <div className="eyebrow">Live value</div>
          {liveValue != null ? (
            <>
              <div className="hero-figure">
                ${liveValue.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </div>
              <div className={`${dollarChange >= 0 ? "up" : "down"}`} style={{ fontSize: 13.5, marginTop: 6 }}>
                {dollarChange >= 0 ? "+" : ""}
                {dollarChange.toLocaleString(undefined, { maximumFractionDigits: 2 })} ({pctChangeSinceBacktest >= 0 ? "+" : ""}
                {pctChangeSinceBacktest.toFixed(2)}% since {portfolio.as_of_date}) · total gain {totalGainPct >= 0 ? "+" : ""}
                {totalGainPct.toFixed(1)}% since {data.equity_curve[0].date}
              </div>
            </>
          ) : (
            <>
              <div className="skeleton" style={{ width: 220, height: 40, marginTop: 4 }} />
              <div className="skeleton" style={{ width: 300, height: 14, marginTop: 10 }} />
            </>
          )}
          <div style={{ fontSize: 11.5, color: "var(--muted)", marginTop: 10 }}>
            {fetchedAt ? `Quotes as of ${new Date(fetchedAt).toLocaleTimeString()}` : "Fetching live quotes…"}
            {error && <span className="down"> · some quotes unavailable</span>}
            {portfolio.source === "static" && (
              <span> · backtest from a cached snapshot (live recompute unavailable right now)</span>
            )}
          </div>
        </Card>

        <Card style={{ marginBottom: 16 }}>
          <EquityChart curve={scaledCurve} liveValue={liveValue} color={`var(--m-${method})`} />
        </Card>

        <Card style={{ padding: "6px 16px" }}>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Ticker</th>
                  <th className="num">Weight</th>
                  <th className="num">Live price</th>
                  <th className="num">Day change</th>
                </tr>
              </thead>
              <tbody>
                {portfolio.tickers.map((t) => {
                  const q = quotes?.[t];
                  return (
                    <tr key={t}>
                      <td style={{ fontWeight: 600 }}>{t}</td>
                      <td className="num">{((data.final_weights[t] || 0) * 100).toFixed(1)}%</td>
                      <td className="num">{q ? `$${q.price.toFixed(2)}` : "…"}</td>
                      <td className={`num ${q && q.dayChangePct != null ? (q.dayChangePct >= 0 ? "up" : "down") : ""}`}>
                        {q && q.dayChangePct != null ? `${q.dayChangePct >= 0 ? "+" : ""}${q.dayChangePct.toFixed(2)}%` : "…"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>
      </main>
    </>
  );
}
