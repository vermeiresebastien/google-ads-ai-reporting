"use client";

import { useState, type MouseEvent } from "react";
import { Term } from "@/components/term";
import { money, num } from "@/lib/format";

export type SeriesPoint = { date: string; cost: number; conversions: number; cpa?: number | null; cpc?: number | null };
export type ChangeMark = { date: string; label: string };

function axisLabel(value: number) {
  if (value >= 1000) return `${(value / 1000).toFixed(value >= 10000 ? 0 : 1)}k`;
  if (value >= 10) return value.toFixed(0);
  return value.toFixed(value < 1 ? 1 : 0);
}

function shortDate(iso: string) {
  const parts = iso.split("-").map(Number);
  if (parts.length === 2) {
    return new Date(parts[0], parts[1] - 1, 1).toLocaleDateString(undefined, { month: "short", year: "numeric" });
  }
  const [year, month, day] = parts;
  return new Date(year, month - 1, day).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export function MetricChart({
  points,
  label,
  color = "#1a73e8",
  format = num,
  percent = false,
}: {
  points: { date: string; value: number | null }[];
  label: string;
  color?: string;
  format?: (value?: number | null) => string;
  percent?: boolean;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const present = points.filter((point) => point.value != null);
  if (present.length < 2) {
    return <p className="text-sm text-neutral-600">This chart needs at least two days with a {label.toLowerCase()} value.</p>;
  }
  const width = 720;
  const height = 220;
  const left = 52;
  const right = 16;
  const top = 16;
  const bottom = 32;
  const shown = (value: number) => (percent ? value * 100 : value);
  const values = present.map((point) => shown(point.value as number));
  const maxValue = Math.max(...values, 0);
  const minValue = Math.min(...values, 0);
  const span = maxValue - minValue || 1;
  const x = (index: number) => left + (index * (width - left - right)) / Math.max(points.length - 1, 1);
  const y = (value: number) => top + (1 - (value - minValue) / span) * (height - top - bottom);
  let path = "";
  let drawing = false;
  points.forEach((point, index) => {
    if (point.value == null) {
      drawing = false;
      return;
    }
    path += `${drawing ? "L" : "M"} ${x(index).toFixed(1)} ${y(shown(point.value)).toFixed(1)} `;
    drawing = true;
  });
  const grid = [0, 0.5, 1];
  const tickEvery = Math.max(1, Math.ceil(points.length / 6));
  const active = hover == null ? null : points[hover];

  function nearest(event: MouseEvent<SVGSVGElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    const svgX = ((event.clientX - rect.left) / rect.width) * width;
    let best = 0;
    let bestDist = Infinity;
    points.forEach((_, index) => {
      const dist = Math.abs(x(index) - svgX);
      if (dist < bestDist) {
        best = index;
        bestDist = dist;
      }
    });
    setHover(best);
  }

  return (
    <div>
      <div className="mb-2 flex gap-4 text-xs text-[#5f6368]">
        <span className="inline-flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: color }} /> <Term>{label}</Term></span>
      </div>
      <div className="relative">
        <svg viewBox={`0 0 ${width} ${height}`} className="h-56 w-full" role="img" aria-label={`${label} over time`} onMouseMove={nearest} onMouseLeave={() => setHover(null)}>
          {grid.map((step) => {
            const gridY = top + (1 - step) * (height - top - bottom);
            return (
              <g key={step}>
                <line x1={left} x2={width - right} y1={gridY} y2={gridY} stroke="#e8eaed" strokeWidth="1" />
                <text x={left - 8} y={gridY + 4} textAnchor="end" fill="#5f6368" fontSize="11">{percent ? `${(minValue + span * step).toFixed(0)}%` : axisLabel(minValue + span * step)}</text>
              </g>
            );
          })}
          <path d={path.trim()} fill="none" stroke={color} strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" />
          {points.map((point, index) => index % tickEvery === 0 || index === points.length - 1 ? (
            <text key={point.date} x={x(index)} y={height - 8} textAnchor="middle" fill="#5f6368" fontSize="11">{shortDate(point.date)}</text>
          ) : null)}
          {hover != null && active?.value != null ? (
            <circle cx={x(hover)} cy={y(shown(active.value))} r="4" fill="#fff" stroke={color} strokeWidth="2" />
          ) : null}
        </svg>
        {hover != null && active ? (
          <div
            className="pointer-events-none absolute top-2 z-10 rounded-lg border border-[#e8eaed] bg-white px-3 py-2 text-xs shadow-md"
            style={{ left: `${(x(hover) / width) * 100}%`, transform: x(hover) > width * 0.72 ? "translateX(-110%)" : "translateX(12px)" }}
          >
            <p className="mb-1 font-medium text-[#202124]">{shortDate(active.date)}</p>
            <p style={{ color }}>{label} {format(active.value)}</p>
          </div>
        ) : null}
      </div>
    </div>
  );
}

export function SeriesChart({ points, changes = [] }: { points: SeriesPoint[]; changes?: ChangeMark[] }) {
  const [hover, setHover] = useState<number | null>(null);
  if (points.length < 2) {
    return <p className="text-sm text-neutral-600">The trend chart needs at least two days of campaign stats.</p>;
  }
  const width = 720;
  const height = 240;
  const left = 46;
  const right = 46;
  const top = 16;
  const bottom = 32;
  const maxCost = Math.max(...points.map((point) => point.cost), 1);
  const maxConv = Math.max(...points.map((point) => point.conversions), 1);
  const x = (index: number) => left + (index * (width - left - right)) / (points.length - 1);
  const yCost = (value: number) => top + (1 - value / maxCost) * (height - top - bottom);
  const yConv = (value: number) => top + (1 - value / maxConv) * (height - top - bottom);
  const line = (values: number[], scale: (value: number) => number) =>
    values.map((value, index) => `${index === 0 ? "M" : "L"} ${x(index).toFixed(1)} ${scale(value).toFixed(1)}`).join(" ");
  const costLine = line(points.map((point) => point.cost), yCost);
  const area = `${costLine} L ${x(points.length - 1).toFixed(1)} ${(height - bottom).toFixed(1)} L ${x(0).toFixed(1)} ${(height - bottom).toFixed(1)} Z`;
  const grid = [0, 0.25, 0.5, 0.75, 1];
  const tickEvery = Math.max(1, Math.ceil(points.length / 6));
  const active = hover == null ? null : points[hover];
  const marks = new Map<string, string[]>();
  for (const change of changes) {
    const list = marks.get(change.date) ?? [];
    list.push(change.label);
    marks.set(change.date, list);
  }
  const indexByDate = new Map(points.map((point, index) => [point.date.slice(0, 10), index]));

  function nearest(event: MouseEvent<SVGSVGElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    const svgX = ((event.clientX - rect.left) / rect.width) * width;
    let best = 0;
    let bestDist = Infinity;
    points.forEach((_, index) => {
      const dist = Math.abs(x(index) - svgX);
      if (dist < bestDist) {
        best = index;
        bestDist = dist;
      }
    });
    setHover(best);
  }

  return (
    <div>
      <div className="mb-2 flex gap-4 text-xs text-[#5f6368]">
        <span className="inline-flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-[#1a73e8]" /> <Term>Spend</Term></span>
        <span className="inline-flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-[#e37400]" /> <Term>Conversions</Term></span>
        {changes.length ? <span className="inline-flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-[#9334e6]" /> Account edits</span> : null}
      </div>
      <div className="relative">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="h-60 w-full"
          role="img"
          aria-label="Spend and conversions over time"
          onMouseMove={nearest}
          onMouseLeave={() => setHover(null)}
        >
          <defs>
            <linearGradient id="gads-spend-fill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#1a73e8" stopOpacity="0.28" />
              <stop offset="100%" stopColor="#1a73e8" stopOpacity="0.02" />
            </linearGradient>
          </defs>
          {grid.map((step) => {
            const y = top + (1 - step) * (height - top - bottom);
            return (
              <g key={step}>
                <line x1={left} x2={width - right} y1={y} y2={y} stroke="#e8eaed" strokeWidth="1" />
                <text x={left - 8} y={y + 4} textAnchor="end" fill="#5f6368" fontSize="11">{axisLabel(maxCost * step)}</text>
                <text x={width - right + 8} y={y + 4} textAnchor="start" fill="#e37400" fontSize="11">{axisLabel(maxConv * step)}</text>
              </g>
            );
          })}
          <path d={area} fill="url(#gads-spend-fill)" />
          <path d={costLine} fill="none" stroke="#1a73e8" strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" />
          <path d={line(points.map((point) => point.conversions), yConv)} fill="none" stroke="#e37400" strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" />
          {[...marks.keys()].map((day) => {
            const index = indexByDate.get(day);
            if (index == null) return null;
            return <circle key={day} cx={x(index)} cy={height - bottom} r="4" fill="#9334e6" />;
          })}
          {points.map((point, index) => index % tickEvery === 0 || index === points.length - 1 ? (
            <text key={point.date} x={x(index)} y={height - 8} textAnchor="middle" fill="#5f6368" fontSize="11">{shortDate(point.date)}</text>
          ) : null)}
          {hover != null && active ? (
            <g>
              <line x1={x(hover)} x2={x(hover)} y1={top} y2={height - bottom} stroke="#dadce0" strokeWidth="1" />
              <circle cx={x(hover)} cy={yCost(active.cost)} r="4" fill="#fff" stroke="#1a73e8" strokeWidth="2" />
              <circle cx={x(hover)} cy={yConv(active.conversions)} r="4" fill="#fff" stroke="#e37400" strokeWidth="2" />
            </g>
          ) : null}
        </svg>
        {hover != null && active ? (
          <div
            className="pointer-events-none absolute top-2 z-10 rounded-lg border border-[#e8eaed] bg-white px-3 py-2 text-xs shadow-md"
            style={{ left: `${(x(hover) / width) * 100}%`, transform: x(hover) > width * 0.72 ? "translateX(-110%)" : "translateX(12px)" }}
          >
            <p className="mb-1 font-medium text-[#202124]">{shortDate(active.date)}</p>
            <p className="text-[#1a73e8]">Spend {money(active.cost)}</p>
            <p className="text-[#e37400]">Conversions {num(active.conversions)}</p>
            {active.cpa != null ? <p className="text-[#5f6368]">CPA {money(active.cpa)}</p> : null}
            {active.cpc != null ? <p className="text-[#5f6368]">CPC {money(active.cpc)}</p> : null}
            {(marks.get(active.date.slice(0, 10)) ?? []).slice(0, 3).map((label) => (
              <p key={label} className="mt-1 max-w-56 text-[#9334e6]">{label}</p>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}
