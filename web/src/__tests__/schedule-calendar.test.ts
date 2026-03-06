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

  it("splits midnight rollover into evening and morning events", () => {
    const schedule = makeSchedule({
      start_time: "23:00",
      end_time: "06:45",
      day_pattern: "all",
    });

    const events = scheduleToCalendarEvents(schedule, WEEK_START, MOCK_PAGES);

    // 7 days × 2 parts (evening + morning) = 14 events
    expect(events).toHaveLength(14);

    const eveningEvents = events.filter((e) => e.resource.splitPart === "evening");
    const morningEvents = events.filter((e) => e.resource.splitPart === "morning");

    expect(eveningEvents).toHaveLength(7);
    expect(morningEvents).toHaveLength(7);

    for (const event of eveningEvents) {
      expect(event.resource.isMidnightSplit).toBe(true);
      expect(event.start.getHours()).toBe(23);
      expect(event.start.getMinutes()).toBe(0);
      // endOfDay returns 23:59:59.999
      expect(event.end.getHours()).toBe(23);
      expect(event.end.getMinutes()).toBe(59);
      expect(event.end.getTime()).toBeGreaterThan(event.start.getTime());
    }

    for (const event of morningEvents) {
      expect(event.resource.isMidnightSplit).toBe(true);
      expect(event.start.getHours()).toBe(0);
      expect(event.start.getMinutes()).toBe(0);
      expect(event.end.getHours()).toBe(6);
      expect(event.end.getMinutes()).toBe(45);
      expect(event.end.getTime()).toBeGreaterThan(event.start.getTime());
    }
  });

  it("splits midnight rollover for custom days", () => {
    const schedule = makeSchedule({
      start_time: "22:00",
      end_time: "02:00",
      day_pattern: "custom",
      custom_days: ["monday"],
    });

    const events = scheduleToCalendarEvents(schedule, WEEK_START, MOCK_PAGES);

    // 1 day × 2 parts = 2 events
    expect(events).toHaveLength(2);

    const evening = events.find((e) => e.resource.splitPart === "evening")!;
    const morning = events.find((e) => e.resource.splitPart === "morning")!;

    expect(evening.start.getHours()).toBe(22);
    expect(evening.end.getHours()).toBe(23); // endOfDay → 23:59:59.999
    expect(morning.start.getHours()).toBe(0);
    expect(morning.end.getHours()).toBe(2);
  });

  it("splits same start/end time as midnight rollover", () => {
    // Edge case: start == end triggers rollover, consistent with backend behavior
    const schedule = makeSchedule({
      start_time: "12:00",
      end_time: "12:00",
      day_pattern: "weekdays",
    });

    const events = scheduleToCalendarEvents(schedule, WEEK_START, MOCK_PAGES);

    // 5 weekdays × 2 parts = 10 events
    expect(events).toHaveLength(10);

    for (const event of events) {
      expect(event.resource.isMidnightSplit).toBe(true);
      expect(event.end.getTime()).toBeGreaterThan(event.start.getTime());
    }
  });

  it("preserves originalSchedule reference on both split parts", () => {
    const schedule = makeSchedule({
      start_time: "23:00",
      end_time: "06:45",
      day_pattern: "custom",
      custom_days: ["wednesday"],
    });

    const events = scheduleToCalendarEvents(schedule, WEEK_START, MOCK_PAGES);
    expect(events).toHaveLength(2);

    // Both parts should reference the same original schedule
    for (const event of events) {
      expect(event.resource.originalSchedule).toBe(schedule);
      expect(event.resource.scheduleId).toBe(schedule.id);
    }
  });

  it("normal same-day events have no split metadata", () => {
    const schedule = makeSchedule({
      start_time: "09:00",
      end_time: "17:00",
      day_pattern: "all",
    });

    const events = scheduleToCalendarEvents(schedule, WEEK_START, MOCK_PAGES);

    for (const event of events) {
      expect(event.resource.isMidnightSplit).toBeUndefined();
      expect(event.resource.splitPart).toBeUndefined();
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

  it("wraps Saturday midnight rollover morning part to Sunday (repeating weekly)", () => {
    const schedule = makeSchedule({
      start_time: "23:00",
      end_time: "06:45",
      day_pattern: "all",
    });

    const events = scheduleToCalendarEvents(schedule, WEEK_START, MOCK_PAGES);
    const morningEvents = events.filter((e) => e.resource.splitPart === "morning");

    // Sunday (weekStart) should have a morning event from Saturday's rollover
    const sundayMorning = morningEvents.find(
      (e) => getDay(e.start) === 0 // Sunday
    );
    expect(sundayMorning).toBeDefined();
    expect(sundayMorning!.start.getHours()).toBe(0);
    expect(sundayMorning!.end.getHours()).toBe(6);
    expect(sundayMorning!.end.getMinutes()).toBe(45);

    // All morning events should fall within the same week (Sun-Sat)
    for (const event of morningEvents) {
      expect(event.start.getTime()).toBeGreaterThanOrEqual(WEEK_START.getTime());
    }
  });

  it("wraps Saturday morning rollover for custom Saturday-only schedule", () => {
    const schedule = makeSchedule({
      start_time: "22:00",
      end_time: "03:00",
      day_pattern: "custom",
      custom_days: ["saturday"],
    });

    const events = scheduleToCalendarEvents(schedule, WEEK_START, MOCK_PAGES);

    // 1 day × 2 parts = 2 events
    expect(events).toHaveLength(2);

    const evening = events.find((e) => e.resource.splitPart === "evening")!;
    const morning = events.find((e) => e.resource.splitPart === "morning")!;

    // Evening is on Saturday
    expect(getDay(evening.start)).toBe(6);
    expect(evening.start.getHours()).toBe(22);

    // Morning wraps to Sunday (weekStart)
    expect(getDay(morning.start)).toBe(0);
    expect(morning.start.getHours()).toBe(0);
    expect(morning.end.getHours()).toBe(3);
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

    // 7 normal events from s1 + 14 split events from s2 (7 evening + 7 morning)
    expect(events).toHaveLength(21);

    const s1Events = events.filter((e) => e.resource.scheduleId === "s1");
    const s2Events = events.filter((e) => e.resource.scheduleId === "s2");

    expect(s1Events).toHaveLength(7);
    expect(s2Events).toHaveLength(14);

    // Normal events should not be marked as split
    for (const event of s1Events) {
      expect(event.resource.isMidnightSplit).toBeUndefined();
    }

    // Split events should all have end after start
    for (const event of s2Events) {
      expect(event.resource.isMidnightSplit).toBe(true);
      expect(event.end.getTime()).toBeGreaterThan(event.start.getTime());
    }
  });
});
