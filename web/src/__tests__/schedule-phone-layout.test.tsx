/**
 * BB-C-3 / BB-C-4 / BB-C-5: Schedule on a phone follows 07d Schedule · Day
 * (`322:19169`): title with Add beside it, one Schedule Mode row, the day
 * chips, then the agenda; week and lookup controls come after it, and there
 * is no seven-column Week. The entry sheet's subtitle names display and days.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { ScheduleEditorBridgeProvider } from "@/components/schedule-editor-bridge-context";

import SchedulePage from "../../app/routes/schedule";
import { server } from "./mocks/server";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/components/current-board-context", () => ({
  useCurrentBoard: () => ({
    currentBoardId: "board-1",
    currentBoard: { id: "board-1", name: "Kitchen board", device_type: "flagship", board_color: "black" },
    boards: [{ id: "board-1", name: "Kitchen board", device_type: "flagship", board_color: "black" }],
  }),
}));

const entry = {
  id: "weekday",
  page_id: "p-1",
  board_id: "",
  start_time: "09:00",
  end_time: "12:00",
  day_pattern: "weekdays",
  recurrence_type: "weekly",
  enabled: true,
};
let matchMedia: typeof window.matchMedia;
function viewport(phone: boolean) {
  window.matchMedia = vi.fn((query: string) => ({
    matches: phone && query === "(max-width: 767.98px)",
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
}
function renderPage() {
  server.use(
    http.get("/api/settings/all", () =>
      HttpResponse.json({ general: { timezone: "UTC" }, silence_schedule: { config: { enabled: false } } }),
    ),
    http.get("/api/v1/schedules", () =>
      HttpResponse.json({ schedules: [entry], enabled: true, default_page_id: null }),
    ),
    http.get("/api/v1/pages", () =>
      HttpResponse.json({ pages: [{ id: "p-1", name: "Clock & Date", device_type: "flagship" }] }),
    ),
    http.post("/api/schedules/validate", () => HttpResponse.json({ valid: true, overlaps: [], gaps: [] })),
  );
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter>
        <ScheduleEditorBridgeProvider>
          <SchedulePage />
        </ScheduleEditorBridgeProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
beforeEach(() => {
  // A Tuesday: the phone Day view opens on today, and the weekday entry is
  // only in it Monday to Friday (this failed on weekends).
  vi.useFakeTimers({ toFake: ["Date"], now: new Date("2026-11-17T10:00:00Z") });
  matchMedia = window.matchMedia;
  localStorage.setItem("schedule-view-mode", "calendar");
});
afterEach(() => {
  vi.useRealTimers();
  window.matchMedia = matchMedia;
});

it("puts title, Add and one Schedule Mode row above the day chips and agenda (BB-C-3)", async () => {
  viewport(true);
  renderPage();
  const title = await screen.findByRole("heading", { level: 1, name: "Schedule" });
  const add = screen.getByRole("button", { name: "Add Schedule" });
  expect(title.parentElement).toContainElement(add);
  expect(screen.getByText("Schedule Mode").closest("label")).toHaveTextContent("Schedule Mode · Kitchen board");
  expect(screen.queryByText(/Automate page rotation/)).not.toBeInTheDocument();
  const chips = screen.getByRole("radiogroup", { name: "Choose a day" });
  const lookup = screen.getByRole("button", { name: "Which page at…" });
  // The week and lookup controls follow the agenda instead of preceding the chips.
  expect(chips.compareDocumentPosition(lookup) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(add.compareDocumentPosition(chips) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
});

it("shows the Day agenda, not the seven-column week, on a phone (BB-C-4)", async () => {
  viewport(true);
  renderPage();
  expect(await screen.findByRole("radiogroup", { name: "Choose a day" })).toBeInTheDocument();
  expect(screen.queryByRole("radio", { name: "Week" })).not.toBeInTheDocument();
  expect(screen.queryByRole("grid", { name: "Week calendar" })).not.toBeInTheDocument();
});

it("keeps the view choice and toolbar on wider screens", async () => {
  viewport(false);
  renderPage();
  expect(await screen.findByRole("radio", { name: "Week" })).toHaveAttribute("aria-checked", "true");
  expect(screen.getByText(/Automate page rotation/)).toBeInTheDocument();
});

it("titles the entry sheet with the display and the days it repeats on (BB-C-5)", async () => {
  viewport(true);
  renderPage();
  fireEvent.click((await screen.findAllByRole("button", { name: /Clock & Date/ }))[0]);
  const dialog = await screen.findByRole("dialog");
  expect(dialog).toHaveAccessibleDescription("Kitchen board · Weekdays");
});
