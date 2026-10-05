"use client";

import { useEffect, useState } from "react";
import { Panel, Shell } from "@/components/shell";
import { api } from "@/lib/api";
import { useAccountId } from "@/lib/use-account";

export default function ReportsPage() {
  const [answer, setAnswer] = useState("");
  const [question, setQuestion] = useState("What happened in Google Ads yesterday, why did it happen, and what should I do today?");
  const [error, setError] = useState("");

  const id = useAccountId();

  useEffect(() => {
    if (!id) return;
    api<{ answer: string }>("/api/ai/query", {
      method: "POST",
      body: JSON.stringify({ account_id: id, question }),
    }).then((payload) => setAnswer(payload.answer)).catch((reason: Error) => setError(reason.message));
    // The initial report is loaded once for the default question.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  async function ask(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    try {
      const payload = await api<{ answer: string }>("/api/ai/query", {
        method: "POST",
        body: JSON.stringify({ account_id: id, question }),
      });
      setAnswer(payload.answer);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Query failed");
    }
  }

  return (
    <Shell>
      <h1 className="mb-4 text-2xl font-semibold">Reports</h1>
      <form onSubmit={ask} className="mb-4 flex flex-col gap-2 sm:flex-row">
        <input className="flex-1 rounded-md border border-line px-3 py-2 text-sm" value={question} onChange={(event) => setQuestion(event.target.value)} />
        <button className="rounded-md bg-pine px-3 py-2 text-sm text-white" type="submit">Ask</button>
      </form>
      {error ? <p className="mb-3 text-sm text-red-700">{error}</p> : null}
      <Panel title="Analyst">
        <pre className="whitespace-pre-wrap font-sans text-sm leading-6">{answer || "Preparing the report from the analytical tools."}</pre>
      </Panel>
    </Shell>
  );
}
