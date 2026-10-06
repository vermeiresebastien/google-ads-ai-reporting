"use client";

import { useEffect, useRef, useState } from "react";
import { Panel } from "@/components/shell";
import { API_URL, api } from "@/lib/api";

type Account = {
  id: string;
  workspace_id: string;
  account_name: string;
  customer_id: string;
  status: string;
  currency_code: string;
  last_successful_sync_at: string | null;
};

type SyncStatus = {
  status: "idle" | "running" | "completed" | "failed";
  total: number;
  completed: number;
  percent: number;
  label: string | null;
  error: string | null;
};

function SyncProgress({ status }: { status: SyncStatus }) {
  if (status.status === "idle" || status.total === 0) return null;
  const width = status.status === "running" ? Math.max(status.percent, 3) : status.percent;
  const title = status.status === "failed" ? "Sync stopped" : status.status === "completed" ? "Sync finished" : status.label ?? "Starting sync";
  return (
    <div className="mt-2">
      <div className="mb-1 flex justify-between gap-3 text-xs text-neutral-600">
        <span>{title}</span>
        <span>{status.completed} / {status.total}</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-line" role="progressbar" aria-valuenow={status.percent} aria-valuemin={0} aria-valuemax={100} aria-label={title}>
        <div className={`h-full transition-all ${status.status === "failed" ? "bg-red-700" : "bg-pine"}`} style={{ width: `${width}%` }} />
      </div>
      {status.error ? <p className="mt-1 text-xs text-red-700">{status.error}</p> : null}
    </div>
  );
}

const CONNECT_ERRORS: Record<string, string> = {
  api_disabled:
    "Google signed you in, but the Google Ads API is turned off for this Cloud project. Enable it, wait a few minutes, then choose Connect Google Ads again.",
  test_access:
    "Google signed you in. This developer token can only read test accounts, so your live Google Ads customer was refused. Apply for Basic access in the Google Ads API Center, then connect again.",
  account_inactive:
    "Google signed you in, but that Ads customer is not enabled or has been deactivated. Connect an active Google Ads account.",
  discovery: "Google signed you in, but no Ads customers could be listed.",
  oauth: "Google did not finish sign-in. Check the OAuth client and redirect URI, then connect again.",
  missing_refresh_token: "Google did not return a refresh token. Connect again and approve offline access.",
};

const HELP_LINKS: Record<string, { href: string; label: string }> = {
  api_disabled: {
    href: "https://console.cloud.google.com/apis/library/googleads.googleapis.com?project=353269740957",
    label: "Enable the Google Ads API",
  },
  test_access: {
    href: "https://ads.google.com/aw/apicenter",
    label: "Open the Google Ads API Center",
  },
};

export function AccountsPanel() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [message, setMessage] = useState("");
  const [messageIsError, setMessageIsError] = useState(true);
  const [helpLink, setHelpLink] = useState<{ href: string; label: string } | null>(null);
  const [progressByAccount, setProgressByAccount] = useState<Record<string, SyncStatus>>({});
  const [watchSync, setWatchSync] = useState(0);
  const previousStatus = useRef<Record<string, string>>({});

  function load() {
    api<{ accounts: Account[] }>("/api/accounts")
      .then((payload) => setAccounts(payload.accounts))
      .catch((reason: Error) => {
        setMessageIsError(true);
        setMessage(reason.message);
      });
  }

  useEffect(() => {
    const error = new URLSearchParams(window.location.search).get("error");
    if (error && CONNECT_ERRORS[error]) {
      setMessageIsError(true);
      setMessage(CONNECT_ERRORS[error]);
      setHelpLink(HELP_LINKS[error] ?? null);
    }
    load();
  }, []);

  useEffect(() => {
    if (accounts.length === 0) return;
    let stop = false;
    let timer = 0;
    const accountIds = accounts.map((account) => account.id);

    async function tick() {
      let running = false;
      const next: Record<string, SyncStatus> = {};
      for (const accountId of accountIds) {
        try {
          const status = await api<SyncStatus>(`/api/accounts/${accountId}/sync/status`);
          next[accountId] = status;
          if (status.status === "running") running = true;
          if (status.status === "completed" && previousStatus.current[accountId] === "running") load();
          previousStatus.current[accountId] = status.status;
        } catch {
          running = true;
        }
      }
      if (stop) return;
      setProgressByAccount((current) => ({ ...current, ...next }));
      if (running) timer = window.setTimeout(tick, 2000);
    }

    void tick();
    return () => {
      stop = true;
      window.clearTimeout(timer);
    };
  }, [accounts, watchSync]);

  async function connect() {
    const workspaceId = accounts[0]?.workspace_id;
    const me = await api<{ workspaces: { id: string }[] }>("/api/auth/me");
    const target = workspaceId ?? me.workspaces[0]?.id;
    if (!target) return;
    const started = await api<{ url: string }>("/api/google/oauth/start", { method: "POST", body: JSON.stringify({ workspace_id: target }) });
    window.location.href = started.url;
  }

  async function sync(accountId: string) {
    setMessage("");
    try {
      const result = await api<{ jobs: string[]; runner: string }>(`/api/accounts/${accountId}/sync`, {
        method: "POST",
        body: JSON.stringify({ mode: "history" }),
      });
      setMessageIsError(false);
      setMessage(result.runner === "local" ? "Sync started." : `Queued ${result.jobs.length} sync jobs.`);
      setWatchSync((value) => value + 1);
    } catch (reason) {
      setMessageIsError(true);
      setMessage(reason instanceof Error ? reason.message : "Sync failed");
    }
  }

  return (
    <section id="accounts">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-xl font-semibold">Accounts</h2>
        <button className="rounded-md bg-pine px-3 py-2 text-sm text-white" onClick={connect}>Connect Google Ads</button>
      </div>
      {message ? <p className={`mb-3 text-sm ${messageIsError ? "text-red-700" : "text-neutral-700"}`}>{message}</p> : null}
      {helpLink ? (
        <p className="mb-3 text-sm">
          <a className="text-pine underline" href={helpLink.href} target="_blank" rel="noreferrer">
            {helpLink.label}
          </a>
        </p>
      ) : null}
      <Panel title="Connected accounts">
        {accounts.length === 0 ? <p className="text-sm text-neutral-600">No Google Ads customer is connected yet.</p> : null}
        {accounts.map((account) => {
          const progress = progressByAccount[account.id];
          const syncing = progress?.status === "running";
          return (
            <div key={account.id} className="border-b border-line py-3 text-sm last:border-0">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <p className="font-medium">{account.account_name || account.customer_id}</p>
                  <p className="text-neutral-600">{account.customer_id} · {account.currency_code} · {account.status}</p>
                  <p className="text-neutral-500">Last sync {account.last_successful_sync_at ?? "never"}</p>
                </div>
                <button className="rounded-md border border-line px-3 py-1 disabled:opacity-60" disabled={syncing} onClick={() => sync(account.id)}>
                  {syncing ? "Syncing" : "Sync"}
                </button>
              </div>
              {progress ? <SyncProgress status={progress} /> : null}
            </div>
          );
        })}
      </Panel>
      <p className="mt-3 text-xs text-neutral-500">OAuth returns to {API_URL}. Refresh tokens stay on the server.</p>
    </section>
  );
}
