// Phase 7: ActivePageDisplay must only overlay the snoozing indicator when
// silence is active AND mode === "indicator". For freeze/page modes it must
// render the underlying page content unmodified.
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { http, HttpResponse } from "msw";
import { server } from "./mocks/server";

import * as snoozingModule from "@/lib/snoozing-indicator";

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
  let spy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    spy = vi.spyOn(snoozingModule, "addSnoozingIndicator");
  });

  afterEach(() => {
    server.resetHandlers();
    spy?.mockRestore();
  });

  it("does NOT overlay when silence is inactive", async () => {
    server.use(
      http.get(`${API_BASE}/silence-status`, () =>
        HttpResponse.json(silenceStatus({ active: false, mode: "indicator" })),
      ),
    );

    render(<ActivePageDisplay />, { wrapper: TestWrapper });
    await waitFor(() => expect(spy).not.toHaveBeenCalled());
  });

  it("overlays when active AND mode === 'indicator'", async () => {
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

    await waitFor(() => expect(spy).toHaveBeenCalled());
    const lastCall = spy.mock.calls.at(-1);
    expect(lastCall).toBeTruthy();
    // Args: (content, numRows, numCols, indicatorText, position)
    expect(lastCall![3]).toBe("BEDTIME");
    expect(lastCall![4]).toBe("bottom-right");
  });

  it("does NOT overlay when active but mode === 'freeze'", async () => {
    server.use(
      http.get(`${API_BASE}/silence-status`, () =>
        HttpResponse.json(silenceStatus({ active: true, mode: "freeze" })),
      ),
    );

    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    // Wait long enough for the silence query to resolve and a re-render to occur
    await waitFor(() => {
      // Component has rendered (some content visible) but addSnoozingIndicator
      // must never have been called.
      expect(spy).not.toHaveBeenCalled();
    });
  });

  it("does NOT overlay when active but mode === 'page'", async () => {
    server.use(
      http.get(`${API_BASE}/silence-status`, () =>
        HttpResponse.json(
          silenceStatus({ active: true, mode: "page", page_id: "page-night" }),
        ),
      ),
    );

    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    await waitFor(() => expect(spy).not.toHaveBeenCalled());
  });

  it("falls back to defaults when indicator_text/position are missing", async () => {
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

    await waitFor(() => expect(spy).toHaveBeenCalled());
    const lastCall = spy.mock.calls.at(-1);
    expect(lastCall![3]).toBe("SNOOZING");
    expect(lastCall![4]).toBe("center");
  });
});
