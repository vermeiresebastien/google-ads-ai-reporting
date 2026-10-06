"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { DateRangePicker, type DateSpan } from "@/components/date-range";
import { SeriesChart } from "@/components/series-chart";
import { Term } from "@/components/term";
import { Panel, Shell } from "@/components/shell";
import { api } from "@/lib/api";
import { CAMPAIGN_RANGES, describeRange, money, num, rangeError, recentRange } from "@/lib/format";
import { useAccountId } from "@/lib/use-account";

type Detail = { name: string; status: string; advertising_channel_type: string; daily_budget: number | null };
type Row = { date: string; cost: number; conversions: number; conversion_value: number; clicks: number; impressions: number };
function monthLabel(isoMonth: string) {
  const [year, month] = isoMonth.split("-").map(Number);
  return new Date(year, month - 1, 1).toLocaleDateString(undefined, { month: "short", year: "numeric" });
}

function dayLabel(iso: string) {
  const [year, month, day] = iso.split("-").map(Number);
  return new Date(year, month - 1, day).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric", year: "numeric" });
}

export default function CampaignDetailPage() {
  const params = useParams<{ id: string }>();
  const [detail, setDetail] = useState<Detail | null>(null);
  const [rows, setRows] = useState<Row[]>([]);
  const [error, setError] = useState("");
  const [span, setSpan] = useState<DateSpan>({ ...recentRange(90), preset: 90 });
  const [view, setView] = useState<"day" | "month" | "custom">("day");

  const id = useAccountId();
  const problem = rangeError(span.start, span.end);
  const rangeLabel = describeRange(span.start, span.end, span.preset);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const start = params.get("start");
    const end = params.get("end");
    const iso = /^\d{4}-\d{2}-\d{2}$/;
    if (start && end && iso.test(start) && iso.test(end)) {
      const match = CAMPAIGN_RANGES.find((item) => {
        const range = recentRange(item[0]);
        return range.start === start && range.end === end;
      });
      setSpan({ start, end, preset: match ? match[0] : "custom" });
      return;
    }
    const requested = Number(params.get("days"));
    if (CAMPAIGN_RANGES.some((item) => item[0] === requested)) {
      setSpan({ ...recentRange(requested), preset: requested });
    }
  }, []);

  useEffect(() => {
    if (!id || !params.id || problem) return;
    setError("");
    api<Detail>(`/api/campaigns/${params.id}?account_id=${id}`).then(setDetail).catch(() => undefined);
    api<{ rows: Row[] }>(`/api/campaigns/${params.id}/performance?account_id=${id}&start_date=${span.start}&end_date=${span.end}`)
      .then((payload) => setRows(payload.rows))
      .catch((reason: Error) => setError(reason.message));
  }, [id, params.id, span.start, span.end, problem]);

  function chooseSpan(next: DateSpan) {
    setSpan(next);
    const url = new URL(window.location.href);
    url.searchParams.set("start", next.start);
    url.searchParams.set("end", next.end);
    url.searchParams.delete("days");
    window.history.replaceState(null, "", url);
  }

  const spend = rows.reduce((sum, row) => sum + row.cost, 0);
  const conversions = rows.reduce((sum, row) => sum + row.conversions, 0);
  const value = rows.reduce((sum, row) => sum + (row.conversion_value || 0), 0);
  const months = new Map<string, { cost: number; conversions: number; value: number }>();
  for (const row of rows) {
    const key = row.date.slice(0, 7);
    const current = months.get(key) ?? { cost: 0, conversions: 0, value: 0 };
    current.cost += row.cost;
    current.conversions += row.conversions;
    current.value += row.conversion_value || 0;
    months.set(key, current);
  }
  const chartPoints = view === "month"
    ? [...months.entries()].map(([month, totals]) => ({ date: month, cost: totals.cost, conversions: totals.conversions }))
    : rows.map((row) => ({ date: row.date, cost: row.cost, conversions: row.conversions }));

  return (
    <Shell>
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">{detail?.name ?? "Campaign"}</h1>
          <p className="text-sm text-neutral-600">{detail?.advertising_channel_type} · {detail?.status} · budget {money(detail?.daily_budget)}</p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex rounded-md border border-line bg-paper p-0.5 text-sm">
            {([["day", "Day by day"], ["month", "By month"], ["custom", "Custom"]] as const).map(([value, name]) => (
              <button
                key={value}
                type="button"
                className={`rounded px-2 py-1 ${view === value ? "bg-white text-ink shadow-sm" : "text-neutral-600"}`}
                onClick={() => setView(value)}
              >
                {name}
              </button>
            ))}
          </div>
        </div>
      </div>
      {error ? <p className="mb-3 text-sm text-red-700">{error}</p> : null}
      <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Panel title="Spend"><p className="text-2xl font-semibold">{money(rows.length ? spend : null)}</p></Panel>
        <Panel title="Conversions"><p className="text-2xl font-semibold">{num(rows.length ? conversions : null)}</p></Panel>
        <Panel title="CPA"><p className="text-2xl font-semibold">{money(conversions ? spend / conversions : null)}</p></Panel>
        <Panel title="ROAS"><p className="text-2xl font-semibold">{num(spend ? value / spend : null)}</p></Panel>
      </div>
      {view === "custom" ? (
        <div className="mb-4">
          <Panel title="Custom dates">
            <DateRangePicker value={span} onChange={chooseSpan} calendars />
          </Panel>
        </div>
      ) : null}
      <Panel title={view === "month" ? "By month · spend and conversions" : view === "custom" ? `${rangeLabel} · spend and conversions` : "Day by day · spend and conversions"}>
        {chartPoints.length > 1 ? <SeriesChart points={chartPoints} /> : <p className="text-sm text-neutral-600">The chart needs at least two {view === "month" ? "months" : "days"} in this range.</p>}
      </Panel>
      {view === "month" ? (
        <div className="mt-4">
        <Panel title="By month">
          {months.size === 0 ? <p className="text-sm text-neutral-600">No daily stats in this range.</p> : (
            <table className="w-full text-left text-sm">
              <thead className="text-neutral-500">
                <tr>
                  <th className="py-2">Month</th>
                  <th><Term>Spend</Term></th>
                  <th><Term>Conv.</Term></th>
                  <th><Term>CPA</Term></th>
                  <th><Term>ROAS</Term></th>
                </tr>
              </thead>
              <tbody>
                {[...months.entries()].map(([month, totals]) => (
                  <tr key={month} className="border-t border-line">
                    <td className="py-2">{monthLabel(month)}</td>
                    <td>{money(totals.cost)}</td>
                    <td>{num(totals.conversions)}</td>
                    <td>{money(totals.conversions ? totals.cost / totals.conversions : null)}</td>
                    <td>{num(totals.cost ? totals.value / totals.cost : null)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Panel>
        </div>
      ) : null}
      {view === "day" ? (
        <div className="mt-4">
        <Panel title={`Day by day · ${rows.length} days`}>
          {rows.length === 0 ? <p className="text-sm text-neutral-600">No daily stats in this range.</p> : (
            <div className="max-h-[32rem] overflow-auto">
              <table className="w-full text-left text-sm">
                <thead className="sticky top-0 bg-white text-neutral-500">
                  <tr>
                    <th className="py-2">Day</th>
                    <th><Term>Spend</Term></th>
                    <th><Term>Conv.</Term></th>
                    <th><Term>Clicks</Term></th>
                    <th><Term>Impr.</Term></th>
                    <th><Term>CPA</Term></th>
                    <th><Term>ROAS</Term></th>
                  </tr>
                </thead>
                <tbody>
                  {[...rows].reverse().map((row) => (
                    <tr key={row.date} className="border-t border-line">
                      <td className="py-2">{dayLabel(row.date)}</td>
                      <td>{money(row.cost)}</td>
                      <td>{num(row.conversions)}</td>
                      <td>{num(row.clicks)}</td>
                      <td>{num(row.impressions)}</td>
                      <td>{money(row.conversions ? row.cost / row.conversions : null)}</td>
                      <td>{num(row.cost ? row.conversion_value / row.cost : null)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
        </div>
      ) : null}
    </Shell>
  );
}
