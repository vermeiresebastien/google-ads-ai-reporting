"use client";

import { useEffect, useState } from "react";
import { Panel, Shell } from "@/components/shell";
import { api } from "@/lib/api";
import { useAccountId } from "@/lib/use-account";
import { money, num, pct } from "@/lib/format";

type Report = {
  date: string;
  data_freshness: { last_successful_sync: string | null };
  account: Record<string, number | null>;
  comparison: { changes: Record<string, { percent: number | null }>; period: Record<string, string> };
  anomalies: { type: string; evidence: string[] }[];
  top_changes: { name: string; spend_delta: number; conversion_delta: number }[];
  recommended_actions: { action: string; evidence: string[] }[];
};

export default function DashboardPage() {
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState("");

  const id = useAccountId();

  useEffect(() => {
    if (!id) return;
    api<Report>(`/api/reports/daily?account_id=${id}`)
      .then(setReport)
      .catch((reason: Error) => setError(reason.message));
  }, [id]);

  const metrics = [
    ["Spend", report?.account.cost, report?.comparison.changes.cost?.percent, money],
    ["Conversions", report?.account.conversions, report?.comparison.changes.conversions?.percent, num],
    ["Conv. value", report?.account.conversion_value, report?.comparison.changes.conversion_value?.percent, money],
    ["CPA", report?.account.cost_per_conversion, report?.comparison.changes.cost_per_conversion?.percent, money],
    ["ROAS", report?.account.roas, report?.comparison.changes.roas?.percent, num],
  ] as const;

  return (
    <Shell>
      <div className="mb-4 flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-2xl font-semibold">Yesterday</h1>
          <p className="text-sm text-neutral-600">
            {report ? `${report.comparison.period.current_start} versus ${report.comparison.period.baseline_start} to ${report.comparison.period.baseline_end} daily average` : "Loading the daily comparison"}
          </p>
        </div>
        <p className="text-sm text-neutral-600">Sync {report?.data_freshness.last_successful_sync ?? "not recorded"}</p>
      </div>
      {error ? <p className="mb-4 text-sm text-red-700">{error}</p> : null}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {metrics.map(([label, value, change, format]) => (
          <Panel key={label} title={label}>
            <p className="text-2xl font-semibold">{format(value as number | null)}</p>
            <p className={change != null && change < 0 ? "text-sm text-red-700" : "text-sm text-pine"}>{pct(change)}</p>
          </Panel>
        ))}
      </div>
      <div className="mt-4 grid gap-3 lg:grid-cols-2">
        <Panel title="Anomalies">
          {report?.anomalies.length ? report.anomalies.map((item) => (
            <p key={item.type + item.evidence.join()} className="mb-2 text-sm">{item.type}: {item.evidence.join(" ")}</p>
          )) : <p className="text-sm text-neutral-600">None crossed the configured thresholds.</p>}
        </Panel>
        <Panel title="Campaign changes">
          {report?.top_changes.length ? report.top_changes.map((item) => (
            <p key={item.name} className="mb-2 text-sm">{item.name}: spend {money(item.spend_delta)}, conversions {num(item.conversion_delta)}</p>
          )) : <p className="text-sm text-neutral-600">No material campaign movement.</p>}
        </Panel>
      </div>
      <div className="mt-4">
        <Panel title="Recommended actions">
          {report?.recommended_actions.map((item) => (
            <p key={item.action} className="mb-2 text-sm">{item.action}</p>
          ))}
        </Panel>
      </div>
    </Shell>
  );
}
