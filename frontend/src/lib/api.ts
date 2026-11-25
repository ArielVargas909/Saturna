const BASE: string = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/+$/, "");
export const API_BASE = BASE;
const KEY = "saturna.tokens";

interface Tokens {
  access_token: string;
  refresh_token: string;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export const tokens = {
  get(): Tokens | null {
    try {
      return JSON.parse(localStorage.getItem(KEY) ?? "null");
    } catch {
      return null;
    }
  },
  set(t: Tokens) {
    localStorage.setItem(KEY, JSON.stringify(t));
  },
  clear() {
    localStorage.removeItem(KEY);
  },
};

function messageOf(body: unknown, fallback: string): string {
  const d = (body as { detail?: unknown })?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d) && d[0]?.msg) return String(d[0].msg);
  return fallback;
}

let refreshing: Promise<boolean> | null = null;
async function refresh(): Promise<boolean> {
  const t = tokens.get();
  if (!t) return false;
  refreshing ??= fetch(`${BASE}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: t.refresh_token }),
  })
    .then(async (r) => {
      if (!r.ok) return false;
      tokens.set(await r.json());
      return true;
    })
    .catch(() => false)
    .finally(() => {
      refreshing = null;
    });
  return refreshing;
}

async function raw(path: string, init: RequestInit = {}, retry = true): Promise<Response> {
  const t = tokens.get();
  const headers = new Headers(init.headers);
  if (init.body) headers.set("Content-Type", "application/json");
  if (t) headers.set("Authorization", `Bearer ${t.access_token}`);
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, "No hay conexión con el servidor. Revisa tu internet.");
  }
  if (res.status === 401 && retry && t && (await refresh())) return raw(path, init, false);
  if (res.status === 401 && t) {
    tokens.clear();
    window.dispatchEvent(new Event("saturna:logout"));
  }
  return res;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await raw(path, init);
  const body = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, messageOf(body, `Error ${res.status}`));
  return body as T;
}

export const api = {
  get: <T>(p: string) => request<T>(p),
  post: <T>(p: string, data?: unknown) =>
    request<T>(p, { method: "POST", body: data === undefined ? undefined : JSON.stringify(data) }),
  patch: <T>(p: string, data?: unknown) =>
    request<T>(p, { method: "PATCH", body: data === undefined ? undefined : JSON.stringify(data) }),
  async download(path: string, filename: string) {
    const res = await raw(path);
    if (!res.ok)
      throw new ApiError(
        res.status,
        messageOf(await res.json().catch(() => null), "No se pudo exportar"),
      );
    const url = URL.createObjectURL(await res.blob());
    const a = Object.assign(document.createElement("a"), { href: url, download: filename });
    a.click();
    URL.revokeObjectURL(url);
  },
};
