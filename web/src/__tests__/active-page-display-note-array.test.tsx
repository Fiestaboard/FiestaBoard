/**
 * ActivePageDisplay on note-array boards (including FiestaPanel virtual
 * boards, which are always auto-fit note arrays).
 *
 * Two dashboard bugs lived here:
 *  - the preview derived only "flagship" | "note" from the board state, so
 *    any note array (e.g. a panel's 12×15 board) rendered as a 6×22
 *    flagship with the real content squeezed into the wrong grid
 *  - manual mode auto-set pages[0] as the default page with no size check;
 *    on a board where pages[0] can never fit, the backend's 400 turned the
 *    effect into an endless retry loop ("Failed to set default page").
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ActivePageDisplay } from "@/components/active-page-display";
import { CurrentBoardProvider } from "@/components/current-board-context";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { ThemeProvider } from "@/hooks/use-theme";

import { server } from "./mocks/server";

const API_BASE = "/api";

vi.mock("@/hooks/use-router", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn(), back: vi.fn() }),
}));

vi.mock("@/components/smart-link", () => ({
  default: ({ children, href, ...rest }: { children: React.ReactNode; href: string }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

/** A flagship plus a FiestaPanel's auto-fit virtual board (1×4 → 12×15). */
const BOARDS_WITH_PANEL = {
  board_type: "black",
  boards: [
    { id: "board-1", name: "Living Room", device_type: "flagship", board_color: "black", enabled: true },
    {
      id: "board-panel",
      name: "Den TV (Panel)",
      device_type: "note_array",
      api_mode: "virtual",
      notes_wide: 1,
      notes_tall: 4,
      board_color: "black",
      enabled: true,
    },
  ],
  devices: ["flagship", "note_array"],
};

const FLAGSHIP_PAGE = {
  id: "welcome-page",
  name: "Welcome",
  type: "template",
  device_type: "flagship",
  template: ["HI"],
  duration_seconds: 300,
  created_at: "2026-08-25T00:00:00+00:00",
};

const PANEL_PAGE = {
  id: "panel-page",
  name: "Panel Page",
  type: "template",
  device_type: "note_array",
  notes_wide: 1,
  notes_tall: 4,
  template: ["HI"],
  duration_seconds: 300,
  created_at: "2026-08-25T00:00:00+00:00",
};

function TestWrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return (
    <QueryClientProvider client={queryClient}>
      <ConfigOverridesProvider>
        <ThemeProvider attribute="class" defaultTheme="light">
          <CurrentBoardProvider>{children}</CurrentBoardProvider>
        </ThemeProvider>
      </ConfigOverridesProvider>
    </QueryClientProvider>
  );
}

function usePanelBoard({
  pages,
  activePageId,
  boardMessage,
  putStatus = 200,
}: {
  pages: Array<Record<string, unknown>>;
  activePageId: string | null;
  boardMessage: string | null;
  /** Status for PUT /settings/active-page; 400 mimics the backend refusing
   *  a page the board cannot render, which is what used to retry forever. */
  putStatus?: number;
}) {
  const puts: Array<{ page_id?: string | null; board_id?: string }> = [];
  server.use(
    http.get(`${API_BASE}/settings/board`, () => HttpResponse.json(BOARDS_WITH_PANEL)),
    http.get(`${API_BASE}/pages`, () => HttpResponse.json({ pages, total: pages.length })),
    http.get(`${API_BASE}/settings/active-page`, () => HttpResponse.json({ page_id: activePageId })),
    http.get(`${API_BASE}/schedules/active/page`, () =>
      HttpResponse.json({ page_id: activePageId, source: "manual", schedule_enabled: false }),
    ),
    http.get(`${API_BASE}/board/current-message`, () =>
      HttpResponse.json({
        characters: boardMessage ? [] : null,
        message: boardMessage,
        rows: 12,
        cols: 15,
        expected_characters: null,
        cached_at: null,
        api_mode: "virtual",
        board_id: "board-panel",
      }),
    ),
    http.put(`${API_BASE}/settings/active-page`, async ({ request }) => {
      puts.push((await request.json()) as { page_id?: string | null; board_id?: string });
      if (putStatus !== 200) {
        return HttpResponse.json({ detail: "page does not fit board" }, { status: putStatus });
      }
      return HttpResponse.json({ status: "success", sent_to_board: true });
    }),
  );
  return puts;
}

describe("ActivePageDisplay on a panel's note-array board", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    localStorage.setItem("fiestaboard_current_board", "board-panel");
  });

  it("renders the preview at the board's true W×H, not as a flagship", async () => {
    usePanelBoard({ pages: [FLAGSHIP_PAGE, PANEL_PAGE], activePageId: "panel-page", boardMessage: "PANEL CONTENT" });

    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    // The 1×4 auto-fit board is 12 rows × 15 cols; the last tile of that
    // grid must exist…
    await waitFor(
      () => {
        expect(document.querySelector('[data-testid="char-tile-11-14"]')).not.toBeNull();
      },
      { timeout: 3000 },
    );
    // …and a flagship-only coordinate (col 21 / row 5-of-6 layout) must not.
    expect(document.querySelector('[data-testid="char-tile-0-21"]')).toBeNull();
    expect(document.querySelector('[data-testid="char-tile-0-15"]')).toBeNull();
  });

  it("auto-selects the first page that actually fits the board", async () => {
    const puts = usePanelBoard({ pages: [FLAGSHIP_PAGE, PANEL_PAGE], activePageId: null, boardMessage: null });

    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    await waitFor(
      () => {
        expect(puts.length).toBeGreaterThan(0);
      },
      { timeout: 3000 },
    );
    expect(puts[0].page_id).toBe("panel-page");
    expect(puts[0].board_id).toBe("board-panel");
  });

  it("auto-selects nothing when no page fits the board", async () => {
    // Pins the compatibility filter, NOT the retry guard: with only a
    // flagship page the effect returns at `!defaultPage` and never reaches
    // the mutation. The retry guard is pinned by the next test.
    const puts = usePanelBoard({ pages: [FLAGSHIP_PAGE], activePageId: null, boardMessage: null });

    render(<ActivePageDisplay />, { wrapper: TestWrapper });
    await screen.findByTestId("active-display-board-name");

    await new Promise((resolve) => setTimeout(resolve, 600));
    expect(puts).toEqual([]);
  });

  it("does not retry-loop when the auto-selected page is rejected", async () => {
    // The real #1249 loop: a page that DOES fit is auto-selected, the
    // backend refuses it, and without `autoDefaultAttemptedForRef` the
    // mutation re-fires on every render (the mutation object's identity
    // changes each time), spraying 400s and error toasts.
    const puts = usePanelBoard({
      pages: [PANEL_PAGE],
      activePageId: null,
      boardMessage: null,
      putStatus: 400,
    });

    render(<ActivePageDisplay />, { wrapper: TestWrapper });
    await screen.findByTestId("active-display-board-name");

    // One attempt must happen…
    await waitFor(() => expect(puts.length).toBeGreaterThan(0), { timeout: 3000 });
    // …and exactly one, however long the component keeps re-rendering.
    await new Promise((resolve) => setTimeout(resolve, 600));
    expect(puts).toHaveLength(1);
  });
});
