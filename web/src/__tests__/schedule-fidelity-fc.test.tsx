/**
 * BB-FC-5, BB-FC-6: Schedule against 07d.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

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

/*
 * BB-FC-6: the week view against 07d `322:9978` — Monday-first columns
 * labelled "Mon 9", hour labels "6 AM", one toolbar row (view switcher,
 * bold range, Today), and gaps drawn as the kit's dashed blocks.
 * BB-FC-5: the phone Day view against 07d `322:19169` — five day chips on
 * one tray ("Thu 5"), no date heading, no week arrows.
 */
beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  // Wednesday 18 November 2026, noon UTC.
  vi.setSystemTime(new Date("2026-11-18T12:00:00Z"));
});
afterEach(() => {
  vi.useRealTimers();
});

describe("Schedule week view (BB-FC-6)", () => {
  it("starts the week on Monday and labels days weekday-first", () => {
    setup();
    const labels = [...document.querySelectorAll("[data-slot=week-calendar-day-label]")].map((el) => el.textContent);
    expect(labels[0]).toMatch(/^Mon\b.*16/);
    expect(labels[6]).toMatch(/^Sun\b.*22/);
  });

  it("places a Monday entry in the first column", () => {
    setup([{ ...entry, day_pattern: "custom", custom_days: ["monday"] } as ScheduleEntry]);
    const columns = document.querySelectorAll("[data-slot=week-calendar-day]");
    expect(columns[0].querySelector("[data-slot=week-calendar-entry]")).not.toBeNull();
    expect(columns[6].querySelector("[data-slot=week-calendar-entry]")).toBeNull();
  });

  it("reads hour labels without minutes", () => {
    setup();
    const hours = [...document.querySelectorAll("[data-slot=week-calendar-hour-label]")].map((el) => el.textContent);
    expect(hours).toContain("6 AM");
    expect(hours.some((label) => /:00/.test(label ?? ""))).toBe(false);
  });

  it("puts the view switcher, the bold range and Today on one toolbar row", () => {
    setup([entry], { viewSwitcher: <button type="button">View switcher</button> });
    const toolbar = screen.getByRole("toolbar", { name: "Schedule" });
    expect(within(toolbar).getByRole("button", { name: "View switcher" })).toBeInTheDocument();
    expect(within(toolbar).getByText(/November 16\s*–\s*22, 2026/)).toBeInTheDocument();
    expect(within(toolbar).getByRole("button", { name: "Today" })).toBeInTheDocument();
  });
});

describe("Schedule phone Day view (BB-FC-5)", () => {
  it("shows five day chips centred on the chosen day, weekday-first, with no arrows or date heading", () => {
    setup([entry], { view: "day", compact: true });
    const chips = within(screen.getByRole("radiogroup", { name: "Choose a day" })).getAllByRole("radio");
    expect(chips.map((chip) => chip.textContent)).toEqual(["Mon 16", "Tue 17", "Wed 18", "Thu 19", "Fri 20"]);
    expect(screen.getByRole("radio", { name: "Wed 18" })).toHaveAttribute("aria-checked", "true");
    expect(screen.queryByRole("button", { name: "Previous week" })).toBeNull();
    expect(screen.queryByText(/Wednesday, November 18/i)).toBeNull();
  });

  it("moves the window with the chosen day", () => {
    setup([entry], { view: "day", compact: true });
    fireEvent.click(screen.getByRole("radio", { name: "Fri 20" }));
    const chips = within(screen.getByRole("radiogroup", { name: "Choose a day" })).getAllByRole("radio");
    expect(chips.map((chip) => chip.textContent)).toEqual(["Wed 18", "Thu 19", "Fri 20", "Sat 21", "Sun 22"]);
  });
});
