"use client";

import { useEffect, useState } from "react";

const WEEKDAYS = ["M", "T", "W", "T", "F", "S", "S"];

function monthCells(year: number, month: number) {
  const first = new Date(year, month, 1);
  const lead = (first.getDay() + 6) % 7;
  const count = new Date(year, month + 1, 0).getDate();
  const cells: (string | null)[] = Array.from({ length: lead }, () => null);
  for (let day = 1; day <= count; day += 1) {
    cells.push(`${year}-${String(month + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`);
  }
  while (cells.length % 7 !== 0) cells.push(null);
  return cells;
}

function isIsoDate(value: string) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const [year, month, day] = value.split("-").map(Number);
  const parsed = new Date(year, month - 1, day);
  return parsed.getFullYear() === year && parsed.getMonth() === month - 1 && parsed.getDate() === day;
}

export function RangeCalendar({
  year,
  month,
  onMonth,
  start,
  end,
  marked,
  onPick,
  onSpan,
  hint,
}: {
  year: number;
  month: number;
  onMonth: (next: { year: number; month: number }) => void;
  start: string;
  end: string;
  marked: Set<string>;
  onPick: (iso: string) => void;
  onSpan: (start: string, end: string) => void;
  hint: string;
}) {
  const [fromDraft, setFromDraft] = useState(start);
  const [toDraft, setToDraft] = useState(end);
  const cells = monthCells(year, month);
  const label = new Date(year, month, 1).toLocaleDateString(undefined, { month: "short", year: "numeric" });

  useEffect(() => setFromDraft(start), [start]);
  useEffect(() => setToDraft(end), [end]);

  function shift(delta: number) {
    const next = new Date(year, month + delta, 1);
    onMonth({ year: next.getFullYear(), month: next.getMonth() });
  }

  function commit(kind: "start" | "end", value: string) {
    if (!isIsoDate(value)) return false;
    const nextStart = kind === "start" ? value : start || value;
    const nextEnd = kind === "end" ? value : end || value;
    onSpan(nextStart, nextEnd);
    const [focusYear, focusMonth] = (kind === "start" ? value : nextEnd).split("-").map(Number);
    if (focusYear && focusMonth) onMonth({ year: focusYear, month: focusMonth - 1 });
    return true;
  }

  return (
    <div className="w-44">
      <div className="mb-1 flex items-center justify-between">
        <button type="button" aria-label="Previous month" className="rounded px-1 text-sm leading-none text-neutral-500 hover:bg-paper" onClick={() => shift(-1)}>‹</button>
        <p className="text-xs font-medium">{label}</p>
        <button type="button" aria-label="Next month" className="rounded px-1 text-sm leading-none text-neutral-500 hover:bg-paper" onClick={() => shift(1)}>›</button>
      </div>
      <div className="grid grid-cols-7 text-center text-[10px] leading-none text-neutral-400">
        {WEEKDAYS.map((day, index) => <span key={`${day}-${index}`}>{day}</span>)}
      </div>
      <div className="mt-1 grid grid-cols-7 gap-px">
        {cells.map((iso, index) => {
          if (!iso) return <span key={`empty-${index}`} className="size-6" />;
          const endpoint = iso === start || iso === end;
          const inside = start && end ? iso >= start && iso <= end : false;
          const saved = marked.has(iso);
          return (
            <button
              key={iso}
              type="button"
              aria-label={iso}
              aria-pressed={endpoint}
              title={saved ? `${iso}, saved` : iso}
              className={`relative size-6 rounded text-[11px] leading-none ${endpoint ? "bg-pine text-white" : inside ? "bg-[#e5f2eb] font-medium text-neutral-900" : saved ? "font-semibold text-neutral-900" : "text-neutral-400"}`}
              onClick={() => onPick(iso)}
            >
              {Number(iso.slice(8))}
              {saved && !endpoint ? <span className={`absolute bottom-0.5 left-1/2 size-1 -translate-x-1/2 rounded-full ${inside ? "bg-pine" : "bg-pine/70"}`} /> : null}
            </button>
          );
        })}
      </div>
      <div className="mt-1.5 flex items-center gap-1">
        <input
          aria-label="From"
          className="w-0 min-w-0 flex-1 rounded border border-line bg-paper px-1 py-0.5 font-mono text-[10px]"
          value={fromDraft}
          placeholder="From"
          spellCheck={false}
          onChange={(event) => setFromDraft(event.target.value)}
          onBlur={() => {
            if (!commit("start", fromDraft)) setFromDraft(start);
          }}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              if (!commit("start", fromDraft)) setFromDraft(start);
            }
          }}
        />
        <span className="text-[10px] text-neutral-400">–</span>
        <input
          aria-label="To"
          className="w-0 min-w-0 flex-1 rounded border border-line bg-paper px-1 py-0.5 font-mono text-[10px]"
          value={toDraft}
          placeholder="To"
          spellCheck={false}
          onChange={(event) => setToDraft(event.target.value)}
          onBlur={() => {
            if (!commit("end", toDraft)) setToDraft(end);
          }}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              if (!commit("end", toDraft)) setToDraft(end);
            }
          }}
        />
      </div>
      <p className="mt-1 text-[10px] leading-snug text-neutral-400">{hint}</p>
    </div>
  );
}
