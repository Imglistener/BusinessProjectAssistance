import { getLang, t } from "../i18n";

const BASE: string = import.meta.env.VITE_API_BASE_URL ?? "/api";
const TOKEN_KEY = "bpa.token";
/** Fired when the server rejects the stored token (expired or invalid); AuthContext logs the user out. */
export const SESSION_EXPIRED_EVENT = "bpa:session-expired";

export const tokenStore = {
  get(): string | null {
    try {
      return localStorage.getItem(TOKEN_KEY);
    } catch {
      return null;
    }
  },
  set(token: string) {
    try {
      localStorage.setItem(TOKEN_KEY, token);
    } catch {
      /* storage unavailable: the session lasts until the page reloads */
    }
  },
  clear() {
    try {
      localStorage.removeItem(TOKEN_KEY);
    } catch {
      /* ignore */
    }
  },
};

export class ApiError extends Error {
  code: string;
  status: number;
  field?: string;
  /** Extra facts from the server, e.g. {line: 2} for a batch of stock changes. */
  details?: Record<string, unknown>;

  constructor(code: string, message: string, status: number, field?: string, details?: Record<string, unknown>) {
    super(message);
    this.code = code;
    this.status = status;
    this.field = field;
    this.details = details;
  }
}

export async function api<T>(path: string, options: { method?: string; body?: unknown } = {}): Promise<T> {
  const headers: Record<string, string> = { "Accept-Language": getLang() };
  const token = tokenStore.get();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (options.body !== undefined) headers["Content-Type"] = "application/json";

  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      method: options.method ?? (options.body !== undefined ? "POST" : "GET"),
      headers,
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    });
  } catch {
    throw new ApiError("network", t("Can't reach the server. Check that the backend is running."), 0);
  }

  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const err = data?.error;
    if (res.status === 401 && token && ["token_expired", "invalid_token", "unauthorized"].includes(err?.code)) {
      tokenStore.clear();
      window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
    }
    throw new ApiError(
      err?.code ?? "unknown",
      err?.message ?? t("Something went wrong. Try again."),
      res.status,
      err?.details?.field,
      err?.details,
    );
  }
  return data as T;
}

/** Fetch an authenticated file (e.g. CSV) and save it; plain links can't send the token. */
export async function download(path: string, fallbackName: string): Promise<void> {
  const token = tokenStore.get();
  let res: Response;
  try {
    const headers: Record<string, string> = { "Accept-Language": getLang() };
    if (token) headers.Authorization = `Bearer ${token}`;
    res = await fetch(`${BASE}${path}`, { headers });
  } catch {
    throw new ApiError("network", t("Can't reach the server. Check that the backend is running."), 0);
  }
  if (!res.ok) {
    const err = (await res.json().catch(() => null))?.error;
    throw new ApiError(err?.code ?? "unknown", err?.message ?? t("The download failed. Try again."), res.status);
  }
  const name = /filename="([^"]+)"/.exec(res.headers.get("Content-Disposition") ?? "")?.[1] ?? fallbackName;
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function authedFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const token = tokenStore.get();
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  headers.set("Accept-Language", getLang());
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, { ...init, headers });
  } catch {
    throw new ApiError("network", t("Can't reach the server. Check that the backend is running."), 0);
  }
  if (!res.ok) {
    const err = (await res.json().catch(() => null))?.error;
    throw new ApiError(
      err?.code ?? "unknown",
      err?.message ?? t("Something went wrong. Try again."),
      res.status,
      err?.details?.field,
    );
  }
  return res;
}

/** Upload one file as multipart form data (the browser sets the boundary header). */
export async function uploadFile<T>(path: string, file: File): Promise<T> {
  const body = new FormData();
  body.append("file", file);
  const res = await authedFetch(path, { method: "POST", body });
  return (await res.json()) as T;
}

/** Open an authenticated file (receipt) in a new tab. */
export async function openFile(path: string): Promise<void> {
  // Open the tab first, synchronously with the click, so pop-up blockers allow it.
  const tab = window.open("", "_blank");
  try {
    const blob = await (await authedFetch(path)).blob();
    const url = URL.createObjectURL(blob);
    if (tab) tab.location.href = url;
    else window.location.href = url;
    setTimeout(() => URL.revokeObjectURL(url), 60_000);
  } catch (e) {
    tab?.close();
    throw e;
  }
}
