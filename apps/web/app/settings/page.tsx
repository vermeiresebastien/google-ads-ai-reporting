"use client";

import { useEffect, useState } from "react";
import { Panel, Shell } from "@/components/shell";
import { api } from "@/lib/api";
import { useAccountId } from "@/lib/use-account";

const FIELDS = [
  ["min_spend_for_waste", "Minimum spend for a waste candidate"],
  ["zero_conversion_min_spend", "Zero-conversion spend"],
  ["min_clicks", "Minimum clicks"],
  ["spend_anomaly_pct", "Spend anomaly"],
  ["cpa_anomaly_pct", "CPA anomaly"],
  ["roas_anomaly_pct", "ROAS anomaly"],
  ["cpc_anomaly_pct", "CPC anomaly"],
  ["cvr_anomaly_pct", "Conversion-rate anomaly"],
  ["conversion_anomaly_pct", "Conversion anomaly"],
  ["budget_lost_is_min", "Budget lost impression share"],
  ["min_spend_for_anomaly", "Minimum spend for an anomaly"],
] as const;

export default function SettingsPage() {
  const [values, setValues] = useState<Record<string, number>>({});
  const [message, setMessage] = useState("");

  const id = useAccountId();

  useEffect(() => {
    if (!id) return;
    api<Record<string, number>>(`/api/accounts/${id}/settings`).then(setValues).catch((reason: Error) => setMessage(reason.message));
  }, [id]);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (!id) return;
    const payload = Object.fromEntries(FIELDS.map(([key]) => [key, Number(values[key])]));
    const updated = await api<Record<string, number>>(`/api/accounts/${id}/settings`, { method: "PUT", body: JSON.stringify(payload) });
    setValues(updated);
    setMessage("Thresholds saved.");
  }

  return (
    <Shell>
      <h1 className="mb-4 text-2xl font-semibold">Settings</h1>
      <form onSubmit={save}>
        <Panel title="Analysis thresholds">
          <div className="grid gap-3 sm:grid-cols-2">
            {FIELDS.map(([key, label]) => (
              <label key={key} className="text-sm">
                {label}
                <input
                  className="mt-1 w-full rounded-md border border-line px-3 py-2"
                  value={values[key] ?? ""}
                  onChange={(event) => setValues({ ...values, [key]: Number(event.target.value) })}
                />
              </label>
            ))}
          </div>
          {message ? <p className="mt-3 text-sm">{message}</p> : null}
          <button className="mt-4 rounded-md bg-pine px-3 py-2 text-sm text-white" type="submit">Save</button>
        </Panel>
      </form>
    </Shell>
  );
}
