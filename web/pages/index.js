import { useEffect, useState } from "react";
import Head from "next/head";
import Nav from "../components/Nav";
import Card from "../components/Card";
import HoldingsEditor, { loadHoldings } from "../components/HoldingsEditor";
import ForecastPanel from "../components/ForecastPanel";
import AddFundsPanel from "../components/AddFundsPanel";

const POLL_MS = 30_000;

// Entirely personalized: no fixed watchlist, no hardcoded starting amount.
// Everything here is read from (and only from) this browser's saved
// holdings. The fixed-watchlist strategy demo lives on /simulator instead
// -- see that page's own note on why it's kept separate.
export default function Home() {
  const [holdings, setHoldings] = useState([]);
  const [holdingsQuotes, setHoldingsQuotes] = useState(null);
  const [holdingsQuotesLoading, setHoldingsQuotesLoading] = useState(false);
  const [currency, setCurrency] = useState("USD");
  const [fxRate, setFxRate] = useState(null);

  useEffect(() => {
    setHoldings(loadHoldings());
  }, []);

  useEffect(() => {
    fetch("/api/fx")
      .then((r) => r.json())
      .then((json) => json.rate && setFxRate(json.rate))
      .catch((e) => console.error(`fx fetch failed: ${e}`));
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

  return (
    <>
      <Head>
        <title>My Portfolio — Live Portfolio Simulator</title>
      </Head>
      <Nav />
      <main id="main-content" className="container">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16, flexWrap: "wrap" }}>
          <h1 className="page-title reveal">My Portfolio</h1>
          <div className="reveal" style={{ display: "flex", gap: 4 }} role="group" aria-label="Display currency">
            {["USD", "CAD"].map((c) => (
              <button
                key={c}
                className={`btn${currency === c ? " active" : ""}`}
                onClick={() => setCurrency(c)}
                disabled={c === "CAD" && !fxRate}
                title={c === "CAD" && !fxRate ? "Loading exchange rate…" : undefined}
              >
                {c}
              </button>
            ))}
          </div>
        </div>
        <p className="lede reveal" style={{ "--reveal-delay": "60ms" }}>
          Your real positions, priced live from this browser&apos;s saved holdings — not a brokerage connection, and
          nothing here ever places an order. Looking for the fixed-watchlist strategy demo instead? That&apos;s on{" "}
          <a href="/simulator" style={{ fontWeight: 600, textDecoration: "underline" }}>
            Strategy Lab
          </a>
          .
        </p>

        <Card className="reveal" style={{ "--reveal-delay": "120ms", marginBottom: 16 }}>
          <HoldingsEditor
            rows={holdings}
            onChange={setHoldings}
            quotes={holdingsQuotes}
            quotesLoading={holdingsQuotesLoading}
            currency={currency}
            fxRate={fxRate}
          />
        </Card>

        <h2 className="reveal" style={{ "--reveal-delay": "160ms", fontSize: 16, fontWeight: 650, margin: "32px 0 2px" }}>
          Add funds (keep current split)
        </h2>
        <p className="lede reveal" style={{ "--reveal-delay": "160ms", marginTop: 4, marginBottom: 14 }}>
          Like Wealthsimple&apos;s auto-invest: a concrete whole-share buy plan that puts new cash into your existing
          positions in their current proportions, nothing re-optimized.
        </p>
        <Card className="reveal" style={{ "--reveal-delay": "190ms", marginBottom: 32 }}>
          <AddFundsPanel holdings={holdings} currency={currency} fxRate={fxRate} />
        </Card>

        <h2 className="reveal" style={{ "--reveal-delay": "220ms", fontSize: 16, fontWeight: 650, margin: "0 0 2px" }}>
          Forecast a new contribution
        </h2>
        <p className="lede reveal" style={{ "--reveal-delay": "220ms", marginTop: 4, marginBottom: 14 }}>
          A different question from above: if you add money, does a <i>different</i> split do better long-run than
          today&apos;s, probabilistically?
        </p>
        <Card className="reveal" style={{ "--reveal-delay": "250ms", marginBottom: 32 }}>
          <ForecastPanel holdings={holdings} currency={currency} fxRate={fxRate} />
        </Card>
      </main>
    </>
  );
}
