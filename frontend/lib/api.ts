// Empty NEXT_PUBLIC_API_URL = same origin (single-container deployment, /api proxied by Next).
export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

export type Mode = "live" | "demo";

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    super(typeof detail === "string" ? detail : (detail as { message?: string })?.message || `HTTP ${status}`);
    this.status = status;
    this.detail = detail;
  }
}

export function getToken(): string | null {
  try {
    return localStorage.getItem("bq_token");
  } catch {
    return null;
  }
}

export async function api<T = any>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const headers: Record<string, string> = { ...(init.headers as Record<string, string>) };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  let body = init.body;
  if (init.json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(init.json);
  }
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, { ...init, headers, body });
  } catch (e) {
    throw new ApiError(0, "BIOQUEST backend unreachable. Is the API running on " + API_URL + "?");
  }
  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) throw new ApiError(res.status, data?.detail ?? data);
  return data as T;
}

export function photoUrl(path: string) {
  const t = getToken();
  return `${API_URL}${path}${t ? `?token=${encodeURIComponent(t)}` : ""}`;
}

// "inat:123" <-> "inat-123" for URL segments
export const keyToSlug = (k: string) => k.replace(":", "-");
export const slugToKey = (s: string) => decodeURIComponent(s).replace("-", ":");
