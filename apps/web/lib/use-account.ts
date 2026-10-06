"use client";

import { useEffect, useState } from "react";
import { accountId, api, setAccountId } from "@/lib/api";

export type AccountChoice = {
  id: string;
  account_name: string;
  customer_id: string;
  platform: string;
  platform_label: string;
  search_terms: boolean;
  changes: boolean;
};

export function useAccountId() {
  const account = useSelectedAccount();
  return account?.id ?? "";
}

export function useSelectedAccount() {
  const [account, setAccount] = useState<AccountChoice | null>(null);

  useEffect(() => {
    const existing = accountId();
    api<{ accounts: AccountChoice[] }>("/api/accounts")
      .then((payload) => {
        const known = payload.accounts.some((item) => item.id === existing);
        const next = known ? existing : payload.accounts[0]?.id ?? "";
        if (next) setAccountId(next);
        else localStorage.removeItem("gads_account_id");
        setAccount(payload.accounts.find((item) => item.id === next) ?? null);
      })
      .catch(() => undefined);
  }, []);

  return account;
}
