import { apiUrl } from "../base-path";
import { sessionsApi } from "./sessions";

export interface PushStatus {
  public_key: string;
  user_enabled: boolean;
  device_enabled: boolean;
  subscribed: boolean;
  expiration_time: number | null;
  event_sources: string[];
  test_available: boolean;
}

export interface PushDeliveryResult {
  sent: number;
  failed: number;
  skipped: number;
  expired: number;
}

export class PushApiError extends Error {
  constructor(public readonly status: number) {
    super("Push request failed");
    this.name = "PushApiError";
  }
}

async function request<T>(path: string, method = "GET", body?: unknown): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (method !== "GET") {
    const context = await sessionsApi.getContext();
    headers["X-CSRF-Token"] = context.csrf_token;
  }
  const response = await fetch(apiUrl(`/push/${path}`), {
    method,
    headers,
    credentials: "same-origin",
    cache: "no-store",
    redirect: "error",
    signal: AbortSignal.timeout(15_000),
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  // Do not reflect subscription endpoints, keys or raw provider responses in UI errors.
  if (!response.ok) throw new PushApiError(response.status);
  return response.json();
}

export const pushApi = {
  getStatus: () => request<PushStatus>("status"),
  setPreference: (enabled: boolean) => request<PushStatus>("preferences", "PUT", { enabled }),
  subscribe: (subscription: PushSubscriptionJSON) =>
    request<PushStatus>("subscription", "PUT", { enabled: true, subscription }),
  unsubscribe: () => request<PushStatus>("subscription", "DELETE"),
  sendTest: () => request<PushDeliveryResult>("test", "POST", {}),
};
