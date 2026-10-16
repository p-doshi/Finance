import { useState } from "react";

// Inline SVG line chart: the real historical equity curve plus a distinct
// live point extending it. Deliberately not a charting library -- this is
// a single line + one extra point, and keeping it as plain SVG keeps the
// bundle tiny and the rendering fully under control (consistent with how
// every other dashboard in this project is built).
export default function EquityChart({ curve, liveValue, color }) {
  const [hover, setHover] = useState(null);
  if (!curve || curve.length === 0) return null;

  const W = 640;
  const H = 320;
  const margin = { top: 20, right: 60, bottom: 36, left: 64 };
  const plotW = W - margin.left - margin.right;
  const plotH = H - margin.top - margin.bottom;

  const allValues = curve.map((p) => p.value).concat(liveValue != null ? [liveValue] : []);
  const minV = Math.min(...allValues);
  const maxV = Math.max(...allValues);
  const pad = (maxV - minV) * 0.08 || maxV * 0.05;
  const yDomain = [minV - pad, maxV + pad];

  const n = curve.length;
  const xAt = (i) => margin.left + (i / Math.max(n - 1, 1)) * plotW;
  const yAt = (v) => margin.top + (1 - (v - yDomain[0]) / (yDomain[1] - yDomain[0])) * plotH;

  const linePath = curve.map((p, i) => `${i === 0 ? "M" : "L"}${xAt(i).toFixed(1)},${yAt(p.value).toFixed(1)}`).join(" ");

  const liveX = margin.left + plotW + 24;
  const liveY = liveValue != null ? yAt(liveValue) : null;

  const yTicks = 4;
  const yTickVals = Array.from({ length: yTicks + 1 }, (_, i) => yDomain[0] + (i * (yDomain[1] - yDomain[0])) / yTicks);

  const xTickEvery = Math.max(1, Math.floor(n / 6));

  return (
    <div style={{ position: "relative" }}>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto", display: "block" }}>
        {yTickVals.map((v, i) => (
          <g key={i}>
            <line
              x1={margin.left}
              x2={margin.left + plotW}
              y1={yAt(v)}
              y2={yAt(v)}
              stroke="var(--grid)"
              strokeWidth="1"
            />
            <text x={margin.left - 8} y={yAt(v) + 3} textAnchor="end" fontSize="10" fill="var(--muted)">
              ${Math.round(v).toLocaleString()}
            </text>
          </g>
        ))}
        {curve.map((p, i) =>
          i % xTickEvery === 0 ? (
            <text
              key={i}
              x={xAt(i)}
              y={margin.top + plotH + 16}
              textAnchor="middle"
              fontSize="10"
              fill="var(--muted)"
            >
              {p.date.slice(0, 7)}
            </text>
          ) : null
        )}
        <path d={linePath} fill="none" stroke={color} strokeWidth="2" />
        {curve.map((p, i) => (
          <circle
            key={i}
            cx={xAt(i)}
            cy={yAt(p.value)}
            r={hover === i ? 5 : 3}
            fill={color}
            stroke="var(--surface-1)"
            strokeWidth="1.5"
            onMouseEnter={() => setHover(i)}
            onMouseLeave={() => setHover(null)}
            style={{ cursor: "pointer" }}
          />
        ))}
        {liveY != null && (
          <>
            <line x1={margin.left + plotW} x2={liveX} y1={yAt(curve[n - 1].value)} y2={liveY} stroke={color} strokeWidth="2" strokeDasharray="3,3" />
            <circle cx={liveX} cy={liveY} r="6" fill="var(--critical)" stroke="var(--surface-1)" strokeWidth="2" />
            <text x={liveX + 10} y={liveY + 4} fontSize="11" fontWeight="650" fill="var(--text-primary)">
              LIVE
            </text>
          </>
        )}
      </svg>
      {hover != null && (
        <div
          style={{
            position: "absolute",
            left: `${(xAt(hover) / W) * 100}%`,
            top: `${(yAt(curve[hover].value) / H) * 100}%`,
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
          <b>{curve[hover].date}</b>
          <br />${curve[hover].value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </div>
      )}
    </div>
  );
}
