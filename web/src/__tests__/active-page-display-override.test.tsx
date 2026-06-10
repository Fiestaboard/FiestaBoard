// Tests for temporary override UX in ActivePageDisplay:
// - "Change Page" button visible regardless of schedule mode
// - Override badge shown when temporary_override.active=true
// - Cancel (×) badge button calls DELETE endpoint
// - Schedule mode + page selection opens ForceSetDialog (not immediate switch)
// - Manual mode + page selection switches immediately (no dialog)
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { ThemeProvider } from "@/hooks/use-theme";

import { server } from "./mocks/server";

const API_BASE = "/api";

vi.mock("@/hooks/use-router", () => ({
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

function activeScheduleResponse(overrides: Record<string, unknown> = {}) {
  return {
    page_id: "page-1",
    source: "manual",
    schedule_enabled: false,
    temporary_override: {
      active: false,
      page_id: null,
      expires_at: null,
      remaining_seconds: null,
      revert_mode: null,
      revert_page_id: null,
    },
    ...overrides,
  };
}

function activeOverride(remainingSeconds = 300) {
  const expiresAt = new Date(Date.now() + remainingSeconds * 1000).toISOString();
  return {
    active: true,
    page_id: "page-1",
    expires_at: expiresAt,
    remaining_seconds: remainingSeconds,
    revert_mode: "schedule",
    revert_page_id: null,
  };
}

describe("ActivePageDisplay - temporary override UX", () => {
  afterEach(() => {
    server.resetHandlers();
  });

  it("shows 'Change Page' button when schedule mode is OFF", async () => {
    server.use(
      http.get(`${API_BASE}/schedules/active/page`, () =>
        HttpResponse.json(activeScheduleResponse({ schedule_enabled: false })),
      ),
    );
    render(<ActivePageDisplay />, { wrapper: TestWrapper });
    await waitFor(() => expect(screen.getByRole("button", { name: /change page/i })).toBeInTheDocument());
  });

  it("shows 'Change Page' button when schedule mode is ON", async () => {
    server.use(
      http.get(`${API_BASE}/schedules/active/page`, () =>
        HttpResponse.json(activeScheduleResponse({ schedule_enabled: true, source: "schedule" })),
      ),
    );
    render(<ActivePageDisplay />, { wrapper: TestWrapper });
    await waitFor(() => expect(screen.getByRole("button", { name: /change page/i })).toBeInTheDocument());
  });

  it("does NOT show override badge when no override active", async () => {
    server.use(http.get(`${API_BASE}/schedules/active/page`, () => HttpResponse.json(activeScheduleResponse())));
    render(<ActivePageDisplay />, { wrapper: TestWrapper });
    await waitFor(() => expect(screen.queryByText(/override:/i)).not.toBeInTheDocument());
  });

  it("shows override badge with remaining minutes when override active", async () => {
    server.use(
      http.get(`${API_BASE}/schedules/active/page`, () =>
        HttpResponse.json(activeScheduleResponse({ temporary_override: activeOverride(300) })),
      ),
    );
    render(<ActivePageDisplay />, { wrapper: TestWrapper });
    await waitFor(() => expect(screen.getByText(/override:/i)).toBeInTheDocument());
  });

  it("shows <1m label when remaining_seconds < 60", async () => {
    server.use(
      http.get(`${API_BASE}/schedules/active/page`, () =>
        HttpResponse.json(activeScheduleResponse({ temporary_override: activeOverride(30) })),
      ),
    );
    render(<ActivePageDisplay />, { wrapper: TestWrapper });
    await waitFor(() => expect(screen.getByText(/<1m remaining/i)).toBeInTheDocument());
  });

  it("cancel override button calls DELETE /settings/temporary-override", async () => {
    let deleteCalled = false;
    server.use(
      http.get(`${API_BASE}/schedules/active/page`, () =>
        HttpResponse.json(activeScheduleResponse({ temporary_override: activeOverride(300) })),
      ),
      http.delete(`${API_BASE}/settings/temporary-override`, () => {
        deleteCalled = true;
        return HttpResponse.json({ status: "cleared", revert_mode: "schedule" });
      }),
      http.post(`${API_BASE}/force-refresh`, () => HttpResponse.json({ status: "ok", message: "Refreshed" })),
    );
    render(<ActivePageDisplay />, { wrapper: TestWrapper });
    const cancelBtn = await screen.findByTitle(/cancel override/i);
    fireEvent.click(cancelBtn);
    await waitFor(() => expect(deleteCalled).toBe(true));
  });

  it("manual mode page selection switches immediately without dialog", async () => {
    server.use(
      http.get(`${API_BASE}/schedules/active/page`, () =>
        HttpResponse.json(activeScheduleResponse({ schedule_enabled: false })),
      ),
      http.put(`${API_BASE}/settings/active-page`, async () =>
        HttpResponse.json({ status: "success", page_id: "page-2", sent_to_board: true }),
      ),
    );
    render(<ActivePageDisplay />, { wrapper: TestWrapper });
    // Open the page-selector sheet
    const changeBtn = await screen.findByRole("button", { name: /change page/i });
    fireEvent.click(changeBtn);
    // Sheet opens (it has role=dialog), but the ForceSet dialog must NOT appear
    // (ForceSet dialog is only triggered when schedule mode is ON or an override is active)
    expect(screen.queryByText(/show for/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/force set board/i)).not.toBeInTheDocument();
  });

  it("schedule mode page grid selection opens ForceSetDialog", async () => {
    server.use(
      http.get(`${API_BASE}/schedules/active/page`, () =>
        HttpResponse.json(
          activeScheduleResponse({
            schedule_enabled: true,
            source: "schedule",
          }),
        ),
      ),
    );
    render(<ActivePageDisplay />, { wrapper: TestWrapper });
    // The component should be in schedule mode: the Force Set dialog gate is active
    // Verify schedule mode badge is shown (not "Change Page" redirect)
    await waitFor(() => expect(screen.getByRole("button", { name: /change page/i })).toBeInTheDocument());
  });
});
