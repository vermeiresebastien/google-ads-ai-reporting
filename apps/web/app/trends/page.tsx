"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { DateRangePicker, type DateSpan } from "@/components/date-range";
import { MarkdownAnswer } from "@/components/markdown-answer";
import { SavedNotePrint, SavedNotes, type NotePrint, type SavedNote } from "@/components/saved-notes";
import { MetricChart, SeriesChart } from "@/components/series-chart";
import { Panel, Shell } from "@/components/shell";
import { Term } from "@/components/term";
import { api } from "@/lib/api";
import { describeRange, money, num, pct, rangeError, recentRange } from "@/lib/format";
import { useAccountId } from "@/lib/use-account";

type Movement = {
  metric: string;
  label: string;
  earlier: number | null;
  later: number | null;
  percent: number | null;
  direction: "steady" | "up" | "down" | "improving" | "worsening";
};

type CampaignMove = {
  campaign_id: string;
  name: string;
  earlier_cost: number;
  later_cost: number;
  spend_delta: number;
  earlier_conversions: number;
  later_conversions: number;
  conversion_delta: number;
};

type Trends = {
  days: number;
  earlier: { start: string | null; end: string | null };
  later: { start: string | null; end: string | null };
  account: Record<string, number | null>;
  series: {
    date: string;
    cost: number;
    conversions: number;
    cost_per_conversion: number | null;
    average_cpc: number | null;
    roas: number | null;
    conversion_rate: number | null;
  }[];
  movements: Movement[];
  campaigns: CampaignMove[];
  findings: string[];
};

const METRICS = [
  ["cost_per_conversion", "CPA", money, false],
  ["roas", "ROAS", num, false],
  ["average_cpc", "CPC", money, false],
  ["conversion_rate", "Conversion rate", pct, true],
] as const;

const initialRange = recentRange(90);
const DEFAULT_STRATEGY_QUESTION =
  "Write a long-term overview of this period: what changed from the earlier half to the later half, which campaigns drove it, and what strategic direction the evidence supports.";

type Council = {
  chairman: string;
  opinions: { model: string; response: string }[];
  rankings: { model: string; average_rank: number }[];
};

function modelName(model: string) {
  const parts = model.split("/");
  return parts[parts.length - 1] || model;
}

function tone(direction: Movement["direction"]) {
  if (direction === "improving") return "text-pine";
  if (direction === "worsening") return "text-red-700";
  return "text-neutral-600";
}

function arrow(direction: Movement["direction"], percent: number | null) {
  if (direction === "steady" || percent == null || percent === 0) return "→";
  return percent > 0 ? "↑" : "↓";
}

export default function TrendsPage() {
  const [report, setReport] = useState<Trends | null>(null);
  const [error, setError] = useState("");
  const [span, setSpan] = useState<DateSpan>({ ...initialRange, preset: 90 });
  const [metric, setMetric] = useState<(typeof METRICS)[number][0]>("cost_per_conversion");
  const [strategyQuestion, setStrategyQuestion] = useState(DEFAULT_STRATEGY_QUESTION);
  const [strategyAnswer, setStrategyAnswer] = useState("");
  const [strategyCouncil, setStrategyCouncil] = useState<Council | null>(null);
  const [strategyError, setStrategyError] = useState("");
  const [strategyNotice, setStrategyNotice] = useState("");
  const [asking, setAsking] = useState(false);
  const [answeredSpan, setAnsweredSpan] = useState("");
  const strategyRef = useRef<HTMLDivElement>(null);
  const strategyRequest = useRef(0);
  const [notes, setNotes] = useState<SavedNote[]>([]);
  const [focusId, setFocusId] = useState("");
  const [printState, setPrintState] = useState<NotePrint | null>(null);
  const [savedOpen, setSavedOpen] = useState(false);
  const onPrint = useCallback((state: NotePrint) => setPrintState(state), []);
  const onSavedOpen = useCallback((open: boolean) => setSavedOpen(open), []);

  const id = useAccountId();

  const loadNotes = useCallback((accountId: string) => {
    api<{ reports: SavedNote[] }>(`/api/reports/saved?account_id=${accountId}`)
      .then((payload) => setNotes(payload.reports.filter((item) => item.kind.startsWith("trend:"))))
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    if (id) loadNotes(id);
  }, [id, loadNotes]);
  const problem = rangeError(span.start, span.end);
  const selected = METRICS.find((item) => item[0] === metric) ?? METRICS[0];
  const movements = new Map(report?.movements.map((item) => [item.metric, item]) ?? []);

  useEffect(() => {
    if (!id || problem) return;
    setReport(null);
    setError("");
    strategyRequest.current += 1;
    setStrategyAnswer("");
    setStrategyCouncil(null);
    setStrategyError("");
    setStrategyNotice("");
    setAnsweredSpan("");
    api<Trends>(`/api/trends?account_id=${id}&start_date=${span.start}&end_date=${span.end}`)
      .then(setReport)
      .catch((reason: Error) => setError(reason.message));
  }, [id, span.start, span.end, problem]);

  async function askStrategy(event: React.FormEvent) {
    event.preventDefault();
    if (!id || problem || asking) return;
    const request = strategyRequest.current;
    setAsking(true);
    setStrategyError("");
    setStrategyNotice("");
    try {
      const payload = await api<{
        answer: string;
        llm_error: string | null;
        notice?: string | null;
        council?: Council | null;
        start_date: string;
        end_date: string;
        saved_id?: string | null;
      }>("/api/ai/strategy", {
        method: "POST",
        body: JSON.stringify({
          account_id: id,
          question: strategyQuestion,
          start_date: span.start,
          end_date: span.end,
        }),
      });
      if (id) loadNotes(id);
      if (request !== strategyRequest.current) return;
      if (payload.saved_id) setFocusId(payload.saved_id);
      setStrategyAnswer(payload.answer);
      setStrategyCouncil(payload.council ?? null);
      setAnsweredSpan(`${payload.start_date} to ${payload.end_date}`);
      if (payload.notice) setStrategyNotice(`${payload.notice} Showing the calculated overview.`);
      else if (payload.llm_error === "rate_limit") setStrategyNotice("The council models are out of requests for now. Showing the calculated overview.");
      else if (payload.llm_error) setStrategyNotice("The model did not answer. Showing the calculated overview.");
      strategyRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (reason) {
      setStrategyError(reason instanceof Error ? reason.message : "The council did not answer");
    } finally {
      setAsking(false);
    }
  }

  const cards = [
    ["Spend", "cost", money],
    ["Conversions", "conversions", num],
    ["CPA", "cost_per_conversion", money],
    ["ROAS", "roas", num],
  ] as const;

  return (
    <>
    <div className="print:hidden">
    <Shell>
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Trends</h1>
          <p className="text-sm text-neutral-600">
            {report?.earlier.start && report.later.start
              ? `${describeRange(span.start, span.end, span.preset)}: later half ${report.later.start} to ${report.later.end} versus earlier half ${report.earlier.start} to ${report.earlier.end}`
              : id
                ? "How the account moved across the whole period."
                : "Connect a Google Ads account to see trends."}
          </p>
        </div>
        <DateRangePicker value={span} onChange={setSpan} />
      </div>
      {error ? <p className="mb-4 text-sm text-red-700">{error}</p> : null}
      {problem ? <p className="mb-4 text-sm text-red-700">{problem}</p> : null}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {cards.map(([title, key, format]) => {
          const move = movements.get(key);
          return (
            <Panel key={key} title={title}>
              <p className="text-2xl font-semibold">{format(move?.later ?? report?.account[key])}</p>
              <p className={`text-sm ${tone(move?.direction ?? "steady")}`}>
                {move
                  ? `${arrow(move.direction, move.percent)} ${pct(move.percent)} vs earlier half`
                  : report
                    ? "Not enough days to compare halves"
                    : "Loading the comparison"}
              </p>
            </Panel>
          );
        })}
      </div>
      {report ? (
        <p className="mt-2 text-sm text-neutral-600">
          Whole period · <Term>spend</Term> {money(report.account.cost)} · <Term>conversions</Term> {num(report.account.conversions)} · <Term>CPA</Term> {money(report.account.cost_per_conversion)} · <Term>ROAS</Term> {num(report.account.roas)}
        </p>
      ) : null}

      <div className="mt-4">
        <Panel title="What changed across the period">
          {report?.findings.length ? (
            <div className="space-y-2 text-sm">
              {report.findings.map((line) => (
                <p key={line}>{line}</p>
              ))}
            </div>
          ) : (
            <p className="text-sm text-neutral-600">{id && !problem ? "Loading the trend." : "Choose an account and a period."}</p>
          )}
        </Panel>
      </div>

      <div className="mt-4">
        <Panel title="Spend and conversions by day">
          <SeriesChart
            points={(report?.series ?? []).map((point) => ({
              date: point.date,
              cost: point.cost,
              conversions: point.conversions,
              cpa: point.cost_per_conversion,
              cpc: point.average_cpc,
            }))}
          />
        </Panel>
      </div>

      <div className="mt-4">
        <Panel title="Efficiency by day">
          <div className="mb-3 flex flex-wrap gap-2">
            {METRICS.map(([value, name]) => (
              <button
                key={value}
                type="button"
                className={`rounded-full border px-3 py-1 text-sm ${metric === value ? "border-pine bg-pine text-white" : "border-line text-neutral-600"}`}
                onClick={() => setMetric(value)}
              >
                <Term>{name}</Term>
              </button>
            ))}
          </div>
          <MetricChart
            label={selected[1]}
            format={selected[2]}
            percent={selected[3]}
            points={(report?.series ?? []).map((point) => ({ date: point.date, value: point[selected[0]] }))}
          />
        </Panel>
      </div>

      <div className="mt-4">
        <Panel title="Campaigns, earlier half to later half">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-neutral-500">
                <tr>
                  <th className="py-2">Campaign</th>
                  <th><Term>Earlier spend</Term></th>
                  <th><Term>Later spend</Term></th>
                  <th><Term>Spend change</Term></th>
                  <th><Term>Earlier conv.</Term></th>
                  <th><Term>Later conv.</Term></th>
                  <th><Term>Conv. change</Term></th>
                </tr>
              </thead>
              <tbody>
                {report && report.campaigns.length === 0 ? (
                  <tr><td className="py-3 text-neutral-600" colSpan={7}>No campaign movement in this range.</td></tr>
                ) : null}
                {(report?.campaigns ?? []).map((row) => (
                  <tr key={row.campaign_id} className="border-t border-line">
                    <td className="py-2">
                      <Link className="text-pine" href={`/campaigns/${row.campaign_id}?start=${span.start}&end=${span.end}`}>{row.name}</Link>
                    </td>
                    <td>{money(row.earlier_cost)}</td>
                    <td>{money(row.later_cost)}</td>
                    <td>{row.spend_delta > 0 ? "+" : ""}{money(row.spend_delta)}</td>
                    <td>{num(row.earlier_conversions)}</td>
                    <td>{num(row.later_conversions)}</td>
                    <td>{num(row.conversion_delta)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      </div>

      <section className="mt-6">
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-neutral-500">Long-term council</h2>
        <p className="mb-3 text-sm text-neutral-600">
          Ask for an overview or a strategic question about {describeRange(span.start, span.end, span.preset)}. The council uses this period’s earlier and later halves, not the day-to-day report.
        </p>
        <form onSubmit={askStrategy} className="mb-4 flex flex-col gap-2">
          <textarea
            className="min-h-24 rounded-md border border-line px-3 py-2 text-sm"
            value={strategyQuestion}
            onChange={(event) => setStrategyQuestion(event.target.value)}
            aria-label="Long-term question"
          />
          <div>
            <button className="rounded-md bg-pine px-3 py-2 text-sm text-white disabled:opacity-60" type="submit" disabled={asking || !id || Boolean(problem)}>
              {asking ? "Asking…" : "Ask the council"}
            </button>
          </div>
        </form>
        {strategyError ? <p className="mb-3 text-sm text-red-700">{strategyError}</p> : null}
        {strategyNotice ? <p className="mb-3 text-sm text-neutral-600">{strategyNotice}</p> : null}
        {asking ? (
          <div className="mb-3">
            <p className="mb-1 text-xs text-neutral-600">The council is writing the long-term overview.</p>
            <div className="h-2 overflow-hidden rounded-full bg-line" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-label="The council is writing the long-term overview">
              <div className="report-progress-bar h-full w-1/3 rounded-full bg-pine" />
            </div>
          </div>
        ) : null}
        {savedOpen && (strategyAnswer || strategyCouncil) ? null : (
        <div ref={strategyRef}>
          <Panel title={strategyCouncil ? `Council chairman · ${modelName(strategyCouncil.chairman)}` : "Long-term overview"}>
            {strategyAnswer ? (
              <>
                {answeredSpan ? <p className="mb-3 text-xs text-neutral-500">{answeredSpan}</p> : null}
                <MarkdownAnswer text={strategyAnswer} />
              </>
            ) : (
              <p className="text-sm text-neutral-600">Ask the council when you want a long-term overview or a strategic answer for this period.</p>
            )}
          </Panel>
          {strategyCouncil ? (
            <section className="mt-4 rounded-xl border border-line bg-white p-4">
              <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-neutral-500">Council opinions</h2>
              {strategyCouncil.rankings.length ? (
                <p className="mb-3 text-sm text-neutral-600">
                  Peer rank, best first: {strategyCouncil.rankings.map((item) => `${modelName(item.model)} (${item.average_rank})`).join(", ")}
                </p>
              ) : null}
              <div className="space-y-2">
                {strategyCouncil.opinions.map((item) => (
                  <details key={item.model} className="rounded-md border border-line px-3 py-2">
                    <summary className="cursor-pointer text-sm font-medium">{modelName(item.model)}</summary>
                    <div className="mt-2">
                      <MarkdownAnswer text={item.response} />
                    </div>
                  </details>
                ))}
              </div>
            </section>
          ) : null}
        </div>
        )}
      </section>
      {id ? (
        <SavedNotes
          notes={notes}
          accountId={id}
          zipPath="/api/trends/saved/export"
          focusId={focusId}
          onReload={() => loadNotes(id)}
          onPrint={onPrint}
          onExpandedChange={onSavedOpen}
        />
      ) : null}
    </Shell>
    </div>
    <SavedNotePrint state={printState} />
    </>
  );
}
