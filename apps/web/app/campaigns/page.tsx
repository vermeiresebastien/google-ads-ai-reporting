"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Panel, Shell } from "@/components/shell";
import { api } from "@/lib/api";
import { useAccountId } from "@/lib/use-account";
import { money, num, pct } from "@/lib/format";

type Row = { campaign_id: string; name: string; cost: number; conversions: number; cost_per_conversion: number | null; roas: number | null; clicks: number; impressions: number };

export default function CampaignsPage() {
  const [rows, setRows] = useState<Row[]>([]);
  const [error, setError] = useState("");

  const id = useAccountId();

  useEffect(() => {
    if (!id) return;
    api<{ rows: Row[] }>(`/api/campaigns?account_id=${id}&limit=100`)
      .then((payload) => setRows(payload.rows))
      .catch((reason: Error) => setError(reason.message));
  }, [id]);

  return (
    <Shell>
      <h1 className="mb-4 text-2xl font-semibold">Campaigns</h1>
      {error ? <p className="mb-3 text-sm text-red-700">{error}</p> : null}
      <Panel title="Last 7 days">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-neutral-500">
              <tr>
                <th className="py-2">Campaign</th>
                <th>Spend</th>
                <th>Conv.</th>
                <th>CPA</th>
                <th>ROAS</th>
                <th>CTR</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.campaign_id} className="border-t border-line">
                  <td className="py-2"><Link className="text-pine" href={`/campaigns/${row.campaign_id}`}>{row.name}</Link></td>
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
