"use client";

import { useEffect, useState } from "react";
import { Panel, Shell } from "@/components/shell";
import { api } from "@/lib/api";
import { useAccountId } from "@/lib/use-account";
import { money, num } from "@/lib/format";

type Term = { search_term: string; campaign_name: string; cost: number; clicks: number; conversions: number };
type Waste = { name: string; reasons: string[]; metrics: { cost: number } };

export default function SearchTermsPage() {
  const [rows, setRows] = useState<Term[]>([]);
  const [waste, setWaste] = useState<Waste[]>([]);

  const id = useAccountId();

  useEffect(() => {
    if (!id) return;
    api<{ rows: Term[] }>(`/api/search-terms?account_id=${id}&limit=100`).then((payload) => setRows(payload.rows)).catch(() => undefined);
    api<{ rows: Waste[] }>(`/api/wasted-spend?account_id=${id}`).then((payload) => setWaste(payload.rows)).catch(() => undefined);
  }, [id]);

  return (
    <Shell>
      <h1 className="mb-4 text-2xl font-semibold">Search terms</h1>
      <div className="grid gap-3 lg:grid-cols-2">
        <Panel title="By spend">
          {rows.map((row) => (
            <p key={row.search_term + row.campaign_name} className="border-b border-line py-2 text-sm">
              {row.search_term} · {money(row.cost)} · {num(row.conversions)} conv. · {row.campaign_name}
            </p>
          ))}
        </Panel>
        <Panel title="Waste candidates">
          {waste.length === 0 ? <p className="text-sm text-neutral-600">No candidate met the spend and click thresholds.</p> : null}
          {waste.map((row) => (
            <p key={row.name} className="mb-2 text-sm">{row.name}: {row.reasons.join(" ")}</p>
          ))}
        </Panel>
      </div>
    </Shell>
  );
}
