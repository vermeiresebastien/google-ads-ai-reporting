"use client";

import { useEffect, useState } from "react";
import { Panel, Shell } from "@/components/shell";
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

export default function AccountsPage() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [message, setMessage] = useState("");

  function load() {
    api<{ accounts: Account[] }>("/api/accounts").then((payload) => setAccounts(payload.accounts)).catch((reason: Error) => setMessage(reason.message));
  }

  useEffect(() => {
    load();
  }, []);

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
      const result = await api<{ jobs: string[] }>(`/api/accounts/${accountId}/sync`, {
        method: "POST",
        body: JSON.stringify({ mode: "initial" }),
      });
      setMessage(`Queued ${result.jobs.length} sync jobs.`);
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "Sync failed");
    }
  }

  return (
    <Shell>
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Accounts</h1>
        <button className="rounded-md bg-pine px-3 py-2 text-sm text-white" onClick={connect}>Connect Google Ads</button>
      </div>
      {message ? <p className="mb-3 text-sm">{message}</p> : null}
      <Panel title="Connected accounts">
        {accounts.length === 0 ? <p className="text-sm text-neutral-600">No account yet. Connect Google Ads or load the demo from the sign-in page.</p> : null}
        {accounts.map((account) => (
          <div key={account.id} className="flex flex-wrap items-center justify-between gap-2 border-b border-line py-3 text-sm last:border-0">
            <div>
              <p className="font-medium">{account.account_name || account.customer_id}</p>
              <p className="text-neutral-600">{account.customer_id} · {account.currency_code} · {account.status}</p>
              <p className="text-neutral-500">Last sync {account.last_successful_sync_at ?? "never"}</p>
            </div>
            <button className="rounded-md border border-line px-3 py-1" onClick={() => sync(account.id)}>Sync</button>
          </div>
        ))}
      </Panel>
      <p className="mt-3 text-xs text-neutral-500">OAuth returns to {API_URL}. Refresh tokens stay on the server.</p>
    </Shell>
  );
}
