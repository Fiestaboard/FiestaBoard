/**
 * Regressions from the #1853 review.
 *
 * 1. First mint on an auth-disabled install: rotate's onSuccess must hold
 *    the freshly minted token unconditionally. If it only holds it when a
 *    previous unlock populated the ref, the post-mint status refetch goes
 *    out with no bearer, 401s, flips the component into the locked view,
 *    and unmounts the reveal dialog before the user can copy the token.
 *
 * 2. Auth-enabled installs: the MCP token calls skip fetchApi's automatic
 *    login redirect (a 401 means "locked" on auth-disabled installs), so
 *    when the *session* expires the component itself must send the user
 *    to /login instead of rendering a perpetual skeleton.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { McpSettings } from "@/components/settings/mcp-settings";

import { server } from "./mocks/server";

const MINTED_TOKEN = "test_first_minted_mcp_token";

function TestWrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

describe("McpSettings first mint and expired-session handling", () => {
  let originalLocation: Location;
  let assignMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    assignMock = vi.fn();
    originalLocation = window.location;
    // Mimic a settings route (not /login) so a login redirect is
    // observable via window.location.assign.
    Object.defineProperty(window, "location", {
      configurable: true,
      value: {
        ...originalLocation,
        pathname: "/settings",
        search: "",
        assign: assignMock,
      },
    });
  });

  afterEach(() => {
    Object.defineProperty(window, "location", {
      configurable: true,
      value: originalLocation,
    });
  });

  it("first mint on an auth-disabled install keeps the reveal open and holds the new token", async () => {
    // Backend state machine: no token at first (open management), then
    // once POST mints one, GET is gated behind the new token — exactly
    // the #1825 backend behavior on auth-disabled installs.
    let minted = false;
    const seenAuth: string[] = [];
    server.use(
      http.get("/api/auth/mcp-token", ({ request }) => {
        const auth = request.headers.get("authorization") ?? "";
        seenAuth.push(auth);
        if (!minted) {
          return HttpResponse.json({ configured: false, source: "none" });
        }
        if (auth === `Bearer ${MINTED_TOKEN}`) {
          return HttpResponse.json({ configured: true, source: "stored" });
        }
        return HttpResponse.json(
          { detail: "MCP token management requires the current token when auth is disabled" },
          { status: 401, headers: { "WWW-Authenticate": 'Bearer realm="FiestaBoard MCP token management"' } },
        );
      }),
      http.post("/api/auth/mcp-token", () => {
        minted = true;
        return HttpResponse.json({ token: MINTED_TOKEN }, { status: 201 });
      }),
    );
    const user = userEvent.setup();

    render(<McpSettings />, { wrapper: TestWrapper });

    // No token configured yet — mint the first one.
    await user.click(await screen.findByRole("button", { name: "Generate token" }));
    await user.click(await screen.findByRole("button", { name: "Generate" }));

    // The reveal dialog shows the new token once.
    expect(await screen.findByText(MINTED_TOKEN)).toBeInTheDocument();

    // The post-mint status refetch must carry the new bearer (the held
    // token was set even though nothing was held before the mint).
    await waitFor(() => {
      expect(seenAuth[seenAuth.length - 1]).toBe(`Bearer ${MINTED_TOKEN}`);
    });

    // The reveal must STAY mounted — flipping into the locked view here
    // would unmount it before the user can copy the token.
    expect(screen.getByText(MINTED_TOKEN)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Unlock" })).not.toBeInTheDocument();
    expect(assignMock).not.toHaveBeenCalled();
  });

  it("redirects to /login when the session is expired and auth is enabled", async () => {
    server.use(
      http.get("/api/auth/status", () => {
        return HttpResponse.json({
          enabled: true,
          setup_required: false,
          authenticated: false,
          username: null,
          mode: "enabled",
          first_run: false,
        });
      }),
      // Session cookie expired: every management call 401s.
      http.get("/api/auth/mcp-token", () => {
        return HttpResponse.json({ detail: "Not authenticated" }, { status: 401 });
      }),
    );

    render(<McpSettings />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(assignMock).toHaveBeenCalledTimes(1);
    });
    expect(String(assignMock.mock.calls[0][0])).toContain("/login?redirect=");
    // Never the locked view — that's an auth-disabled concept.
    expect(screen.queryByRole("button", { name: "Unlock" })).not.toBeInTheDocument();
  });
});
