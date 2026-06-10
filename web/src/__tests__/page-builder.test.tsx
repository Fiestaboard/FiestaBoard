import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { ThemeProvider } from "@/hooks/use-theme";

import { server } from "./mocks/server";

const API_BASE = "/api";
import { PageBuilder } from "@/components/page-builder";

vi.mock("@/hooks/use-router", () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    prefetch: vi.fn(),
    back: vi.fn(),
  }),
}));

function TestWrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return (
    <QueryClientProvider client={queryClient}>
      <ConfigOverridesProvider>
        <ThemeProvider attribute="class" defaultTheme="light">
          {children}
        </ThemeProvider>
      </ConfigOverridesProvider>
    </QueryClientProvider>
  );
}

describe("PageBuilder — Sync from Board", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows the Sync from Board button when creating a new page", async () => {
    render(<PageBuilder onClose={vi.fn()} />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Sync from current board display" })).toBeInTheDocument();
    });
  });

  it("does not show the Sync from Board button when editing an existing page", async () => {
    render(<PageBuilder pageId="page-1" onClose={vi.fn()} />, {
      wrapper: TestWrapper,
    });

    // Wait for the page data to load
    await waitFor(() => {
      expect(screen.queryByText("Syncing...")).not.toBeInTheDocument();
    });

    // The button must not be present in edit mode
    expect(screen.queryByRole("button", { name: "Sync from current board display" })).not.toBeInTheDocument();
  });

  it("populates template lines and shows a success toast on successful sync", async () => {
    const toastSpy = vi.spyOn((await import("sonner")).toast, "success");
    const user = userEvent.setup();

    render(<PageBuilder onClose={vi.fn()} />, { wrapper: TestWrapper });

    const syncBtn = await screen.findByRole("button", {
      name: "Sync from current board display",
    });
    await user.click(syncBtn);

    await waitFor(() => {
      expect(toastSpy).toHaveBeenCalledWith(expect.stringContaining("Weather Page"));
    });
  });

  it("shows an error toast when the sync API call fails", async () => {
    const toastSpy = vi.spyOn((await import("sonner")).toast, "error");
    const user = userEvent.setup();

    server.use(
      http.get(`${API_BASE}/pages/current-display`, () => {
        return HttpResponse.json({ detail: "No active page set" }, { status: 404 });
      }),
    );

    render(<PageBuilder onClose={vi.fn()} />, { wrapper: TestWrapper });

    const syncBtn = await screen.findByRole("button", {
      name: "Sync from current board display",
    });
    await user.click(syncBtn);

    await waitFor(() => {
      expect(toastSpy).toHaveBeenCalled();
    });
  });
});
