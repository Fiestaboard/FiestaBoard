// Shared fetch plumbing for the FiestaBoard API client.
//
// All API calls go through nginx at /api/* (same origin, unified
// container). URLs are built via apiUrl() so they pick up the runtime
// base path when the app is served from a subpath (HA Ingress) — see
// lib/base-path.ts. Every domain module under ./ builds on fetchApi;
// the SSE chat client (lib/api-stream.ts) shares
// redirectToLoginIfNeeded so streaming 401/409s land on /login too.

import { apiUrl, appUrl, stripBasePath } from "../base-path";
import { isPanelPath } from "../chromeless";

const DEFAULT_TIMEOUT_MS = 30000;

/**
 * On 401 (not authenticated) or 409 setup-required responses, send the
 * user to /login. The login page handles both cases: an unsigned-in
 * user sees the sign-in form; a fresh install with no admin yet sees
 * the first-run picker / setup form.
 *
 * Runs in the browser only and never on the login page itself (to avoid
 * a redirect loop while signing in). The current URL is preserved in the
 * `redirect` query param so we can bounce back after a successful login.
 *
 * Returns true if a redirect was initiated.
 */
export function redirectToLoginIfNeeded(res: globalThis.Response): boolean {
  if (typeof window === "undefined") return false;
  // Compare app-relative routes: under HA Ingress the raw pathname is
  // "<prefix>/login", which a bare "/login" check would miss and loop.
  if (stripBasePath(window.location.pathname).startsWith("/login")) return false;
  // The FiestaPanel viewer runs on TVs with no session; a stray 401/409
  // from a background query must never bounce the wall display to /login.
  if (isPanelPath(window.location.pathname)) return false;
  if (res.status === 401 || res.status === 409) {
    // For 409 only redirect when the body actually says setup_required —
    // other 409s (e.g. "already set up") should bubble up as errors.
    if (res.status === 409) {
      const ct = res.headers.get("content-type") ?? "";
      if (!ct.includes("application/json")) return false;
      // Peek at the body without consuming it for the caller.
      const cloned = res.clone();
      cloned
        .json()
        .then((body) => {
          if (body?.setup_required) {
            window.location.assign(appUrl(`/login?redirect=${loginRedirectTarget()}`));
          }
        })
        .catch(() => {
          // Not JSON or malformed — leave the caller to surface the error.
        });
      return false;
    }
    window.location.assign(appUrl(`/login?redirect=${loginRedirectTarget()}`));
    return true;
  }
  return false;
}

/**
 * App-relative route to bounce back to after login. Kept prefix-free:
 * the login page navigates with the basename-aware router, which
 * re-applies the ingress prefix on its own.
 */
function loginRedirectTarget(): string {
  return encodeURIComponent(stripBasePath(window.location.pathname) + window.location.search);
}

/**
 * Error thrown by fetchApi for non-2xx responses. Carries the HTTP
 * status so callers can branch on it — e.g. a 401 from /auth/mcp-token
 * on an auth-disabled install means "management is locked behind the
 * current token" (#1825), not "not signed in".
 */
export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export async function fetchApi<T>(
  path: string,
  options?: RequestInit & { timeoutMs?: number; skipAuthRedirect?: boolean },
): Promise<T> {
  const { timeoutMs = DEFAULT_TIMEOUT_MS, skipAuthRedirect = false, ...fetchOptions } = options ?? {};
  const timeoutSignal = AbortSignal.timeout(timeoutMs);
  const signal = fetchOptions.signal ? AbortSignal.any([fetchOptions.signal, timeoutSignal]) : timeoutSignal;

  let res: globalThis.Response;
  try {
    res = await fetch(apiUrl(path), {
      ...fetchOptions,
      signal,
      // Send the session cookie on every API call so auth-protected
      // endpoints work when FIESTABOARD_AUTH_ENABLED is on. Same-origin
      // requests already include cookies by default, but be explicit so
      // future cross-origin deployments behave the same way.
      credentials: fetchOptions.credentials ?? "include",
      headers: {
        "Content-Type": "application/json",
        ...fetchOptions.headers,
      },
    });
  } catch (err) {
    throw err;
  }
  if (!res.ok) {
    if (!skipAuthRedirect) {
      redirectToLoginIfNeeded(res);
    }
    let detail = `API error: ${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail) {
        detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
      }
    } catch {
      // ignore JSON parse errors; use status text fallback
    }
    throw new ApiError(detail, res.status);
  }
  return res.json();
}
