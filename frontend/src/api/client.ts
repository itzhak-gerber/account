export class ApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

let csrfToken: string | null = null;

/** Set from /api/v1/me; sent on every state-changing request. */
export function setCsrfToken(token: string | null) {
  csrfToken = token;
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  const isForm = body instanceof FormData;
  if (body !== undefined && !isForm) headers["Content-Type"] = "application/json";
  if (method !== "GET" && csrfToken) headers["X-CSRF-Token"] = csrfToken;
  const response = await fetch(path.startsWith("/auth/") ? path : `/api/v1${path}`, {
    method,
    credentials: "same-origin",
    headers,
    body: body === undefined ? undefined : isForm ? body : JSON.stringify(body),
  });
  if (response.status === 204) return undefined as T;
  const data: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const error = (data as { error?: { code?: string; message?: string } } | null)?.error;
    const detail = (data as { detail?: unknown } | null)?.detail;
    const code = error?.code ?? (response.status === 422 ? "validation_error" : "unknown_error");
    throw new ApiError(response.status, code, error?.message ?? JSON.stringify(detail ?? ""));
  }
  return data as T;
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body ?? {}),
  patch: <T>(path: string, body: unknown) => request<T>("PATCH", path, body),
  put: <T>(path: string, body: unknown) => request<T>("PUT", path, body),
  delete: (path: string) => request<void>("DELETE", path),
  /** Multipart upload of a single file in the "file" field. */
  upload: <T>(path: string, file: File, method = "PUT") => {
    const form = new FormData();
    form.append("file", file);
    return request<T>(method, path, form);
  },
};

/** Kept for existing callers. */
export const apiGet = api.get;

/** Full-page navigation into the login flow (Keycloak pages). */
export function startLogin(options: {
  returnTo?: string;
  register?: boolean;
  action?: "UPDATE_PASSWORD" | "CONFIGURE_TOTP";
  reauth?: boolean;
}) {
  const params = new URLSearchParams();
  const here = new URLSearchParams(window.location.search);
  here.delete("auth_error");
  const query = here.toString();
  params.set(
    "return_to",
    options.returnTo ?? window.location.pathname + (query ? `?${query}` : ""),
  );
  if (options.register) params.set("register", "true");
  if (options.action) params.set("action", options.action);
  if (options.reauth) params.set("reauth", "true");
  window.location.assign(`/auth/login?${params.toString()}`);
}
