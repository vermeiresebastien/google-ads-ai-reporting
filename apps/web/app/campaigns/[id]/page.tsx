"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Panel, Shell } from "@/components/shell";
import { api } from "@/lib/api";
import { useAccountId } from "@/lib/use-account";
import { money, num } from "@/lib/format";

type Detail = { name: string; status: string; advertising_channel_type: string; daily_budget: number | null };
type Row = { date: string; cost: number; conversions: number; clicks: number; impressions: number };

export default function CampaignDetailPage() {
  const params = useParams<{ id: string }>();
  const [detail, setDetail] = useState<Detail | null>(null);
  const [rows, setRows] = useState<Row[]>([]);

  const id = useAccountId();

  useEffect(() => {
    if (!id || !params.id) return;
    api<Detail>(`/api/campaigns/${params.id}?account_id=${id}`).then(setDetail).catch(() => undefined);
    api<{ rows: Row[] }>(`/api/campaigns/${params.id}/performance?account_id=${id}`).then((payload) => setRows(payload.rows)).catch(() => undefined);
  }, [id, params.id]);

  return (
    <Shell>
      <h1 className="text-2xl font-semibold">{detail?.name ?? "Campaign"}</h1>
      <p className="mb-4 text-sm text-neutral-600">{detail?.advertising_channel_type} · {detail?.status} · budget {money(detail?.daily_budget)}</p>
      <Panel title="Daily performance">
        {rows.map((row) => (
          <p key={row.date} className="border-b border-line py-2 text-sm">{row.date}: spend {money(row.cost)}, conversions {num(row.conversions)}, clicks {num(row.clicks)}</p>
        ))}
      </Panel>
    </Shell>
  );
}
