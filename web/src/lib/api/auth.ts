// Auth domain: session status, sign-out, credential changes, the
// auth-mode preference, and the MCP bearer token.

import { apiUrl } from "../base-path";
import { fetchApi } from "./core";

/**
 * Shape of /auth/status. Exported so other UI surfaces (login page,
 * profile page) can share the type instead of redeclaring it.
 */
export type AuthStatusResponse = {
  enabled: boolean;
  setup_required: boolean;
  authenticated: boolean;
  username: string | null;
  mode: "enabled" | "disabled" | "undecided";
  first_run: boolean;
};

/**
 * Status of the pre-shared bearer token used by external MCP clients.
 * ``source: "env"`` means ``FIESTABOARD_MCP_TOKEN`` is pinned by ops and
 * the UI must hide rotate/clear actions; ``"stored"`` means it's
 * UI-managed; ``"none"`` means no token is configured (cookie auth only).
 */
export type McpTokenStatus = {
  configured: boolean;
  source: "env" | "stored" | "none";
};

export const authApi = {
  // --- Auth -----------------------------------------------------------
  // The login/setup forms talk to /api/auth/* directly (see
  // web/app/routes/login.tsx) because they need access to the response
  // `detail` field. The helpers below are for the rest of the UI — e.g.
  // a "Sign out" button in the profile menu.

  getAuthStatus: () => fetchApi<AuthStatusResponse>("/auth/status"),

  logout: () => fetchApi<{ status: string }>("/auth/logout", { method: "POST" }),

  /**
   * Change the signed-in user's password. Uses a bespoke fetch (rather than
   * fetchApi) so the caller can surface FastAPI's ``detail`` body — e.g.
   * "Current password is incorrect".
   */
  changePassword: async (currentPassword: string, newPassword: string) => {
    const res = await fetch(apiUrl("/auth/change-password"), {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        current_password: currentPassword,
        new_password: newPassword,
      }),
    });
    if (!res.ok) {
      let detail: string | undefined;
      try {
        const data = await res.json();
        if (data && typeof data.detail === "string") {
          detail = data.detail;
        }
      } catch {
        /* no JSON body */
      }
      throw new Error(detail || `Password change failed (${res.status})`);
    }
    return (await res.json()) as { status: string; username: string };
  },

  /** Rename the signed-in user. Same bespoke-fetch reasoning as changePassword. */
  changeUsername: async (currentPassword: string, newUsername: string) => {
    const res = await fetch(apiUrl("/auth/change-username"), {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        current_password: currentPassword,
        new_username: newUsername,
      }),
    });
    if (!res.ok) {
      let detail: string | undefined;
      try {
        const data = await res.json();
        if (data && typeof data.detail === "string") {
          detail = data.detail;
        }
      } catch {
        /* no JSON body */
      }
      throw new Error(detail || `Username change failed (${res.status})`);
    }
    return (await res.json()) as { status: string; username: string };
  },

  /**
   * Record the first-run / "should we lock this down" preference.
   * The backend refuses (409) when an admin user already exists or
   * when FIESTABOARD_AUTH_ENABLED pins the mode. Used by the first-
   * run picker on /login and by the "Turn on login" card in the
   * Account tab after a user has previously disabled auth.
   */
  setAuthPreference: async (enabled: boolean) => {
    const res = await fetch(apiUrl("/auth/preference"), {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled }),
    });
    if (!res.ok) {
      let detail: string | undefined;
      try {
        const data = await res.json();
        if (data && typeof data.detail === "string") {
          detail = data.detail;
        }
      } catch {
        /* no JSON body */
      }
      throw new Error(detail || `Setting preference failed (${res.status})`);
    }
    return (await res.json()) as { status: string };
  },

  /**
   * Turn off auth enforcement and delete the admin user. Gated by the
   * current password server-side so a stolen cookie alone can't open
   * the install up. After this returns the install is wide open —
   * the caller should redirect somewhere sensible (e.g. the home
   * page) since /login no longer applies.
   */
  disableAuth: async (currentPassword: string) => {
    const res = await fetch(apiUrl("/auth/disable"), {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ current_password: currentPassword }),
    });
    if (!res.ok) {
      let detail: string | undefined;
      try {
        const data = await res.json();
        if (data && typeof data.detail === "string") {
          detail = data.detail;
        }
      } catch {
        /* no JSON body */
      }
      throw new Error(detail || `Disable auth failed (${res.status})`);
    }
    return (await res.json()) as { status: string };
  },

  // ── MCP bearer token (admin only) ───────────────────────────────────────
  // Lets external MCP clients (Claude Desktop, Claude Code) connect by
  // pasting a one-time-shown token into their connector config instead
  // of editing FIESTABOARD_MCP_TOKEN in .env. See src/auth/routes.py.

  // On auth-disabled installs the backend gates these routes behind the
  // *current* token once one exists (#1825): a 401 here means "locked",
  // not "not signed in", so all three skip the login redirect and accept
  // an optional bearer to pass through as `Authorization`.

  getMcpTokenStatus: (currentToken?: string) =>
    fetchApi<McpTokenStatus>("/auth/mcp-token", {
      skipAuthRedirect: true,
      headers: currentToken ? { Authorization: `Bearer ${currentToken}` } : undefined,
    }),

  /**
   * Generate a fresh token, persist it server-side, and return the
   * plaintext value ONCE. The caller is responsible for showing it to
   * the user immediately — it can't be read back after this response.
   */
  rotateMcpToken: (currentToken?: string) =>
    fetchApi<{ token: string }>("/auth/mcp-token", {
      method: "POST",
      skipAuthRedirect: true,
      headers: currentToken ? { Authorization: `Bearer ${currentToken}` } : undefined,
    }),

  clearMcpToken: (currentToken?: string) =>
    fetchApi<{ status: string }>("/auth/mcp-token", {
      method: "DELETE",
      skipAuthRedirect: true,
      headers: currentToken ? { Authorization: `Bearer ${currentToken}` } : undefined,
    }),
};
