import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ActivePageDisplay } from "@/components/active-page-display";
import { CurrentBoardProvider, useCurrentBoard } from "@/components/current-board-context";
import { queryKeys } from "@/hooks/use-board";
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

vi.mock("@/components/smart-link", () => ({
  default: ({ children, href, ...rest }: { children: React.ReactNode; href: string }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

const TWO_BOARDS = {
  board_type: "black",
  boards: [
    { id: "board-1", name: "Living Room", device_type: "flagship", board_color: "black", enabled: true },
    { id: "board-2", name: "Kitchen", device_type: "flagship", board_color: "black", enabled: true },
  ],
  devices: ["flagship"],
};

function boardId(request: Request): string | null {
  return new URL(request.url).searchParams.get("board_id");
}

function useTwoBoards() {
  server.use(http.get(`${API_BASE}/settings/board`, () => HttpResponse.json(TWO_BOARDS)));
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
      <ConfigOverridesProvider>
        <ThemeProvider attribute="class" defaultTheme="light">
          <CurrentBoardProvider>{children}</CurrentBoardProvider>
        </ThemeProvider>
      </ConfigOverridesProvider>
    </QueryClientProvider>
  );
}

/** Test-only harness for driving the board selector from inside the provider. */
function SwitchBoardButton({ to }: { to: string }) {
  const { setCurrentBoardId } = useCurrentBoard();
  return (
    <button type="button" onClick={() => setCurrentBoardId(to)}>
      switch-board-{to}
    </button>
  );
}

describe("ActivePageDisplay per-board scoping (issue #1247)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it("board-scopes query keys, keeping the unscoped key as a prefix", () => {
    expect(queryKeys.activePage()).toEqual(["activePage"]);
    expect(queryKeys.activePage("board-2")).toEqual(["activePage", "board-2"]);
    expect(queryKeys.boardCurrentMessage()).toEqual(["board-current-message"]);
    expect(queryKeys.boardCurrentMessage("board-2")).toEqual(["board-current-message", "board-2"]);
  });

  it("fetches the selected board's active page, board state, and active schedule", async () => {
    const seen = {
      activePage: [] as (string | null)[],
      currentMessage: [] as (string | null)[],
      schedule: [] as (string | null)[],
    };
    useTwoBoards();
    server.use(
      http.get(`${API_BASE}/settings/active-page`, ({ request }) => {
        seen.activePage.push(boardId(request));
        return HttpResponse.json({ page_id: "page-1" });
      }),
      http.get(`${API_BASE}/board/current-message`, ({ request }) => {
        seen.currentMessage.push(boardId(request));
        return HttpResponse.json({
          characters: [],
          message: "KITCHEN CONTENT",
          rows: 6,
          cols: 22,
          expected_characters: null,
          cached_at: null,
          api_mode: "local",
          board_id: boardId(request),
        });
      }),
      http.get(`${API_BASE}/schedules/active/page`, ({ request }) => {
        seen.schedule.push(boardId(request));
        return HttpResponse.json({ page_id: "page-1", source: "manual", schedule_enabled: false });
      }),
    );
    localStorage.setItem("fiestaboard_current_board", "board-2");

    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    // Board scoping only kicks in after boards load -> context effect runs ->
    // scopedBoardId flips -> queries re-key -> refetch; give that chain more
    // than the default 1000ms under CI's heavier parallel load.
    await waitFor(
      () => {
        expect(seen.activePage).toContain("board-2");
        expect(seen.currentMessage).toContain("board-2");
        expect(seen.schedule).toContain("board-2");
      },
      { timeout: 3000 },
    );
  });

  it("shows which board the Active Display is reflecting", async () => {
    useTwoBoards();
    localStorage.setItem("fiestaboard_current_board", "board-2");

    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    const indicator = await screen.findByTestId("active-display-board-name");
    expect(indicator).toHaveTextContent("Showing Kitchen");
  });

  it("switching the current board refetches with the new board id", async () => {
    const seenActivePage: (string | null)[] = [];
    useTwoBoards();
    server.use(
      http.get(`${API_BASE}/settings/active-page`, ({ request }) => {
        seenActivePage.push(boardId(request));
        return HttpResponse.json({ page_id: "page-1" });
      }),
    );
    localStorage.setItem("fiestaboard_current_board", "board-2");

    const user = userEvent.setup();
    render(
      <>
        <ActivePageDisplay />
        <SwitchBoardButton to="board-1" />
      </>,
      { wrapper: TestWrapper },
    );

    await waitFor(
      () => {
        expect(seenActivePage).toContain("board-2");
      },
      { timeout: 3000 },
    );

    await user.click(screen.getByRole("button", { name: "switch-board-board-1" }));

    await waitFor(
      () => {
        expect(seenActivePage).toContain("board-1");
      },
      { timeout: 3000 },
    );
  });

  it.each(["board-1", "board-2"])(
    "opening and switching away from unpinned %s does not persist a page",
    async (selectedBoard) => {
      const puts: unknown[] = [];
      useTwoBoards();
      server.use(
        http.get(`${API_BASE}/settings/active-page`, () => HttpResponse.json({ page_id: null })),
        http.put(`${API_BASE}/settings/active-page`, async ({ request }) => {
          puts.push(await request.json());
          return HttpResponse.json({ status: "success", sent_to_board: true });
        }),
      );
      localStorage.setItem("fiestaboard_current_board", selectedBoard);
      const otherBoard = selectedBoard === "board-1" ? "board-2" : "board-1";
      const user = userEvent.setup();
      render(
        <>
          <ActivePageDisplay />
          <SwitchBoardButton to={otherBoard} />
        </>,
        { wrapper: TestWrapper },
      );

      await screen.findByTestId("active-display-board-name");
      await user.click(screen.getByRole("button", { name: /Change Page/i }));
      await screen.findByText("Custom Template");
      expect(puts).toEqual([]);
      await user.keyboard("{Escape}");
      await user.click(screen.getByRole("button", { name: `switch-board-${otherBoard}` }));
      await waitFor(() =>
        expect(screen.getByTestId("active-display-board-name")).toHaveTextContent(
          otherBoard === "board-1" ? "Showing Living Room" : "Showing Kitchen",
        ),
      );
      await user.click(screen.getByRole("button", { name: /Change Page/i }));
      await screen.findByText("Custom Template");
      expect(puts).toEqual([]);
    },
  );

  it("Change Page sets the active page for the selected board only", async () => {
    let putBody: { page_id?: string | null; board_id?: string } | null = null;
    useTwoBoards();
    server.use(
      http.put(`${API_BASE}/settings/active-page`, async ({ request }) => {
        putBody = (await request.json()) as { page_id?: string | null; board_id?: string };
        return HttpResponse.json({ status: "success", page_id: putBody.page_id, sent_to_board: true });
      }),
    );
    localStorage.setItem("fiestaboard_current_board", "board-2");

    const user = userEvent.setup();
    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Change Page/i })).toBeInTheDocument();
    });
    await user.click(screen.getByRole("button", { name: /Change Page/i }));

    // Wait for sheet content and page grid to load (420ms animation + data fetch)
    await waitFor(
      () => {
        expect(screen.queryByText("Custom Template")).toBeInTheDocument();
      },
      { timeout: 3000 },
    );
    await user.click(screen.getByText("Custom Template"));

    await waitFor(
      () => {
        expect(putBody).not.toBeNull();
        expect(putBody?.board_id).toBe("board-2");
      },
      { timeout: 3000 },
    );
  });

  it("falls back to the active page render when a secondary board has no cached content", async () => {
    const previewedPageIds: string[] = [];
    useTwoBoards();
    server.use(
      http.get(`${API_BASE}/board/current-message`, ({ request }) =>
        HttpResponse.json({
          characters: null,
          message: null,
          rows: 6,
          cols: 22,
          expected_characters: null,
          cached_at: null,
          api_mode: "local",
          board_id: boardId(request),
        }),
      ),
      http.post(`${API_BASE}/pages/:id/preview`, ({ params }) => {
        previewedPageIds.push(String(params.id));
        return HttpResponse.json({
          page_id: params.id,
          message: "Preview content",
          lines: ["Preview content"],
          display_type: "single",
          raw: {},
        });
      }),
    );
    localStorage.setItem("fiestaboard_current_board", "board-2");

    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    await waitFor(
      () => {
        expect(previewedPageIds).toContain("page-1");
      },
      { timeout: 3000 },
    );
  });

  it("single-board installs stay unscoped with no board indicator", async () => {
    // Default handlers return a single board — behavior must match pre-#1247.
    const seenActivePage: (string | null)[] = [];
    server.use(
      http.get(`${API_BASE}/settings/active-page`, ({ request }) => {
        seenActivePage.push(boardId(request));
        return HttpResponse.json({ page_id: "page-1" });
      }),
    );

    render(<ActivePageDisplay />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText("Weather Page")).toBeInTheDocument();
    });
    expect(seenActivePage.length).toBeGreaterThan(0);
    expect(seenActivePage.every((id) => id === null)).toBe(true);
    expect(screen.queryByTestId("active-display-board-name")).not.toBeInTheDocument();
  });

  it.each([
    { device_type: "note", rows: 3, cols: 15, geometry: {} },
    { device_type: "note_array", rows: 3, cols: 15, geometry: { notes_wide: 1, notes_tall: 1 } },
    { device_type: "note_array", rows: 6, cols: 30, geometry: { notes_wide: 2, notes_tall: 2 } },
    { device_type: "panel", rows: 7, cols: 23, geometry: { grid_rows: 7, grid_cols: 23 } },
  ])(
    "saves the selected $device_type board's observed characters and geometry",
    async ({ device_type, rows, cols, geometry }) => {
      localStorage.setItem("fiestaboard_current_board", "board-2");
      const observed = Array.from({ length: rows }, () => Array(cols).fill(0));
      observed[0].splice(0, 7, 0, 8, 9, 63, 70, 71, 62);
      let createdBody: Record<string, unknown> | null = null;
      server.use(
        http.get(`${API_BASE}/settings/board`, () =>
          HttpResponse.json({
            ...TWO_BOARDS,
            boards: [TWO_BOARDS.boards[0], { ...TWO_BOARDS.boards[1], device_type, ...geometry }],
          }),
        ),
        http.get(`${API_BASE}/board/current-message`, ({ request }) => {
          const selected = boardId(request) === "board-2";
          return HttpResponse.json({
            characters: selected ? observed : Array.from({ length: 6 }, () => Array(22).fill(1)),
            message: "THIS PREVIEW TEXT MUST NOT BE SAVED",
            rows: selected ? rows : 6,
            cols: selected ? cols : 22,
            expected_characters: selected ? Array.from({ length: rows }, () => Array(cols).fill(2)) : null,
            cached_at: null,
            api_mode: "local",
            board_id: boardId(request),
          });
        }),
        http.post(`${API_BASE}/v1/pages`, async ({ request }) => {
          createdBody = (await request.json()) as Record<string, unknown>;
          return HttpResponse.json({ id: "saved-external", ...createdBody }, { status: 201 });
        }),
      );

      render(<ActivePageDisplay />, { wrapper: TestWrapper });
      await userEvent.setup().click(await screen.findByRole("button", { name: /Save as page/i }));

      await waitFor(() => expect(createdBody).not.toBeNull());
      expect(createdBody).toMatchObject({
        type: "template",
        device_type,
        ...geometry,
        template: [" HI{{red}}{{black}}{{filled}}°", ...Array(rows - 1).fill("")],
      });
      expect(createdBody).not.toHaveProperty("board_id");
    },
  );
});
