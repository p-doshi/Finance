import { useEffect, useMemo, useState } from "react";
import Head from "next/head";
import staticBacktest from "../data/backtest.json";
import EquityChart from "../components/EquityChart";
import Nav from "../components/Nav";
import Card from "../components/Card";
import TickerAutocomplete from "../components/TickerAutocomplete";

const MIN_TICKERS = 2;
const MAX_TICKERS = 20;

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

// This is deliberately generic, not personalized: a fixed 12-name research
// watchlist and a round starting number, used to validate the methodology
// (see docs/methodology.md). Your actual holdings and their forecast live
// on My Portfolio -- this page never reads or writes that data.
export default function Simulator() {
  const [method, setMethod] = useState("risk_parity");
  const [amount, setAmount] = useState(10_000);
  const [portfolio, setPortfolio] = useState(INITIAL_PORTFOLIO);
  const [quotes, setQuotes] = useState(null);
  const [fetchedAt, setFetchedAt] = useState(null);
  const [error, setError] = useState(null);
  // null = "use the default 12-name research watchlist"; once the visitor
  // edits the list, this holds their actual chosen tickers instead.
  const [customTickers, setCustomTickers] = useState(null);
  const [tickerDraft, setTickerDraft] = useState("");
  const [portfolioError, setPortfolioError] = useState(null);

  const tickersKey = portfolio.tickers.join(",");

  useEffect(() => {
    let cancelled = false;
    async function poll() {
      try {
        const res = await fetch(`/api/quotes?tickers=${encodeURIComponent(tickersKey)}`);
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
  }, [tickersKey]);

  useEffect(() => {
    let cancelled = false;
    async function loadMethod() {
      try {
        const qs = customTickers ? `&tickers=${encodeURIComponent(customTickers.join(","))}` : "";
        const res = await fetch(`/api/portfolio?method=${method}${qs}`);
        const json = await res.json();
        if (cancelled) return;
        if (!res.ok) {
          setPortfolioError(json.detail || json.error || `HTTP ${res.status}`);
        } else {
          setPortfolio(json);
          setPortfolioError(null);
        }
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
  }, [method, customTickers]);

  const addTicker = (ticker) => {
    const next = [...new Set([...portfolio.tickers, ticker.toUpperCase()])];
    if (next.length > MAX_TICKERS) return;
    setCustomTickers(next);
    setTickerDraft("");
  };
  const removeTicker = (ticker) => {
    const next = portfolio.tickers.filter((t) => t !== ticker);
    if (next.length < MIN_TICKERS) return;
    setCustomTickers(next);
  };

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
        <title>Strategy Lab — Live Portfolio Simulator</title>
      </Head>
      <Nav />
      <main id="main-content" className="container">
        <h1 className="page-title reveal">Strategy Lab</h1>
        <p className="lede reveal" style={{ "--reveal-delay": "60ms" }}>
          A backward-looking question, answered rigorously: how would these weighting methods actually have performed
          on these names, out-of-sample? A real walk-forward backtest ({data.equity_curve[0].date} to{" "}
          {portfolio.as_of_date}), re-estimated and rebalanced on a schedule, never peeking at future data. The{" "}
          <b className="down">LIVE</b> point extends it with real-time quotes against the last-rebalanced weights.
          This is deliberately not about your real holdings or a forward prediction — for that, see{" "}
          <a href="/" style={{ fontWeight: 600, textDecoration: "underline" }}>
            My Portfolio
          </a>
          &apos;s forecast panel instead.
        </p>

        <div className="reveal" style={{ "--reveal-delay": "90ms", marginBottom: 16 }}>
          <div className="eyebrow" style={{ marginBottom: 8 }}>
            Tickers ({portfolio.tickers.length})
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 10 }}>
            {portfolio.tickers.map((t) => (
              <span
                key={t}
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 6,
                  fontSize: 12.5,
                  fontWeight: 600,
                  padding: "4px 6px 4px 10px",
                  borderRadius: 20,
                  background: "var(--surface-2)",
                }}
              >
                {t}
                <button
                  onClick={() => removeTicker(t)}
                  disabled={portfolio.tickers.length <= MIN_TICKERS}
                  aria-label={`Remove ${t}`}
                  style={{
                    border: "none",
                    background: "none",
                    cursor: portfolio.tickers.length <= MIN_TICKERS ? "default" : "pointer",
                    color: "var(--muted)",
                    fontSize: 14,
                    lineHeight: 1,
                    padding: 0,
                  }}
                >
                  ×
                </button>
              </span>
            ))}
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "flex-end", flexWrap: "wrap" }}>
            <TickerAutocomplete
              value={tickerDraft}
              onChange={setTickerDraft}
              onPick={(row) => addTicker(row.ticker)}
              onSubmit={() => tickerDraft.trim() && addTicker(tickerDraft)}
              excludeTickers={portfolio.tickers}
              placeholder="Add a ticker"
              width={140}
            />
            {customTickers && (
              <button className="btn" onClick={() => setCustomTickers(null)}>
                Reset to research watchlist
              </button>
            )}
          </div>
          {portfolioError && (
            <div className="down" style={{ fontSize: 12.5, marginTop: 8 }}>
              {portfolioError}
            </div>
          )}
        </div>

        <div className="reveal" style={{ "--reveal-delay": "100ms", display: "flex", gap: 14, flexWrap: "wrap", marginBottom: 20 }}>
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

        <Card className="reveal" style={{ "--reveal-delay": "140ms", marginBottom: 16 }}>
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
            {fetchedAt && <span className="live-dot" style={{ marginRight: 6, verticalAlign: "middle" }} />}
            {fetchedAt ? `Quotes as of ${new Date(fetchedAt).toLocaleTimeString()}` : "Fetching live quotes…"}
            {error && <span className="down"> · some quotes unavailable</span>}
            {portfolio.source === "static" && (
              <span> · backtest from a cached snapshot (live recompute unavailable right now)</span>
            )}
            {portfolio.window_days && portfolio.window_days < 756 && (
              <span> · estimation window shortened to {portfolio.window_days} trading days (less overlapping history across these tickers than the default 3 years)</span>
            )}
          </div>
        </Card>

        <Card className="reveal" style={{ "--reveal-delay": "180ms", marginBottom: 16 }}>
          <EquityChart curve={scaledCurve} liveValue={liveValue} color={`var(--m-${method})`} />
        </Card>

        <Card className="reveal" style={{ "--reveal-delay": "220ms", padding: "6px 16px" }}>
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
