import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SilenceImminentBanner } from "@/components/silence-imminent-banner";

import { server } from "./mocks/server";

const API_BASE = "/api";

function silenceStatus(overrides: Record<string, unknown> = {}) {
  return {
    enabled: true,
    active: false,
    start_time_utc: "04:00+00:00",
    end_time_utc: "15:00+00:00",
    current_time_utc: "2025-12-26T03:58:30+00:00",
    next_change_utc: "04:00+00:00",
    seconds_until_next_change: 90,
    mode: "page",
    page_id: "page-quiet",
    indicator_text: "SNOOZING",
    indicator_position: "center",
    ...overrides,
  };
}

function setupHandlers(opts: {
  silence?: Record<string, unknown>;
  schedulePageId?: string | null;
  scheduleEnabled?: boolean;
  manualPageId?: string | null;
  pages?: Array<{ id: string; name: string }>;
  onOverride?: (body: unknown) => void;
}) {
  server.use(
    http.get(`${API_BASE}/silence-status`, () => HttpResponse.json(silenceStatus(opts.silence))),
    http.get(`${API_BASE}/schedules/active/page`, () =>
      HttpResponse.json({
        page_id: opts.schedulePageId ?? null,
        source: opts.scheduleEnabled ? "schedule" : "manual",
        schedule_enabled: opts.scheduleEnabled ?? false,
        temporary_override: {
          active: false,
          page_id: null,
          expires_at: null,
          remaining_seconds: null,
          revert_mode: null,
          revert_page_id: null,
        },
      }),
    ),
    http.get(`${API_BASE}/settings/active-page`, () => HttpResponse.json({ page_id: opts.manualPageId ?? null })),
    http.get(`${API_BASE}/pages`, () =>
      HttpResponse.json({
        pages: opts.pages ?? [{ id: "page-quiet", name: "Quiet" }],
        total: (opts.pages ?? [{ id: "page-quiet", name: "Quiet" }]).length,
      }),
    ),
    http.post(`${API_BASE}/settings/temporary-override`, async ({ request }) => {
      const body = await request.json();
      opts.onOverride?.(body);
      return HttpResponse.json({
        active: true,
        page_id: (body as { page_id: string }).page_id,
        expires_at: null,
        remaining_seconds: 90,
        revert_mode: "schedule",
        revert_page_id: null,
      });
    }),
    http.post(`${API_BASE}/force-refresh`, () => HttpResponse.json({ status: "ok" })),
  );
}

function TestWrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

describe("SilenceImminentBanner", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows when silence is starting within 2 minutes and the silence page isn't active", async () => {
    setupHandlers({ manualPageId: "page-home" });
    render(<SilenceImminentBanner />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByTestId("silence-imminent-banner")).toBeInTheDocument();
    });
    expect(screen.getByText(/Silence starts in/)).toBeInTheDocument();
    expect(screen.getByText(/Quiet/)).toBeInTheDocument();
  });

  it("does not render when silence is disabled", async () => {
    setupHandlers({ silence: { enabled: false }, manualPageId: "page-home" });
    const { container } = render(<SilenceImminentBanner />, { wrapper: TestWrapper });
    await new Promise((r) => setTimeout(r, 50));
    expect(container.firstChild).toBeNull();
  });

  it("does not render when mode is not 'page'", async () => {
    setupHandlers({
      silence: { mode: "freeze", page_id: null },
      manualPageId: "page-home",
    });
    const { container } = render(<SilenceImminentBanner />, { wrapper: TestWrapper });
    await new Promise((r) => setTimeout(r, 50));
    expect(container.firstChild).toBeNull();
  });

  it("does not render when silence is already active", async () => {
    setupHandlers({
      silence: { active: true, seconds_until_next_change: 600 },
      manualPageId: "page-home",
    });
    const { container } = render(<SilenceImminentBanner />, { wrapper: TestWrapper });
    await new Promise((r) => setTimeout(r, 50));
    expect(container.firstChild).toBeNull();
  });

  it("does not render when the silence page is already showing", async () => {
    setupHandlers({ manualPageId: "page-quiet" });
    const { container } = render(<SilenceImminentBanner />, { wrapper: TestWrapper });
    await new Promise((r) => setTimeout(r, 50));
    expect(container.firstChild).toBeNull();
  });

  it("does not render when silence is far away", async () => {
    setupHandlers({
      silence: { seconds_until_next_change: 30 * 60 },
      manualPageId: "page-home",
    });
    const { container } = render(<SilenceImminentBanner />, { wrapper: TestWrapper });
    await new Promise((r) => setTimeout(r, 50));
    expect(container.firstChild).toBeNull();
  });

  it("dismiss hides the banner", async () => {
    setupHandlers({ manualPageId: "page-home" });
    const user = userEvent.setup();
    render(<SilenceImminentBanner />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByTestId("silence-imminent-banner")).toBeInTheDocument();
    });
    await user.click(screen.getByRole("button", { name: /Dismiss/i }));
    expect(screen.queryByTestId("silence-imminent-banner")).not.toBeInTheDocument();
  });

  it("Switch now calls temporary-override with the silence page id", async () => {
    const captured: { body?: unknown } = {};
    setupHandlers({
      manualPageId: "page-home",
      onOverride: (body) => {
        captured.body = body;
      },
    });
    const user = userEvent.setup();
    render(<SilenceImminentBanner />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByTestId("silence-imminent-banner")).toBeInTheDocument();
    });
    await user.click(screen.getByRole("button", { name: /Switch now/i }));

    await waitFor(() => {
      expect(captured.body).toBeDefined();
    });
    expect(captured.body).toMatchObject({
      page_id: "page-quiet",
      revert_mode: "schedule",
    });
    expect((captured.body as { duration_minutes: number }).duration_minutes).toBeGreaterThanOrEqual(1);
  });
});
