import { useEffect, useState } from "react";
import ForecastChart from "./ForecastChart";

const METHOD_LABELS = {
  risk_parity: "Risk Parity",
  hrp: "Hierarchical Risk Parity",
  min_variance: "Min Variance",
  max_sharpe: "Max Sharpe",
  equal_weight: "Equal Weight",
};
const HORIZONS = { "3M": 63, "6M": 126, "1Y": 252 };
const fmtMoney = (n) => `$${Math.round(n).toLocaleString()}`;

// Answers "if I add $X next month, should I split it the same way my
// current holdings are split, or re-optimize?" -- by running the
// block-bootstrap forecast (research.forecast) under both allocations over
// the same simulated future and showing both bands side by side. This is a
// simulation under a stationarity assumption (the trailing return
// distribution continuing), not a prediction -- the uncertainty band is
// the honest part of the answer, not a caveat to skip past.
export default function ForecastPanel({ holdings }) {
  const [amount, setAmount] = useState(100);
  const [compareMethod, setCompareMethod] = useState("risk_parity");
  const [horizonKey, setHorizonKey] = useState("1Y");
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  // holdings keyed to a stable string so editing a shares field (which
  // creates a new array reference per keystroke) doesn't retrigger this on
  // every digit typed -- only when the actual ticker/shares values settle.
  const holdingsKey = (holdings || []).map((h) => `${h.ticker}:${h.shares}`).join(",");

  useEffect(() => {
    // cleared synchronously (not just on response) so a changed compareMethod
    // never renders stale `result` -- the previous result's scenarios dict
    // doesn't have the newly-selected method's p10/p50/p90 yet, and spreading
    // that missing data into ForecastChart crashed it
    setResult(null);
    if (!holdings || holdings.length === 0) {
      return;
    }
    let cancelled = false;
    // debounced: each run recomputes 2,000 bootstrap paths per scenario
    // against freshly-fetched price history, not worth firing per keystroke
    const timer = setTimeout(() => {
      setLoading(true);
      setError(null);
      const holdingsObj = Object.fromEntries(holdings.map((h) => [h.ticker, h.shares]));
      fetch("/api/forecast", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          holdings: holdingsObj,
          add_amount: amount,
          distributions: ["same", compareMethod],
          horizon_days: HORIZONS[horizonKey],
        }),
      })
        .then(async (r) => {
          const json = await r.json();
          if (cancelled) return;
          if (!r.ok) setError(json.detail || json.error || `HTTP ${r.status}`);
          else setResult(json);
        })
        .catch((e) => !cancelled && setError(String(e)))
        .finally(() => !cancelled && setLoading(false));
    }, 500);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [holdingsKey, amount, compareMethod, horizonKey]);

  if (!holdings || holdings.length === 0) {
    return <p style={{ color: "var(--muted)", fontSize: 13 }}>Add at least one position above to forecast a new contribution.</p>;
  }

  const sameFinal = result?.scenarios?.same?.p50?.slice(-1)[0];
  const altFinal = result?.scenarios?.[compareMethod]?.p50?.slice(-1)[0];
  const diff = sameFinal != null && altFinal != null ? altFinal - sameFinal : null;

  return (
    <div>
      <div style={{ display: "flex", gap: 14, flexWrap: "wrap", marginBottom: 16 }}>
        <label className="field">
          Amount to add next month
          <input
            className="input"
            type="number"
            min="0"
            step="10"
            value={amount}
            onChange={(e) => setAmount(Math.max(0, Number(e.target.value) || 0))}
            style={{ width: 110 }}
          />
        </label>
        <label className="field">
          Compare &quot;same split&quot; against
          <select className="select" value={compareMethod} onChange={(e) => setCompareMethod(e.target.value)}>
            {Object.entries(METHOD_LABELS).map(([k, label]) => (
              <option key={k} value={k}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          Horizon
          <select className="select" value={horizonKey} onChange={(e) => setHorizonKey(e.target.value)}>
            {Object.keys(HORIZONS).map((h) => (
              <option key={h} value={h}>
                {h}
              </option>
            ))}
          </select>
        </label>
      </div>

      {error && <div className="down" style={{ fontSize: 13, marginBottom: 12 }}>Couldn&apos;t run the forecast: {error}</div>}

      {result && !error && (
        <>
          <ForecastChart
            dates={result.dates}
            scenarios={[
              { key: "same", label: "Same split as today", color: "var(--text-secondary)", ...result.scenarios.same },
              { key: compareMethod, label: `Re-optimized: ${METHOD_LABELS[compareMethod]}`, color: `var(--m-${compareMethod})`, ...result.scenarios[compareMethod] },
            ]}
          />
          <p style={{ fontSize: 11.5, color: "var(--muted)", margin: "10px 0 0" }}>
            Shaded band = 10th-90th percentile across {result.n_sims.toLocaleString()} simulated paths, built by
            block-bootstrap resampling {result.block_size}-day blocks of {result.tickers.join(", ")}&apos;s trailing
            2-year daily returns from {result.as_of} forward. This assumes the recent past&apos;s return distribution
            continues -- it is a simulation under that assumption, not a forecast of what will actually happen.
          </p>
          {diff != null && (
            <p style={{ fontSize: 13.5, marginTop: 12 }}>
              Median outcome after {horizonKey} on {fmtMoney(result.total_initial)} total: keeping today&apos;s split
              lands near <b>{fmtMoney(sameFinal)}</b>; re-optimizing to {METHOD_LABELS[compareMethod]} lands near{" "}
              <b>{fmtMoney(altFinal)}</b> ({diff >= 0 ? "+" : ""}
              {fmtMoney(diff)}). Both numbers are the center of a wide range, not a guarantee -- see the band above.
            </p>
          )}
        </>
      )}

      {loading && !result && (
        <div className="skeleton" style={{ width: "100%", height: 280, borderRadius: 14 }} />
      )}
    </div>
  );
}
