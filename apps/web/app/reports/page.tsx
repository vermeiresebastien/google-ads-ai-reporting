"use client";

import { useEffect, useRef, useState } from "react";
import { AnnotatedSummary } from "@/components/annotated-summary";
import { HIGHLIGHT_CLASS, MarkdownAnswer, type SummaryHighlight } from "@/components/markdown-answer";
import { RangeCalendar } from "@/components/range-calendar";
import { Panel, Shell } from "@/components/shell";
import { API_URL, api, token } from "@/lib/api";
import { money, num, pct } from "@/lib/format";
import { useAccountId } from "@/lib/use-account";

type SavedReport = {
  id: string;
  report_date: string;
  kind: string;
  period_start: string | null;
  period_end: string | null;
  question: string;
  title: string;
  body: string;
  updated_at: string | null;
  highlights: SummaryHighlight[];
};

const PERIOD_LABELS: Record<string, string> = {
  today_vs_yesterday: "Yesterday to today",
  yesterday_vs_prev7_avg: "Yesterday",
  last_7_vs_prev_7: "Last 7 days",
  last_30_vs_prev_30: "Last 30 days",
  last_90_vs_prev_90: "Last 90 days",
  month_to_date_vs_prev: "This month",
  quarter_to_date_vs_prev: "This quarter",
  all_time: "All time",
};

type Totals = Record<string, number | null>;
type FeedReport = {
  date: string;
  data_freshness?: { last_successful_sync?: string | null; datasets?: Record<string, string | null> };
  account: Totals;
  comparison: {
    current?: Totals;
    baseline?: Totals;
    changes: Record<string, { percent: number | null; absolute?: number | null }>;
    period: Record<string, string>;
  };
  top_changes?: { name: string; bucket: string; spend_delta: number; conversion_delta: number; value_delta: number }[];
  anomalies?: { type: string; name?: string; evidence?: string[] }[];
  budget_opportunities?: unknown[];
  wasted_spend?: { name: string; campaign_name?: string; reasons: string[]; metrics: { cost: number } }[];
  recent_changes?: { change_type?: string; resource_type?: string; user_email?: string; event_timestamp?: string }[];
  recommended_actions?: { action: string; evidence?: string[] }[];
  channels?: { channels: { label: string; cost?: number | null; conversions?: number | null }[] };
};

type Council = {
  chairman: string;
  opinions: { model: string; response: string }[];
  rankings: { model: string; average_rank: number }[];
};

function kindForQuestion(question: string) {
  const text = question.toLowerCase();
  if (text.includes("quarter")) return "quarter_to_date_vs_prev";
  if (text.includes("month")) return "month_to_date_vs_prev";
  if (text.includes("90") || text.includes("history")) return "last_90_vs_prev_90";
  if (text.includes("today") || (text.includes("yesterday") && text.includes("change"))) return "today_vs_yesterday";
  if (text.includes("week") && !text.includes("yesterday")) return "last_7_vs_prev_7";
  if (text.includes("30")) return "last_30_vs_prev_30";
  return "yesterday_vs_prev7_avg";
}

function bucketLabel(bucket: string) {
  return bucket.replaceAll("_", " ");
}

function FeedOverview({ report, tools }: { report: FeedReport; tools: string[] }) {
  const [open, setOpen] = useState(false);
  const period = report.comparison.period;
  const kind = period.kind ?? "";
  const changes = report.comparison.changes ?? {};
  const sync = report.data_freshness?.last_successful_sync;
  const metrics = [
    ["Spend", report.account.cost, changes.cost?.percent, money],
    ["Conversions", report.account.conversions, changes.conversions?.percent, num],
    ["CPA", report.account.cost_per_conversion, changes.cost_per_conversion?.percent, money],
    ["ROAS", report.account.roas, changes.roas?.percent, num],
  ] as const;
  const movers = (report.top_changes ?? []).slice(0, 5);
  const channels = (report.channels?.channels ?? []).filter((item) => (item.cost ?? 0) > 0).slice(0, 6);
  const anomalies = report.anomalies ?? [];
  const waste = report.wasted_spend ?? [];
  const edits = report.recent_changes ?? [];
  const actions = report.recommended_actions ?? [];
  const budgets = report.budget_opportunities ?? [];

  return (
    <section className="rounded-xl border border-line bg-white p-4">
      <button type="button" className="flex w-full items-center justify-between text-left" aria-expanded={open} onClick={() => setOpen((value) => !value)}>
        <h2 className="text-sm font-semibold uppercase tracking-wide text-neutral-500">Data fed to the AI</h2>
        <span className="text-sm text-neutral-500">{open ? "Hide" : "Show"}</span>
      </button>
      {open ? (
        <div className="mt-4">
          <p className="mb-3 text-sm text-neutral-600">
            {PERIOD_LABELS[kind] ?? (kind || "Comparison")}: {period.current_start} to {period.current_end} versus {period.baseline_start}{" "}
            to {period.baseline_end}. As of {report.date}
            {sync ? ` · Last sync ${sync.slice(0, 19).replace("T", " ")}` : ""}.
          </p>
          <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {metrics.map(([label, value, change, format]) => (
              <div key={label}>
                <p className="text-xs uppercase tracking-wide text-neutral-500">{label}</p>
                <p className="text-lg font-semibold text-neutral-900">{format(value)}</p>
                <p className="text-xs text-neutral-600">{change == null ? "No prior period" : `${pct(change)} vs baseline`}</p>
              </div>
            ))}
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <div>
              <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-neutral-500">Campaign movers</h3>
              {movers.length === 0 ? (
                <p className="text-sm text-neutral-600">No material campaign moves in this window.</p>
              ) : (
                <ul className="space-y-1 text-sm text-neutral-800">
                  {movers.map((item) => (
                    <li key={`${item.name}-${item.bucket}`}>
                      <span className="font-medium">{item.name}</span>
                      <span className="text-neutral-500"> · {bucketLabel(item.bucket)}</span>
                      <span className="text-neutral-600">
                        {" "}
                        · spend {item.spend_delta >= 0 ? "+" : ""}
                        {money(item.spend_delta)}, conv {item.conversion_delta >= 0 ? "+" : ""}
                        {num(item.conversion_delta)}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div>
              <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-neutral-500">Signals in the JSON</h3>
              <ul className="space-y-1 text-sm text-neutral-800">
                <li>{anomalies.length} anomalies</li>
                <li>{waste.length} wasted-spend candidates</li>
                <li>{budgets.length} budget opportunities</li>
                <li>{edits.length} account edits in the period</li>
                <li>{actions.length} recommended actions</li>
                {tools.length ? <li>Tools selected for the question: {tools.join(", ")}</li> : null}
              </ul>
              {channels.length ? (
                <p className="mt-2 text-sm text-neutral-600">
                  Channels by spend:{" "}
                  {channels.map((item) => `${item.label} ${money(item.cost)}`).join(" · ")}
                </p>
              ) : null}
              {waste[0] ? (
                <p className="mt-2 text-sm text-neutral-600">
                  Top waste: {waste[0].name}
                  {waste[0].campaign_name ? ` in ${waste[0].campaign_name}` : ""} ({money(waste[0].metrics.cost)}
                  {waste[0].reasons[0] ? ` · ${waste[0].reasons[0]}` : ""})
                </p>
              ) : null}
              {edits[0] ? (
                <p className="mt-2 text-sm text-neutral-600">
                  Latest edit: {[edits[0].change_type, edits[0].resource_type].filter(Boolean).join(" ")}
                  {edits[0].user_email ? ` by ${edits[0].user_email}` : ""}
                  {edits[0].event_timestamp ? ` · ${String(edits[0].event_timestamp).slice(0, 16).replace("T", " ")}` : ""}
                </p>
              ) : null}
            </div>
          </div>
          <details className="mt-4">
            <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wide text-neutral-500">Raw JSON</summary>
            <pre className="mt-2 max-h-48 overflow-auto rounded-md border border-line bg-paper p-3 text-xs leading-5 text-neutral-800">
              {JSON.stringify(report, null, 2)}
            </pre>
          </details>
        </div>
      ) : null}
    </section>
  );
}

function savedForDay(reports: SavedReport[], asOf: string) {
  const daily = reports.filter(
    (item) => item.report_date === asOf && (item.kind.startsWith("ask:") || item.kind === "today_vs_yesterday"),
  );
  const asks = daily.filter((item) => item.kind.startsWith("ask:"));
  const pool = asks.length ? asks : daily;
  return [...pool].sort((left, right) => (right.updated_at ?? "").localeCompare(left.updated_at ?? ""))[0];
}

function fileSlug(value: string) {
  const slug = value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return slug.slice(0, 80) || "summary";
}

function pdfFileName(item: SavedReport, view: "full" | "note" | "period", rangeStart: string, rangeEnd: string) {
  if (view === "period") {
    const start = rangeStart || item.period_start || item.report_date;
    const end = rangeEnd || item.period_end || item.report_date;
    return start === end ? `${start}-highlights` : `${start}-to-${end}-highlights`;
  }
  const date = item.period_start || item.report_date;
  return `${date}-${fileSlug(summaryLabel(item))}-${view === "note" ? "highlights" : "full"}`;
}

function downloadPdf(name: string) {
  const previous = document.title;
  const restore = () => {
    document.title = previous;
    window.removeEventListener("afterprint", restore);
  };
  window.addEventListener("afterprint", restore);
  document.title = name;
  window.print();
}

function summaryLabel(item: SavedReport) {
  const custom = item.title?.trim();
  if (custom) return custom;
  if (item.kind.startsWith("ask:")) {
    const text = item.question.trim() || "Question";
    return text.length > 80 ? `${text.slice(0, 77)}…` : text;
  }
  return PERIOD_LABELS[item.kind] ?? item.kind;
}

function modelName(model: string) {
  const parts = model.split("/");
  return parts[parts.length - 1] || model;
}

function previousDay(iso: string) {
  const [year, month, day] = iso.split("-").map(Number);
  const value = new Date(Date.UTC(year, month - 1, day));
  value.setUTCDate(value.getUTCDate() - 1);
  return value.toISOString().slice(0, 10);
}

function covers(item: SavedReport, start: string, end: string) {
  const itemStart = item.period_start ?? item.report_date;
  const itemEnd = item.period_end ?? item.report_date;
  return itemStart <= end && itemEnd >= start;
}

function ReportProgress() {
  return (
    <div className="mb-3">
      <p className="mb-1 text-xs text-neutral-600">The council is writing this report.</p>
      <div className="h-2 overflow-hidden rounded-full bg-line" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-label="The council is writing this report">
        <div className="report-progress-bar h-full w-1/3 rounded-full bg-pine" />
      </div>
    </div>
  );
}

function HighlightBits({
  groups,
  empty,
  showTitles = false,
  onOpen,
}: {
  groups: { id: string; title: string; highlights: SummaryHighlight[] }[];
  empty: string;
  showTitles?: boolean;
  onOpen?: (id: string) => void;
}) {
  const filled = groups.filter((group) => group.highlights.length > 0);
  if (!filled.length) return <p className="text-sm text-neutral-600">{empty}</p>;
  return (
    <div className="space-y-4">
      {filled.map((group) => (
        <section key={group.id}>
          {showTitles ? (
            onOpen ? (
              <button type="button" className="mb-2 text-sm font-medium text-neutral-900" onClick={() => onOpen(group.id)}>
                {group.title}
              </button>
            ) : (
              <h2 className="mb-2 text-sm font-semibold text-neutral-900">{group.title}</h2>
            )
          ) : null}
          <ul className="space-y-2">
            {group.highlights.map((highlight) => (
              <li key={highlight.id}>
                <mark className={`rounded px-0.5 text-sm leading-6 text-inherit ${HIGHLIGHT_CLASS[highlight.color] ?? "bg-amber-200"}`}>
                  {highlight.quote}
                </mark>
                {highlight.note ? <p className="mt-1 text-xs italic text-neutral-700">{highlight.note}</p> : null}
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

export default function ReportsPage() {
  const [answer, setAnswer] = useState("");
  const [question, setQuestion] = useState("What happened in Google Ads yesterday, why did it happen, and what should I do today?");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [asking, setAsking] = useState(false);
  const [council, setCouncil] = useState<Council | null>(null);
  const [feed, setFeed] = useState<FeedReport | null>(null);
  const [feedTools, setFeedTools] = useState<string[]>([]);
  const [feedError, setFeedError] = useState("");
  const answerRef = useRef<HTMLDivElement>(null);
  const [exportError, setExportError] = useState("");
  const [archiveError, setArchiveError] = useState("");
  const [saved, setSaved] = useState<SavedReport[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [rename, setRename] = useState<{ id: string; where: "list" | "note" } | null>(null);
  const [draftTitle, setDraftTitle] = useState("");
  const [pendingDeleteId, setPendingDeleteId] = useState("");
  const skipRename = useRef(false);
  const [archiveOpen, setArchiveOpen] = useState(false);
  const [highlightView, setHighlightView] = useState<"full" | "note" | "period">("full");
  const [rangeStart, setRangeStart] = useState("");
  const [rangeEnd, setRangeEnd] = useState("");
  const [visibleMonth, setVisibleMonth] = useState(() => {
    const today = new Date();
    return { year: today.getFullYear(), month: today.getMonth() };
  });

  const id = useAccountId();
  const savedDates = new Set(saved.map((item) => item.report_date));
  const visible = rangeStart && rangeEnd ? saved.filter((item) => covers(item, rangeStart, rangeEnd)) : [];
  const selected = visible.find((item) => item.id === selectedId) ?? visible[0];
  const spanLabel = rangeStart && rangeStart === rangeEnd ? rangeStart : `${rangeStart} – ${rangeEnd}`;

  function setSpan(start: string, end: string) {
    if (!start || !end) return;
    const [from, to] = start <= end ? [start, end] : [end, start];
    setRangeStart(from);
    setRangeEnd(to);
    setSelectedId("");
  }

  function pickDay(iso: string) {
    if (!rangeStart || rangeStart !== rangeEnd) setSpan(iso, iso);
    else setSpan(rangeStart, iso);
  }

  function loadSaved(accountId: string) {
    return api<{ reports: SavedReport[]; as_of: string }>(`/api/reports/saved?account_id=${accountId}`)
      .then((payload) => {
        setSaved(payload.reports.filter((item) => !item.kind.startsWith("trend:")));
        return payload;
      })
      .catch(() => null);
  }

  function loadFeed(accountId: string, ask: string, tools: string[] = []) {
    const kind = kindForQuestion(ask);
    return api<FeedReport>(`/api/reports/daily?account_id=${accountId}&kind=${kind}&save=false`)
      .then((report) => {
        setFeed(report);
        setFeedTools(tools);
        setFeedError("");
        return report;
      })
      .catch((reason: Error) => {
        setFeedError(reason.message || "Could not load the AI data overview");
        return null;
      });
  }

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    setError("");
    setNotice("");
    setFeedError("");
    loadFeed(id, question);
    loadSaved(id).then(async (savedPayload) => {
      if (cancelled) return;
      const existing = savedPayload ? savedForDay(savedPayload.reports, savedPayload.as_of) : undefined;
      if (existing) {
        setAnswer(existing.body);
        setCouncil(null);
        if (existing.question) {
          setQuestion(existing.question);
          loadFeed(id, existing.question);
        }
        return;
      }
      setAsking(true);
      try {
        const payload = await api<{
          answer: string;
          council?: Council | null;
          report?: FeedReport;
          tools?: string[];
        }>("/api/ai/query", {
          method: "POST",
          body: JSON.stringify({ account_id: id, question }),
        });
        if (cancelled) return;
        setAnswer(payload.answer);
        setCouncil(payload.council ?? null);
        if (payload.report) {
          setFeed(payload.report);
          setFeedTools(payload.tools ?? []);
          setFeedError("");
        } else {
          loadFeed(id, question, payload.tools ?? []);
        }
        loadSaved(id);
      } catch (reason) {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "Query failed");
      } finally {
        if (!cancelled) setAsking(false);
      }
    });
    return () => {
      cancelled = true;
    };
    // A saved daily report is shown as-is. A new one is written only when that day has none.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  useEffect(() => {
    if (rangeStart || saved.length === 0) return;
    const latest = saved[0].report_date;
    setRangeStart(latest);
    setRangeEnd(latest);
    const [year, month] = latest.split("-").map(Number);
    if (year && month) setVisibleMonth({ year, month: month - 1 });
  }, [saved, rangeStart]);

  async function addHighlight(reportId: string, quote: string, color: string, note: string) {
    if (!id) return;
    const created = await api<SummaryHighlight>(`/api/reports/saved/${reportId}/highlights?account_id=${id}`, {
      method: "POST",
      body: JSON.stringify({ quote, color, note }),
    });
    setSaved((current) =>
      current.map((item) => (item.id === reportId ? { ...item, highlights: [...(item.highlights ?? []), created] } : item)),
    );
  }

  async function removeHighlight(reportId: string, highlightId: string) {
    if (!id) return;
    setArchiveError("");
    try {
      await api(`/api/reports/saved/${reportId}/highlights/${highlightId}?account_id=${id}`, { method: "DELETE" });
      setSaved((current) =>
        current.map((item) =>
          item.id === reportId
            ? { ...item, highlights: (item.highlights ?? []).filter((highlight) => highlight.id !== highlightId) }
            : item,
        ),
      );
    } catch (reason) {
      setArchiveError(reason instanceof Error ? reason.message : "Could not remove the highlight");
    }
  }

  function beginRename(item: SavedReport, where: "list" | "note") {
    skipRename.current = false;
    setSelectedId(item.id);
    setRename({ id: item.id, where });
    setDraftTitle(summaryLabel(item));
  }

  async function commitRename(item: SavedReport) {
    if (skipRename.current) {
      skipRename.current = false;
      return;
    }
    const next = draftTitle.trim();
    setRename(null);
    if (!id || next === summaryLabel(item)) return;
    setArchiveError("");
    try {
      const renamed = await api<{ id: string; title: string }>(`/api/reports/saved/${item.id}?account_id=${id}`, {
        method: "PATCH",
        body: JSON.stringify({ title: next }),
      });
      setSaved((current) => current.map((row) => (row.id === item.id ? { ...row, title: renamed.title } : row)));
    } catch (reason) {
      setArchiveError(reason instanceof Error ? reason.message : "Could not rename the summary");
    }
  }

  async function saveBody(reportId: string, body: string) {
    if (!id) return;
    setArchiveError("");
    const updated = await api<{ id: string; title?: string; body?: string }>(`/api/reports/saved/${reportId}?account_id=${id}`, {
      method: "PATCH",
      body: JSON.stringify({ body }),
    });
    if (typeof updated.body !== "string") {
      throw new Error("Could not save the note. Restart the API and try again.");
    }
    setSaved((current) =>
      current.map((row) =>
        row.id === reportId
          ? { ...row, body: updated.body as string, ...(typeof updated.title === "string" ? { title: updated.title } : {}) }
          : row,
      ),
    );
  }

  async function removeSaved(reportId: string) {
    if (!id) return;
    setPendingDeleteId("");
    setArchiveError("");
    try {
      await api(`/api/reports/saved/${reportId}?account_id=${id}`, { method: "DELETE" });
      setSaved((current) => current.filter((item) => item.id !== reportId));
      if (selectedId === reportId) setSelectedId("");
      if (rename?.id === reportId) setRename(null);
    } catch (reason) {
      setArchiveError(reason instanceof Error ? reason.message : "Delete failed");
    }
  }

  async function downloadZip() {
    if (!id || !rangeStart || !rangeEnd) return;
    setExportError("");
    try {
      const response = await fetch(`${API_URL}/api/reports/saved/export?account_id=${id}&start=${rangeStart}&end=${rangeEnd}`, {
        headers: token() ? { Authorization: `Bearer ${token()}` } : {},
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(typeof body.detail === "string" ? body.detail : "Download failed");
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      const header = response.headers.get("Content-Disposition") ?? "";
      const match = header.match(/filename="([^"]+)"/);
      link.href = url;
      const fallback = rangeStart === rangeEnd ? `${previousDay(rangeStart)} to ${rangeStart}.zip` : `${rangeStart} to ${rangeEnd}.zip`;
      link.download = match?.[1] ?? fallback;
      link.click();
      URL.revokeObjectURL(url);
    } catch (reason) {
      setExportError(reason instanceof Error ? reason.message : "Download failed");
    }
  }

  async function ask(event: React.FormEvent) {
    event.preventDefault();
    if (!id || asking) return;
    setAsking(true);
    setError("");
    setNotice("");
    try {
      const payload = await api<{
        answer: string;
        llm_error: string | null;
        notice?: string | null;
        council?: Council | null;
        report?: FeedReport;
        tools?: string[];
      }>("/api/ai/query", {
        method: "POST",
        body: JSON.stringify({ account_id: id, question }),
      });
      setAnswer(payload.answer);
      setCouncil(payload.council ?? null);
      if (payload.report) {
        setFeed(payload.report);
        setFeedTools(payload.tools ?? []);
        setFeedError("");
      } else {
        await loadFeed(id, question, payload.tools ?? []);
      }
      if (payload.notice) setNotice(`${payload.notice} Showing the calculated report.`);
      else if (payload.llm_error === "rate_limit") setNotice("The council models are out of requests for now. Showing the calculated report.");
      else if (payload.llm_error) setNotice("The model did not answer. Showing the calculated report.");
      if (id) loadSaved(id);
      answerRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Query failed");
    } finally {
      setAsking(false);
    }
  }

  const selectedPeriod = selected
    ? selected.period_start && selected.period_end
      ? `${selected.period_start} – ${selected.period_end}`
      : selected.report_date
    : "";

  return (
    <>
    <div className="print:hidden">
    <Shell>
      <h1 className="mb-4 text-2xl font-semibold">Reports</h1>
      {feedError ? <p className="mb-3 text-sm text-red-700">{feedError}</p> : null}
      {feed ? (
        <div className="mb-4">
          <FeedOverview report={feed} tools={feedTools} />
        </div>
      ) : !feedError ? (
        <p className="mb-4 text-sm text-neutral-600">Loading the numbers the AI will use…</p>
      ) : null}
      <form onSubmit={ask} className="mb-4 flex flex-col gap-2 sm:flex-row">
        <input className="flex-1 rounded-md border border-line px-3 py-2 text-sm" value={question} onChange={(event) => setQuestion(event.target.value)} />
        <button className="rounded-md bg-pine px-3 py-2 text-sm text-white disabled:opacity-60" type="submit" disabled={asking || !id}>
          {asking ? "Asking…" : "Ask"}
        </button>
      </form>
      {error ? <p className="mb-3 text-sm text-red-700">{error}</p> : null}
      {notice ? <p className="mb-3 text-sm text-neutral-600">{notice}</p> : null}
      {asking ? <ReportProgress /> : null}
      {archiveOpen && (answer || council) ? null : (
      <div ref={answerRef}>
      <Panel title={council ? `Council chairman · ${modelName(council.chairman)}` : "Analyst"}>
        {answer ? <MarkdownAnswer text={answer} /> : <p className="text-sm text-neutral-600">Preparing the report from the analytical tools.</p>}
      </Panel>
      {council ? (
        <section className="mt-4 rounded-xl border border-line bg-white p-4">
          <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-neutral-500">Council opinions</h2>
          {council.rankings.length ? (
            <p className="mb-3 text-sm text-neutral-600">
              Peer rank, best first: {council.rankings.map((item) => `${modelName(item.model)} (${item.average_rank})`).join(", ")}
            </p>
          ) : null}
          <div className="space-y-2">
            {council.opinions.map((item) => (
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
      <section className="mt-6 rounded-xl border border-line bg-white p-4">
        <button
          type="button"
          className="flex w-full items-center justify-between text-left"
          aria-expanded={archiveOpen}
          onClick={() => setArchiveOpen((open) => !open)}
        >
          <h2 className="text-sm font-semibold uppercase tracking-wide text-neutral-500">
            Saved summaries{saved.length ? ` (${saved.length})` : ""}
          </h2>
          <span className="text-sm text-neutral-500">{archiveOpen ? "Hide" : "Show"}</span>
        </button>
        {archiveOpen ? (
          <div className="mt-4">
            {saved.length === 0 ? (
              <p className="text-sm text-neutral-600">Summaries are kept when you open a period on the dashboard or ask a question here.</p>
            ) : (
              <div className="grid gap-4 lg:grid-cols-[11rem_1fr]">
                <div>
                  <RangeCalendar
                    year={visibleMonth.year}
                    month={visibleMonth.month}
                    onMonth={setVisibleMonth}
                    start={rangeStart}
                    end={rangeEnd}
                    marked={savedDates}
                    onPick={pickDay}
                    onSpan={setSpan}
                    hint="Start day, then end day. Dots mark a saved summary."
                  />
                  <button type="button" className="mt-2 w-full rounded-md bg-pine px-2 py-1 text-xs text-white disabled:opacity-40" disabled={!rangeStart || !rangeEnd} onClick={downloadZip}>
                    Download zip
                  </button>
                  <p className="mt-2 text-xs text-neutral-500">Each file is that day’s change from the day before.</p>
                  {exportError ? <p className="mt-2 text-xs text-red-700">{exportError}</p> : null}
                  {archiveError ? <p className="mt-2 text-xs text-red-700">{archiveError}</p> : null}
                </div>
                <div>
                  {visible.length === 0 ? (
                    <p className="text-sm text-neutral-600">{rangeStart ? `No saved summary covers ${spanLabel}.` : "Pick a start and end date to read summaries for that period."}</p>
                  ) : (
                    <>
                      <div className="mb-3 flex flex-wrap gap-2">
                        {visible.map((item) => (
                          <div
                            key={item.id}
                            className={`rounded-md border px-2 py-1 text-sm ${selected?.id === item.id ? "border-pine bg-paper" : "border-line"}`}
                            onClick={() => setSelectedId(item.id)}
                          >
                            {rename?.id === item.id && rename.where === "list" ? (
                              <input
                                aria-label="Summary title"
                                className="w-full rounded border border-line bg-white px-1 py-0.5 text-sm"
                                value={draftTitle}
                                autoFocus
                                onClick={(event) => event.stopPropagation()}
                                onChange={(event) => setDraftTitle(event.target.value)}
                                onBlur={() => commitRename(item)}
                                onKeyDown={(event) => {
                                  if (event.key === "Enter") {
                                    event.preventDefault();
                                    event.currentTarget.blur();
                                  }
                                  if (event.key === "Escape") {
                                    event.preventDefault();
                                    skipRename.current = true;
                                    setRename(null);
                                  }
                                }}
                              />
                            ) : (
                              <span
                                className={`block ${selected?.id === item.id ? "font-medium" : ""}`}
                                title="Double-click to rename"
                                onDoubleClick={(event) => {
                                  event.stopPropagation();
                                  beginRename(item, "list");
                                }}
                              >
                                {summaryLabel(item)}
                              </span>
                            )}
                            <span className="block text-xs text-neutral-500">{item.period_start && item.period_end ? `${item.period_start} – ${item.period_end}` : item.report_date}</span>
                            <span className="block text-xs text-neutral-500">Saved {item.report_date}</span>
                          </div>
                        ))}
                      </div>
                      {selected ? (
                        <div>
                          <div className="mb-2 flex items-start justify-between gap-3">
                            {rename?.id === selected.id && rename.where === "note" ? (
                              <input
                                aria-label="Summary title"
                                className="min-w-0 flex-1 rounded border border-line bg-white px-2 py-1 text-base font-semibold"
                                value={draftTitle}
                                autoFocus
                                onChange={(event) => setDraftTitle(event.target.value)}
                                onBlur={() => commitRename(selected)}
                                onKeyDown={(event) => {
                                  if (event.key === "Enter") {
                                    event.preventDefault();
                                    event.currentTarget.blur();
                                  }
                                  if (event.key === "Escape") {
                                    event.preventDefault();
                                    skipRename.current = true;
                                    setRename(null);
                                  }
                                }}
                              />
                            ) : (
                              <h3
                                className="text-base font-semibold text-neutral-900"
                                title="Double-click to rename"
                                onDoubleClick={() => beginRename(selected, "note")}
                              >
                                {summaryLabel(selected)}
                              </h3>
                            )}
                            <div className="flex shrink-0 gap-3">
                              <button type="button" className="text-xs text-pine" onClick={() => downloadPdf(pdfFileName(selected, highlightView, rangeStart, rangeEnd))}>
                                Download PDF
                              </button>
                              <button type="button" className="text-xs text-red-700" onClick={() => setPendingDeleteId(selected.id)}>
                                Delete
                              </button>
                            </div>
                          </div>
                          <div className="mb-3 flex flex-wrap gap-2" role="group" aria-label="What to show">
                            {(
                              [
                                ["full", "Full note"],
                                ["note", "Highlights in this note"],
                                ["period", "Highlights in this period"],
                              ] as const
                            ).map(([value, label]) => (
                              <button
                                key={value}
                                type="button"
                                aria-pressed={highlightView === value}
                                className={`rounded-md border px-2 py-1 text-xs ${highlightView === value ? "border-pine bg-paper font-medium" : "border-line"}`}
                                onClick={() => setHighlightView(value)}
                              >
                                {label}
                              </button>
                            ))}
                          </div>
                          {highlightView === "full" ? (
                            <AnnotatedSummary
                              text={selected.body}
                              highlights={selected.highlights ?? []}
                              noteKey={selected.id}
                              onAdd={(quote, color, note) => addHighlight(selected.id, quote, color, note)}
                              onRemove={(highlightId) => removeHighlight(selected.id, highlightId)}
                              onSave={(body) => saveBody(selected.id, body)}
                            />
                          ) : highlightView === "note" ? (
                            <HighlightBits
                              groups={[{ id: selected.id, title: summaryLabel(selected), highlights: selected.highlights ?? [] }]}
                              empty="This note has no highlighted text."
                            />
                          ) : (
                            <HighlightBits
                              groups={visible.map((item) => ({ id: item.id, title: summaryLabel(item), highlights: item.highlights ?? [] }))}
                              empty={`No highlighted text in ${spanLabel}.`}
                              showTitles
                              onOpen={setSelectedId}
                            />
                          )}
                        </div>
                      ) : null}
                    </>
                  )}
                </div>
              </div>
            )}
          </div>
        ) : null}
      </section>
      {pendingDeleteId ? (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/30 p-4" role="presentation" onClick={() => setPendingDeleteId("")}>
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-summary-title"
            className="w-full max-w-sm rounded-lg border border-line bg-white p-4 shadow-lg"
            onClick={(event) => event.stopPropagation()}
          >
            <h3 id="delete-summary-title" className="text-base font-semibold text-neutral-900">Delete this saved summary?</h3>
            <p className="mt-2 text-sm text-neutral-600">The summary and its highlights will be removed.</p>
            <div className="mt-4 flex justify-end gap-2">
              <button type="button" className="rounded-md border border-line px-3 py-1.5 text-sm" onClick={() => setPendingDeleteId("")}>
                Cancel
              </button>
              <button type="button" className="rounded-md bg-red-700 px-3 py-1.5 text-sm text-white" onClick={() => removeSaved(pendingDeleteId)}>
                Delete
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </Shell>
    </div>
    <article className="hidden bg-white p-8 text-neutral-900 print:block">
      {highlightView === "period" ? (
        <>
          <h1 className="mb-6 text-2xl font-semibold">Highlights · {spanLabel}</h1>
          <HighlightBits
            groups={visible.map((item) => ({ id: item.id, title: summaryLabel(item), highlights: item.highlights ?? [] }))}
            empty={`No highlighted text in ${spanLabel}.`}
            showTitles
          />
        </>
      ) : selected ? (
        <>
          <h1 className="mb-1 text-2xl font-semibold">{summaryLabel(selected)}</h1>
          <p className="mb-6 text-sm text-neutral-600">
            {selectedPeriod} · Saved {selected.report_date}
          </p>
          {highlightView === "note" ? (
            <HighlightBits
              groups={[{ id: selected.id, title: summaryLabel(selected), highlights: selected.highlights ?? [] }]}
              empty="This note has no highlighted text."
            />
          ) : (
            <MarkdownAnswer text={selected.body} highlights={selected.highlights ?? []} forPrint />
          )}
        </>
      ) : null}
    </article>
    </>
  );
}
