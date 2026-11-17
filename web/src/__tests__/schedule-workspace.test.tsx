import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import { ScheduleWorkspace } from "@/components/schedule/schedule-workspace";
import type { Page, ScheduleEntry } from "@/lib/api";

import { server } from "./mocks/server";
const pages = [{ id: "page-1", name: "Morning page", device_type: "flagship" }] as Page[];
const entry = {
  id: "entry-1",
  page_id: "page-1",
  start_time: "09:00",
  end_time: "12:00",
  enabled: true,
  day_pattern: "all",
} as ScheduleEntry;
function setup(schedules = [entry], extra = {}) {
  const props = {
    view: "calendar" as const,
    schedules,
    pages,
    collections: [],
    boardId: "display-2",
    boardName: "Second display",
    timezone: "UTC",
    defaultPageId: "page-1",
    onEdit: vi.fn(),
    onDelete: vi.fn(),
    onToggleEnabled: vi.fn(),
    onCreate: vi.fn(),
    onSilenceClick: vi.fn(),
    ...extra,
  };
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <ScheduleWorkspace {...props} />
    </QueryClientProvider>,
  );
  return props;
}
describe("Schedule workspace", () => {
  it.each(["day", "list"])("offers default preview and entry creation in an empty %s view", (view) => {
    const props = setup([], { view });
    expect(screen.getByRole("region", { name: "No schedules created yet" })).toBeInTheDocument();
    expect(screen.getByText("Gaps use Morning page.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Add Schedule" }));
    expect(props.onCreate).toHaveBeenCalled();
  });
  it("opens lookup on request and restores the selected inspector when closed", () => {
    setup();
    expect(screen.queryByLabelText("Instant")).not.toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("button", { name: /Morning page/ })[0]);
    const lookup = screen.getByRole("button", { name: "Which page at…" });
    fireEvent.click(lookup);
    expect(lookup).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByLabelText("Instant")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit entry" })).not.toBeInTheDocument();
    fireEvent.click(lookup);
    expect(lookup).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByLabelText("Instant")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit entry" })).toBeInTheDocument();
  });
  it("explains the actual default page in an empty schedule and opens entry creation", () => {
    const props = setup([]);
    expect(screen.getByText("No schedules created yet")).toBeInTheDocument();
    expect(screen.getByText("Gaps use Morning page.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Add Schedule" }));
    expect(props.onCreate).toHaveBeenCalled();
  });
  it("selects a calendar occurrence and edits the original stored entry", () => {
    const props = setup();
    fireEvent.click(screen.getAllByRole("button", { name: /Morning page/ })[0]);
    fireEvent.click(screen.getByRole("button", { name: "Edit entry" }));
    expect(props.onEdit).toHaveBeenCalledWith(entry);
  });
  it("preserves delete and enabled actions on the selected entry", () => {
    const props = setup();
    fireEvent.click(screen.getAllByRole("button", { name: /Morning page/ })[0]);
    fireEvent.click(screen.getByRole("switch"));
    expect(props.onToggleEnabled).toHaveBeenCalledWith(entry, false);
    fireEvent.click(screen.getByRole("button", { name: "Delete entry…" }));
    expect(props.onDelete).toHaveBeenCalledWith("entry-1");
  });
  it("offers the existing move/resize calendar without losing the kit week view", () => {
    setup([entry], { legacyCalendar: <p>Existing drag calendar</p> });
    fireEvent.click(screen.getByRole("button", { name: "Move or resize entries" }));
    expect(screen.getByText("Existing drag calendar")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Week calendar" }));
    expect(screen.queryByText("Existing drag calendar")).not.toBeInTheDocument();
  });
  it("gets current playback from the selected display instead of guessing a winning overlapping entry", async () => {
    server.use(
      http.get("/api/schedules/active/page", () =>
        HttpResponse.json({ page_id: "page-1", source: "schedule", temporary_override: { active: false } }),
      ),
    );
    setup([{ ...entry, start_time: "00:00", end_time: "23:59" }], { view: "day" });
    expect(await screen.findByRole("button", { current: "time" })).toHaveTextContent("Now");
  });
});

it("navigates weeks and day chips without rewriting the stored recurrence", () => {
  setup([entry], { view: "day" });
  const today = within(screen.getByRole("radiogroup", { name: "Choose a day" })).getByRole("radio", {
    checked: true,
  }).textContent;
  fireEvent.click(screen.getByRole("button", { name: "Next week" }));
  expect(
    within(screen.getByRole("radiogroup", { name: "Choose a day" })).getByRole("radio", { checked: true }).textContent,
  ).not.toBe(today);
  fireEvent.click(screen.getByRole("button", { name: "Previous week" }));
  expect(
    within(screen.getByRole("radiogroup", { name: "Choose a day" })).getByRole("radio", { checked: true }).textContent,
  ).toBe(today);
  fireEvent.click(
    within(screen.getByRole("radiogroup", { name: "Choose a day" }))
      .getAllByRole("radio")
      .find((radio) => radio.getAttribute("aria-checked") === "false")!,
  );
  expect(
    within(screen.getByRole("radiogroup", { name: "Choose a day" })).getByRole("radio", { checked: true }).textContent,
  ).not.toBe(today);
  fireEvent.click(screen.getByRole("button", { name: "Today" }));
  expect(
    within(screen.getByRole("radiogroup", { name: "Choose a day" })).getByRole("radio", { checked: true }).textContent,
  ).toBe(today);
});
it("shows hub conflict words and retains the quiet-hours action and default gaps", () => {
  const props = setup([entry], {
    gaps: [{ start_time: "13:00", end_time: "17:00", days: ["monday"] }],
    overlaps: [
      { schedule1_id: "entry-1", schedule2_id: "other", conflict_description: "Hub says the later start wins" },
    ],
    silenceSchedule: {
      enabled: true,
      startTimeLocal: "22:00",
      endTimeLocal: "07:00",
      mode: "freeze",
      indicatorText: null,
      pageId: null,
    },
  });
  expect(screen.getByRole("button", { name: /Gap · Morning page/ })).toBeInTheDocument();
  fireEvent.click(screen.getAllByRole("button", { name: /Silence Schedule/ })[0]);
  expect(props.onSilenceClick).toHaveBeenCalled();
  fireEvent.click(
    screen.getAllByRole("button", { name: /Morning page/ }).find((button) => !button.textContent?.includes("Gap"))!,
  );
  expect(screen.getByText("Hub says the later start wins")).toBeInTheDocument();
});
it("reports unavailable solar data while keeping the saved fallback entry editable", async () => {
  server.use(
    http.get("/api/settings/location/sun-times-week", () =>
      HttpResponse.json({ location_configured: false, dates: {} }),
    ),
  );
  setup([{ ...entry, start_type: "sunrise" }]);
  expect(
    await screen.findByText("Sunrise and sunset times are unavailable. Entries use their saved fallback times."),
  ).toBeInTheDocument();
});
