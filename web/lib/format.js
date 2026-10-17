// Shared display formatters for market-snapshot fields (market cap,
// volume, day change) -- used by Explore and Underdogs, both of which
// render the same /api/universe-shaped rows.
export const fmtCap = (n) => {
  if (n == null) return "—";
  if (n >= 1e12) return `$${(n / 1e12).toFixed(2)}T`;
  if (n >= 1e9) return `$${(n / 1e9).toFixed(2)}B`;
  if (n >= 1e6) return `$${(n / 1e6).toFixed(0)}M`;
  return `$${n.toLocaleString()}`;
};

export const fmtVolume = (n) => {
  if (n == null) return "—";
  if (n >= 1e9) return `${(n / 1e9).toFixed(2)}B`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(0)}K`;
  return `${n}`;
};

export const fmtChange = (pct) => (pct != null ? `${pct >= 0 ? "+" : ""}${pct.toFixed(2)}%` : "—");
