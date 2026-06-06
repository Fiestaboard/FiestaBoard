import { startOfWeek } from "date-fns";
import { describe, expect, it } from "vitest";

import type { Page, ScheduleEntry } from "@/lib/api";
import { scheduleToCalendarEvents } from "@/lib/schedule-calendar";

const MOCK_PAGES: Page[] = [
  {
    id: "page1",
    name: "Birthday Page",
    type: "template",
    device_type: "flagship",
    duration_seconds: 30,
    created_at: "2025-01-01T00:00:00Z",
  },
];

function makeSchedule(overrides: Partial<ScheduleEntry>): ScheduleEntry {
  return {
    id: "sched-1",
    page_id: "page1",
    start_time: "08:00",
    end_time: "16:00",
    day_pattern: "all",
    enabled: true,
    created_at: "2025-01-01T00:00:00Z",
    ...overrides,
  };
}

describe("annual_date recurrence on the calendar", () => {
  it("emits exactly one event on the matching MM-DD in the visible week", () => {
    // Week containing June 15, 2026 (a Monday)
    const weekStart = startOfWeek(new Date(2026, 5, 15), { weekStartsOn: 0 });
    const schedule = makeSchedule({
      recurrence_type: "annual_date",
      annual_date: "06-15",
    });

    const events = scheduleToCalendarEvents(schedule, weekStart, MOCK_PAGES);

    expect(events).toHaveLength(1);
    expect(events[0].start.getMonth()).toBe(5);
    expect(events[0].start.getDate()).toBe(15);
  });

  it("emits no events in a week that doesn't contain the MM-DD", () => {
    const weekStart = startOfWeek(new Date(2026, 0, 5), { weekStartsOn: 0 });
    const schedule = makeSchedule({
      recurrence_type: "annual_date",
      annual_date: "06-15",
    });

    const events = scheduleToCalendarEvents(schedule, weekStart, MOCK_PAGES);

    expect(events).toHaveLength(0);
  });

  it("emits events across an annual_end_date range", () => {
    // Week containing Dec 25, 2026 (Friday)
    const weekStart = startOfWeek(new Date(2026, 11, 25), { weekStartsOn: 0 });
    const schedule = makeSchedule({
      recurrence_type: "annual_date",
      annual_date: "12-24",
      annual_end_date: "12-26",
    });

    const events = scheduleToCalendarEvents(schedule, weekStart, MOCK_PAGES);

    expect(events).toHaveLength(3);
    const days = events.map((e) => e.start.getDate()).sort((a, b) => a - b);
    expect(days).toEqual([24, 25, 26]);
  });

  it("handles year-boundary annual ranges (Dec 30 - Jan 02)", () => {
    // Week of Sun Dec 27 2026 - Sat Jan 02 2027
    const weekStart = startOfWeek(new Date(2026, 11, 30), { weekStartsOn: 0 });
    const schedule = makeSchedule({
      recurrence_type: "annual_date",
      annual_date: "12-30",
      annual_end_date: "01-02",
    });

    const events = scheduleToCalendarEvents(schedule, weekStart, MOCK_PAGES);

    expect(events).toHaveLength(4);
  });
});

describe("one_off_date recurrence on the calendar", () => {
  it("emits an event only on the matching ISO date", () => {
    const weekStart = startOfWeek(new Date(2026, 5, 15), { weekStartsOn: 0 });
    const schedule = makeSchedule({
      recurrence_type: "one_off_date",
      one_off_date: "2026-06-15",
    });

    const events = scheduleToCalendarEvents(schedule, weekStart, MOCK_PAGES);

    expect(events).toHaveLength(1);
    expect(events[0].start.getFullYear()).toBe(2026);
    expect(events[0].start.getMonth()).toBe(5);
    expect(events[0].start.getDate()).toBe(15);
  });

  it("does NOT match on the same MM-DD in a different year", () => {
    // Visible week is in 2025 — one-off is for 2026
    const weekStart = startOfWeek(new Date(2025, 5, 15), { weekStartsOn: 0 });
    const schedule = makeSchedule({
      recurrence_type: "one_off_date",
      one_off_date: "2026-06-15",
    });

    const events = scheduleToCalendarEvents(schedule, weekStart, MOCK_PAGES);

    expect(events).toHaveLength(0);
  });

  it("supports a date range with one_off_end_date", () => {
    const weekStart = startOfWeek(new Date(2026, 5, 15), { weekStartsOn: 0 });
    const schedule = makeSchedule({
      recurrence_type: "one_off_date",
      one_off_date: "2026-06-15",
      one_off_end_date: "2026-06-17",
    });

    const events = scheduleToCalendarEvents(schedule, weekStart, MOCK_PAGES);

    expect(events).toHaveLength(3);
  });
});
