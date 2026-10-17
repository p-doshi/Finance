import { useMemo, useRef, useState } from "react";

const STORAGE_KEY = "pps_holdings_v1";
const TICKER_RE = /^[A-Za-z0-9.-]{1,10}$/;
const MAX_SUGGESTIONS = 8;

// Real position data is personal financial information. This never leaves
// the browser: no server, no database, no git -- saved to localStorage
// only, which is why it's scoped to this device/browser rather than a real
// account (there's no account system here to sync it through). Read the
// web/README section this ships with for the tradeoff and the upgrade
// path if cross-device persistence is ever wanted.
export function loadHoldings() {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function saveHoldings(rows) {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(rows));
  } catch {
    // private browsing / storage disabled -- editing still works for the
    // session, it just won't persist across a reload
  }
}

const fmtMoney = (n) => `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

export default function HoldingsEditor({ rows, onChange, quotes, quotesLoading }) {
  const [draft, setDraft] = useState({ ticker: "", shares: "" });
  const [draftError, setDraftError] = useState(null);
  const [universe, setUniverse] = useState(null);
  const [suggestOpen, setSuggestOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const fetchedUniverse = useRef(false);
  const sharesInputRef = useRef(null);

  // Lazy: only fetch the ~4,000-row market snapshot (same /api/universe as
  // the Explore page) once the ticker field is actually touched, not on
  // every page load.
  const ensureUniverseLoaded = () => {
    if (fetchedUniverse.current) return;
    fetchedUniverse.current = true;
    fetch("/api/universe")
      .then((r) => r.json())
      .then((json) => {
        if (Array.isArray(json.rows)) setUniverse(json.rows);
      })
      .catch((e) => console.error(`universe fetch for autocomplete failed: ${e}`));
  };

  const suggestions = useMemo(() => {
    const q = draft.ticker.trim().toUpperCase();
    if (!q || !universe) return [];
    const held = new Set(rows.map((r) => r.ticker));
    const starts = universe.filter((r) => !held.has(r.ticker) && r.ticker.startsWith(q));
    const contains = universe.filter(
      (r) => !held.has(r.ticker) && !r.ticker.startsWith(q) && r.name.toUpperCase().includes(q)
    );
    return [...starts, ...contains].slice(0, MAX_SUGGESTIONS);
  }, [draft.ticker, universe, rows]);

  const update = (next) => {
    onChange(next);
    saveHoldings(next);
  };

  const pickSuggestion = (row) => {
    setDraft((d) => ({ ...d, ticker: row.ticker }));
    setSuggestOpen(false);
    setActiveIndex(-1);
    sharesInputRef.current?.focus();
  };

  const addRow = () => {
    const ticker = draft.ticker.trim().toUpperCase();
    const shares = Number(draft.shares);
    if (!TICKER_RE.test(ticker)) {
      setDraftError("Enter a valid ticker (e.g. AAPL, RY)");
      return;
    }
    if (!(shares > 0)) {
      setDraftError("Shares must be a positive number");
      return;
    }
    if (rows.some((r) => r.ticker === ticker)) {
      setDraftError(`${ticker} is already in your holdings -- edit its shares instead`);
      return;
    }
    setDraftError(null);
    update([...rows, { ticker, shares }]);
    setDraft({ ticker: "", shares: "" });
    setSuggestOpen(false);
    setActiveIndex(-1);
  };

  const handleTickerKeyDown = (e) => {
    if (suggestOpen && suggestions.length > 0) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setActiveIndex((i) => Math.min(i + 1, suggestions.length - 1));
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setActiveIndex((i) => Math.max(i - 1, 0));
        return;
      }
      if (e.key === "Escape") {
        setSuggestOpen(false);
        setActiveIndex(-1);
        return;
      }
      if (e.key === "Enter" && activeIndex >= 0) {
        e.preventDefault();
        pickSuggestion(suggestions[activeIndex]);
        return;
      }
    }
    if (e.key === "Enter") addRow();
  };

  const removeRow = (ticker) => update(rows.filter((r) => r.ticker !== ticker));
  const editShares = (ticker, shares) =>
    update(rows.map((r) => (r.ticker === ticker ? { ...r, shares } : r)));

  const withPrices = rows.map((r) => {
    const q = quotes?.[r.ticker];
    const price = q?.price ?? null;
    const value = price != null ? price * r.shares : null;
    return { ...r, price, value, dayChangePct: q?.dayChangePct ?? null };
  });
  const totalValue = withPrices.reduce((sum, r) => sum + (r.value ?? 0), 0);
  const allPriced = withPrices.length > 0 && withPrices.every((r) => r.value != null);

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 14 }}>
        <div>
          <div className="eyebrow">Total value</div>
          {rows.length === 0 ? (
            <div style={{ fontSize: 14, color: "var(--muted)", marginTop: 4 }}>No positions yet -- add one below.</div>
          ) : allPriced ? (
            <div className="hero-figure" style={{ fontSize: 32 }}>{fmtMoney(totalValue)}</div>
          ) : (
            <div className="skeleton" style={{ width: 160, height: 32, marginTop: 4 }} />
          )}
        </div>
        <div style={{ fontSize: 11, color: "var(--muted)", textAlign: "right" }}>
          Saved only in this browser
          <br />
          (localStorage, never sent anywhere)
        </div>
      </div>

      {rows.length > 0 && (
        <div className="table-wrap" style={{ marginBottom: 14 }}>
          <table className="table">
            <thead>
              <tr>
                <th>Ticker</th>
                <th className="num">Shares</th>
                <th className="num">Price</th>
                <th className="num">Value</th>
                <th className="num">Weight</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {withPrices.map((r) => (
                <tr key={r.ticker}>
                  <td style={{ fontWeight: 600 }}>{r.ticker}</td>
                  <td className="num">
                    <input
                      className="input"
                      type="number"
                      min="0"
                      step="any"
                      value={r.shares}
                      onChange={(e) => editShares(r.ticker, Math.max(0, Number(e.target.value) || 0))}
                      style={{ width: 90, textAlign: "right", padding: "6px 8px" }}
                    />
                  </td>
                  <td className="num">{r.price != null ? fmtMoney(r.price) : quotesLoading ? "…" : "—"}</td>
                  <td className="num">{r.value != null ? fmtMoney(r.value) : "—"}</td>
                  <td className="num">{allPriced ? `${((r.value / totalValue) * 100).toFixed(1)}%` : "—"}</td>
                  <td>
                    <button className="btn" onClick={() => removeRow(r.ticker)} style={{ padding: "4px 10px" }} aria-label={`Remove ${r.ticker}`}>
                      ×
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div style={{ display: "flex", gap: 8, alignItems: "flex-end", flexWrap: "wrap" }}>
        <label className="field" style={{ position: "relative" }}>
          Ticker
          <input
            className="input"
            type="text"
            placeholder="AAPL"
            autoComplete="off"
            value={draft.ticker}
            onFocus={ensureUniverseLoaded}
            onChange={(e) => {
              setDraft((d) => ({ ...d, ticker: e.target.value }));
              setSuggestOpen(true);
              setActiveIndex(-1);
            }}
            onKeyDown={handleTickerKeyDown}
            onBlur={() => setTimeout(() => setSuggestOpen(false), 120)}
            style={{ width: 100 }}
          />
          {suggestOpen && suggestions.length > 0 && (
            <ul
              role="listbox"
              style={{
                position: "absolute",
                top: "100%",
                left: 0,
                marginTop: 4,
                width: 260,
                maxHeight: 240,
                overflowY: "auto",
                background: "var(--surface-1)",
                border: "1px solid var(--border)",
                borderRadius: 9,
                boxShadow: "0 8px 24px rgba(0,0,0,0.12)",
                listStyle: "none",
                padding: 4,
                margin: 0,
                zIndex: 20,
              }}
            >
              {suggestions.map((row, i) => (
                <li
                  key={row.ticker}
                  role="option"
                  aria-selected={i === activeIndex}
                  onMouseDown={(e) => {
                    e.preventDefault(); // fires before the input's onBlur
                    pickSuggestion(row);
                  }}
                  onMouseEnter={() => setActiveIndex(i)}
                  style={{
                    padding: "7px 10px",
                    borderRadius: 6,
                    cursor: "pointer",
                    background: i === activeIndex ? "var(--surface-2)" : "transparent",
                    display: "flex",
                    justifyContent: "space-between",
                    gap: 10,
                    fontSize: 12.5,
                  }}
                >
                  <span style={{ fontWeight: 650 }}>{row.ticker}</span>
                  <span
                    style={{
                      color: "var(--muted)",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                      textAlign: "right",
                    }}
                  >
                    {row.name}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </label>
        <label className="field">
          Shares
          <input
            ref={sharesInputRef}
            className="input"
            type="number"
            min="0"
            step="any"
            placeholder="10"
            value={draft.shares}
            onChange={(e) => setDraft((d) => ({ ...d, shares: e.target.value }))}
            onKeyDown={(e) => e.key === "Enter" && addRow()}
            style={{ width: 100 }}
          />
        </label>
        <button className="btn" onClick={addRow}>
          Add position
        </button>
      </div>
      {draftError && (
        <div className="down" style={{ fontSize: 12, marginTop: 8 }}>
          {draftError}
        </div>
      )}
    </div>
  );
}
