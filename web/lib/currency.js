// Every dollar figure computed in this app (holdings value, forecasts,
// trade tickets) is in USD -- that's what stockanalysis.com/Yahoo report
// prices in for the tickers this project fetches, and nothing about the
// underlying math changes with display currency. This is purely a
// presentation-layer conversion: multiply by a live USD/CAD rate
// (pages/api/fx.js) when the viewer wants CAD, format either way.
export function convert(usdAmount, currency, fxRate) {
  if (usdAmount == null) return null;
  return currency === "CAD" && fxRate ? usdAmount * fxRate : usdAmount;
}

export function formatMoney(usdAmount, currency, fxRate, opts = {}) {
  const amount = convert(usdAmount, currency, fxRate);
  if (amount == null) return "—";
  const { decimals = 2 } = opts;
  const prefix = currency === "CAD" && fxRate ? "C$" : "$";
  return `${prefix}${amount.toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}`;
}
