import { useImperativeHandle, useMemo, useRef, useState, forwardRef } from "react";

const MAX_SUGGESTIONS = 8;

// Shared ticker-search input: lazy-loads the same ~4,000-row /api/universe
// snapshot Explore uses, matches ticker-prefix first then name-substring,
// shown as a keyboard-navigable dropdown. Used by HoldingsEditor (pick a
// ticker, then enter shares) and Strategy Lab's ticker picker (pick a
// ticker, add it to the backtest list) -- same interaction, different
// "what happens when you pick one" callback.
const TickerAutocomplete = forwardRef(function TickerAutocomplete(
  { value, onChange, onPick, onSubmit, excludeTickers = [], placeholder = "AAPL", width = 100 },
  ref
) {
  const [universe, setUniverse] = useState(null);
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const fetchedUniverse = useRef(false);
  const inputRef = useRef(null);

  useImperativeHandle(ref, () => ({ focus: () => inputRef.current?.focus() }));

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

  const excludeSet = useMemo(() => new Set(excludeTickers), [excludeTickers]);
  const suggestions = useMemo(() => {
    const q = value.trim().toUpperCase();
    if (!q || !universe) return [];
    const starts = universe.filter((r) => !excludeSet.has(r.ticker) && r.ticker.startsWith(q));
    const contains = universe.filter(
      (r) => !excludeSet.has(r.ticker) && !r.ticker.startsWith(q) && r.name.toUpperCase().includes(q)
    );
    return [...starts, ...contains].slice(0, MAX_SUGGESTIONS);
  }, [value, universe, excludeSet]);

  const pick = (row) => {
    setOpen(false);
    setActiveIndex(-1);
    onPick(row);
  };

  const handleKeyDown = (e) => {
    if (open && suggestions.length > 0) {
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
        setOpen(false);
        setActiveIndex(-1);
        return;
      }
      if (e.key === "Enter" && activeIndex >= 0) {
        e.preventDefault();
        pick(suggestions[activeIndex]);
        return;
      }
    }
    if (e.key === "Enter") onSubmit?.();
  };

  return (
    <label className="field" style={{ position: "relative" }}>
      Ticker
      <input
        ref={inputRef}
        className="input"
        type="text"
        placeholder={placeholder}
        autoComplete="off"
        value={value}
        onFocus={ensureUniverseLoaded}
        onChange={(e) => {
          onChange(e.target.value);
          setOpen(true);
          setActiveIndex(-1);
        }}
        onKeyDown={handleKeyDown}
        onBlur={() => setTimeout(() => setOpen(false), 120)}
        style={{ width }}
      />
      {open && suggestions.length > 0 && (
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
                pick(row);
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
  );
});

export default TickerAutocomplete;
