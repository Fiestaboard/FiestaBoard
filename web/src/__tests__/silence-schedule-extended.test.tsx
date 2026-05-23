// Branch coverage for SilenceSchedule page-mode and indicator-position handlers.
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import { http, HttpResponse } from "msw";
import { server } from "./mocks/server";
import { mockTransitionSettings, mockOutputSettings, mockPages } from "./mocks/handlers";

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    refresh: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
    prefetch: vi.fn(),
  }),
  usePathname: () => "/settings",
}));

import { SilenceSchedule } from "@/components/settings/silence-schedule";

const API_BASE = "/api";

function allSettings(silenceOverrides: Record<string, unknown> = {}) {
  return {
    general: {
      timezone: "America/Los_Angeles",
      refresh_interval_seconds: 300,
      output_target: "board",
    },
    silence_schedule: {
      config: {
        enabled: true,
        start_time: "04:00+00:00",
        end_time: "15:00+00:00",
        mode: "page",
        page_id: null,
        indicator_text: "SNOOZING",
        indicator_position: "center",
        ...silenceOverrides,
      },
    },
    polling: { interval_seconds: 300, board_read_interval_local: 30, board_read_interval_cloud: 180 },
    transitions: mockTransitionSettings,
    output: mockOutputSettings,
    board: { board_type: "black", color: "black", primary_board_id: "board-1" },
    mqtt: { enabled: false, host: "", port: 1883 },
    display: { reduce_motion: false },
    location: { latitude: null, longitude: null },
    beta: { https_enabled: false },
    plugins: { auto_update_enabled: true },
    status: { running: true },
  };
}

function TestWrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider attribute="class" defaultTheme="light">
        {children}
      </ThemeProvider>
    </QueryClientProvider>
  );
}

describe("SilenceSchedule — indicator position handler", () => {
  beforeEach(() => {
    server.use(
      http.get(`${API_BASE}/settings/all`, () =>
        HttpResponse.json(allSettings({ mode: "indicator" })),
      ),
      http.get(`${API_BASE}/pages`, () => HttpResponse.json({ pages: mockPages })),
    );
  });
  afterEach(() => server.resetHandlers());

  it("changing indicator position invokes handleSilenceIndicatorPositionChange", async () => {
    const user = userEvent.setup();
    render(<SilenceSchedule />, { wrapper: TestWrapper });

    const positionTrigger = await screen.findByRole("combobox", {
      name: /message position/i,
    });
    await user.click(positionTrigger);

    const listbox = await screen.findByRole("listbox");
    const topLeft = within(listbox).getByRole("option", { name: /top left/i });
    await user.click(topLeft);

    await waitFor(() => {
      expect(positionTrigger).toHaveTextContent(/top left/i);
    });
  });
});
