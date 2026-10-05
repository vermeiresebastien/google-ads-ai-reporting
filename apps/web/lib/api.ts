export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function token() {
  return typeof window === "undefined" ? "" : localStorage.getItem("gads_token") ?? "";
}

export function accountId() {
  return typeof window === "undefined" ? "" : localStorage.getItem("gads_account_id") ?? "";
}

export function setAccountId(id: string) {
  localStorage.setItem("gads_account_id", id);
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token() ? { Authorization: `Bearer ${token()}` } : {}),
      ...(init.headers ?? {}),
    },
  });
  if (response.status === 401 && typeof window !== "undefined" && !path.startsWith("/api/auth")) {
    window.location.href = "/login";
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail = body.detail;
    throw new Error(typeof detail === "string" ? detail : response.statusText);
  }
  return response.json();
}
