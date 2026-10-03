/**
 * Pause / resume from Home (issue #2051).
 *
 * Pausing used to live five clicks deep in Settings → Hardware. Home already
 * shows the "Paused" badge, so it offers the toggle too, next to Change Page,
 * for the board the Active Display is showing.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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

type Board = { id: string; name: string; paused?: boolean };

/**
 * Board settings backed by mutable state, so a PATCH is visible to the
 * refetch that follows it. Returns the PATCH calls the component made.
 */
function serveBoards(boards: Board[]) {
  const patches: { board: string; body: unknown }[] = [];
  server.use(
    http.get(`${API_BASE}/settings/board`, () =>
      HttpResponse.json({
        board_type: "black",
        boards: boards.map((b) => ({ device_type: "flagship", board_color: "black", enabled: true, ...b })),
        devices: ["flagship"],
      }),
    ),
    http.patch(`${API_BASE}/v1/boards/:board`, async ({ request, params }) => {
      const body = (await request.json()) as { paused: boolean };
      patches.push({ board: String(params.board), body });
      const board = boards.find((b) => b.id === params.board);
      if (board) board.paused = body.paused;
      return HttpResponse.json({ id: params.board, paused: body.paused });
    }),
  );
  return patches;
}

function Wrapper({ children }: { children: React.ReactNode }) {
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

describe("ActivePageDisplay pause toggle (issue #2051)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it("pauses a running board from Home and then offers to resume it", async () => {
    const patches = serveBoards([{ id: "default", name: "Flagship", paused: false }]);
    const user = userEvent.setup();
    render(<ActivePageDisplay />, { wrapper: Wrapper });

    await user.click(await screen.findByRole("button", { name: "Pause sends" }));

    expect(patches).toEqual([{ board: "default", body: { paused: true } }]);
    expect(await screen.findByRole("button", { name: "Resume sends" })).toBeInTheDocument();
    expect(screen.getByTestId("board-paused-badge")).toBeInTheDocument();
  });

  it("resumes a paused board from Home", async () => {
    const patches = serveBoards([{ id: "default", name: "Flagship", paused: true }]);
    const user = userEvent.setup();
    render(<ActivePageDisplay />, { wrapper: Wrapper });

    await user.click(await screen.findByRole("button", { name: "Resume sends" }));

    expect(patches).toEqual([{ board: "default", body: { paused: false } }]);
    expect(await screen.findByRole("button", { name: "Pause sends" })).toBeInTheDocument();
    expect(screen.queryByTestId("board-paused-badge")).not.toBeInTheDocument();
  });

  it("acts on the board selected in the sidebar, not the primary one", async () => {
    const patches = serveBoards([
      { id: "board-1", name: "Living Room", paused: false },
      { id: "board-2", name: "Kitchen", paused: true },
    ]);
    localStorage.setItem("fiestaboard_current_board", "board-2");
    const user = userEvent.setup();
    render(<ActivePageDisplay />, { wrapper: Wrapper });

    // Kitchen is paused, so the toggle offers to resume it even though the
    // primary board (Living Room) is running.
    await user.click(await screen.findByRole("button", { name: "Resume sends" }));

    expect(patches).toEqual([{ board: "board-2", body: { paused: false } }]);
  });

  it("explains what pausing does on the button itself", async () => {
    serveBoards([{ id: "default", name: "Flagship", paused: false }]);
    render(<ActivePageDisplay />, { wrapper: Wrapper });

    const button = await screen.findByRole("button", { name: "Pause sends" });
    expect(button).toHaveAttribute("title", expect.stringContaining("does not push anything to this board"));
  });

  // On phones the header actions collapse into a kebab menu (the inline
  // buttons are hidden below the sm breakpoint; jsdom renders both).
  it("pauses the board from the phone-width actions menu", async () => {
    const patches = serveBoards([{ id: "default", name: "Flagship", paused: false }]);
    const user = userEvent.setup();
    render(<ActivePageDisplay />, { wrapper: Wrapper });

    await user.click(await screen.findByRole("button", { name: "More options" }));
    await user.click(await screen.findByRole("menuitem", { name: "Pause sends" }));

    await waitFor(() => expect(patches).toEqual([{ board: "default", body: { paused: true } }]));
  });

  it("opens the page picker from the phone-width actions menu", async () => {
    serveBoards([{ id: "default", name: "Flagship", paused: false }]);
    const user = userEvent.setup();
    render(<ActivePageDisplay />, { wrapper: Wrapper });

    await user.click(await screen.findByRole("button", { name: "More options" }));
    await user.click(await screen.findByRole("menuitem", { name: "Change Page" }));

    expect(await screen.findByText("Select Page")).toBeInTheDocument();
  });

  it("links to the schedule from the phone-width actions menu when a schedule is running", async () => {
    serveBoards([{ id: "default", name: "Flagship", paused: false }]);
    server.use(
      http.get(`${API_BASE}/schedules/active/page`, () =>
        HttpResponse.json({ page_id: "page-1", source: "schedule", schedule_enabled: true }),
      ),
    );
    const user = userEvent.setup();
    render(<ActivePageDisplay />, { wrapper: Wrapper });

    await screen.findByRole("link", { name: /View Schedule/i });
    await user.click(screen.getByRole("button", { name: "More options" }));

    expect(await screen.findByRole("menuitem", { name: "View Schedule" })).toHaveAttribute("href", "/schedule");
  });

  it("shows the error and leaves the board state alone when the request fails", async () => {
    const errorToast = vi.spyOn((await import("sonner")).toast, "error");
    serveBoards([{ id: "default", name: "Flagship", paused: false }]);
    server.use(
      http.patch(`${API_BASE}/v1/boards/:board`, () =>
        HttpResponse.json({ detail: "Board is unreachable" }, { status: 503 }),
      ),
    );
    const user = userEvent.setup();
    render(<ActivePageDisplay />, { wrapper: Wrapper });

    await user.click(await screen.findByRole("button", { name: "Pause sends" }));

    await waitFor(() => expect(errorToast).toHaveBeenCalled());
    expect(screen.getByRole("button", { name: "Pause sends" })).toBeEnabled();
    expect(screen.queryByTestId("board-paused-badge")).not.toBeInTheDocument();
    errorToast.mockRestore();
  });
});
