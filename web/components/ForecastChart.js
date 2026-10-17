import { useMemo, useState } from "react";

// Fan chart: one or two scenarios, each a p50 median line (2px, series hue)
// with its p10-p90 band as the same hue at ~10% opacity -- the uncertainty
// band is the whole point of a forecast chart, never a single collapsed
// line. Shared crosshair tracks the pointer's X and shows every scenario's
// median + range at that date in one tooltip (dataviz skill: "one
// tooltip, every series").
export default function ForecastChart({ dates, scenarios }) {
  const [hoverX, setHoverX] = useState(null);
  const n = dates?.length || 0;
  if (!n || !scenarios?.length) return null;

  const W = 640;
  const H = 320;
  const margin = { top: 16, right: 16, bottom: 32, left: 64 };
  const plotW = W - margin.left - margin.right;
  const plotH = H - margin.top - margin.bottom;

  const allVals = scenarios.flatMap((s) => [...s.p10, ...s.p90]);
  const minV = Math.min(...allVals);
  const maxV = Math.max(...allVals);
  const pad = (maxV - minV) * 0.08 || maxV * 0.05;
  const yDomain = [Math.max(0, minV - pad), maxV + pad];

  const xAt = (i) => margin.left + (i / Math.max(n - 1, 1)) * plotW;
  const yAt = (v) => margin.top + (1 - (v - yDomain[0]) / (yDomain[1] - yDomain[0])) * plotH;

  const bandPath = (p10, p90) => {
    const top = p90.map((v, i) => `${i === 0 ? "M" : "L"}${xAt(i).toFixed(1)},${yAt(v).toFixed(1)}`).join(" ");
    const bottom = p10
      .map((v, i) => `L${xAt(n - 1 - i).toFixed(1)},${yAt(p10[n - 1 - i]).toFixed(1)}`)
      .join(" ");
    return `${top} ${bottom} Z`;
  };
  const linePath = (vals) => vals.map((v, i) => `${i === 0 ? "M" : "L"}${xAt(i).toFixed(1)},${yAt(v).toFixed(1)}`).join(" ");

  const yTicks = 4;
  const yTickVals = Array.from({ length: yTicks + 1 }, (_, i) => yDomain[0] + (i * (yDomain[1] - yDomain[0])) / yTicks);
  const xTickEvery = Math.max(1, Math.floor(n / 6));

  const hoverIdx = hoverX == null ? null : Math.max(0, Math.min(n - 1, Math.round(((hoverX - margin.left) / plotW) * (n - 1))));

  return (
    <div style={{ position: "relative" }}>
      {scenarios.length > 1 && (
        <div style={{ display: "flex", gap: 16, marginBottom: 10, fontSize: 12 }}>
          {scenarios.map((s) => (
            <span key={s.key} style={{ display: "inline-flex", alignItems: "center", gap: 6, color: "var(--text-secondary)" }}>
              <span style={{ display: "inline-block", width: 14, height: 2, background: s.color, borderRadius: 1 }} />
              {s.label}
            </span>
          ))}
        </div>
      )}
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto", display: "block" }}>
        {yTickVals.map((v, i) => (
          <g key={i}>
            <line x1={margin.left} x2={margin.left + plotW} y1={yAt(v)} y2={yAt(v)} stroke="var(--grid)" strokeWidth="1" />
            <text x={margin.left - 8} y={yAt(v) + 3} textAnchor="end" fontSize="10" fill="var(--muted)">
              ${Math.round(v).toLocaleString()}
            </text>
          </g>
        ))}
        {dates.map((d, i) =>
          i % xTickEvery === 0 ? (
            <text key={i} x={xAt(i)} y={margin.top + plotH + 16} textAnchor="middle" fontSize="10" fill="var(--muted)">
              {d.slice(0, 7)}
            </text>
          ) : null
        )}

        {scenarios.map((s) => (
          <path key={`${s.key}-band`} d={bandPath(s.p10, s.p90)} fill={s.color} opacity="0.1" stroke="none" />
        ))}
        {scenarios.map((s) => (
          <path key={`${s.key}-line`} d={linePath(s.p50)} fill="none" stroke={s.color} strokeWidth="2" />
        ))}
        {scenarios.map((s) => (
          <text
            key={`${s.key}-label`}
            x={xAt(n - 1) + 6}
            y={yAt(s.p50[n - 1]) + 4}
            fontSize="10.5"
            fontWeight="650"
            fill="var(--text-primary)"
          >
            ${Math.round(s.p50[n - 1]).toLocaleString()}
          </text>
        ))}

        <rect
          x={margin.left}
          y={margin.top}
          width={plotW}
          height={plotH}
          fill="transparent"
          onMouseMove={(e) => {
            // the <rect> hit target is sized in viewBox units (W/H) but
            // rendered at the container's actual CSS width, so convert the
            // pointer's pixel offset back into viewBox space before using it
            const rect = e.currentTarget.ownerSVGElement.getBoundingClientRect();
            const xInViewBox = ((e.clientX - rect.left) / rect.width) * W;
            setHoverX(xInViewBox);
          }}
          onMouseLeave={() => setHoverX(null)}
        />
        {hoverIdx != null && (
          <>
            <line x1={xAt(hoverIdx)} x2={xAt(hoverIdx)} y1={margin.top} y2={margin.top + plotH} stroke="var(--baseline)" strokeWidth="1" />
            {scenarios.map((s) => (
              <circle key={`${s.key}-dot`} cx={xAt(hoverIdx)} cy={yAt(s.p50[hoverIdx])} r="4" fill={s.color} stroke="var(--surface-1)" strokeWidth="1.5" />
            ))}
          </>
        )}
      </svg>
      {hoverIdx != null && (
        <div
          style={{
            position: "absolute",
            left: `${(xAt(hoverIdx) / W) * 100}%`,
            top: 4,
            transform: xAt(hoverIdx) > W / 2 ? "translateX(-100%)" : "none",
            background: "var(--text-primary)",
            color: "var(--surface-1)",
            padding: "8px 12px",
            borderRadius: "8px",
            fontSize: "11.5px",
            whiteSpace: "nowrap",
            pointerEvents: "none",
          }}
        >
          <div style={{ fontWeight: 700, marginBottom: 4 }}>{dates[hoverIdx]}</div>
          {scenarios.map((s) => (
            <div key={s.key} style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span style={{ display: "inline-block", width: 10, height: 2, background: s.color }} />
              <span>
                ${Math.round(s.p50[hoverIdx]).toLocaleString()}{" "}
                <span style={{ opacity: 0.7 }}>
                  (${Math.round(s.p10[hoverIdx]).toLocaleString()}–${Math.round(s.p90[hoverIdx]).toLocaleString()})
                </span>
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
