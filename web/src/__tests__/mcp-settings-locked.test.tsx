/**
 * Locked-state flow for MCP token management on auth-disabled installs
 * (#1825). When auth mode is "disabled" and a token is already
 * configured, the backend answers 401 (Bearer challenge) on
 * GET/POST/DELETE /auth/mcp-token unless the caller presents the
 * current token. The UI must treat that 401 as "locked" — never as
 * "not logged in" — and offer an unlock form instead of bouncing to
 * /login.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { McpSettings } from "@/components/settings/mcp-settings";

import { server } from "./mocks/server";

const CORRECT_TOKEN = "test_current_mcp_token";
const ROTATED_TOKEN = "test_rotated_mcp_token";

function TestWrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

/**
 * Install a GET /api/auth/mcp-token handler that mimics the backend
 * gate: 401 + Bearer challenge unless the request carries
 * `Authorization: Bearer <expected>`.
 */
function useLockedStatusHandler(expected: string, seenAuth: string[] = []) {
  server.use(
    http.get("/api/auth/mcp-token", ({ request }) => {
      const auth = request.headers.get("authorization") ?? "";
      seenAuth.push(auth);
      if (auth === `Bearer ${expected}`) {
        return HttpResponse.json({ configured: true, source: "stored" });
      }
      return HttpResponse.json(
        { detail: "MCP token management requires the current token when auth is disabled" },
        { status: 401, headers: { "WWW-Authenticate": 'Bearer realm="FiestaBoard MCP token management"' } },
      );
    }),
  );
  return seenAuth;
}

describe("McpSettings locked state (auth disabled + token configured)", () => {
  let originalLocation: Location;
  let assignMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    assignMock = vi.fn();
    originalLocation = window.location;
    // Mimic a settings route (not /login) so a login redirect, if one
    // were wrongly triggered, would actually fire and be observable.
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

  it("renders the locked state on 401 without redirecting to /login", async () => {
    useLockedStatusHandler(CORRECT_TOKEN);

    render(<McpSettings />, { wrapper: TestWrapper });

    expect(await screen.findByLabelText("Current MCP token")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Unlock" })).toBeInTheDocument();
    expect(assignMock).not.toHaveBeenCalled();
  });

  it("unlocking with the correct token shows the token status", async () => {
    useLockedStatusHandler(CORRECT_TOKEN);
    const user = userEvent.setup();

    render(<McpSettings />, { wrapper: TestWrapper });

    await user.type(await screen.findByLabelText("Current MCP token"), CORRECT_TOKEN);
    await user.click(screen.getByRole("button", { name: "Unlock" }));

    expect(await screen.findByText("Configured")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Unlock" })).not.toBeInTheDocument();
    expect(assignMock).not.toHaveBeenCalled();
  });

  it("rotating while unlocked sends the bearer and updates the held token", async () => {
    const seenAuth = useLockedStatusHandler(CORRECT_TOKEN);
    const rotateAuth: string[] = [];
    server.use(
      http.post("/api/auth/mcp-token", ({ request }) => {
        const auth = request.headers.get("authorization") ?? "";
        rotateAuth.push(auth);
        if (auth !== `Bearer ${CORRECT_TOKEN}`) {
          return HttpResponse.json({ detail: "Bad token" }, { status: 401 });
        }
        return HttpResponse.json({ token: ROTATED_TOKEN }, { status: 201 });
      }),
    );
    const user = userEvent.setup();

    render(<McpSettings />, { wrapper: TestWrapper });

    // Unlock first.
    await user.type(await screen.findByLabelText("Current MCP token"), CORRECT_TOKEN);
    await user.click(screen.getByRole("button", { name: "Unlock" }));
    expect(await screen.findByText("Configured")).toBeInTheDocument();

    // Rotation invalidates the old token: from now on the status
    // endpoint only accepts the NEW one, mimicking the backend.
    server.use(
      http.get("/api/auth/mcp-token", ({ request }) => {
        const auth = request.headers.get("authorization") ?? "";
        seenAuth.push(auth);
        if (auth === `Bearer ${ROTATED_TOKEN}`) {
          return HttpResponse.json({ configured: true, source: "stored" });
        }
        return HttpResponse.json({ detail: "stale token" }, { status: 401 });
      }),
    );

    // Rotate: open the confirm dialog, then confirm.
    await user.click(screen.getByRole("button", { name: "Rotate token" }));
    await user.click(await screen.findByRole("button", { name: "Rotate" }));

    // The reveal dialog shows the new token once.
    expect(await screen.findByText(ROTATED_TOKEN)).toBeInTheDocument();
    // The rotate call itself carried the (then-current) bearer.
    expect(rotateAuth).toEqual([`Bearer ${CORRECT_TOKEN}`]);

    // The post-rotate status refetch must use the NEW token — i.e. the
    // held token was updated — and management must stay unlocked.
    await waitFor(() => {
      expect(seenAuth[seenAuth.length - 1]).toBe(`Bearer ${ROTATED_TOKEN}`);
    });
    expect(screen.queryByRole("button", { name: "Unlock" })).not.toBeInTheDocument();
    expect(assignMock).not.toHaveBeenCalled();
  });

  it("shows an inline error toast when the unlock token is wrong", async () => {
    useLockedStatusHandler(CORRECT_TOKEN);
    const user = userEvent.setup();

    render(<McpSettings />, { wrapper: TestWrapper });

    await user.type(await screen.findByLabelText("Current MCP token"), "wrong-token");
    await user.click(screen.getByRole("button", { name: "Unlock" }));

    // Still locked, no redirect.
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Unlock" })).toBeInTheDocument();
    });
    expect(screen.queryByText("Configured")).not.toBeInTheDocument();
    expect(assignMock).not.toHaveBeenCalled();
  });
});
