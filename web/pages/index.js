import { useEffect, useState } from "react";
import Head from "next/head";
import Nav from "../components/Nav";
import Card from "../components/Card";
import HoldingsEditor, { loadHoldings } from "../components/HoldingsEditor";
import ForecastPanel from "../components/ForecastPanel";

const POLL_MS = 30_000;

// Entirely personalized: no fixed watchlist, no hardcoded starting amount.
// Everything here is read from (and only from) this browser's saved
// holdings. The fixed-watchlist strategy demo lives on /simulator instead
// -- see that page's own note on why it's kept separate.
export default function Home() {
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

  return (
    <>
      <Head>
        <title>My Portfolio — Live Portfolio Simulator</title>
      </Head>
      <Nav />
      <main id="main-content" className="container">
        <h1 className="page-title">My Portfolio</h1>
        <p className="lede">
          Your real positions, priced live from this browser&apos;s saved holdings — not a brokerage connection, and
          nothing here ever places an order. Looking for the fixed-watchlist strategy demo instead? That&apos;s on{" "}
          <a href="/simulator" style={{ fontWeight: 600, textDecoration: "underline" }}>
            Strategy Lab
          </a>
          .
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
      </main>
    </>
  );
}
