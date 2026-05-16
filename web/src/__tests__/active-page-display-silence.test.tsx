// ActivePageDisplay shows the Moon "Silence mode active" badge when silence is
// active (regardless of mode). The old snoozing indicator overlay was removed
// when Active Display was refactored to show the polled board state directly.
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, waitFor, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { http, HttpResponse } from "msw";
import { server } from "./mocks/server";

const API_BASE = "/api";

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    prefetch: vi.fn(),
    back: vi.fn(),
  }),
}));

import { ActivePageDisplay } from "@/components/active-page-display";

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

function silenceStatus(overrides: Record<string, unknown>) {
  return {
    enabled: true,
    active: false,
    start_time_utc: "04:00+00:00",
    end_time_utc: "15:00+00:00",
    current_time_utc: "2026-05-04T10:00:00+00:00",
    next_change_utc: "2026-05-04T15:00:00+00:00",
    mode: "freeze",
    page_id: null,
    indicator_text: "SNOOZING",
    indicator_position: "center",
    ...overrides,
  };
}

describe("ActivePageDisplay - silence overlay visibility", () => {
  afterEach(() => {
    server.resetHandlers();
  });

  it("does NOT show silence badge when silence is inactive", async () => {
    server.use(
      http.get(`${API_BASE}/silence-status`, () =>
        HttpResponse.json(silenceStatus({ active: false, mode: "indicator" })),
      ),
    );

    render(<ActivePageDisplay />, { wrapper: TestWrapper });
    await waitFor(() => {
      expect(screen.queryByText("Silence mode active")).not.toBeInTheDocument();
    });
  });

  it("shows silence badge when active AND mode === 'indicator'", async () => {
    server.use(
      http.get(`${API_BASE}/silence-status`, () =>
        HttpResponse.json(
          silenceStatus({
            active: true,
            mode: "indicator",
            indicator_text: "BEDTIME",
            indicator_position: "bottom-right",
          }),
        ),
      ),
    );

    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    await waitFor(() =>
      expect(screen.getByText("Silence mode active")).toBeInTheDocument(),
    );
  });

  it("shows silence badge when active and mode === 'freeze'", async () => {
    server.use(
      http.get(`${API_BASE}/silence-status`, () =>
        HttpResponse.json(silenceStatus({ active: true, mode: "freeze" })),
      ),
    );

    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    await waitFor(() =>
      expect(screen.getByText("Silence mode active")).toBeInTheDocument(),
    );
  });

  it("shows silence badge when active and mode === 'page'", async () => {
    server.use(
      http.get(`${API_BASE}/silence-status`, () =>
        HttpResponse.json(
          silenceStatus({ active: true, mode: "page", page_id: "page-night" }),
        ),
      ),
    );

    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    await waitFor(() =>
      expect(screen.getByText("Silence mode active")).toBeInTheDocument(),
    );
  });

  it("shows silence badge even when indicator_text/position are missing", async () => {
    server.use(
      http.get(`${API_BASE}/silence-status`, () =>
        HttpResponse.json({
          enabled: true,
          active: true,
          start_time_utc: "04:00+00:00",
          end_time_utc: "15:00+00:00",
          current_time_utc: "2026-05-04T10:00:00+00:00",
          next_change_utc: "2026-05-04T15:00:00+00:00",
          mode: "indicator",
          page_id: null,
          // indicator_text and indicator_position omitted
        }),
      ),
    );

    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    await waitFor(() =>
      expect(screen.getByText("Silence mode active")).toBeInTheDocument(),
    );
  });
});
