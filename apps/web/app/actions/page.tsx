"use client";

import { useCallback, useEffect, useState } from "react";
import { Panel, Shell } from "@/components/shell";
import { api } from "@/lib/api";
import { money } from "@/lib/format";
import { useAccountId } from "@/lib/use-account";

type ActionRow = {
  id: string;
  action_type: string;
  status: string;
  title: string;
  rationale: string;
  evidence: string[];
  params: Record<string, unknown>;
  confidence: string;
  source_kind?: string | null;
  source_as_of?: string | null;
  error_message?: string | null;
  applied_at?: string | null;
  created_at?: string | null;
};

const PERIODS = [
  ["yesterday_vs_prev7_avg", "Yesterday"],
  ["last_7_vs_prev_7", "Last 7 days"],
  ["last_30_vs_prev_30", "Last 30 days"],
  ["last_90_vs_prev_90", "Last 90 days"],
] as const;

function typeLabel(type: string) {
  if (type === "add_negative_keyword") return "Negative keyword";
  if (type === "increase_budget") return "Budget increase";
  return type;
}

function statusClass(status: string) {
  if (status === "proposed") return "text-pine";
  if (status === "applied") return "text-neutral-700";
  if (status === "failed") return "text-red-700";
  return "text-neutral-500";
}

function paramSummary(row: ActionRow) {
  const params = row.params || {};
  if (row.action_type === "add_negative_keyword") {
    return `${params.match_type || "PHRASE"} · ${params.campaign_name || "campaign"}`;
  }
  if (row.action_type === "increase_budget") {
    const current = Number(params.current_daily_budget ?? 0);
    const proposed = Number(params.proposed_daily_budget ?? 0);
    return `${money(current)} → ${money(proposed)} · ${params.campaign_name || "campaign"}`;
  }
  return "";
}

export default function ActionsPage() {
  const id = useAccountId();
  const [actions, setActions] = useState<ActionRow[]>([]);
  const [kind, setKind] = useState<(typeof PERIODS)[number][0]>("last_30_vs_prev_30");
  const [filter, setFilter] = useState("proposed");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState("");
  const [confirmId, setConfirmId] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!id) return;
    const statusQuery = filter === "all" ? "" : `&status=${filter}`;
    api<{ actions: ActionRow[] }>(`/api/actions?account_id=${id}${statusQuery}`)
      .then((payload) => setActions(payload.actions))
      .catch((reason: Error) => setError(reason.message));
  }, [id, filter]);

  useEffect(() => {
    setError("");
    load();
  }, [load]);

  async function propose() {
    if (!id) return;
    setBusy("propose");
    setError("");
    setMessage("");
    try {
      const result = await api<{ count: number; skipped: number }>("/api/actions/propose", {
        method: "POST",
        body: JSON.stringify({ account_id: id, kind }),
      });
      setMessage(`Created ${result.count} proposal${result.count === 1 ? "" : "s"} (${result.skipped} skipped).`);
      setFilter("proposed");
      load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Propose failed");
    } finally {
      setBusy("");
    }
  }

  async function apply(actionId: string, dryRun: boolean) {
    setBusy(actionId + (dryRun ? ":dry" : ":apply"));
    setError("");
    setMessage("");
    try {
      const result = await api<{ dry_run: boolean; ok: boolean }>(`/api/actions/${actionId}/apply`, {
        method: "POST",
        body: JSON.stringify({ confirm: true, dry_run: dryRun }),
      });
      setConfirmId(null);
      setMessage(result.dry_run ? "Dry run succeeded — Google was not changed." : "Applied to Google Ads.");
      load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Apply failed");
      load();
    } finally {
      setBusy("");
    }
  }

  async function reject(actionId: string) {
    setBusy(actionId + ":reject");
    setError("");
    setMessage("");
    try {
      await api(`/api/actions/${actionId}/reject`, { method: "POST", body: "{}" });
      setConfirmId(null);
      setMessage("Action rejected.");
      load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Reject failed");
    } finally {
      setBusy("");
    }
  }

  return (
    <Shell>
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Actions</h1>
          <p className="text-sm text-neutral-600">
            Structured proposals from waste and budget findings. Nothing writes to Google until you confirm.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <label className="text-sm text-neutral-600">
            Period
            <select
              className="ml-2 rounded-md border border-line bg-paper px-2 py-1"
              value={kind}
              onChange={(event) => setKind(event.target.value as (typeof PERIODS)[number][0])}
            >
              {PERIODS.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className="rounded-md bg-ink px-3 py-1.5 text-sm text-white disabled:opacity-50"
            disabled={!id || busy === "propose"}
            onClick={propose}
          >
            {busy === "propose" ? "Proposing…" : "Generate proposals"}
          </button>
        </div>
      </div>

      {error ? <p className="mb-3 text-sm text-red-700">{error}</p> : null}
      {message ? <p className="mb-3 text-sm text-pine">{message}</p> : null}

      <div className="mb-3 flex flex-wrap gap-2 text-sm">
        {["proposed", "applied", "rejected", "failed", "all"].map((value) => (
          <button
            key={value}
            type="button"
            className={filter === value ? "font-semibold text-pine" : "text-neutral-600"}
            onClick={() => setFilter(value)}
          >
            {value}
          </button>
        ))}
      </div>

      <Panel title="Queue">
        {!id ? (
          <p className="text-sm text-neutral-600">Select an account to review actions.</p>
        ) : actions.length === 0 ? (
          <p className="text-sm text-neutral-600">No actions in this filter. Generate proposals from the current period.</p>
        ) : (
          <ul className="space-y-4">
            {actions.map((row) => {
              const open = row.status === "proposed" || row.status === "failed";
              const confirming = confirmId === row.id;
              return (
                <li key={row.id} className="border-t border-line pt-4 first:border-t-0 first:pt-0">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <p className="font-medium">{row.title}</p>
                      <p className="mt-1 text-sm text-neutral-600">{row.rationale}</p>
                      <p className="mt-1 text-xs text-neutral-500">
                        {typeLabel(row.action_type)} · <span className={statusClass(row.status)}>{row.status}</span>
                        {row.confidence ? ` · ${row.confidence} confidence` : ""}
                        {paramSummary(row) ? ` · ${paramSummary(row)}` : ""}
                      </p>
                      {row.evidence?.length ? (
                        <p className="mt-1 text-xs text-neutral-500">{row.evidence.join(" ")}</p>
                      ) : null}
                      {row.error_message ? <p className="mt-1 text-xs text-red-700">{row.error_message}</p> : null}
                    </div>
                    {open ? (
                      <div className="flex flex-wrap gap-2">
                        {!confirming ? (
                          <>
                            <button
                              type="button"
                              className="rounded-md border border-line px-2 py-1 text-sm"
                              disabled={Boolean(busy)}
                              onClick={() => apply(row.id, true)}
                            >
                              {busy === `${row.id}:dry` ? "Checking…" : "Dry run"}
                            </button>
                            <button
                              type="button"
                              className="rounded-md bg-pine px-2 py-1 text-sm text-white"
                              disabled={Boolean(busy)}
                              onClick={() => setConfirmId(row.id)}
                            >
                              Apply…
                            </button>
                            <button
                              type="button"
                              className="rounded-md border border-line px-2 py-1 text-sm"
                              disabled={Boolean(busy)}
                              onClick={() => reject(row.id)}
                            >
                              Reject
                            </button>
                          </>
                        ) : (
                          <>
                            <span className="self-center text-sm text-neutral-600">Write this to Google Ads?</span>
                            <button
                              type="button"
                              className="rounded-md bg-red-700 px-2 py-1 text-sm text-white"
                              disabled={Boolean(busy)}
                              onClick={() => apply(row.id, false)}
                            >
                              {busy === `${row.id}:apply` ? "Applying…" : "Confirm apply"}
                            </button>
                            <button
                              type="button"
                              className="rounded-md border border-line px-2 py-1 text-sm"
                              disabled={Boolean(busy)}
                              onClick={() => setConfirmId(null)}
                            >
                              Cancel
                            </button>
                          </>
                        )}
                      </div>
                    ) : null}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </Panel>

      <p className="mt-4 text-xs text-neutral-500">
        Live applies require <code>ALLOW_GOOGLE_MUTATIONS=true</code> on the API. Dry run validates without writing.
      </p>
    </Shell>
  );
}
