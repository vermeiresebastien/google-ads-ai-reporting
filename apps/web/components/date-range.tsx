"use client";

import { CAMPAIGN_RANGES, rangeError, recentRange } from "@/lib/format";

export type DateSpan = { start: string; end: string; preset: number | "custom" };

const fieldClass = "mt-1 block rounded-md border border-line bg-paper px-2 py-1";

export function DateRangePicker({ value, onChange, calendars = false }: { value: DateSpan; onChange: (next: DateSpan) => void; calendars?: boolean }) {
  const yesterday = recentRange(1).end;
  const problem = rangeError(value.start, value.end);

  function applyDates(start: string, end: string) {
    onChange({ start, end, preset: "custom" });
  }

  return (
    <div className="flex flex-wrap items-end gap-3 text-sm text-neutral-600">
      <label>
        Period
        <select
          className={fieldClass}
          value={String(value.preset)}
          onChange={(event) => {
            const next = event.target.value;
            if (next === "custom") {
              onChange({ ...value, preset: "custom" });
              return;
            }
            onChange({ ...recentRange(Number(next)), preset: Number(next) });
          }}
        >
          {CAMPAIGN_RANGES.map(([days, name]) => (
            <option key={days} value={days}>{name}</option>
          ))}
          <option value="custom">Custom dates</option>
        </select>
      </label>
      {calendars || value.preset === "custom" ? (
        <>
          <label>
            From
            <input className={fieldClass} type="date" value={value.start} max={value.end || yesterday} onChange={(event) => applyDates(event.target.value, value.end)} />
          </label>
          <label>
            To
            <input className={fieldClass} type="date" value={value.end} min={value.start} max={yesterday} onChange={(event) => applyDates(value.start, event.target.value)} />
          </label>
          <label>
            One day
            <input
              className={fieldClass}
              type="date"
              value={value.start === value.end ? value.start : ""}
              max={yesterday}
              onChange={(event) => {
                if (event.target.value) applyDates(event.target.value, event.target.value);
              }}
            />
          </label>
        </>
      ) : null}
      {problem ? <p className="pb-1 text-xs text-red-700">{problem}</p> : null}
    </div>
  );
}
