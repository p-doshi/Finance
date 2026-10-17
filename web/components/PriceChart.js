import { useState } from "react";

// Plain SVG line chart for a single price series -- same no-library
// approach as EquityChart.js, but without that component's "live point"
// extension and dollar-curve assumptions, which don't apply to a raw
// per-share price history.
export default function PriceChart({ series, color = "var(--m-risk_parity)" }) {
  const [hover, setHover] = useState(null);
  if (!series || series.length === 0) return null;

  const W = 640;
  const H = 280;
  const margin = { top: 16, right: 16, bottom: 32, left: 56 };
  const plotW = W - margin.left - margin.right;
  const plotH = H - margin.top - margin.bottom;

  const values = series.map((p) => p.close);
  const minV = Math.min(...values);
  const maxV = Math.max(...values);
  const pad = (maxV - minV) * 0.08 || maxV * 0.05;
  const yDomain = [minV - pad, maxV + pad];

  const n = series.length;
  const xAt = (i) => margin.left + (i / Math.max(n - 1, 1)) * plotW;
  const yAt = (v) => margin.top + (1 - (v - yDomain[0]) / (yDomain[1] - yDomain[0])) * plotH;

  const linePath = series.map((p, i) => `${i === 0 ? "M" : "L"}${xAt(i).toFixed(1)},${yAt(p.close).toFixed(1)}`).join(" ");
  const rising = series[n - 1].close >= series[0].close;
  const lineColor = color === "auto" ? (rising ? "var(--good)" : "var(--critical)") : color;

  const yTicks = 4;
  const yTickVals = Array.from({ length: yTicks + 1 }, (_, i) => yDomain[0] + (i * (yDomain[1] - yDomain[0])) / yTicks);
  const xTickEvery = Math.max(1, Math.floor(n / 6));

  return (
    <div style={{ position: "relative" }}>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto", display: "block" }}>
        {yTickVals.map((v, i) => (
          <g key={i}>
            <line x1={margin.left} x2={margin.left + plotW} y1={yAt(v)} y2={yAt(v)} stroke="var(--grid)" strokeWidth="1" />
            <text x={margin.left - 8} y={yAt(v) + 3} textAnchor="end" fontSize="10" fill="var(--muted)">
              ${v.toFixed(0)}
            </text>
          </g>
        ))}
        {series.map((p, i) =>
          i % xTickEvery === 0 ? (
            <text key={i} x={xAt(i)} y={margin.top + plotH + 16} textAnchor="middle" fontSize="10" fill="var(--muted)">
              {p.date.slice(0, 7)}
            </text>
          ) : null
        )}
        <path className="chart-line" pathLength="1" d={linePath} fill="none" stroke={lineColor} strokeWidth="2" />
        <rect
          x={margin.left}
          y={margin.top}
          width={plotW}
          height={plotH}
          fill="transparent"
          onMouseMove={(e) => {
            const rect = e.currentTarget.getBoundingClientRect();
            const frac = (e.clientX - rect.left) / rect.width;
            const i = Math.max(0, Math.min(n - 1, Math.round(frac * (n - 1))));
            setHover(i);
          }}
          onMouseLeave={() => setHover(null)}
        />
        {hover != null && (
          <circle cx={xAt(hover)} cy={yAt(series[hover].close)} r="4" fill={lineColor} stroke="var(--surface-1)" strokeWidth="1.5" />
        )}
      </svg>
      {hover != null && (
        <div
          style={{
            position: "absolute",
            left: `${(xAt(hover) / W) * 100}%`,
            top: `${(yAt(series[hover].close) / H) * 100}%`,
            transform: "translate(-50%, -130%)",
            background: "var(--text-primary)",
            color: "var(--surface-1)",
            padding: "6px 10px",
            borderRadius: "6px",
            fontSize: "11.5px",
            whiteSpace: "nowrap",
            pointerEvents: "none",
          }}
        >
          <b>{series[hover].date}</b>
          <br />${series[hover].close.toFixed(2)}
        </div>
      )}
    </div>
  );
}
