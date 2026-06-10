import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { server } from "./mocks/server";

const replaceMock = vi.fn();

vi.mock("@/hooks/use-router", () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: replaceMock,
    refresh: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
    prefetch: vi.fn(),
  }),
  usePathname: () => "/profile",
}));

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

import { AccountSection } from "@/components/account-section";

function TestWrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

const authStatusAuthenticated = {
  enabled: true,
  setup_required: false,
  authenticated: true,
  username: "admin",
  mode: "enabled" as const,
  first_run: false,
};

const authStatusDisabled = {
  enabled: false,
  setup_required: false,
  authenticated: false,
  username: null,
  mode: "disabled" as const,
  first_run: false,
};

function mockAuthStatus(payload: typeof authStatusAuthenticated | typeof authStatusDisabled) {
  server.use(http.get("/api/auth/status", () => HttpResponse.json(payload)));
}

describe("AccountSection", () => {
  beforeEach(() => {
    replaceMock.mockReset();
  });

  it("renders nothing when auth is disabled", async () => {
    mockAuthStatus(authStatusDisabled);
    const { container } = render(<AccountSection />, { wrapper: TestWrapper });
    await waitFor(() => {
      expect(container.querySelector('[data-testid="account-loading"]')).toBeNull();
    });
    // No Account heading should be visible.
    expect(screen.queryByText(/Account/)).not.toBeInTheDocument();
  });

  it("shows the signed-in username when authenticated", async () => {
    mockAuthStatus(authStatusAuthenticated);
    render(<AccountSection />, { wrapper: TestWrapper });
    await screen.findByText("Signed in");
    expect(screen.getByText("admin")).toBeInTheDocument();
  });

  it("submits a username change with the current password", async () => {
    mockAuthStatus(authStatusAuthenticated);
    const calls: Array<{ current_password: string; new_username: string }> = [];
    server.use(
      http.post("/api/auth/change-username", async ({ request }) => {
        const body = (await request.json()) as {
          current_password: string;
          new_username: string;
        };
        calls.push(body);
        return HttpResponse.json({ status: "ok", username: body.new_username });
      }),
    );

    render(<AccountSection />, { wrapper: TestWrapper });
    await screen.findByText("Change username");

    const user = userEvent.setup();
    const usernameInput = screen.getByLabelText(/New username/i);
    await user.clear(usernameInput);
    await user.type(usernameInput, "owner");
    await user.type(
      screen.getByLabelText(/Current password/i, { selector: "#account-username-password" }),
      "supersecret",
    );
    await user.click(screen.getByRole("button", { name: /Save username/i }));

    await waitFor(() => {
      expect(calls).toHaveLength(1);
    });
    expect(calls[0]).toEqual({ current_password: "supersecret", new_username: "owner" });
  });

  it("submits a password change with confirm + current", async () => {
    mockAuthStatus(authStatusAuthenticated);
    const calls: Array<{ current_password: string; new_password: string }> = [];
    server.use(
      http.post("/api/auth/change-password", async ({ request }) => {
        calls.push((await request.json()) as never);
        return HttpResponse.json({ status: "ok", username: "admin" });
      }),
    );

    render(<AccountSection />, { wrapper: TestWrapper });
    await screen.findByText("Change password");

    const user = userEvent.setup();
    await user.type(
      screen.getByLabelText(/Current password/i, { selector: "#account-current-password" }),
      "supersecret",
    );
    await user.type(screen.getByLabelText(/^New password/i), "brandnewpassword");
    await user.type(screen.getByLabelText(/Confirm new password/i), "brandnewpassword");
    await user.click(screen.getByRole("button", { name: /Save password/i }));

    await waitFor(() => {
      expect(calls).toHaveLength(1);
    });
    expect(calls[0]).toEqual({
      current_password: "supersecret",
      new_password: "brandnewpassword",
    });
  });

  it("rejects new passwords shorter than 8 chars without calling the API", async () => {
    mockAuthStatus(authStatusAuthenticated);
    let called = false;
    server.use(
      http.post("/api/auth/change-password", () => {
        called = true;
        return HttpResponse.json({ status: "ok", username: "admin" });
      }),
    );

    render(<AccountSection />, { wrapper: TestWrapper });
    await screen.findByText("Change password");

    const user = userEvent.setup();
    await user.type(
      screen.getByLabelText(/Current password/i, { selector: "#account-current-password" }),
      "supersecret",
    );
    await user.type(screen.getByLabelText(/^New password/i), "short");
    await user.type(screen.getByLabelText(/Confirm new password/i), "short");
    await user.click(screen.getByRole("button", { name: /Save password/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/at least 8/i);
    expect(called).toBe(false);
  });

  it("rejects mismatched confirm without calling the API", async () => {
    mockAuthStatus(authStatusAuthenticated);
    let called = false;
    server.use(
      http.post("/api/auth/change-password", () => {
        called = true;
        return HttpResponse.json({ status: "ok", username: "admin" });
      }),
    );

    render(<AccountSection />, { wrapper: TestWrapper });
    await screen.findByText("Change password");

    const user = userEvent.setup();
    await user.type(
      screen.getByLabelText(/Current password/i, { selector: "#account-current-password" }),
      "supersecret",
    );
    await user.type(screen.getByLabelText(/^New password/i), "brandnewpassword");
    await user.type(screen.getByLabelText(/Confirm new password/i), "different");
    await user.click(screen.getByRole("button", { name: /Save password/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/do not match/i);
    expect(called).toBe(false);
  });

  it("signs out and redirects to /login", async () => {
    mockAuthStatus(authStatusAuthenticated);
    let logoutCalled = false;
    server.use(
      http.post("/api/auth/logout", () => {
        logoutCalled = true;
        return HttpResponse.json({ status: "ok" });
      }),
    );

    render(<AccountSection />, { wrapper: TestWrapper });
    await screen.findByText("Signed in");

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /Sign out/i }));

    await waitFor(() => {
      expect(logoutCalled).toBe(true);
    });
    expect(replaceMock).toHaveBeenCalledWith("/login");
  });

  it("renders the 'Turn on login' nudge when auth is disabled", async () => {
    mockAuthStatus(authStatusDisabled);
    render(<AccountSection />, { wrapper: TestWrapper });
    await screen.findByText("Turn on login");
    expect(screen.getByRole("button", { name: /Set up a username/i })).toBeInTheDocument();
  });

  it("'Turn on login' button POSTs preference and routes to /login", async () => {
    mockAuthStatus(authStatusDisabled);
    let body: { enabled?: boolean } | null = null;
    const pushMock = vi.fn();
    // Re-mock useRouter for this test to capture push().
    const navMock = await import("@/hooks/use-router");
    vi.spyOn(navMock, "useRouter").mockReturnValue({
      push: pushMock,
      replace: replaceMock,
      refresh: vi.fn(),
      back: vi.fn(),
      forward: vi.fn(),
      prefetch: vi.fn(),
    } as never);
    server.use(
      http.post("/api/auth/preference", async ({ request }) => {
        body = (await request.json()) as { enabled?: boolean };
        return HttpResponse.json({ status: "ok" });
      }),
    );

    render(<AccountSection />, { wrapper: TestWrapper });
    await screen.findByText("Turn on login");
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /Set up a username/i }));

    await waitFor(() => {
      expect(body).toEqual({ enabled: true });
    });
    expect(pushMock).toHaveBeenCalledWith("/login");
  });

  it("opens the Disable login confirmation when the button is clicked", async () => {
    mockAuthStatus(authStatusAuthenticated);
    render(<AccountSection />, { wrapper: TestWrapper });
    // Wait until the section finishes loading.
    await screen.findByRole("button", { name: /^Disable login$/i });

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /^Disable login$/i }));

    // Modal opens and asks for current password.
    await screen.findByText(/Disable login for this FiestaBoard\?/i);
    expect(screen.getByLabelText(/Confirm your current password/i)).toBeInTheDocument();
  });

  it("'Disable login' POSTs the current password and clears auth", async () => {
    mockAuthStatus(authStatusAuthenticated);
    let body: { current_password?: string } | null = null;
    server.use(
      http.post("/api/auth/disable", async ({ request }) => {
        body = (await request.json()) as { current_password?: string };
        return HttpResponse.json({ status: "ok" });
      }),
    );

    render(<AccountSection />, { wrapper: TestWrapper });
    await screen.findByRole("button", { name: /^Disable login$/i });
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /^Disable login$/i }));
    await screen.findByText(/Disable login for this FiestaBoard\?/i);

    await user.type(screen.getByLabelText(/Confirm your current password/i), "supersecret");
    await user.click(screen.getByRole("button", { name: /Yes, disable login/i }));

    await waitFor(() => {
      expect(body).toEqual({ current_password: "supersecret" });
    });
    expect(replaceMock).toHaveBeenCalledWith("/");
  });
});
