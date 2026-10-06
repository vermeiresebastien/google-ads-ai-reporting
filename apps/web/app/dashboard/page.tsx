"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { SeriesChart } from "@/components/series-chart";
import { Term } from "@/components/term";
import { Panel, Shell } from "@/components/shell";
import { api } from "@/lib/api";
import { money, num, pct } from "@/lib/format";
import { useAccountId } from "@/lib/use-account";

type Totals = Record<string, number | null>;
type Channel = Totals & {
  label: string;
  search_impression_share: number | null;
  search_budget_lost_impression_share: number | null;
};
type Waste = {
  name: string;
  campaign_name?: string;
  reasons: string[];
  metrics: { cost: number; clicks: number; conversions: number };
};
type TopChange = {
  campaign_id: string;
  name: string;
  bucket?: string;
  spend_delta: number;
  conversion_delta: number;
  value_delta?: number;
};
type Anomaly = {
  type: string;
  evidence: string[];
  confidence?: string;
};
type BudgetOpportunity = {
  name: string;
  evidence: string[];
  confidence?: string;
  budget_lost_impression_share?: number | null;
};
type EvidenceClaim = {
  claim: string;
  evidence: string[];
  confidence?: string;
};
type Report = {
  date: string;
  account: Totals;
  comparison: {
    changes: Record<string, { percent: number | null }>;
    period: Record<string, string>;
  };
  data_freshness?: {
    last_successful_sync?: string | null;
    datasets?: Record<string, string | null>;
  };
  channels: { channels: Channel[]; brand: Totals; other: Totals };
  series: { date: string; cost: number; conversions: number; cpa?: number | null; cpc?: number | null }[];
  change_marks: { date: string; label: string }[];
  top_changes?: TopChange[];
  anomalies?: Anomaly[];
  budget_opportunities?: BudgetOpportunity[];
  evidence?: EvidenceClaim[];
  wasted_spend: Waste[];
  recommended_actions: { action: string; evidence: string[]; confidence?: string }[];
};

const PERIODS = [
  ["yesterday_vs_prev7_avg", "Yesterday"],
  ["last_7_vs_prev_7", "Last 7 days"],
  ["last_30_vs_prev_30", "Last 30 days"],
  ["last_90_vs_prev_90", "Last 90 days"],
  ["month_to_date_vs_prev", "This month"],
  ["quarter_to_date_vs_prev", "This quarter"],
  ["all_time", "All time"],
] as const;

function share(value?: number | null) {
  if (value == null || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(1)}%`;
}

function Trend({ value, better }: { value: number | null | undefined; better: "up" | "down" | "either" }) {
  if (value == null) return <p className="text-sm text-neutral-500">No prior period</p>;
  const arrow = value > 0 ? "↑" : value < 0 ? "↓" : "→";
  const improved = better === "up" ? value > 0 : better === "down" ? value < 0 : false;
  const worsened = better !== "either" && value !== 0 && !improved;
  const color = improved ? "text-pine" : worsened ? "text-red-700" : "text-neutral-600";
  return <p className={`text-sm ${color}`}>{arrow} {pct(value)} vs previous period</p>;
}

function freshnessLabel(sync?: string | null) {
  if (!sync) return "No successful sync recorded — figures may be empty or stale.";
  return `Last successful sync ${sync}`;
}

export default function DashboardPage() {
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState("");
  const [kind, setKind] = useState<(typeof PERIODS)[number][0]>("last_30_vs_prev_30");

  const id = useAccountId();
  const label = PERIODS.find((item) => item[0] === kind)?.[1] ?? "Report";
  const period = report?.comparison.period;
  const normalization = period?.normalization;

  useEffect(() => {
    if (!id) return;
    setReport(null);
    setError("");
    api<Report>(`/api/reports/daily?account_id=${id}&kind=${kind}`)
      .then(setReport)
      .catch((reason: Error) => setError(reason.message));
  }, [id, kind]);

  const cards = [
    ["Spend", report?.account.cost, report?.comparison.changes.cost?.percent, money, "either"],
    ["Conversions", report?.account.conversions, report?.comparison.changes.conversions?.percent, num, "up"],
    ["Conversion value", report?.account.conversion_value, report?.comparison.changes.conversion_value?.percent, money, "up"],
    ["CPA", report?.account.cost_per_conversion, report?.comparison.changes.cost_per_conversion?.percent, money, "down"],
    ["ROAS", report?.account.roas, report?.comparison.changes.roas?.percent, num, "up"],
  ] as const;

  const topChanges = report?.top_changes ?? [];
  const anomalies = report?.anomalies ?? [];
  const budgets = report?.budget_opportunities ?? [];
  const evidence = report?.evidence ?? [];

  return (
    <Shell>
      <div className="mb-4 flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-2xl font-semibold">Account report</h1>
          <p className="text-sm text-neutral-600">
            {report && period
              ? `${label}: ${period.current_start} to ${period.current_end} versus ${period.baseline_start} to ${period.baseline_end}${normalization ? ` (${normalization})` : ""}`
              : id
                ? "Loading the comparison"
                : "Connect a Google Ads account to see a report."}
          </p>
          {report ? (
            <p className={`mt-1 text-xs ${report.data_freshness?.last_successful_sync ? "text-neutral-500" : "text-red-700"}`}>
              {freshnessLabel(report.data_freshness?.last_successful_sync)}
            </p>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <label className="text-sm text-neutral-600">
            Period
            <select
              className="ml-2 rounded-md border border-line bg-paper px-2 py-1"
              value={kind}
              onChange={(event) => setKind(event.target.value as (typeof PERIODS)[number][0])}
            >
              {PERIODS.map(([value, name]) => (
                <option key={value} value={value}>{name}</option>
              ))}
            </select>
          </label>
        </div>
      </div>
      {error ? <p className="mb-4 text-sm text-red-700">{error}</p> : null}

      <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-neutral-500">Executive summary</h2>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {cards.map(([title, value, change, format, better]) => (
          <Panel key={title} title={title}>
            <p className="text-2xl font-semibold">{format(value as number | null)}</p>
            <Trend value={change} better={better} />
          </Panel>
        ))}
      </div>
      {report ? (
        <p className="mt-2 text-sm text-neutral-600">
          <Term>Conversion rate</Term> {share(report.account.conversion_rate)} · <Term>CPC</Term> {money(report.account.average_cpc)}
        </p>
      ) : null}

      <div className="mt-4">
        <Panel title={report && period ? `Spend, conversions, and account edits · ${period.current_start} to ${period.current_end}` : "Spend, conversions, and account edits"}>
          <SeriesChart points={report?.series ?? []} changes={report?.change_marks ?? []} />
          {report?.change_marks?.length ? (
            <div className="mt-3 space-y-1 text-sm">
              {report.change_marks.slice(0, 8).map((mark) => (
                <p key={mark.date + mark.label}><span className="text-neutral-500">{mark.date}</span> {mark.label}</p>
              ))}
            </div>
          ) : report ? (
            <p className="mt-3 text-sm text-neutral-600">No account edits are stored for this period. Google only returns 30 days of change history, and only after that step of sync succeeds.</p>
          ) : null}
        </Panel>
      </div>

      <h2 className="mb-2 mt-6 text-sm font-semibold uppercase tracking-wide text-neutral-500">What changed</h2>
      <div className="grid gap-3 lg:grid-cols-2">
        <Panel title="Top campaign drivers">
          {topChanges.length ? (
            <ul className="space-y-2 text-sm">
              {topChanges.slice(0, 5).map((row) => (
                <li key={row.campaign_id} className="border-t border-line pt-2 first:border-t-0 first:pt-0">
                  <p className="font-medium">{row.name}</p>
                  <p className="text-neutral-600">
                    Spend Δ {money(row.spend_delta)} · Conv. Δ {num(row.conversion_delta)}
                    {row.value_delta != null ? ` · Value Δ ${money(row.value_delta)}` : ""}
                  </p>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-neutral-600">No campaign moved enough to list for this comparison.</p>
          )}
        </Panel>
        <Panel title="Evidence">
          {evidence.length ? (
            <ul className="space-y-2 text-sm">
              {evidence.map((item) => (
                <li key={item.claim} className="border-t border-line pt-2 first:border-t-0 first:pt-0">
                  <p className="font-medium">{item.claim}</p>
                  <p className="text-neutral-600">{item.evidence.join(" ")}</p>
                  {item.confidence ? <p className="text-xs text-neutral-500">{item.confidence} confidence</p> : null}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-neutral-600">No structured evidence claims for this period.</p>
          )}
        </Panel>
      </div>

      <h2 className="mb-2 mt-6 text-sm font-semibold uppercase tracking-wide text-neutral-500">Where the money is working</h2>
      <div className="grid gap-3 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <Panel title="By channel">
            {report?.channels.channels.length ? (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead className="text-neutral-500">
                    <tr>
                      <th className="py-2">Channel</th>
                      <th><Term>Spend</Term></th>
                      <th><Term>Conv.</Term></th>
                      <th><Term>CPA</Term></th>
                      <th><Term>ROAS</Term></th>
                      <th><Term>Impr. share</Term></th>
                      <th><Term>Lost to budget</Term></th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.channels.channels.map((row) => (
                      <tr key={row.label} className="border-t border-line">
                        <td className="py-2">{row.label}</td>
                        <td>{money(row.cost)}</td>
                        <td>{num(row.conversions)}</td>
                        <td>{money(row.cost_per_conversion)}</td>
                        <td>{num(row.roas)}</td>
                        <td>{share(row.search_impression_share)}</td>
                        <td>{share(row.search_budget_lost_impression_share)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : <p className="text-sm text-neutral-600">No campaign stats in this period.</p>}
          </Panel>
        </div>
        <Panel title="Brand vs other">
          <p className="text-sm">Brand campaigns · <Term>spend</Term> {money(report?.channels.brand.cost)} · <Term>CPA</Term> {money(report?.channels.brand.cost_per_conversion)} · <Term>ROAS</Term> {num(report?.channels.brand.roas)}</p>
          <p className="mt-2 text-sm">Other campaigns · <Term>spend</Term> {money(report?.channels.other.cost)} · <Term>CPA</Term> {money(report?.channels.other.cost_per_conversion)} · <Term>ROAS</Term> {num(report?.channels.other.roas)}</p>
          <p className="mt-3 text-xs text-neutral-500">Brand is any campaign whose name contains “brand”. Performance Max, Display, and YouTube stay in Other so they are not credited as high-intent search.</p>
        </Panel>
      </div>

      <h2 className="mb-2 mt-6 text-sm font-semibold uppercase tracking-wide text-neutral-500">Problems and opportunities</h2>
      <div className="grid gap-3 lg:grid-cols-2">
        <Panel title="Anomalies">
          {anomalies.length ? (
            <ul className="space-y-2 text-sm">
              {anomalies.slice(0, 6).map((item) => (
                <li key={item.type + (item.evidence[0] ?? "")} className="border-t border-line pt-2 first:border-t-0 first:pt-0">
                  <p className="font-medium">{item.type}</p>
                  <p className="text-neutral-600">{item.evidence.join(" ")}</p>
                  {item.confidence ? <p className="text-xs text-neutral-500">{item.confidence} confidence</p> : null}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-neutral-600">No anomaly crossed the configured thresholds.</p>
          )}
        </Panel>
        <Panel title="Budget opportunities">
          {budgets.length ? (
            <ul className="space-y-2 text-sm">
              {budgets.slice(0, 6).map((item) => (
                <li key={item.name} className="border-t border-line pt-2 first:border-t-0 first:pt-0">
                  <p className="font-medium">{item.name}</p>
                  <p className="text-neutral-600">{item.evidence.join(" ")}</p>
                  {item.confidence ? <p className="text-xs text-neutral-500">{item.confidence} confidence</p> : null}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-neutral-600">No budget opportunity has both a material constraint and acceptable efficiency.</p>
          )}
        </Panel>
      </div>

      <div className="mt-4">
        <Panel title="Search terms wasting spend">
          {report?.wasted_spend.length ? (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-neutral-500">
                  <tr>
                    <th className="py-2">Query</th>
                    <th>Campaign</th>
                    <th><Term>Spend</Term></th>
                    <th><Term>Clicks</Term></th>
                    <th><Term>Conv.</Term></th>
                  </tr>
                </thead>
                <tbody>
                  {report.wasted_spend.slice(0, 8).map((row) => (
                    <tr key={row.name + (row.campaign_name ?? "")} className="border-t border-line">
                      <td className="py-2">{row.name}</td>
                      <td>{row.campaign_name || "—"}</td>
                      <td>{money(row.metrics.cost)}</td>
                      <td>{num(row.metrics.clicks)}</td>
                      <td>{num(row.metrics.conversions)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : <p className="text-sm text-neutral-600">No query crossed the waste thresholds in this period.</p>}
        </Panel>
      </div>

      <div className="mt-4">
        <Panel title="Recommended actions">
          {report?.recommended_actions.length ? (
            report.recommended_actions.slice(0, 3).map((item, index) => (
              <div key={item.action} className="mb-3 text-sm last:mb-0">
                <p className="font-medium">{index + 1}. {item.action}</p>
                {item.evidence.length ? <p className="text-neutral-600">{item.evidence.join(" ")}</p> : null}
                {item.confidence ? <p className="text-xs text-neutral-500">{item.confidence} confidence</p> : null}
              </div>
            ))
          ) : (
            <p className="text-sm text-neutral-600">No recommended actions for this period.</p>
          )}
          <p className="mt-3 text-sm">
            <Link className="text-pine underline" href="/actions">
              Review and apply structured actions
            </Link>
          </p>
        </Panel>
      </div>
    </Shell>
  );
}
