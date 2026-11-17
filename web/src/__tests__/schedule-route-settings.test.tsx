import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ScheduleEditorBridgeProvider } from "@/components/schedule-editor-bridge-context";

import SchedulePage from "../../app/routes/schedule";
import { server } from "./mocks/server";

const boardContext = vi.hoisted(() => ({
  currentBoardId: "board-1",
  currentBoard: { id: "board-1", name: "First", device_type: "flagship", board_color: "black" },
  boards: [
    { id: "board-1", name: "First", device_type: "flagship", board_color: "black" },
    { id: "board-2", name: "Second", device_type: "flagship", board_color: "black" },
  ],
}));
vi.mock("@/components/current-board-context", () => ({ useCurrentBoard: () => boardContext }));

function settings(overrides: Record<string, unknown> = {}, timezone = "UTC") {
  server.use(
    http.get("/api/settings/all", () =>
      HttpResponse.json({
        general: { timezone, refresh_interval_seconds: 300, output_target: "board" },
        silence_schedule: {
          config: {
            enabled: true,
            start_time: "04:00+00:00",
            end_time: "15:00+00:00",
            mode: "indicator",
            indicator_text: "GLOBAL",
            page_id: null,
            indicator_position: "center",
            show_queued_on_exit: false,
            ...overrides,
          },
        },
      }),
    ),
  );
}
function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const tree = () => (
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ScheduleEditorBridgeProvider>
          <SchedulePage />
        </ScheduleEditorBridgeProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
  const view = render(tree());
  return {
    ...view,
    switchBoard: () => {
      boardContext.currentBoardId = "board-2";
      boardContext.currentBoard = boardContext.boards[1];
      view.rerender(tree());
    },
  };
}

beforeEach(() => {
  localStorage.setItem("schedule-view-mode", "list");
  boardContext.currentBoardId = "board-1";
  boardContext.boards = [
    { id: "board-1", name: "First", device_type: "flagship", board_color: "black" },
    { id: "board-2", name: "Second", device_type: "flagship", board_color: "black" },
  ];
  boardContext.currentBoard = boardContext.boards[0];
});

describe("Schedule settings presentation", () => {
  it("uses board-specific silence times and refreshes them when the board changes", async () => {
    settings({ by_board: { "board-1": { start_time: "06:00+00:00" }, "board-2": { start_time: "08:00+00:00" } } });
    const view = renderPage();
    expect(
      (await screen.findAllByRole("button", { name: "Silence schedule, 6:00 AM – 3:00 PM, opens settings" }))[0],
    ).toBeInTheDocument();
    view.switchBoard();
    expect(
      (await screen.findAllByRole("button", { name: "Silence schedule, 8:00 AM – 3:00 PM, opens settings" }))[0],
    ).toBeInTheDocument();
  });

  it("hides silence when the selected board explicitly disables global quiet hours", async () => {
    settings({ by_board: { "board-2": { enabled: false } } });
    const view = renderPage();
    await screen.findAllByRole("button", { name: /Silence schedule, 4:00 AM/ });
    view.switchBoard();
    await waitFor(() => expect(screen.queryByRole("button", { name: /Silence schedule,/ })).not.toBeInTheDocument());
  });

  it("inherits global silence for a board without overrides", async () => {
    settings();
    renderPage();
    expect(
      (await screen.findAllByRole("button", { name: "Silence schedule, 4:00 AM – 3:00 PM, opens settings" }))[0],
    ).toBeInTheDocument();
  });

  it("honors overrides for a single-board install", async () => {
    boardContext.boards = [boardContext.boards[0]];
    settings({ by_board: { "board-1": { start_time: "09:00+00:00" } } });
    renderPage();
    expect(
      (await screen.findAllByRole("button", { name: "Silence schedule, 9:00 AM – 3:00 PM, opens settings" }))[0],
    ).toBeInTheDocument();
  });

  it("labels the schedule with the configured timezone used to convert silence times", async () => {
    settings({}, "Asia/Tokyo");
    renderPage();
    expect(await screen.findByText("Automate page rotation by time and day · Asia/Tokyo")).toBeInTheDocument();
    expect(
      (await screen.findAllByRole("button", { name: "Silence schedule, 1:00 PM – 12:00 AM, opens settings" }))[0],
    ).toBeInTheDocument();
  });
});

it("uses the shared three-view Schedule selector", async () => {
  settings();
  renderPage();
  expect(await screen.findByRole("radiogroup", { name: "Schedule view" })).toBeInTheDocument();
  expect(screen.getByRole("radio", { name: "Day" })).toBeInTheDocument();
  expect(screen.getByRole("radio", { name: "Week" })).toBeInTheDocument();
  expect(screen.getByRole("radio", { name: "List" })).toBeInTheDocument();
});

it("updates the default view across breakpoints until the reader chooses a view", async () => {
  localStorage.removeItem("schedule-view-mode");
  const original = window.innerWidth;
  Object.defineProperty(window, "innerWidth", { value: 390, configurable: true, writable: true });
  settings();
  renderPage();
  expect(await screen.findByRole("radio", { name: "Day" })).toHaveAttribute("aria-checked", "true");
  fireEvent(window, new Event("resize"));
  Object.defineProperty(window, "innerWidth", { value: 900, configurable: true, writable: true });
  fireEvent(window, new Event("resize"));
  expect(screen.getByRole("radio", { name: "List" })).toHaveAttribute("aria-checked", "true");
  fireEvent.click(screen.getByRole("radio", { name: "Day" }));
  Object.defineProperty(window, "innerWidth", { value: 1280, configurable: true, writable: true });
  fireEvent(window, new Event("resize"));
  expect(screen.getByRole("radio", { name: "Day" })).toHaveAttribute("aria-checked", "true");
  Object.defineProperty(window, "innerWidth", { value: original, configurable: true, writable: true });
});
