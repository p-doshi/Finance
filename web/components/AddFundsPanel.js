import { useEffect, useState } from "react";
import { formatMoney } from "../lib/currency";

// Wealthsimple-style "just add money": computes a concrete whole-share buy
// plan that puts new cash into your existing positions in their current
// proportions. Deliberately NOT a what-if comparison across strategies --
// that's ForecastPanel below. This answers a narrower, more mechanical
// question: "I'm adding $X, what do I actually buy to keep the same
// split?" Reuses decision.trade_ticket, the same whole-share trade-ticket
// logic the rest of this project already uses and tests.
export default function AddFundsPanel({ holdings, currency, fxRate }) {
  const [amount, setAmount] = useState(100);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const holdingsKey = (holdings || []).map((h) => `${h.ticker}:${h.shares}`).join(",");

  useEffect(() => {
    setResult(null);
    if (!holdings || holdings.length === 0) return;
    let cancelled = false;
    const timer = setTimeout(() => {
      setLoading(true);
      setError(null);
      const holdingsObj = Object.fromEntries(holdings.map((h) => [h.ticker, h.shares]));
      fetch("/api/add-funds", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ holdings: holdingsObj, add_amount: amount }),
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
  }, [holdingsKey, amount]);

  if (!holdings || holdings.length === 0) {
    return <p style={{ color: "var(--muted)", fontSize: 13 }}>Add at least one position above to plan a deposit.</p>;
  }

  const money = (v) => formatMoney(v, currency, fxRate);

  return (
    <div>
      <label className="field" style={{ marginBottom: 16, maxWidth: 160 }}>
        Amount to add ({currency})
        <input
          className="input"
          type="number"
          min="0"
          step="10"
          value={currency === "CAD" && fxRate ? Math.round(amount * fxRate) : amount}
          onChange={(e) => {
            const typed = Math.max(0, Number(e.target.value) || 0);
            setAmount(currency === "CAD" && fxRate ? typed / fxRate : typed);
          }}
        />
      </label>

      {error && <div className="down" style={{ fontSize: 13, marginBottom: 12 }}>Couldn&apos;t plan this deposit: {error}</div>}

      {result && !error && (
        <>
          {result.trades.length === 0 ? (
            <p style={{ fontSize: 13, color: "var(--muted)" }}>
              {money(amount)} split across your current weights isn&apos;t enough to buy a full share of any
              position yet -- try a larger amount.
            </p>
          ) : (
            <div className="table-wrap" style={{ marginBottom: 12 }}>
              <table className="table">
                <thead>
                  <tr>
                    <th>Ticker</th>
                    <th className="num">Buy</th>
                    <th className="num">Price</th>
                    <th className="num">Cost</th>
                  </tr>
                </thead>
                <tbody>
                  {result.trades.map((t) => (
                    <tr key={t.ticker}>
                      <td style={{ fontWeight: 600 }}>{t.ticker}</td>
                      <td className="num">{t.shares}</td>
                      <td className="num">{money(t.price)}</td>
                      <td className="num">{money(t.est_value)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p style={{ fontSize: 12.5, color: "var(--text-secondary)" }}>
            Current value {money(result.current_value)} + {money(result.add_amount)} added ={" "}
            {money(result.total_value_after)} total, keeping the same split as today. {money(result.cash_after)} left
            uninvested (can&apos;t buy fractional shares).
          </p>
        </>
      )}

      {loading && !result && <div className="skeleton" style={{ width: "100%", height: 120, borderRadius: 14 }} />}
    </div>
  );
}
