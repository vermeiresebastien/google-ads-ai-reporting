"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { API_URL } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("demo@example.com");
  const [password, setPassword] = useState("demo-password-123");
  const [workspaceName, setWorkspaceName] = useState("My workspace");
  const [error, setError] = useState("");

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    const path = mode === "login" ? "/api/auth/login" : "/api/auth/register";
    const body = mode === "login" ? { email, password } : { email, password, workspace_name: workspaceName };
    const response = await fetch(`${API_URL}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const payload = await response.json();
    if (!response.ok) {
      setError(typeof payload.detail === "string" ? payload.detail : "Request failed");
      return;
    }
    localStorage.setItem("gads_token", payload.access_token);
    router.push("/dashboard");
  }

  async function loadDemo() {
    setError("");
    const response = await fetch(`${API_URL}/api/demo/seed`, { method: "POST" });
    const payload = await response.json();
    if (!response.ok) {
      setError(typeof payload.detail === "string" ? payload.detail : "Demo seed is disabled");
      return;
    }
    setEmail(payload.email);
    setPassword(payload.password);
    setMode("login");
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-4">
      <h1 className="text-3xl font-semibold tracking-tight">Google Ads analyst</h1>
      <p className="mt-2 text-sm text-neutral-600">Ask what changed, why, and what to do. Answers come from the analytical tools.</p>
      <form onSubmit={submit} className="mt-6 space-y-3 rounded-xl border border-line bg-white p-4">
        <label className="block text-sm">
          Email
          <input className="mt-1 w-full rounded-md border border-line px-3 py-2" value={email} onChange={(event) => setEmail(event.target.value)} />
        </label>
        <label className="block text-sm">
          Password
          <input type="password" className="mt-1 w-full rounded-md border border-line px-3 py-2" value={password} onChange={(event) => setPassword(event.target.value)} />
        </label>
        {mode === "register" ? (
          <label className="block text-sm">
            Workspace
            <input className="mt-1 w-full rounded-md border border-line px-3 py-2" value={workspaceName} onChange={(event) => setWorkspaceName(event.target.value)} />
          </label>
        ) : null}
        {error ? <p className="text-sm text-red-700">{error}</p> : null}
        <button className="w-full rounded-md bg-pine px-3 py-2 text-white" type="submit">
          {mode === "login" ? "Sign in" : "Create workspace"}
        </button>
        <button className="w-full text-sm text-neutral-600" type="button" onClick={() => setMode(mode === "login" ? "register" : "login")}>
          {mode === "login" ? "Need a workspace? Register" : "Already registered? Sign in"}
        </button>
        <button className="w-full text-sm text-pine" type="button" onClick={loadDemo}>
          Load local demo data
        </button>
      </form>
    </main>
  );
}
