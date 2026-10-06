"use client";

import { useEffect, useState } from "react";
import { Panel, Shell } from "@/components/shell";
import { api } from "@/lib/api";
import { useSelectedAccount } from "@/lib/use-account";

type Change = { id: string; event_timestamp: string; resource_type: string; change_type: string; field_changed: string; user_email: string; client_type: string };

export default function ChangesPage() {
  const [rows, setRows] = useState<Change[]>([]);

  const account = useSelectedAccount();
  const id = account?.id ?? "";

  useEffect(() => {
    if (!id || account?.changes === false) return;
    api<{ rows: Change[] }>(`/api/changes?account_id=${id}&limit=100`).then((payload) => setRows(payload.rows)).catch(() => undefined);
  }, [id, account?.changes]);

  if (account && !account.changes) {
    return (
      <Shell>
        <h1 className="mb-4 text-2xl font-semibold">Recent changes</h1>
        <p className="text-sm text-neutral-600">Change history is available for Google Ads. {account.platform_label} uses the dashboard, campaigns, reports, and trends.</p>
      </Shell>
    );
  }

  return (
    <Shell>
      <h1 className="mb-4 text-2xl font-semibold">Recent changes</h1>
      <Panel title="Account history">
        {rows.length === 0 ? (
          <p className="text-sm text-neutral-600">
            No change events in the last 7 days (including today). Run a sync to pull Google’s change history — applying an action here does not fill this list by itself.
          </p>
        ) : null}
        {rows.map((row) => (
          <p key={row.id} className="border-b border-line py-2 text-sm">
            {row.event_timestamp}: {row.change_type} {row.resource_type} {row.field_changed} by {row.user_email || "unknown"} via {row.client_type || "unknown client"}
          </p>
        ))}
      </Panel>
    </Shell>
  );
}
