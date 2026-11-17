import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ScheduleEditorBridgeProvider } from "@/components/schedule-editor-bridge-context";

import SchedulePage from "../../app/routes/schedule";
import { server } from "./mocks/server";

const scheduleToasts = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast: scheduleToasts }));

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
  vi.clearAllMocks();
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

it("waits for the hub timezone before initializing the lookup wall clock", async () => {
  let release!: () => void;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  server.use(
    http.get("/api/settings/all", async () => {
      await gate;
      return HttpResponse.json({ general: { timezone: "UTC" }, silence_schedule: { config: { enabled: false } } });
    }),
  );
  renderPage();
  await screen.findByRole("heading", { name: "Schedule" });
  expect(screen.queryByLabelText("Instant")).not.toBeInTheDocument();
  release();
  const instant = await screen.findByLabelText("Instant");
  expect((instant as HTMLInputElement).value.slice(11, 13)).toBe(String(new Date().getUTCHours()).padStart(2, "0"));
});

it("repairs a supported weekly conflict and undoes with the returned revision on the same non-primary board", async () => {
  settings({ enabled: false });
  boardContext.currentBoardId = "board-2";
  boardContext.currentBoard = boardContext.boards[1];
  localStorage.setItem("schedule-view-mode", "calendar");
  const entry = {
    id: "repair-entry",
    page_id: "repair-page",
    board_id: "board-2",
    start_time: "12:00",
    end_time: "15:00",
    day_pattern: "all",
    recurrence_type: "weekly",
    enabled: true,
    revision: "before",
    edit_protocol: "schedule-revision-v1",
  };
  const other = { ...entry, id: "other-entry", page_id: "other-page", start_time: "10:00", end_time: "13:00" };
  const writes: Record<string, unknown>[] = [];
  server.use(
    http.get("/api/v1/schedules", () =>
      HttpResponse.json({ schedules: [entry, other], enabled: true, default_page_id: null }),
    ),
    http.get("/api/v1/pages", () =>
      HttpResponse.json({
        pages: [
          { id: "repair-page", name: "Repair target", device_type: "flagship" },
          { id: "other-page", name: "Other page", device_type: "flagship" },
        ],
      }),
    ),
    http.post("/api/schedules/validate", () =>
      HttpResponse.json({
        overlaps: [{ schedule1_id: entry.id, schedule2_id: other.id, conflict_description: "Weekly overlap" }],
        gaps: [],
      }),
    ),
    http.put("/api/v1/schedules/repair-entry", async ({ request }) => {
      const body = (await request.json()) as Record<string, unknown>;
      writes.push(body);
      return HttpResponse.json({ ...entry, ...body, revision: "after", warnings: [] });
    }),
  );
  renderPage();
  fireEvent.click((await screen.findAllByRole("button", { name: /Repair target/ }))[0]);
  fireEvent.click(await screen.findByRole("button", { name: "Start at 1:00 PM instead" }));
  await waitFor(() =>
    expect(writes[0]).toMatchObject({ board_id: "board-2", start_time: "13:00", expected_revision: "before" }),
  );
  const savedToast = scheduleToasts.success.mock.calls.find((call) => call[0] === "Entry start updated");
  expect(savedToast).toBeDefined();
  await savedToast![1].action.onClick();
  await waitFor(() =>
    expect(writes[1]).toMatchObject({ board_id: "board-2", start_time: "12:00", expected_revision: "after" }),
  );
});
