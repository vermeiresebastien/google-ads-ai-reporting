"use client";

import { useEffect, useState } from "react";
import { DateRangePicker, type DateSpan } from "@/components/date-range";
import { Shell } from "@/components/shell";
import { api } from "@/lib/api";
import { recentRange } from "@/lib/format";
import { useAccountId } from "@/lib/use-account";

const REPORT_KINDS = [
  ["yesterday_vs_prev7_avg", "Yesterday"],
  ["today_vs_yesterday", "Yesterday to today"],
  ["last_7_vs_prev_7", "Last 7 days"],
  ["last_30_vs_prev_30", "Last 30 days"],
  ["last_90_vs_prev_90", "Last 90 days"],
  ["month_to_date_vs_prev", "This month"],
  ["quarter_to_date_vs_prev", "This quarter"],
  ["all_time", "All time"],
] as const;

const STRATEGY_NOTE =
  "For strategy questions, the council also receives a short preface telling it this is a long-term half-vs-half overview with a weekly series, not a day-to-day report.";

type TrendsPayload = {
  ai_context?: unknown;
};

function downloadJson(filename: string, value: unknown) {
  const blob = new Blob([JSON.stringify(value, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function downloadText(filename: string, value: string) {
  const blob = new Blob([value], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

async function copyText(value: string) {
  await navigator.clipboard.writeText(value);
}

function JsonPanel({
  title,
  subtitle,
  open,
  onToggle,
  value,
  filename,
  loading,
  error,
  children,
}: {
  title: string;
  subtitle?: string;
  open: boolean;
  onToggle: () => void;
  value: unknown;
  filename: string;
  loading?: boolean;
  error?: string;
  children?: React.ReactNode;
}) {
  const [copied, setCopied] = useState(false);
  const text = typeof value === "string" ? value : value != null ? JSON.stringify(value, null, 2) : "";

  async function onCopy() {
    if (!text) return;
    await copyText(text);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  }

  return (
    <section className="rounded-xl border border-line bg-white p-4">
      <button type="button" className="flex w-full items-center justify-between text-left" aria-expanded={open} onClick={onToggle}>
        <h2 className="text-sm font-semibold uppercase tracking-wide text-neutral-500">{title}</h2>
        <span className="text-sm text-neutral-500">{open ? "Hide" : "Show"}</span>
      </button>
      {open ? (
        <div className="mt-4">
          {subtitle ? <p className="mb-3 text-sm text-neutral-600">{subtitle}</p> : null}
          {children}
          {error ? <p className="mt-3 text-sm text-red-700">{error}</p> : null}
          {loading ? <p className="mt-3 text-sm text-neutral-600">Loading…</p> : null}
          {text ? (
            <>
              <div className="mt-3 flex flex-wrap gap-3">
                <button type="button" className="text-sm text-pine" onClick={() => void onCopy()}>
                  {copied ? "Copied" : "Copy"}
                </button>
                <button
                  type="button"
                  className="text-sm text-pine"
                  onClick={() => (typeof value === "string" ? downloadText(filename, value) : downloadJson(filename, value))}
                >
                  Download
                </button>
              </div>
              <details className="mt-3">
                <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wide text-neutral-500">
                  {typeof value === "string" ? "Raw text" : "Raw JSON"}
                </summary>
                <pre className="mt-2 max-h-48 overflow-auto rounded-md border border-line bg-paper p-3 text-xs leading-5 text-neutral-800">{text}</pre>
              </details>
            </>
          ) : !loading && !error ? (
            <p className="mt-3 text-sm text-neutral-600">Nothing loaded yet.</p>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

export default function RawDataPage() {
  const id = useAccountId();
  const [promptOpen, setPromptOpen] = useState(false);
  const [reportOpen, setReportOpen] = useState(false);
  const [strategyOpen, setStrategyOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);

  const [prompt, setPrompt] = useState("");
  const [promptError, setPromptError] = useState("");
  const [promptLoading, setPromptLoading] = useState(false);

  const [reportKind, setReportKind] = useState<(typeof REPORT_KINDS)[number][0]>("last_30_vs_prev_30");
  const [report, setReport] = useState<unknown>(null);
  const [reportError, setReportError] = useState("");
  const [reportLoading, setReportLoading] = useState(false);

  const [span, setSpan] = useState<DateSpan>({ ...recentRange(90), preset: 90 });
  const [strategy, setStrategy] = useState<unknown>(null);
  const [strategyError, setStrategyError] = useState("");
  const [strategyLoading, setStrategyLoading] = useState(false);

  const [settings, setSettings] = useState<unknown>(null);
  const [settingsError, setSettingsError] = useState("");
  const [settingsLoading, setSettingsLoading] = useState(false);
  const [copyAllBusy, setCopyAllBusy] = useState(false);
  const [copyAllLabel, setCopyAllLabel] = useState("Copy all");
  const [copyAllError, setCopyAllError] = useState("");

  useEffect(() => {
    setPromptLoading(true);
    setPromptError("");
    api<{ prompt: string }>("/api/ai/system-prompt")
      .then((payload) => setPrompt(payload.prompt))
      .catch((reason: Error) => setPromptError(reason.message))
      .finally(() => setPromptLoading(false));
  }, []);

  useEffect(() => {
    if (!id) {
      setReport(null);
      setStrategy(null);
      setSettings(null);
      return;
    }
    setReport(null);
    setStrategy(null);
    setSettings(null);
    setReportError("");
    setStrategyError("");
    setSettingsError("");
    setCopyAllError("");
  }, [id]);

  async function loadReport() {
    if (!id) return null;
    setReportLoading(true);
    setReportError("");
    try {
      const payload = await api(`/api/reports/daily?account_id=${id}&kind=${reportKind}&save=false`);
      setReport(payload);
      return payload;
    } catch (reason) {
      setReport(null);
      setReportError(reason instanceof Error ? reason.message : "Could not load the report JSON");
      return null;
    } finally {
      setReportLoading(false);
    }
  }

  async function loadStrategy() {
    if (!id) return null;
    setStrategyLoading(true);
    setStrategyError("");
    try {
      const payload = await api<TrendsPayload>(`/api/trends?account_id=${id}&start_date=${span.start}&end_date=${span.end}`);
      const context = payload.ai_context ?? payload;
      setStrategy(context);
      return context;
    } catch (reason) {
      setStrategy(null);
      setStrategyError(reason instanceof Error ? reason.message : "Could not load the strategy JSON");
      return null;
    } finally {
      setStrategyLoading(false);
    }
  }

  async function loadSettings() {
    if (!id) return null;
    setSettingsLoading(true);
    setSettingsError("");
    try {
      const payload = await api(`/api/accounts/${id}/settings`);
      setSettings(payload);
      return payload;
    } catch (reason) {
      setSettings(null);
      setSettingsError(reason instanceof Error ? reason.message : "Could not load settings");
      return null;
    } finally {
      setSettingsLoading(false);
    }
  }

  function asBlock(title: string, value: unknown) {
    if (value == null || value === "") return "";
    const body = typeof value === "string" ? value : JSON.stringify(value, null, 2);
    return `## ${title}\n\n${body}`;
  }

  async function copyAll() {
    setCopyAllError("");
    setCopyAllBusy(true);
    try {
      let nextPrompt = prompt;
      if (!nextPrompt) {
        const payload = await api<{ prompt: string }>("/api/ai/system-prompt");
        nextPrompt = payload.prompt;
        setPrompt(nextPrompt);
      }
      const nextReport = id ? await loadReport() : null;
      const nextStrategy = id ? await loadStrategy() : null;
      const nextSettings = id ? await loadSettings() : null;
      const parts = [
        asBlock("System prompt", nextPrompt),
        asBlock(`Report feed (${reportKind})`, nextReport),
        asBlock(`Strategy feed (${span.start} to ${span.end})`, nextStrategy),
        asBlock("Analytics settings", nextSettings),
      ].filter(Boolean);
      if (!parts.length) {
        setCopyAllError("Nothing to copy yet.");
        return;
      }
      await copyText(parts.join("\n\n---\n\n"));
      setCopyAllLabel("Copied all");
      window.setTimeout(() => setCopyAllLabel("Copy all"), 1500);
    } catch (reason) {
      setCopyAllError(reason instanceof Error ? reason.message : "Could not copy everything");
    } finally {
      setCopyAllBusy(false);
    }
  }

  return (
    <Shell>
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="mb-2 text-2xl font-semibold">Raw Data</h1>
          <p className="text-sm text-neutral-600">
            Pull the same JSON the council uses, plus the system prompt and thresholds, so you can paste them into another model. Nothing here calls an LLM.
          </p>
        </div>
        <button
          type="button"
          className="rounded-md bg-pine px-3 py-2 text-sm text-white disabled:opacity-60"
          disabled={copyAllBusy || (!id && !prompt)}
          onClick={() => void copyAll()}
        >
          {copyAllBusy ? "Loading…" : copyAllLabel}
        </button>
      </div>
      {copyAllError ? <p className="mb-4 text-sm text-red-700">{copyAllError}</p> : null}
      {!id ? <p className="mb-4 text-sm text-neutral-600">Connect a Google Ads account to load account-scoped feeds.</p> : null}

      <div className="space-y-4">
        <JsonPanel
          title="System prompt"
          subtitle="Instructions every council model receives before the report or strategy JSON."
          open={promptOpen}
          onToggle={() => setPromptOpen((value) => !value)}
          value={prompt || null}
          filename="system-prompt.txt"
          loading={promptLoading}
          error={promptError}
        />

        <JsonPanel
          title="Report feed"
          subtitle="Same payload as Reports → Data fed to the AI. Loaded with save=false so saved notes are not overwritten."
          open={reportOpen}
          onToggle={() => setReportOpen((value) => !value)}
          value={report}
          filename={`report-${reportKind}.json`}
          loading={reportLoading}
          error={reportError}
        >
          <div className="flex flex-wrap items-end gap-3">
            <label className="text-sm text-neutral-600">
              Period
              <select
                className="ml-2 rounded-md border border-line bg-paper px-2 py-1"
                value={reportKind}
                onChange={(event) => setReportKind(event.target.value as (typeof REPORT_KINDS)[number][0])}
              >
                {REPORT_KINDS.map(([value, name]) => (
                  <option key={value} value={value}>
                    {name}
                  </option>
                ))}
              </select>
            </label>
            <button type="button" className="rounded-md bg-pine px-3 py-1.5 text-sm text-white disabled:opacity-60" disabled={!id || reportLoading} onClick={() => void loadReport()}>
              Load
            </button>
          </div>
        </JsonPanel>

        <JsonPanel
          title="Strategy feed"
          subtitle={`${STRATEGY_NOTE} This is trends.ai_context, not the full daily series.`}
          open={strategyOpen}
          onToggle={() => setStrategyOpen((value) => !value)}
          value={strategy}
          filename={`strategy-${span.start}-to-${span.end}.json`}
          loading={strategyLoading}
          error={strategyError}
        >
          <div className="flex flex-wrap items-end gap-3">
            <DateRangePicker value={span} onChange={setSpan} />
            <button
              type="button"
              className="rounded-md bg-pine px-3 py-1.5 text-sm text-white disabled:opacity-60"
              disabled={!id || strategyLoading}
              onClick={() => void loadStrategy()}
            >
              Load
            </button>
          </div>
        </JsonPanel>

        <JsonPanel
          title="Analytics settings"
          subtitle="Anomaly, waste, and budget thresholds used when the report JSON is built."
          open={settingsOpen}
          onToggle={() => setSettingsOpen((value) => !value)}
          value={settings}
          filename="analytics-settings.json"
          loading={settingsLoading}
          error={settingsError}
        >
          <button type="button" className="rounded-md bg-pine px-3 py-1.5 text-sm text-white disabled:opacity-60" disabled={!id || settingsLoading} onClick={() => void loadSettings()}>
            Load
          </button>
        </JsonPanel>
      </div>
    </Shell>
  );
}
