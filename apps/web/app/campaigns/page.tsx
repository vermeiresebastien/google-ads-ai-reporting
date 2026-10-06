"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { DateRangePicker, type DateSpan } from "@/components/date-range";
import { Term } from "@/components/term";
import { Panel, Shell } from "@/components/shell";
import { api } from "@/lib/api";
import { useAccountId } from "@/lib/use-account";
import { describeRange, money, num, pct, rangeError, recentRange } from "@/lib/format";

type Row = {
  campaign_id: string;
  name: string;
  status: string;
  daily_budget: number | null;
  cost: number;
  conversions: number;
  cost_per_conversion: number | null;
  roas: number | null;
  clicks: number;
  impressions: number;
};

const initialRange = recentRange(90);

function statusLabel(status: string) {
  const value = (status || "").toUpperCase();
  if (value === "ENABLED") return "Active";
  if (value === "PAUSED") return "Paused";
  if (value === "REMOVED") return "Removed";
  return status || "—";
}

export default function CampaignsPage() {
  const [rows, setRows] = useState<Row[]>([]);
  const [error, setError] = useState("");
  const [span, setSpan] = useState<DateSpan>({ ...initialRange, preset: 90 });

  const id = useAccountId();
  const problem = rangeError(span.start, span.end);

  useEffect(() => {
    if (!id || problem) return;
    api<{ rows: Row[] }>(`/api/campaigns?account_id=${id}&limit=100&start_date=${span.start}&end_date=${span.end}`)
      .then((payload) => setRows(payload.rows))
      .catch((reason: Error) => setError(reason.message));
  }, [id, span.start, span.end, problem]);

  return (
    <Shell>
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <h1 className="text-2xl font-semibold">Campaigns</h1>
        <DateRangePicker value={span} onChange={setSpan} />
      </div>
      {error ? <p className="mb-3 text-sm text-red-700">{error}</p> : null}
      <Panel title={describeRange(span.start, span.end, span.preset)}>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-neutral-500">
              <tr>
                <th className="py-2">Campaign</th>
                <th>Status</th>
                <th>Daily budget</th>
                <th><Term>Spend</Term></th>
                <th><Term>Conv.</Term></th>
                <th><Term>CPA</Term></th>
                <th><Term>ROAS</Term></th>
                <th><Term>CTR</Term></th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 ? (
                <tr><td className="py-3 text-neutral-600" colSpan={8}>No campaign stats in this range.</td></tr>
              ) : null}
              {rows.map((row) => (
                <tr key={row.campaign_id} className="border-t border-line">
                  <td className="py-2"><Link className="text-pine" href={`/campaigns/${row.campaign_id}?start=${span.start}&end=${span.end}`}>{row.name}</Link></td>
                  <td className={row.status?.toUpperCase() === "ENABLED" ? "text-pine" : "text-neutral-600"}>
                    {statusLabel(row.status)}
                  </td>
                  <td>{money(row.daily_budget)}</td>
                  <td>{money(row.cost)}</td>
                  <td>{num(row.conversions)}</td>
                  <td>{money(row.cost_per_conversion)}</td>
                  <td>{num(row.roas)}</td>
                  <td>{pct(row.impressions ? row.clicks / row.impressions : null)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </Shell>
  );
}
