const BASE: string = import.meta.env.VITE_API_BASE_URL ?? "/api";
const TOKEN_KEY = "bpa.token";

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

  constructor(code: string, message: string, status: number, field?: string) {
    super(message);
    this.code = code;
    this.status = status;
    this.field = field;
  }
}

export async function api<T>(path: string, options: { method?: string; body?: unknown } = {}): Promise<T> {
  const headers: Record<string, string> = {};
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
    throw new ApiError("network", "Can't reach the server. Check that the backend is running.", 0);
  }

  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const err = data?.error;
    throw new ApiError(
      err?.code ?? "unknown",
      err?.message ?? "Something went wrong. Try again.",
      res.status,
      err?.details?.field,
    );
  }
  return data as T;
}
