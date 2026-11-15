/**
 * The board context menu on Home (slice 2.2, WEB-18, 07a §6) and pause /
 * resume from it (issue #2051).
 *
 * 07a moves Pause off the card's action row into the board menu (and the
 * Displays page): right-click, Shift+F10 or a long-press on the board, or the
 * ⋯ button that shows on hover, focus and touch. Items: Change Page… ·
 * Compose a message… · Edit page · Copy as text · Refresh board │ Pause <display>.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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

async function openMenu(user: ReturnType<typeof userEvent.setup>, name: string | RegExp = /^Actions for /) {
  await user.click(await screen.findByRole("button", { name }));
  return screen.findByRole("menu");
}

describe("ActivePageDisplay board menu (WEB-18) and pause (issue #2051)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it("lists 07a's items, with Pause apart and named for the display", async () => {
    serveBoards([{ id: "default", name: "Flagship", paused: false }]);
    const user = userEvent.setup();
    render(<ActivePageDisplay />, { wrapper: Wrapper });
    const menu = await openMenu(user, "Actions for Flagship");
    const items = within(menu)
      .getAllByRole("menuitem")
      .map((item) => item.textContent?.replace(/[PCE]$/, ""));
    expect(items).toEqual(["Change Page…", "Compose a message…", "Edit page", "Refresh board", "Pause Flagship"]);
  });

  it("opens the same menu on a right-click on the board", async () => {
    serveBoards([{ id: "default", name: "Flagship", paused: false }]);
    render(<ActivePageDisplay />, { wrapper: Wrapper });
    fireEvent.contextMenu(await screen.findByTestId("home-board"));
    expect(await screen.findByRole("menuitem", { name: /Change Page…/ })).toBeInTheDocument();
  });

  it("opens Change Page and asks for Compose from the menu", async () => {
    serveBoards([{ id: "default", name: "Flagship", paused: false }]);
    const onCompose = vi.fn();
    const user = userEvent.setup();
    render(<ActivePageDisplay onCompose={onCompose} />, { wrapper: Wrapper });
    await openMenu(user);
    await user.click(screen.getByRole("menuitem", { name: /Compose a message…/ }));
    expect(onCompose).toHaveBeenCalledTimes(1);
    await openMenu(user);
    await user.click(screen.getByRole("menuitem", { name: /Change Page…/ }));
    expect(await screen.findByRole("dialog", { name: "Change Page" })).toBeInTheDocument();
  });

  it("refreshes the display through its own restore route", async () => {
    serveBoards([{ id: "default", name: "Flagship", paused: false }]);
    let restored = 0;
    server.use(
      http.post(`${API_BASE}/v1/boards/:board/restore`, () => {
        restored += 1;
        return HttpResponse.json({
          board_id: "default",
          page_id: "page-1",
          sent: true,
          reason: null,
          device_observed: false,
        });
      }),
    );
    const user = userEvent.setup();
    render(<ActivePageDisplay />, { wrapper: Wrapper });
    await openMenu(user);
    await user.click(screen.getByRole("menuitem", { name: "Refresh board" }));
    await waitFor(() => expect(restored).toBe(1));
  });

  it("copies the board's text when the hub reports it", async () => {
    serveBoards([{ id: "default", name: "Flagship", paused: false }]);
    let detailRead = false;
    server.use(
      http.get(`${API_BASE}/v1/boards/:board`, () => {
        detailRead = true;
        return HttpResponse.json({ id: "default", name: "Flagship", text: "GOOD EVENING\nMAYA" });
      }),
    );
    // userEvent installs its own clipboard stub on setup.
    const user = userEvent.setup();
    render(<ActivePageDisplay />, { wrapper: Wrapper });
    await waitFor(() => expect(detailRead).toBe(true));
    await openMenu(user);
    await user.click(await screen.findByRole("menuitem", { name: "Copy as text" }));
    await waitFor(async () => expect(await navigator.clipboard.readText()).toBe("GOOD EVENING\nMAYA"));
  });

  it("pauses a running display from the menu and then offers to resume it", async () => {
    const patches = serveBoards([{ id: "default", name: "Flagship", paused: false }]);
    const user = userEvent.setup();
    render(<ActivePageDisplay />, { wrapper: Wrapper });

    await openMenu(user);
    await user.click(screen.getByRole("menuitem", { name: "Pause Flagship" }));

    await waitFor(() => expect(patches).toEqual([{ board: "default", body: { paused: true } }]));
    expect(await screen.findByTestId("board-paused-badge")).toBeInTheDocument();
    await openMenu(user);
    expect(screen.getByRole("menuitem", { name: "Resume Flagship" })).toBeInTheDocument();
  });

  it("acts on the display selected in the sidebar, not the primary one", async () => {
    const patches = serveBoards([
      { id: "board-1", name: "Living Room", paused: false },
      { id: "board-2", name: "Kitchen", paused: true },
    ]);
    localStorage.setItem("fiestaboard_current_board", "board-2");
    const user = userEvent.setup();
    render(<ActivePageDisplay />, { wrapper: Wrapper });

    await openMenu(user, "Actions for Kitchen");
    await user.click(screen.getByRole("menuitem", { name: "Resume Kitchen" }));

    await waitFor(() => expect(patches).toEqual([{ board: "board-2", body: { paused: false } }]));
  });

  it("does not show the Paused badge while viewing a running board when another board is paused", async () => {
    serveBoards([
      { id: "board-1", name: "Living Room", paused: false },
      { id: "board-2", name: "Kitchen", paused: true },
    ]);
    localStorage.setItem("fiestaboard_current_board", "board-1");
    render(<ActivePageDisplay />, { wrapper: Wrapper });

    await screen.findByRole("region", { name: /Now showing.*Living Room/ });

    expect(screen.queryByTestId("board-paused-badge")).not.toBeInTheDocument();
  });

  it("shows the Paused badge without the board name when viewing the paused board", async () => {
    serveBoards([
      { id: "board-1", name: "Living Room", paused: false },
      { id: "board-2", name: "Kitchen", paused: true },
    ]);
    localStorage.setItem("fiestaboard_current_board", "board-2");
    render(<ActivePageDisplay />, { wrapper: Wrapper });

    expect(await screen.findByTestId("board-paused-badge")).toHaveTextContent(/^Paused$/);
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

    await openMenu(user);
    await user.click(screen.getByRole("menuitem", { name: "Pause Flagship" }));

    await waitFor(() => expect(errorToast).toHaveBeenCalled());
    expect(screen.queryByTestId("board-paused-badge")).not.toBeInTheDocument();
    errorToast.mockRestore();
  });
});
