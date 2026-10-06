"use client";

import { useEffect, useState } from "react";
import { accountId, api, setAccountId } from "@/lib/api";

export function useAccountId() {
  const [id, setId] = useState("");

  useEffect(() => {
    const existing = accountId();
    api<{ accounts: { id: string }[] }>("/api/accounts")
      .then((payload) => {
        const known = payload.accounts.some((account) => account.id === existing);
        const next = known ? existing : payload.accounts[0]?.id ?? "";
        if (next) setAccountId(next);
        else localStorage.removeItem("gads_account_id");
        setId(next);
      })
      .catch(() => undefined);
  }, []);

  return id;
}
