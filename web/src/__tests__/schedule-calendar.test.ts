import { describe, it, expect } from "vitest";
import { startOfWeek, getDay, addDays } from "date-fns";
import {
  scheduleToCalendarEvents,
  schedulesToCalendarEvents,
} from "@/lib/schedule-calendar";
import type { ScheduleEntry, Page } from "@/lib/api";

// Fixed reference date: a known Sunday
const WEEK_START = startOfWeek(new Date(2025, 0, 5), { weekStartsOn: 0 }); // Sun Jan 5 2025

const MOCK_PAGES: Page[] = [
  { id: "page1", name: "Night Page", type: "template", device_type: "flagship", duration_seconds: 30, created_at: "2025-01-01T00:00:00Z" },
  { id: "page2", name: "Day Page", type: "template", device_type: "flagship", duration_seconds: 30, created_at: "2025-01-01T00:00:00Z" },
];

function makeSchedule(overrides: Partial<ScheduleEntry>): ScheduleEntry {
  return {
    id: "sched-1",
    page_id: "page1",
    start_time: "09:00",
    end_time: "17:00",
    day_pattern: "all",
    enabled: true,
    created_at: "2025-01-01T00:00:00Z",
    ...overrides,
  };
}

describe("scheduleToCalendarEvents", () => {
  it("creates events for a normal same-day schedule", () => {
    const schedule = makeSchedule({
      start_time: "09:00",
      end_time: "17:00",
      day_pattern: "all",
    });

    const events = scheduleToCalendarEvents(schedule, WEEK_START, MOCK_PAGES);

    expect(events).toHaveLength(7); // All 7 days of the week
    for (const event of events) {
      expect(event.start.getHours()).toBe(9);
      expect(event.start.getMinutes()).toBe(0);
      expect(event.end.getHours()).toBe(17);
      expect(event.end.getMinutes()).toBe(0);
      // End should be on the same day as start
      expect(event.end.getDate()).toBe(event.start.getDate());
    }
  });

  it("handles midnight rollover (end time before start time)", () => {
    const schedule = makeSchedule({
      start_time: "23:00",
      end_time: "06:45",
      day_pattern: "all",
    });

    const events = scheduleToCalendarEvents(schedule, WEEK_START, MOCK_PAGES);

    expect(events).toHaveLength(7);
    for (const event of events) {
      expect(event.start.getHours()).toBe(23);
      expect(event.start.getMinutes()).toBe(0);
      expect(event.end.getHours()).toBe(6);
      expect(event.end.getMinutes()).toBe(45);
      // End should be on the NEXT day (midnight rollover)
      expect(event.end.getDate()).toBe(
        new Date(
          event.start.getFullYear(),
          event.start.getMonth(),
          event.start.getDate() + 1
        ).getDate()
      );
      // End time must be after start time
      expect(event.end.getTime()).toBeGreaterThan(event.start.getTime());
    }
  });

  it("handles midnight rollover for custom days", () => {
    const schedule = makeSchedule({
      start_time: "22:00",
      end_time: "02:00",
      day_pattern: "custom",
      custom_days: ["monday"],
    });

    const events = scheduleToCalendarEvents(schedule, WEEK_START, MOCK_PAGES);

    expect(events).toHaveLength(1);
    const event = events[0];
    expect(event.start.getHours()).toBe(22);
    expect(event.end.getHours()).toBe(2);
    // End should be next day (Tuesday)
    expect(event.end.getTime()).toBeGreaterThan(event.start.getTime());
  });

  it("treats same start/end time as midnight rollover (full 24h span)", () => {
    // Edge case: start == end triggers rollover, consistent with backend behavior
    // (end_minutes <= start_minutes means midnight rollover)
    const schedule = makeSchedule({
      start_time: "12:00",
      end_time: "12:00",
      day_pattern: "weekdays",
    });

    const events = scheduleToCalendarEvents(schedule, WEEK_START, MOCK_PAGES);

    for (const event of events) {
      expect(event.end.getTime()).toBeGreaterThan(event.start.getTime());
    }
  });

  it("handles end time just before midnight (23:59)", () => {
    const schedule = makeSchedule({
      start_time: "20:00",
      end_time: "23:59",
      day_pattern: "all",
    });

    const events = scheduleToCalendarEvents(schedule, WEEK_START, MOCK_PAGES);

    for (const event of events) {
      expect(event.start.getHours()).toBe(20);
      expect(event.end.getHours()).toBe(23);
      expect(event.end.getMinutes()).toBe(59);
      // Same day, no rollover
      expect(event.end.getDate()).toBe(event.start.getDate());
    }
  });

  it("handles start at midnight and end later in the day", () => {
    const schedule = makeSchedule({
      start_time: "00:00",
      end_time: "06:00",
      day_pattern: "all",
    });

    const events = scheduleToCalendarEvents(schedule, WEEK_START, MOCK_PAGES);

    for (const event of events) {
      expect(event.start.getHours()).toBe(0);
      expect(event.end.getHours()).toBe(6);
      // Same day, no rollover
      expect(event.end.getDate()).toBe(event.start.getDate());
    }
  });
});

describe("schedulesToCalendarEvents", () => {
  it("combines events from multiple schedules", () => {
    const schedules = [
      makeSchedule({ id: "s1", start_time: "09:00", end_time: "17:00" }),
      makeSchedule({
        id: "s2",
        start_time: "23:00",
        end_time: "06:00",
        page_id: "page2",
      }),
    ];

    const events = schedulesToCalendarEvents(schedules, WEEK_START, MOCK_PAGES);

    // 7 events from each schedule
    expect(events).toHaveLength(14);

    const s1Events = events.filter((e) => e.resource.scheduleId === "s1");
    const s2Events = events.filter((e) => e.resource.scheduleId === "s2");

    expect(s1Events).toHaveLength(7);
    expect(s2Events).toHaveLength(7);

    // Verify midnight rollover events have end after start
    for (const event of s2Events) {
      expect(event.end.getTime()).toBeGreaterThan(event.start.getTime());
    }
  });
});
