export function money(value?: number | null) {
  if (value == null || Number.isNaN(value)) return "—";
  return Number(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function num(value?: number | null) {
  if (value == null || Number.isNaN(value)) return "—";
  return Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 });
}

export const CAMPAIGN_RANGES = [
  [30, "Last 30 days"],
  [90, "Last 90 days"],
  [180, "Last 6 months"],
  [365, "Last year"],
  [395, "Full history"],
] as const;

export const MAX_RANGE_DAYS = 400;

export function spanLength(start: string, end: string) {
  const from = new Date(`${start}T00:00:00`);
  const to = new Date(`${end}T00:00:00`);
  return Math.round((to.getTime() - from.getTime()) / 86_400_000) + 1;
}

export function rangeError(start: string, end: string) {
  if (!start || !end) return "Choose a start and end date.";
  if (end < start) return "The end date is before the start date.";
  if (spanLength(start, end) > MAX_RANGE_DAYS) return `A period can cover at most ${MAX_RANGE_DAYS} days.`;
  return "";
}

export function describeRange(start: string, end: string, preset: number | "custom") {
  if (start === end) return start;
  if (preset !== "custom") {
    const named = CAMPAIGN_RANGES.find((item) => item[0] === preset);
    if (named) return named[1];
  }
  return `${start} to ${end}`;
}

export function recentRange(days: number) {
  const end = new Date();
  end.setDate(end.getDate() - 1);
  const start = new Date(end);
  start.setDate(start.getDate() - (days - 1));
  const iso = (value: Date) => {
    const month = String(value.getMonth() + 1).padStart(2, "0");
    const day = String(value.getDate()).padStart(2, "0");
    return `${value.getFullYear()}-${month}-${day}`;
  };
  return { start: iso(start), end: iso(end) };
}

export function pct(value?: number | null) {
  if (value == null || Number.isNaN(value)) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${(value * 100).toFixed(1)}%`;
}
