"use client";

import { useEffect, useState } from "react";
import { Panel } from "@/components/shell";
import { api } from "@/lib/api";
import { useAccountId } from "@/lib/use-account";

const FIELDS = [
  ["min_spend_for_waste", "Minimum spend for a waste candidate", "A search term or keyword is ignored until it has spent at least this much. Below this, a bad query is treated as too small to act on."],
  ["zero_conversion_min_spend", "Zero-conversion spend", "Spend with no conversions is flagged once it reaches this amount. A query can also be listed as waste when it hits this spend and still has zero conversions."],
  ["min_clicks", "Minimum clicks", "A search term or keyword needs at least this many clicks before it can be called waste. This avoids judging a query on one or two clicks."],
  ["spend_anomaly_pct", "Spend anomaly", "Flags the account when spend is higher than the previous period by at least this fraction. 0.30 means a 30% increase."],
  ["cpa_anomaly_pct", "CPA anomaly", "CPA is cost divided by conversions. This flags the account when CPA is higher than the previous period by at least this fraction. 0.25 means CPA rose 25%. The same fraction marks a query whose CPA is that far above the account CPA."],
  ["roas_anomaly_pct", "ROAS anomaly", "ROAS is conversion value divided by spend. This flags the account when ROAS is lower than the previous period by at least this fraction. 0.20 means ROAS fell 20%."],
  ["cpc_anomaly_pct", "CPC anomaly", "CPC is spend divided by clicks. This flags the account when CPC is higher than the previous period by at least this fraction. 0.25 means each click costs 25% more."],
  ["cvr_anomaly_pct", "Conversion-rate anomaly", "Conversion rate is conversions divided by clicks. This flags a move up or down of at least this fraction versus the previous period. 0.20 means the rate changed by 20% in either direction."],
  ["conversion_anomaly_pct", "Conversion anomaly", "Flags the account when the number of conversions is lower than the previous period by at least this fraction. 0.25 means conversions fell 25%."],
  ["budget_lost_is_min", "Budget lost impression share", "Share of eligible impressions lost because the budget ran out. A campaign is a budget opportunity once this share is at least this fraction and its efficiency is still close to the account. 0.15 means 15% of impressions were lost to budget."],
  ["min_spend_for_anomaly", "Minimum spend for an anomaly", "Anomalies are skipped until the current or previous period spent at least this much. A budget recommendation also requires the campaign to have spent this much and recorded conversions."],
] as const;

type Preset = { id: string; name: string; values: Record<string, number> };

function thresholdPayload(values: Record<string, number>) {
  return Object.fromEntries(FIELDS.map(([key]) => [key, Number(values[key])]));
}

export function SettingsPanel() {
  const [values, setValues] = useState<Record<string, number>>({});
  const [presets, setPresets] = useState<Preset[]>([]);
  const [presetName, setPresetName] = useState("");
  const [chosenId, setChosenId] = useState("");
  const [message, setMessage] = useState("");
  const [messageTone, setMessageTone] = useState<"ok" | "error">("ok");
  const [confirmReset, setConfirmReset] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const id = useAccountId();

  useEffect(() => {
    if (!id) return;
    let current = true;
    Promise.all([
      api<Record<string, number>>(`/api/accounts/${id}/settings`),
      api<{ presets: Preset[] }>(`/api/accounts/${id}/settings/presets`),
    ])
      .then(([settings, listed]) => {
        if (!current) return;
        setValues(settings);
        setPresets(listed.presets);
      })
      .catch((reason: Error) => {
        if (current) note(reason.message, "error");
      });
    return () => {
      current = false;
    };
  }, [id]);

  function note(text: string, tone: "ok" | "error" = "ok") {
    setMessage(text);
    setMessageTone(tone);
  }

  function editValue(key: string, next: number) {
    setChosenId("");
    setValues({ ...values, [key]: next });
  }

  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (!id) return;
    try {
      const updated = await api<Record<string, number>>(`/api/accounts/${id}/settings`, {
        method: "PUT",
        body: JSON.stringify(thresholdPayload(values)),
      });
      setValues(updated);
      note("Thresholds saved.");
    } catch (reason) {
      note(reason instanceof Error ? reason.message : "Could not save the thresholds.", "error");
    }
  }

  async function savePreset() {
    if (!id) return;
    const name = presetName.trim();
    if (!name) {
      note("Name the preset first.", "error");
      return;
    }
    try {
      const saved = await api<Preset>(`/api/accounts/${id}/settings/presets`, {
        method: "POST",
        body: JSON.stringify({ name, ...thresholdPayload(values) }),
      });
      const listed = await api<{ presets: Preset[] }>(`/api/accounts/${id}/settings/presets`);
      setPresets(listed.presets);
      setChosenId(saved.id);
      setPresetName(saved.name);
      note(`Saved preset ${saved.name}.`);
    } catch (reason) {
      note(reason instanceof Error ? reason.message : "Could not save the preset.", "error");
    }
  }

  async function applyPreset(presetId: string) {
    if (!id) return;
    const preset = presets.find((item) => item.id === presetId);
    setChosenId(presetId);
    try {
      const updated = await api<Record<string, number>>(`/api/accounts/${id}/settings/presets/${presetId}/apply`, {
        method: "POST",
      });
      setValues(updated);
      if (preset) setPresetName(preset.name);
      note(`Using ${preset?.name ?? "preset"}.`);
    } catch (reason) {
      setChosenId("");
      note(reason instanceof Error ? reason.message : "Could not use that preset.", "error");
    }
  }

  async function resetThresholds() {
    if (!id) return;
    setConfirmReset(false);
    try {
      const updated = await api<Record<string, number>>(`/api/accounts/${id}/settings/reset`, { method: "POST" });
      setValues(updated);
      setChosenId("");
      setPresetName("");
      note("Thresholds are back to the original values.");
    } catch (reason) {
      note(reason instanceof Error ? reason.message : "Could not reset the thresholds.", "error");
    }
  }

  async function removePreset() {
    if (!id || !chosenId) return;
    const preset = presets.find((item) => item.id === chosenId);
    setConfirmDelete(false);
    try {
      await api(`/api/accounts/${id}/settings/presets/${chosenId}`, { method: "DELETE" });
      setPresets(presets.filter((item) => item.id !== chosenId));
      setChosenId("");
      setPresetName("");
      note(`${preset?.name ?? "Preset"} deleted.`);
    } catch (reason) {
      note(reason instanceof Error ? reason.message : "Could not delete that preset.", "error");
    }
  }

  return (
    <section id="settings" className="mt-8">
      <h2 className="mb-4 text-xl font-semibold">Settings</h2>
      <form onSubmit={save}>
        <Panel title="Analysis thresholds">
          <div className="mb-4 flex flex-wrap items-end gap-2">
            <label className="text-sm">
              Preset
              <select
                aria-label="Saved presets"
                className="mt-1 block rounded-md border border-line bg-white px-2 py-2"
                value={chosenId}
                onChange={(event) => {
                  const next = event.target.value;
                  if (!next) {
                    setChosenId("");
                    return;
                  }
                  void applyPreset(next);
                }}
              >
                <option value="">Saved presets</option>
                {presets.map((preset) => (
                  <option key={preset.id} value={preset.id}>
                    {preset.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-sm">
              Preset name
              <input
                aria-label="Preset name"
                className="mt-1 block w-44 rounded-md border border-line px-3 py-2"
                value={presetName}
                placeholder="Name"
                onChange={(event) => setPresetName(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault();
                    void savePreset();
                  }
                }}
              />
            </label>
            <button type="button" className="rounded-md border border-line px-3 py-2 text-sm" onClick={() => void savePreset()}>
              Save preset
            </button>
            {chosenId ? (
              <button type="button" className="rounded-md px-3 py-2 text-sm text-red-700" onClick={() => setConfirmDelete(true)}>
                Delete preset
              </button>
            ) : null}
            <button type="button" className="rounded-md border border-line px-3 py-2 text-sm" onClick={() => setConfirmReset(true)}>
              Reset
            </button>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            {FIELDS.map(([key, label, help]) => (
              <label key={key} className="group relative text-sm">
                <span className="cursor-help underline decoration-dotted decoration-neutral-400">{label}</span>
                <span id={`${key}-help`} className="pointer-events-none absolute bottom-full left-0 z-10 mb-1 hidden w-72 rounded-md bg-ink px-2 py-1.5 text-xs font-normal leading-5 text-white shadow-md group-hover:block">
                  {help}
                </span>
                <input
                  className="mt-1 w-full rounded-md border border-line px-3 py-2"
                  aria-describedby={`${key}-help`}
                  value={values[key] ?? ""}
                  onChange={(event) => editValue(key, Number(event.target.value))}
                />
              </label>
            ))}
          </div>
          {message ? <p className={`mt-3 text-sm ${messageTone === "error" ? "text-red-700" : "text-neutral-600"}`}>{message}</p> : null}
          <button className="mt-4 rounded-md bg-pine px-3 py-2 text-sm text-white" type="submit">Save</button>
        </Panel>
      </form>
      {confirmReset ? (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/30 p-4" role="presentation" onClick={() => setConfirmReset(false)}>
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="reset-thresholds-title"
            className="w-full max-w-sm rounded-lg border border-line bg-white p-4 shadow-lg"
            onClick={(event) => event.stopPropagation()}
          >
            <h3 id="reset-thresholds-title" className="text-base font-semibold text-neutral-900">Reset thresholds?</h3>
            <p className="mt-2 text-sm text-neutral-600">The analysis thresholds go back to the original values. Saved presets stay.</p>
            <div className="mt-4 flex justify-end gap-2">
              <button type="button" className="rounded-md border border-line px-3 py-1.5 text-sm" onClick={() => setConfirmReset(false)}>
                Cancel
              </button>
              <button type="button" className="rounded-md bg-pine px-3 py-1.5 text-sm text-white" onClick={() => void resetThresholds()}>
                Reset
              </button>
            </div>
          </div>
        </div>
      ) : null}
      {confirmDelete ? (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/30 p-4" role="presentation" onClick={() => setConfirmDelete(false)}>
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-preset-title"
            className="w-full max-w-sm rounded-lg border border-line bg-white p-4 shadow-lg"
            onClick={(event) => event.stopPropagation()}
          >
            <h3 id="delete-preset-title" className="text-base font-semibold text-neutral-900">Delete this preset?</h3>
            <p className="mt-2 text-sm text-neutral-600">The current thresholds stay as they are.</p>
            <div className="mt-4 flex justify-end gap-2">
              <button type="button" className="rounded-md border border-line px-3 py-1.5 text-sm" onClick={() => setConfirmDelete(false)}>
                Cancel
              </button>
              <button type="button" className="rounded-md bg-red-700 px-3 py-1.5 text-sm text-white" onClick={() => void removePreset()}>
                Delete
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
