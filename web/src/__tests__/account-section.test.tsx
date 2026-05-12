import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "./mocks/server";

const replaceMock = vi.fn();

vi.mock("next/navigation", () => ({
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
  server.use(
    http.get("/api/auth/status", () => HttpResponse.json(payload)),
  );
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
    await screen.findByText("Account");
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
    await screen.findByText("Account");

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /Sign out/i }));

    await waitFor(() => {
      expect(logoutCalled).toBe(true);
    });
    expect(replaceMock).toHaveBeenCalledWith("/login");
  });
});
