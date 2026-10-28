import { apiUrl } from "../base-path";

export type SessionSummary = {
  id: string;
  kind: "browser" | "tv" | "legacy";
  device_name: string;
  client_id?: string | null;
  app_version?: string | null;
  method: "password" | "device_code";
  created_at: string;
  last_active_at: string;
  expires_at: string;
};
export type SessionList = { sessions: SessionSummary[]; current_session_id: string };
export type DeviceInspection = {
  user_code: string;
  device_name: string;
  client_id: string;
  app_version?: string | null;
  expires_in: number;
  scope: "tv_panels";
};
export class SessionApiError extends Error {
  constructor(
    public readonly code: string,
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "SessionApiError";
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(apiUrl(path), {
    ...options,
    credentials: "same-origin",
    cache: "no-store",
    redirect: "error",
    signal: options.signal ?? AbortSignal.timeout(30_000),
    headers: { "Content-Type": "application/json", ...options.headers },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new SessionApiError(body.error ?? "request_failed", response.status, body.detail ?? "Request failed");
  }
  return response.status === 204 ? (undefined as T) : response.json();
}
function getContext() {
  return request<{ csrf_token: string; expires_in: number }>("/auth/sessions/context");
}
async function mutate<T>(path: string, method: string, body?: unknown): Promise<T> {
  // Fetch immediately before each mutation: no nonce survives logout or account changes.
  const { csrf_token } = await getContext();
  return request<T>(path, {
    method,
    headers: { "X-CSRF-Token": csrf_token },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}
export const sessionsApi = {
  getContext,
  inspectDevice: (user_code: string) => mutate<DeviceInspection>("/auth/device/inspect", "POST", { user_code }),
  approveDevice: (user_code: string) => mutate<{ status: string }>("/auth/device/approve", "POST", { user_code }),
  denyDevice: (user_code: string) => mutate<{ status: string }>("/auth/device/deny", "POST", { user_code }),
  listSessions: () => request<SessionList>("/auth/sessions"),
  revokeSession: (id: string) => mutate<{ status: string }>(`/auth/sessions/${encodeURIComponent(id)}`, "DELETE"),
  revokeSessions: (include_current: boolean) =>
    mutate<{ status: string }>("/auth/sessions/revoke", "POST", { include_current }),
  getDeviceSettings: () => request<{ enabled: boolean }>("/auth/device/settings"),
  updateDeviceSettings: (enabled: boolean) => mutate<{ enabled: boolean }>("/auth/device/settings", "PUT", { enabled }),
};
