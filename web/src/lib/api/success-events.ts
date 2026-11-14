/**
 * A tiny pub-sub for successful API calls, fed by `fetchApi`.
 *
 * It lets app-wide features react to "something worked" (the install offer
 * waits for a real success, WEB-12) without every send and save site in the
 * app knowing about them. Listeners get the method and the API path only,
 * never a request or response body.
 */

export interface ApiSuccess {
  method: string;
  /** The API path as passed to fetchApi, e.g. "/v1/pages" (no base path, no query). */
  path: string;
}

type Listener = (event: ApiSuccess) => void;

const listeners = new Set<Listener>();

export function onApiSuccess(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function emitApiSuccess(method: string | undefined, path: string): void {
  if (listeners.size === 0) return;
  const event: ApiSuccess = { method: (method ?? "GET").toUpperCase(), path: path.split("?")[0] };
  for (const listener of listeners) {
    try {
      listener(event);
    } catch {
      // A listener's bug must never fail the API call that succeeded.
    }
  }
}

/**
 * Which successes count as value for the install offer (07 `58:34443`: "3rd
 * send, or a saved page"). Sends: a composed message, a page shown now, the
 * setup wizard's welcome message. Saves: a page created or updated.
 */
export function classifyInstallSuccess({ method, path }: ApiSuccess): "send" | "save" | null {
  if (method === "POST" && /^\/v1\/boards\/[^/]+\/message$/.test(path)) return "send";
  if (method === "PUT" && path === "/settings/active-page") return "send";
  if (method === "POST" && path === "/send-welcome-message") return "send";
  if (method === "POST" && path === "/v1/pages") return "save";
  if (method === "PUT" && /^\/v1\/pages\/[^/]+$/.test(path)) return "save";
  return null;
}
