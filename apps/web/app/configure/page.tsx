"use client";

import { AccountsPanel } from "@/components/accounts-panel";
import { SettingsPanel } from "@/components/settings-panel";
import { Shell } from "@/components/shell";

export default function ConfigurePage() {
  return (
    <Shell>
      <h1 className="mb-6 text-2xl font-semibold">Configure</h1>
      <AccountsPanel />
      <SettingsPanel />
    </Shell>
  );
}
