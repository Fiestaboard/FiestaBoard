import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TooltipProvider } from "@/components/ui/tooltip";

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
  usePathname: () => "/",
}));

import { SidebarAccount } from "@/components/sidebar-account";

function TestWrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>{children}</TooltipProvider>
    </QueryClientProvider>
  );
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

describe("SidebarAccount", () => {
  beforeEach(() => {
    replaceMock.mockReset();
  });

  it("renders nothing when auth is disabled", async () => {
    mockAuthStatus(authStatusDisabled);
    const { container } = render(<SidebarAccount />, { wrapper: TestWrapper });
    // Give the auth-status query a tick to resolve.
    await waitFor(() => {
      expect(container.querySelector("button")).toBeNull();
    });
  });

  it("renders a Sign out button when authenticated", async () => {
    mockAuthStatus(authStatusAuthenticated);
    render(<SidebarAccount />, { wrapper: TestWrapper });
    await screen.findByRole("button", { name: /Sign out/i });
  });

  it("signs out and routes to /login", async () => {
    mockAuthStatus(authStatusAuthenticated);
    let logoutCalled = false;
    server.use(
      http.post("/api/auth/logout", () => {
        logoutCalled = true;
        return HttpResponse.json({ status: "ok" });
      }),
    );

    render(<SidebarAccount />, { wrapper: TestWrapper });
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /Sign out/i }));

    await waitFor(() => {
      expect(logoutCalled).toBe(true);
    });
    expect(replaceMock).toHaveBeenCalledWith("/login");
  });

  it("still routes to /login even if the logout API errors", async () => {
    // Best-effort behavior — the local cache should be dropped regardless.
    mockAuthStatus(authStatusAuthenticated);
    server.use(http.post("/api/auth/logout", () => HttpResponse.json({ detail: "boom" }, { status: 500 })));

    render(<SidebarAccount />, { wrapper: TestWrapper });
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /Sign out/i }));

    await waitFor(() => {
      expect(replaceMock).toHaveBeenCalledWith("/login");
    });
  });

  it("hides the label text but keeps the icon when collapsed", async () => {
    mockAuthStatus(authStatusAuthenticated);
    render(<SidebarAccount collapsed />, { wrapper: TestWrapper });
    const button = await screen.findByRole("button", { name: /Sign out/i });
    // The visible label span is hidden via opacity-0 / max-w-0; the button
    // itself still has the aria-label so screen readers find it.
    const labelSpan = button.querySelector("span");
    expect(labelSpan?.className).toMatch(/opacity-0/);
  });

  it("uses larger touch targets in the mobile variant", async () => {
    mockAuthStatus(authStatusAuthenticated);
    render(<SidebarAccount variant="mobile" />, { wrapper: TestWrapper });
    const button = await screen.findByRole("button", { name: /Sign out/i });
    // Mobile variant matches the 48px tap-target sibling nav items.
    expect(button.className).toMatch(/min-h-\[48px\]/);
    expect(button.className).toMatch(/text-base/);
  });
});
