"use client";

import { useEffect, useState } from "react";
import { Panel, Shell } from "@/components/shell";
import { Term as MetricTerm } from "@/components/term";
import { api } from "@/lib/api";
import { useSelectedAccount } from "@/lib/use-account";
import { money, num, recentRange } from "@/lib/format";

const RANGES = [7, 30, 90, 365] as const;

type Term = { search_term: string; campaign_name: string; cost: number; clicks: number; conversions: number };
type Waste = { name: string; reasons: string[]; metrics: { cost: number } };

export default function SearchTermsPage() {
  const [rows, setRows] = useState<Term[]>([]);
  const [waste, setWaste] = useState<Waste[]>([]);
  const [days, setDays] = useState<(typeof RANGES)[number]>(7);

  const account = useSelectedAccount();
  const id = account?.id ?? "";

  useEffect(() => {
    if (!id || account?.search_terms === false) return;
    const range = recentRange(days);
    const query = `account_id=${id}&start_date=${range.start}&end_date=${range.end}`;
    api<{ rows: Term[] }>(`/api/search-terms?${query}&limit=100`).then((payload) => setRows(payload.rows)).catch(() => undefined);
    api<{ rows: Waste[] }>(`/api/wasted-spend?${query}`).then((payload) => setWaste(payload.rows)).catch(() => undefined);
  }, [id, days, account?.search_terms]);

  if (account && !account.search_terms) {
    return (
      <Shell>
        <h1 className="mb-4 text-2xl font-semibold">Search terms</h1>
        <p className="text-sm text-neutral-600">Search terms are available for Google Ads and Microsoft Advertising. {account.platform_label} uses the dashboard, campaigns, reports, and trends.</p>
      </Shell>
    );
  }

  return (
    <Shell>
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Search terms</h1>
        <label className="text-sm text-neutral-600">
          Range
          <select className="ml-2 rounded-md border border-line bg-paper px-2 py-1" value={days} onChange={(event) => setDays(Number(event.target.value) as (typeof RANGES)[number])}>
            {RANGES.map((value) => (
              <option key={value} value={value}>Last {value} days</option>
            ))}
          </select>
        </label>
      </div>
      <div className="grid gap-3 lg:grid-cols-2">
        <Panel title="By spend">
          {rows.map((row) => (
            <p key={row.search_term + row.campaign_name} className="border-b border-line py-2 text-sm">
              {row.search_term} · {money(row.cost)} · {num(row.conversions)} <MetricTerm>conv.</MetricTerm> · {row.campaign_name}
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
