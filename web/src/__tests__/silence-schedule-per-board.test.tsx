// Per-board silence schedule UI (issue #1788)
//
// Silence settings used to be global: every board shared one quiet period and
// one silence page, so a Note and a Flagship could not both have a valid page.
// The form now scopes to the selected board in multi-board installs and
// filters the page picker to pages that fit that board.
//
// Covers:
// - resolveSilenceConfig: per-board entry wins, unconfigured board falls back
// - the form seeds from the selected board's entry
// - PUT always carries board_id, single-board installs included: the engine
//   resolves per board on every install, so the layer the form writes has to
//   be the layer the engine reads (PR #1801 review, BLOCKER 1)
// - the page picker only offers pages that fit the selected board
// - saving invalidates the silenceStatus query key the consumers actually use
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CurrentBoardProvider } from "@/components/current-board-context";
import { SilenceSchedule } from "@/components/settings/silence-schedule";
import { queryKeys } from "@/hooks/use-board";
import { ThemeProvider } from "@/hooks/use-theme";
import { resolveSilenceConfig } from "@/lib/silence-config";

import { mockOutputSettings, mockTransitionSettings } from "./mocks/handlers";
import { server } from "./mocks/server";

vi.mock("@/hooks/use-router", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn(), back: vi.fn(), forward: vi.fn() }),
  usePathname: () => "/settings",
}));

const API_BASE = "/api";

const FLAGSHIP = { id: "flag-1", name: "Kitchen", device_type: "flagship", board_color: "black" };
const NOTE = { id: "note-1", name: "Desk", device_type: "note", board_color: "white" };

const PAGES = [
  { id: "big", name: "Big Page", device_type: "flagship", notes_wide: 1, notes_tall: 1 },
  { id: "small", name: "Small Page", device_type: "note", notes_wide: 1, notes_tall: 1 },
];

function allSettingsResponse(silenceOverrides: Record<string, unknown> = {}, boards = [FLAGSHIP]) {
  return {
    general: { timezone: "UTC", refresh_interval_seconds: 300, output_target: "board" },
    silence_schedule: {
      config: {
        enabled: true,
        start_time: "04:00+00:00",
        end_time: "15:00+00:00",
        mode: "indicator",
        page_id: null,
        indicator_text: "SNOOZING",
        indicator_position: "center",
        ...silenceOverrides,
      },
    },
    polling: { interval_seconds: 15 },
    transitions: mockTransitionSettings,
    output: mockOutputSettings,
    board: { board_type: "black", boards, devices: ["flagship"] },
    mqtt: { enabled: false, broker_host: "localhost", broker_port: 1883, username: "", password: "", external_url: "" },
    status: { running: true, config_summary: {} },
  };
}

function makeWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  function Wrapper({ children }: { children: React.ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <ThemeProvider attribute="class" defaultTheme="light">
          <CurrentBoardProvider>{children}</CurrentBoardProvider>
        </ThemeProvider>
      </QueryClientProvider>
    );
  }
  return { Wrapper, queryClient };
}

function stub({ boards = [FLAGSHIP], silence = {} as Record<string, unknown>, onPut = (_body: unknown) => {} }) {
  server.use(
    http.get(`${API_BASE}/settings/all`, () => HttpResponse.json(allSettingsResponse(silence, boards))),
    http.get(`${API_BASE}/settings/board`, () =>
      HttpResponse.json({ board_type: "black", boards, devices: ["flagship"] }),
    ),
    http.get(`${API_BASE}/pages`, () => HttpResponse.json({ pages: PAGES, total: PAGES.length })),
    http.put(`${API_BASE}/settings/silence-schedule`, async ({ request }) => {
      const body = await request.json();
      onPut(body);
      return HttpResponse.json({ status: "success", config: body, board_id: null });
    }),
  );
}

describe("resolveSilenceConfig", () => {
  const base = {
    enabled: true,
    start_time: "04:00+00:00",
    end_time: "15:00+00:00",
    mode: "freeze" as const,
    page_id: null,
    indicator_text: "SNOOZING",
    indicator_position: "center",
  };

  it("returns the install-wide layer when no board is given", () => {
    const resolved = resolveSilenceConfig({ ...base, by_board: { "note-1": { start_time: "06:00+00:00" } } });
    expect(resolved.start_time).toBe("04:00+00:00");
  });

  it("lets a board's own entry win key by key", () => {
    const resolved = resolveSilenceConfig(
      { ...base, by_board: { "note-1": { start_time: "06:00+00:00", mode: "page", page_id: "small" } } },
      "note-1",
    );
    expect(resolved.start_time).toBe("06:00+00:00");
    expect(resolved.mode).toBe("page");
    expect(resolved.page_id).toBe("small");
    // Not overridden -> inherited from the install-wide layer.
    expect(resolved.end_time).toBe("15:00+00:00");
  });

  it("falls back to the install-wide layer for a board with no entry", () => {
    const resolved = resolveSilenceConfig({ ...base, by_board: { "note-1": { start_time: "06:00+00:00" } } }, "flag-1");
    expect(resolved.start_time).toBe("04:00+00:00");
  });

  it("never leaks by_board into the resolved config", () => {
    const resolved = resolveSilenceConfig({ ...base, by_board: { "note-1": {} } }, "note-1");
    expect(resolved).not.toHaveProperty("by_board");
  });
});

describe("SilenceSchedule - board scoping", () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => server.resetHandlers());

  // This replaces an assertion that encoded the wrong contract
  // (`expect(puts[0]).not.toHaveProperty("board_id")`). Omitting board_id on a
  // single-board install writes the install-wide layer, but the engine always
  // resolves per board (`check_and_send_for_board(primary_id, ...)`), so a
  // seeded `by_board` entry shadowed the save key-by-key and the board kept
  // snoozing at the old time forever.
  it("sends the board_id on a single-board install so the save reaches the engine", async () => {
    const puts: Array<Record<string, unknown>> = [];
    stub({ boards: [FLAGSHIP], onPut: (b) => puts.push(b as Record<string, unknown>) });
    const user = userEvent.setup();
    const { Wrapper } = makeWrapper();
    render(<SilenceSchedule />, { wrapper: Wrapper });

    const textInput = await screen.findByLabelText(/message text/i);
    await user.clear(textInput);
    await user.type(textInput, "ZZZZ");

    await waitFor(() => expect(puts.length).toBeGreaterThan(0), { timeout: 5000 });
    expect(puts[0].board_id).toBe("flag-1");
  });

  it("sends the selected board_id on a multi-board install", async () => {
    const puts: Array<Record<string, unknown>> = [];
    stub({ boards: [FLAGSHIP, NOTE], onPut: (b) => puts.push(b as Record<string, unknown>) });
    const user = userEvent.setup();
    const { Wrapper } = makeWrapper();
    render(<SilenceSchedule />, { wrapper: Wrapper });

    const textInput = await screen.findByLabelText(/message text/i);
    await user.clear(textInput);
    await user.type(textInput, "ZZZZ");

    await waitFor(() => expect(puts.length).toBeGreaterThan(0), { timeout: 5000 });
    expect(puts[0].board_id).toBe("flag-1");
  });

  it("seeds the form from the selected board's own entry", async () => {
    stub({
      boards: [FLAGSHIP, NOTE],
      silence: { by_board: { "flag-1": { indicator_text: "BEDTIME" } } },
    });
    const { Wrapper } = makeWrapper();
    render(<SilenceSchedule />, { wrapper: Wrapper });

    const text = await screen.findByLabelText(/message text/i);
    await waitFor(() => expect((text as HTMLInputElement).value).toBe("BEDTIME"));
  });

  // The read half of the same bug: a single-board install that has a
  // `by_board` entry (every upgraded install does — the seeding migration
  // writes one) showed the install-wide values while the engine used the
  // board entry, so the form and the board disagreed with no feedback.
  it("seeds the form from the board's own entry on a single-board install", async () => {
    stub({
      boards: [FLAGSHIP],
      silence: { by_board: { "flag-1": { indicator_text: "BEDTIME" } } },
    });
    const { Wrapper } = makeWrapper();
    render(<SilenceSchedule />, { wrapper: Wrapper });

    const text = await screen.findByLabelText(/message text/i);
    await waitFor(() => expect((text as HTMLInputElement).value).toBe("BEDTIME"));
  });
});

describe("SilenceSchedule - page picker board compatibility", () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => server.resetHandlers());

  it("only offers pages that fit the selected board", async () => {
    stub({ boards: [FLAGSHIP, NOTE], silence: { mode: "page", page_id: "big" } });
    const user = userEvent.setup();
    const { Wrapper } = makeWrapper();
    render(<SilenceSchedule />, { wrapper: Wrapper });

    const picker = await screen.findByRole("combobox", { name: /silence page/i });
    await user.click(picker);

    // Current board is the flagship: the Note page must not be offered.
    // "Big Page" appears twice (trigger label + option), hence findAllByText.
    expect((await screen.findAllByText("Big Page")).length).toBeGreaterThan(0);
    expect(screen.queryByText("Small Page")).not.toBeInTheDocument();
  });
});

describe("SilenceSchedule - cache invalidation", () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => server.resetHandlers());

  it("invalidates the silenceStatus key the consumers actually read", async () => {
    // Regression: the mutation invalidated ["silence-status"] (hyphenated)
    // while SilenceImminentBanner / ActivePageDisplay read ["silenceStatus"],
    // so the banner kept showing a stale window after a save.
    stub({ boards: [FLAGSHIP] });
    const user = userEvent.setup();
    const { Wrapper, queryClient } = makeWrapper();
    const spy = vi.spyOn(queryClient, "invalidateQueries");
    render(<SilenceSchedule />, { wrapper: Wrapper });

    const textInput = await screen.findByLabelText(/message text/i);
    await user.clear(textInput);
    await user.type(textInput, "ZZZZ");

    await waitFor(
      () => expect(spy).toHaveBeenCalledWith(expect.objectContaining({ queryKey: queryKeys.silenceStatus() })),
      { timeout: 5000 },
    );
  });
});
