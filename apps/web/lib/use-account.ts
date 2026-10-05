"use client";

import { useEffect, useState } from "react";
import { accountId, api, setAccountId } from "@/lib/api";

export function useAccountId() {
  const [id, setId] = useState("");

  useEffect(() => {
    const existing = accountId();
    if (existing) {
      setId(existing);
      return;
    }
    api<{ accounts: { id: string }[] }>("/api/accounts")
      .then((payload) => {
        const next = payload.accounts[0]?.id ?? "";
        if (next) {
          setAccountId(next);
          setId(next);
        }
      })
      .catch(() => undefined);
  }, []);

  return id;
}
