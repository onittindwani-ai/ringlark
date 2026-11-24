export class ApiError extends Error {
  constructor(message: string, public status: number) {
    super(message);
  }
}

type Init = Omit<RequestInit, "body"> & { json?: unknown };

/** Every call goes to this app's own /api, which forwards to the real API with the session cookie. */
export async function api<T>(path: string, init: Init = {}): Promise<T> {
  const { json, headers, ...rest } = init;
  let res: Response;
  try {
    res = await fetch(`/api${path}`, {
      ...rest,
      headers: { "x-ringlark": "1", ...(json !== undefined ? { "content-type": "application/json" } : {}), ...headers },
      body: json !== undefined ? JSON.stringify(json) : undefined,
      cache: "no-store",
    });
  } catch {
    throw new ApiError("Could not reach the server. Check your connection and try again.", 0);
  }
  if (res.status === 401 && typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
    const here = window.location.pathname + window.location.search;
    window.location.assign(here === "/" ? "/login" : `/login?next=${encodeURIComponent(here)}`);
  }
  if (!res.ok) {
    let msg = `The server answered ${res.status}.`;
    try {
      const body = await res.json();
      msg = body?.error?.message ?? body?.detail?.[0]?.msg ?? msg;
    } catch {
      /* keep the generic message */
    }
    throw new ApiError(msg, res.status);
  }
  return (res.headers.get("content-type")?.includes("json") ? res.json() : res.text()) as Promise<T>;
}

export const get = <T,>(path: string) => api<T>(path);
export const post = <T,>(path: string, json?: unknown) => api<T>(path, { method: "POST", json: json ?? {} });
export const put = <T,>(path: string, json: unknown) => api<T>(path, { method: "PUT", json });
