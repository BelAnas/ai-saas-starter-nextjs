"use client";

import { useState } from "react";
import { formatCompact, formatDay, formatNumber, formatUsd, niceMax } from "@/lib/format";
import type { DayUsage } from "@/lib/types";

export type Metric = "messages" | "tokens" | "cost_usd";

export const METRICS: Record<Metric, { label: string; format: (v: number) => string; tick: (v: number) => string }> = {
  messages: { label: "Messages", format: formatNumber, tick: formatCompact },
  tokens: { label: "Tokens", format: formatNumber, tick: formatCompact },
  cost_usd: { label: "Model cost", format: formatUsd, tick: (v) => `$${v < 1 ? v.toFixed(2) : formatCompact(v)}` },
};

const W = 720, H = 240;
const M = { left: 48, right: 8, top: 12, bottom: 28 };

/** One measure per day as bars. One series, so no legend: the selected tab names it. */
export function UsageChart({ series, metric }: { series: DayUsage[]; metric: Metric }) {
  const [hover, setHover] = useState<number | null>(null);
  const { label, format, tick } = METRICS[metric];
  const innerW = W - M.left - M.right;
  const innerH = H - M.top - M.bottom;
  const top = niceMax(Math.max(...series.map((d) => d[metric])));
  const band = innerW / series.length;
  const barW = Math.min(28, band - 2); // at least a 2px gap between neighbours
  const y = (value: number) => M.top + innerH - (value / top) * innerH;
  const labelEvery = Math.ceil(series.length / 7);
  const hovered = hover === null ? null : series[hover];

  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img"
        aria-label={`${label} per day for the last ${series.length} days`} onMouseLeave={() => setHover(null)}>
        {[0, 0.5, 1].map((share) => (
          <g key={share}>
            <line x1={M.left} x2={W - M.right} y1={y(top * share)} y2={y(top * share)}
              stroke="var(--color-line)" strokeWidth={1} />
            <text x={M.left - 8} y={y(top * share) + 4} textAnchor="end" fontSize={11} fill="var(--color-muted)">
              {tick(top * share)}
            </text>
          </g>
        ))}
        {series.map((d, i) => {
          const x = M.left + i * band + (band - barW) / 2;
          const height = (d[metric] / top) * innerH;
          const r = Math.min(4, height); // rounded at the data end only, square on the baseline
          const base = M.top + innerH;
          return (
            <g key={d.date}>
              {height > 0 && (
                <path
                  d={`M${x},${base} V${base - height + r} Q${x},${base - height} ${x + r},${base - height} H${x + barW - r} Q${x + barW},${base - height} ${x + barW},${base - height + r} V${base} Z`}
                  fill="var(--color-series)" opacity={hover === null || hover === i ? 1 : 0.45}
                />
              )}
              {i % labelEvery === 0 && (
                <text x={x + barW / 2} y={H - 8} textAnchor="middle" fontSize={11} fill="var(--color-muted)">
                  {formatDay(d.date)}
                </text>
              )}
              {/* The hit area is the whole column, so short bars are as easy to point at as tall ones. */}
              <rect x={M.left + i * band} y={M.top} width={band} height={innerH} fill="transparent"
                onMouseEnter={() => setHover(i)} />
            </g>
          );
        })}
      </svg>
      {hovered && hover !== null && (
        <div className="pointer-events-none absolute top-0 -translate-x-1/2 rounded-md border border-line bg-panel px-3 py-2 text-xs shadow-md"
          style={{ left: `${((M.left + (hover + 0.5) * band) / W) * 100}%` }}>
          <div className="font-medium">{formatDay(hovered.date)}</div>
          <div className="text-muted">
            {label}: <span className="font-medium text-ink">{format(hovered[metric])}</span>
          </div>
          <div className="text-muted">Active users: {hovered.active_users}</div>
        </div>
      )}
    </div>
  );
}
