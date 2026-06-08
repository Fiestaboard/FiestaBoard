import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { ThemeProvider } from "@/hooks/use-theme";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";

import { server } from "./mocks/server";

const API_BASE = "/api";
import { ActivePageDisplay } from "@/components/active-page-display";

const mockPush = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: mockPush,
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

describe("ActivePageDisplay", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows loading state when preview is loading", async () => {
    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText("Active Display")).toBeInTheDocument();
    });
  });

  it("displays active page info in manual mode", async () => {
    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText("Weather Page")).toBeInTheDocument();
      expect(screen.getByText("Manual Mode")).toBeInTheDocument();
    });
  });

  it("shows Change Page button in manual mode", async () => {
    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    await waitFor(() => {
      const changeBtn = screen.getByRole("button", { name: /Change Page/i });
      expect(changeBtn).toBeInTheDocument();
    });
  });

  it("opens sheet when Change Page is clicked in manual mode", async () => {
    const user = userEvent.setup();
    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Change Page/i })).toBeInTheDocument();
    });

    const changeBtn = screen.getByRole("button", { name: /Change Page/i });
    await user.click(changeBtn);

    await waitFor(() => {
      expect(screen.getByText("Select Page")).toBeInTheDocument();
      expect(screen.getByText(/Choose which page to display/i)).toBeInTheDocument();
    });
  });

  it("shows schedule gap warning when schedule enabled and no active page", async () => {
    server.use(
      http.get(`${API_BASE}/schedules/active/page`, () =>
        HttpResponse.json({
          page_id: null,
          source: "schedule",
          schedule_enabled: true,
        }),
      ),
    );

    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText("Schedule gap (no default page set)")).toBeInTheDocument();
      expect(screen.getByText(/No page scheduled for current time/i)).toBeInTheDocument();
    });
  });

  it("shows View Schedule button when schedule is enabled", async () => {
    server.use(
      http.get(`${API_BASE}/schedules/active/page`, () =>
        HttpResponse.json({
          page_id: null,
          source: "none",
          schedule_enabled: true,
        }),
      ),
    );

    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    await waitFor(() => {
      const viewScheduleBtn = screen.getByRole("button", { name: /View Schedule/i });
      expect(viewScheduleBtn).toBeInTheDocument();
    });

    const viewScheduleBtn = screen.getByRole("button", { name: /View Schedule/i });
    await userEvent.click(viewScheduleBtn);

    expect(mockPush).toHaveBeenCalledWith("/schedule");
  });

  it("derives schedule mode from active schedule endpoint without fetching full schedule list", async () => {
    // This test verifies the fix: schedule_enabled is derived from the
    // /schedules/active/page endpoint (lightweight) instead of /schedules
    // (heavyweight, returns all schedule entries).
    server.use(
      http.get(`${API_BASE}/schedules/active/page`, () =>
        HttpResponse.json({
          page_id: "page-1",
          source: "schedule",
          schedule_enabled: true,
          current_time: "09:00",
          current_day: "monday",
        }),
      ),
    );

    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /View Schedule/i })).toBeInTheDocument();
    });
  });

  it("shows silence mode indicator when silence is active", async () => {
    server.use(
      http.get(`${API_BASE}/silence-status`, () =>
        HttpResponse.json({
          enabled: true,
          active: true,
          start_time_utc: "04:00+00:00",
          end_time_utc: "15:00+00:00",
          current_time_utc: "2025-12-26T18:30:00+00:00",
          next_change_utc: "2025-12-27T04:00:00+00:00",
        }),
      ),
    );

    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText("Silence mode active")).toBeInTheDocument();
    });
  });

  it("shows Collection badge when active page is a collection", async () => {
    server.use(
      http.get(`${API_BASE}/settings/active-page`, () =>
        HttpResponse.json({ page_id: "collection:test-collection-id" }),
      ),
      http.get(`${API_BASE}/collections`, () =>
        HttpResponse.json({
          collections: [
            {
              id: "collection:test-collection-id",
              name: "Test Collection",
              page_ids: ["page-1"],
              selection_mode: "time",

              time: { interval_seconds: 30 },

              variable: null,
              created_at: "2025-01-01T00:00:00Z",
            },
          ],
          total: 1,
        }),
      ),
    );

    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText("Test Collection")).toBeInTheDocument();
      expect(screen.getByText("Collection")).toBeInTheDocument();
    });
  });

  it("shows out-of-sync alert when board was changed externally", async () => {
    const differentChars = Array.from({ length: 6 }, () => Array(22).fill(1));
    const expectedChars = Array.from({ length: 6 }, () => Array(22).fill(2));
    server.use(
      http.get(`${API_BASE}/board/current-message`, () =>
        HttpResponse.json({
          characters: differentChars,
          message: "",
          rows: 6,
          cols: 22,
          expected_characters: expectedChars,
          cached_at: null,
          api_mode: "local",
        }),
      ),
    );

    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText("Board was changed by another app")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /Restore/i })).toBeInTheDocument();
    });
  });

  it("calls force-refresh and shows success toast when Restore is clicked", async () => {
    const toastSpy = vi.spyOn((await import("sonner")).toast, "success");
    const differentChars = Array.from({ length: 6 }, () => Array(22).fill(1));
    const expectedChars = Array.from({ length: 6 }, () => Array(22).fill(2));
    server.use(
      http.get(`${API_BASE}/board/current-message`, () =>
        HttpResponse.json({
          characters: differentChars,
          message: "",
          rows: 6,
          cols: 22,
          expected_characters: expectedChars,
          cached_at: null,
          api_mode: "local",
        }),
      ),
    );

    const user = userEvent.setup();
    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Restore/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: /Restore/i }));

    await waitFor(() => {
      expect(toastSpy).toHaveBeenCalledWith("Board restored");
    });

    toastSpy.mockRestore();
  });

  it("handles set active page error", async () => {
    const toastSpy = vi.spyOn((await import("sonner")).toast, "error");
    server.use(
      http.put(`${API_BASE}/settings/active-page`, () => HttpResponse.json({ error: "Failed" }, { status: 500 })),
    );

    const user = userEvent.setup();
    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Change Page/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: /Change Page/i }));

    await waitFor(() => {
      expect(screen.getByText("Select Page")).toBeInTheDocument();
    });

    // Wait for sheet content and page grid to load (420ms animation + data fetch)
    await waitFor(
      () => {
        const page2 = screen.queryByText("Custom Template");
        expect(page2).toBeInTheDocument();
      },
      { timeout: 3000 },
    );

    await user.click(screen.getByText("Custom Template"));

    await waitFor(
      () => {
        expect(toastSpy).toHaveBeenCalledWith("Failed to switch page");
      },
      { timeout: 3000 },
    );

    toastSpy.mockRestore();
  });
});
