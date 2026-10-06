"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { API_URL } from "@/lib/api";

function messageFrom(payload: { detail?: unknown }, status: number): string {
  const detail = payload.detail;
  if (typeof detail === "string") {
    if (status === 401) return "No account matches that email and password. Register a workspace first.";
    return detail;
  }
  if (Array.isArray(detail)) {
    const password = detail.find(
      (item) => item && typeof item === "object" && "loc" in item && Array.isArray(item.loc) && item.loc.includes("password"),
    );
    if (password) return "Password must be at least 8 characters.";
  }
  return "Request failed";
}

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [workspaceName, setWorkspaceName] = useState("My workspace");
  const [error, setError] = useState("");

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    const form = new FormData(event.currentTarget);
    const submittedEmail = String(form.get("email") ?? email).trim();
    const submittedPassword = String(form.get("password") ?? password);
    const submittedWorkspace = String(form.get("workspace") ?? workspaceName).trim();
    if (submittedPassword.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    const path = mode === "login" ? "/api/auth/login" : "/api/auth/register";
    const body =
      mode === "login"
        ? { email: submittedEmail, password: submittedPassword }
        : { email: submittedEmail, password: submittedPassword, workspace_name: submittedWorkspace || "My workspace" };
    const response = await fetch(`${API_URL}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      setError(messageFrom(payload, response.status));
      return;
    }
    localStorage.removeItem("gads_account_id");
    localStorage.setItem("gads_token", payload.access_token);
    router.push("/dashboard");
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-4">
      <h1 className="text-3xl font-semibold tracking-tight">Google Ads analyst</h1>
      <p className="mt-2 text-sm text-neutral-600">Ask what changed, why, and what to do. Answers come from the analytical tools.</p>
      <form onSubmit={submit} className="mt-6 space-y-3 rounded-xl border border-line bg-white p-4">
        <label className="block text-sm">
          Email
          <input name="email" autoComplete="username" className="mt-1 w-full rounded-md border border-line px-3 py-2" value={email} onChange={(event) => setEmail(event.target.value)} />
        </label>
        <label className="block text-sm">
          Password
          <input name="password" type="password" autoComplete={mode === "login" ? "current-password" : "new-password"} minLength={8} className="mt-1 w-full rounded-md border border-line px-3 py-2" value={password} onChange={(event) => setPassword(event.target.value)} />
        </label>
        {mode === "register" ? (
          <label className="block text-sm">
            Workspace
            <input name="workspace" className="mt-1 w-full rounded-md border border-line px-3 py-2" value={workspaceName} onChange={(event) => setWorkspaceName(event.target.value)} />
          </label>
        ) : null}
        {mode === "register" ? <p className="text-xs text-neutral-500">Password must be at least 8 characters.</p> : null}
        {error ? <p className="text-sm text-red-700">{error}</p> : null}
        <button className="w-full rounded-md bg-pine px-3 py-2 text-white" type="submit">
          {mode === "login" ? "Sign in" : "Create workspace"}
        </button>
        <button className="w-full text-sm text-neutral-600" type="button" onClick={() => setMode(mode === "login" ? "register" : "login")}>
          {mode === "login" ? "Need a workspace? Register" : "Already registered? Sign in"}
        </button>
      </form>
    </main>
  );
}
