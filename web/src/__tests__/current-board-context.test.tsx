import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";

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
