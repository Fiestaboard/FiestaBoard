import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { http, HttpResponse } from "msw";
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
      http.get(`${API_BASE}/schedules`, () =>
        HttpResponse.json({
          schedules: [],
          total: 0,
          default_page_id: null,
          enabled: true,
        })
      ),
      http.get(`${API_BASE}/schedules/active/page`, () =>
        HttpResponse.json({
          page_id: null,
          source: "schedule",
          schedule_enabled: true,
        })
      )
    );

    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText("Schedule gap (no default page set)")).toBeInTheDocument();
      expect(screen.getByText(/No page scheduled for current time/i)).toBeInTheDocument();
    });
  });

  it("shows View Schedule button when schedule is enabled", async () => {
    server.use(
      http.get(`${API_BASE}/schedules`, () =>
        HttpResponse.json({
          schedules: [],
          total: 0,
          default_page_id: null,
          enabled: true,
        })
      )
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
        })
      )
    );

    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText("Silence mode active")).toBeInTheDocument();
    });
  });

  it("shows Carousel badge when active page is a carousel", async () => {
    server.use(
      http.get(`${API_BASE}/settings/active-page`, () =>
        HttpResponse.json({ page_id: "carousel:test-carousel-id" })
      ),
      http.get(`${API_BASE}/carousels`, () =>
        HttpResponse.json({
          carousels: [{
            id: "carousel:test-carousel-id",
            name: "Test Carousel",
            page_ids: ["page-1"],
            interval_seconds: 30,
            created_at: "2025-01-01T00:00:00Z",
          }],
          total: 1,
        })
      )
    );

    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText("Test Carousel")).toBeInTheDocument();
      expect(screen.getByText("Carousel")).toBeInTheDocument();
    });
  });

  it("handles set active page error", async () => {
    const toastSpy = vi.spyOn((await import("sonner")).toast, "error");
    server.use(
      http.put(`${API_BASE}/settings/active-page`, () =>
        HttpResponse.json({ error: "Failed" }, { status: 500 })
      )
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
    await waitFor(() => {
      const page2 = screen.queryByText("Custom Template");
      expect(page2).toBeInTheDocument();
    }, { timeout: 3000 });

    await user.click(screen.getByText("Custom Template"));

    await waitFor(() => {
      expect(toastSpy).toHaveBeenCalledWith("Failed to switch page");
    }, { timeout: 3000 });

    toastSpy.mockRestore();
  });
});
