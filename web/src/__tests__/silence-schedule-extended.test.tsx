// Branch coverage for SilenceSchedule page-mode and indicator-position handlers.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CurrentBoardProvider } from "@/components/current-board-context";
import { ThemeProvider } from "@/hooks/use-theme";
import { resolveSilenceConfig } from "@/lib/silence-config";

import { mockOutputSettings, mockPages, mockTransitionSettings } from "./mocks/handlers";
import { server } from "./mocks/server";

vi.mock("@/hooks/use-router", () => ({
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
      http.get(`${API_BASE}/settings/all`, () => HttpResponse.json(allSettings({ mode: "indicator" }))),
      http.get(`${API_BASE}/v1/pages`, () => HttpResponse.json({ pages: mockPages })),
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

// ---------------------------------------------------------------------------
// #1944 — "Show held messages when silence ends"
// ---------------------------------------------------------------------------

describe("SilenceSchedule — show held messages when silence ends (#1944)", () => {
  const FLAGSHIP = { id: "flag-1", name: "Kitchen", device_type: "flagship", board_color: "black" };
  const NOTE = { id: "note-1", name: "Desk", device_type: "note", board_color: "white" };

  function stubBoards(silence: Record<string, unknown>, boards = [FLAGSHIP, NOTE]) {
    const puts: Array<Record<string, unknown>> = [];
    server.use(
      http.get(`${API_BASE}/settings/all`, () =>
        HttpResponse.json({
          ...allSettings({ mode: "indicator", ...silence }),
          board: { board_type: "black", boards, devices: ["flagship"] },
        }),
      ),
      http.get(`${API_BASE}/settings/board`, () =>
        HttpResponse.json({ board_type: "black", boards, devices: ["flagship"] }),
      ),
      http.get(`${API_BASE}/v1/pages`, () => HttpResponse.json(mockPages)),
      http.put(`${API_BASE}/settings/silence-schedule`, async ({ request }) => {
        const body = (await request.json()) as Record<string, unknown>;
        puts.push(body);
        return HttpResponse.json({ config: body, board_id: body.board_id ?? null });
      }),
    );
    return puts;
  }

  function BoardWrapper({ children }: { children: React.ReactNode }) {
    return (
      <TestWrapper>
        <CurrentBoardProvider>{children}</CurrentBoardProvider>
      </TestWrapper>
    );
  }

  afterEach(() => server.resetHandlers());

  it("seeds the switch from the selected board's own entry", async () => {
    stubBoards({ show_queued_on_exit: false, by_board: { "flag-1": { show_queued_on_exit: true } } });
    render(<SilenceSchedule />, { wrapper: BoardWrapper });

    const toggle = await screen.findByRole("switch", { name: "Show held messages when silence ends" });
    await waitFor(() => expect(toggle).toHaveAttribute("aria-checked", "true"));
    expect(
      screen.getByText(/A message sent to this board during silence is held and shown the moment silence ends/),
    ).toBeInTheDocument();
  });

  it("flipping it autosaves show_queued_on_exit with the board_id", async () => {
    const puts = stubBoards({});
    const user = userEvent.setup();
    render(<SilenceSchedule />, { wrapper: BoardWrapper });

    const toggle = await screen.findByRole("switch", { name: "Show held messages when silence ends" });
    await waitFor(() => expect(toggle).toHaveAttribute("aria-checked", "false"));
    await user.click(toggle);

    await waitFor(() => expect(puts.length).toBeGreaterThan(0), { timeout: 5000 });
    expect(puts[0]).toMatchObject({ show_queued_on_exit: true, board_id: "flag-1" });
  });

  it("any other change also sends the current value (so a save never wipes it)", async () => {
    const puts = stubBoards({ by_board: { "flag-1": { show_queued_on_exit: true } } });
    const user = userEvent.setup();
    render(<SilenceSchedule />, { wrapper: BoardWrapper });

    const toggle = await screen.findByRole("switch", { name: "Show held messages when silence ends" });
    await waitFor(() => expect(toggle).toHaveAttribute("aria-checked", "true"));
    const text = await screen.findByLabelText(/message text/i);
    await user.clear(text);
    await user.type(text, "ZZZ");

    await waitFor(() => expect(puts.length).toBeGreaterThan(0), { timeout: 5000 });
    expect(puts[puts.length - 1]).toMatchObject({ show_queued_on_exit: true, indicator_text: "ZZZ" });
  });

  it("resolveSilenceConfig returns the per-board value", () => {
    const resolved = resolveSilenceConfig(
      {
        enabled: true,
        start_time: "04:00+00:00",
        end_time: "15:00+00:00",
        mode: "freeze",
        page_id: null,
        indicator_text: null,
        indicator_position: null,
        show_queued_on_exit: false,
        by_board: { "note-1": { show_queued_on_exit: true } },
      },
      "note-1",
    );
    expect(resolved.show_queued_on_exit).toBe(true);
  });
});
