"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Term } from "@/components/term";
import { accountId, api, setAccountId, token } from "@/lib/api";

const LINKS = [
  ["/dashboard", "Dashboard"],
  ["/campaigns", "Campaigns"],
  ["/search-terms", "Search terms"],
  ["/changes", "Changes"],
  ["/reports", "Reports"],
  ["/trends", "Trends"],
  ["/actions", "Actions"],
  ["/raw-data", "Raw Data"],
];

type Account = {
  id: string;
  account_name: string;
  customer_id: string;
  platform_label?: string;
  search_terms?: boolean;
  changes?: boolean;
};

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [selected, setSelected] = useState("");
  const current = accounts.find((account) => account.id === selected);
  const links = LINKS.filter(([href]) => {
    if (!current) return true;
    if (href === "/search-terms") return current.search_terms !== false;
    if (href === "/changes") return current.changes !== false;
    return true;
  });

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
        } else {
          localStorage.removeItem("gads_account_id");
          setSelected("");
        }
      })
      .catch(() => undefined);
  }, [router]);

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-30 border-b border-line bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-4 px-4 py-4">
          <Link href="/dashboard" className="text-lg font-semibold tracking-tight">
            Ads analyst
          </Link>
          <nav className="flex flex-wrap gap-3 text-sm">
            {links.map(([href, label]) => (
              <Link key={href} href={href} className={pathname === href ? "font-semibold text-pine" : "text-neutral-600"}>
                {label}
              </Link>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-3">
            <select
              aria-label="Advertising account"
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
                  {account.platform_label ? `${account.account_name || account.customer_id} · ${account.platform_label}` : account.account_name || account.customer_id}
                </option>
              ))}
            </select>
            <Link
              href="/configure"
              aria-label="Configure"
              title="Configure"
              className={`rounded-md p-1 ${pathname === "/configure" ? "text-pine" : "text-neutral-600"}`}
            >
              <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z" />
                <path strokeLinecap="round" strokeLinejoin="round" d="M19.4 13a7.7 7.7 0 0 0 .1-2l2-1.2-2-3.4-2.3.7a7.8 7.8 0 0 0-1.7-1L15 3.5h-4l-.5 2.6a7.8 7.8 0 0 0-1.7 1L6.5 6.4l-2 3.4L6.5 11a7.7 7.7 0 0 0 .1 2l-2 1.2 2 3.4 2.3-.7a7.8 7.8 0 0 0 1.7 1l.5 2.6h4l.5-2.6a7.8 7.8 0 0 0 1.7-1l2.3.7 2-3.4-2-1.2Z" />
              </svg>
            </Link>
            <button
              className="text-sm text-neutral-600"
              onClick={() => {
                localStorage.removeItem("gads_token");
                localStorage.removeItem("gads_account_id");
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
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-neutral-500"><Term>{title}</Term></h2>
      {children}
    </section>
  );
}
