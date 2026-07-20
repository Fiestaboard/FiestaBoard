import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CurrentBoardProvider, useCurrentBoard } from "@/components/current-board-context";

import { server } from "./mocks/server";

const API_BASE = "/api";
const STORAGE_KEY = "fiestaboard_current_board";

function boardsResponse(boards: Array<{ id: string; name: string }>) {
  return HttpResponse.json({
    board_type: "black",
    boards: boards.map((b) => ({
      ...b,
      device_type: "flagship",
      board_color: "black",
    })),
    devices: ["flagship"],
  });
}

function Probe() {
  const { currentBoardId, currentBoard, boards, setCurrentBoardId } = useCurrentBoard();
  return (
    <div>
      <span data-testid="current-id">{currentBoardId}</span>
      <span data-testid="current-name">{currentBoard?.name ?? ""}</span>
      <span data-testid="board-count">{boards.length}</span>
      <button data-testid="select-one" onClick={() => setCurrentBoardId("one")} />
      <button data-testid="select-two" onClick={() => setCurrentBoardId("two")} />
    </div>
  );
}

function renderProbe() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <CurrentBoardProvider>
        <Probe />
      </CurrentBoardProvider>
    </QueryClientProvider>,
  );
}

describe("CurrentBoardProvider", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("defaults to the primary board when nothing is stored", async () => {
    server.use(
      http.get(`${API_BASE}/settings/board`, () =>
        boardsResponse([
          { id: "one", name: "Kitchen" },
          { id: "two", name: "Office" },
        ]),
      ),
    );

    renderProbe();

    await waitFor(() => expect(screen.getByTestId("current-id")).toHaveTextContent("one"));
    expect(screen.getByTestId("current-name")).toHaveTextContent("Kitchen");
  });

  it("restores a valid stored board id from localStorage", async () => {
    localStorage.setItem(STORAGE_KEY, "two");
    server.use(
      http.get(`${API_BASE}/settings/board`, () =>
        boardsResponse([
          { id: "one", name: "Kitchen" },
          { id: "two", name: "Office" },
        ]),
      ),
    );

    renderProbe();

    await waitFor(() => expect(screen.getByTestId("current-id")).toHaveTextContent("two"));
    expect(screen.getByTestId("current-name")).toHaveTextContent("Office");
  });

  it("drops a stale stored id and falls back to the primary board", async () => {
    localStorage.setItem(STORAGE_KEY, "deleted-board");
    server.use(
      http.get(`${API_BASE}/settings/board`, () =>
        boardsResponse([
          { id: "one", name: "Kitchen" },
          { id: "two", name: "Office" },
        ]),
      ),
    );

    renderProbe();

    await waitFor(() => expect(screen.getByTestId("current-id")).toHaveTextContent("one"));
  });

  it("persists a new selection to localStorage", async () => {
    server.use(
      http.get(`${API_BASE}/settings/board`, () =>
        boardsResponse([
          { id: "one", name: "Kitchen" },
          { id: "two", name: "Office" },
        ]),
      ),
    );

    renderProbe();

    await waitFor(() => expect(screen.getByTestId("current-id")).toHaveTextContent("one"));

    fireEvent.click(screen.getByTestId("select-two"));

    await waitFor(() => expect(screen.getByTestId("current-id")).toHaveTextContent("two"));
    expect(localStorage.getItem(STORAGE_KEY)).toBe("two");
  });
});

describe("CurrentBoardProvider — board switch view transition", () => {
  const twoBoards = () =>
    server.use(
      http.get(`${API_BASE}/settings/board`, () =>
        boardsResponse([
          { id: "one", name: "Kitchen" },
          { id: "two", name: "Office" },
        ]),
      ),
    );

  // jsdom has no View Transitions API — install a stub that runs the update
  // callback synchronously and resolves `finished`, like the real thing.
  let startViewTransition: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    localStorage.clear();
    startViewTransition = vi.fn((cb: () => void) => {
      cb();
      return { finished: Promise.resolve() };
    });
    (document as unknown as { startViewTransition: unknown }).startViewTransition = startViewTransition;
  });

  afterEach(() => {
    delete (document as unknown as { startViewTransition?: unknown }).startViewTransition;
    delete document.documentElement.dataset.boardSwitch;
    document.documentElement.classList.remove("reduce-motion", "site-animations-off");
  });

  it("switching to a later board runs a forward view transition", async () => {
    twoBoards();
    renderProbe();
    await waitFor(() => expect(screen.getByTestId("current-id")).toHaveTextContent("one"));

    fireEvent.click(screen.getByTestId("select-two"));

    expect(startViewTransition).toHaveBeenCalledTimes(1);
    // Direction is stamped on <html> so CSS can pick slide-left vs slide-right.
    expect(document.documentElement.dataset.boardSwitch).toBe("forward");
    await waitFor(() => expect(screen.getByTestId("current-id")).toHaveTextContent("two"));
    // Cleaned up once the transition settles.
    await waitFor(() => expect(document.documentElement.dataset.boardSwitch).toBeUndefined());
  });

  it("switching back to an earlier board runs a backward view transition", async () => {
    localStorage.setItem(STORAGE_KEY, "two");
    twoBoards();
    renderProbe();
    await waitFor(() => expect(screen.getByTestId("current-id")).toHaveTextContent("two"));

    fireEvent.click(screen.getByTestId("select-one"));

    expect(startViewTransition).toHaveBeenCalledTimes(1);
    expect(document.documentElement.dataset.boardSwitch).toBe("backward");
    await waitFor(() => expect(screen.getByTestId("current-id")).toHaveTextContent("one"));
  });

  it("re-selecting the current board does not start a transition", async () => {
    twoBoards();
    renderProbe();
    await waitFor(() => expect(screen.getByTestId("current-id")).toHaveTextContent("one"));

    fireEvent.click(screen.getByTestId("select-one"));

    expect(startViewTransition).not.toHaveBeenCalled();
  });

  it("skips the transition when reduced motion is requested", async () => {
    document.documentElement.classList.add("reduce-motion");
    twoBoards();
    renderProbe();
    await waitFor(() => expect(screen.getByTestId("current-id")).toHaveTextContent("one"));

    fireEvent.click(screen.getByTestId("select-two"));

    expect(startViewTransition).not.toHaveBeenCalled();
    // The switch itself still happens instantly.
    await waitFor(() => expect(screen.getByTestId("current-id")).toHaveTextContent("two"));
  });

  it("skips the transition when site animations are off", async () => {
    document.documentElement.classList.add("site-animations-off");
    twoBoards();
    renderProbe();
    await waitFor(() => expect(screen.getByTestId("current-id")).toHaveTextContent("one"));

    fireEvent.click(screen.getByTestId("select-two"));

    expect(startViewTransition).not.toHaveBeenCalled();
    await waitFor(() => expect(screen.getByTestId("current-id")).toHaveTextContent("two"));
  });

  it("falls back to an instant switch when the API is unavailable", async () => {
    delete (document as unknown as { startViewTransition?: unknown }).startViewTransition;
    twoBoards();
    renderProbe();
    await waitFor(() => expect(screen.getByTestId("current-id")).toHaveTextContent("one"));

    fireEvent.click(screen.getByTestId("select-two"));

    await waitFor(() => expect(screen.getByTestId("current-id")).toHaveTextContent("two"));
    expect(document.documentElement.dataset.boardSwitch).toBeUndefined();
  });
});
