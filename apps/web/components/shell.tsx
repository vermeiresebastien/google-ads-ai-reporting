"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { accountId, api, setAccountId, token } from "@/lib/api";

const LINKS = [
  ["/dashboard", "Dashboard"],
  ["/accounts", "Accounts"],
  ["/campaigns", "Campaigns"],
  ["/search-terms", "Search terms"],
  ["/changes", "Changes"],
  ["/reports", "Reports"],
  ["/settings", "Settings"],
];

type Account = { id: string; account_name: string; customer_id: string };

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [selected, setSelected] = useState("");

  useEffect(() => {
    if (!token()) {
      router.replace("/login");
      return;
    }
    api<{ accounts: Account[] }>("/api/accounts")
      .then((payload) => {
        setAccounts(payload.accounts);
        const stored = accountId();
        const next = payload.accounts.some((item) => item.id === stored) ? stored : payload.accounts[0]?.id ?? "";
        if (next) {
          setAccountId(next);
          setSelected(next);
        }
      })
      .catch(() => undefined);
  }, [router]);

  return (
    <div className="min-h-screen">
      <header className="border-b border-line bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-4 px-4 py-4">
          <Link href="/dashboard" className="text-lg font-semibold tracking-tight">
            Ads analyst
          </Link>
          <nav className="flex flex-wrap gap-3 text-sm">
            {LINKS.map(([href, label]) => (
              <Link key={href} href={href} className={pathname === href ? "font-semibold text-pine" : "text-neutral-600"}>
                {label}
              </Link>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-3">
            <select
              aria-label="Google Ads account"
              className="rounded-md border border-line bg-paper px-2 py-1 text-sm"
              value={selected}
              onChange={(event) => {
                setAccountId(event.target.value);
                setSelected(event.target.value);
                router.refresh();
                window.location.reload();
              }}
            >
              {accounts.length === 0 ? <option value="">No account</option> : null}
              {accounts.map((account) => (
                <option key={account.id} value={account.id}>
                  {account.account_name || account.customer_id}
                </option>
              ))}
            </select>
            <button
              className="text-sm text-neutral-600"
              onClick={() => {
                localStorage.removeItem("gads_token");
                router.push("/login");
              }}
            >
              Sign out
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6">{children}</main>
    </div>
  );
}

export function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-xl border border-line bg-white p-4">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-neutral-500">{title}</h2>
      {children}
    </section>
  );
}
