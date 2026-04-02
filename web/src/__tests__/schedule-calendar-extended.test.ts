import { describe, it, expect } from "vitest";
import {
  scheduleToCalendarEvents,
  schedulesToCalendarEvents,
  getCurrentWeekStart,
  formatWeekRange,
  formatDayPattern,
  getPageColor,
  getPageColorLight,
  isEventOnDay,
  extractTimeFromDate,
  getDayNameFromDate,
  type CalendarEvent,
} from "@/lib/schedule-calendar";
import type { ScheduleEntry, Page } from "@/lib/api";
import { startOfWeek, addDays, getDay } from "date-fns";

const mockPages: Page[] = [
  {
    id: "page-1",
    name: "Weather",
    type: "single",
    device_type: "flagship",
    display_type: "weather",
    duration_seconds: 300,
    created_at: "2024-01-01T00:00:00Z",
  },
  {
    id: "page-2",
    name: "Dashboard",
    type: "template",
    device_type: "flagship",
    duration_seconds: 300,
    created_at: "2024-01-01T00:00:00Z",
  },
];

function makeSchedule(overrides: Partial<ScheduleEntry> = {}): ScheduleEntry {
  return {
    id: "sched-1",
    page_id: "page-1",
    start_time: "09:00",
    end_time: "17:00",
    day_pattern: "all",
    enabled: true,
    created_at: "2024-01-01T00:00:00Z",
    ...overrides,
  };
}

// Use a fixed week start (Sunday Jan 5 2025)
const weekStart = new Date(2025, 0, 5);

describe("schedule-calendar extended", () => {
  describe("scheduleToCalendarEvents", () => {
    it("creates 7 events for 'all' day pattern", () => {
      const schedule = makeSchedule({ day_pattern: "all" });
      const events = scheduleToCalendarEvents(schedule, weekStart, mockPages);
      expect(events).toHaveLength(7);
    });

    it("creates 5 events for 'weekdays' pattern", () => {
      const schedule = makeSchedule({ day_pattern: "weekdays" });
      const events = scheduleToCalendarEvents(schedule, weekStart, mockPages);
      expect(events).toHaveLength(5);
      events.forEach((e) => {
        const dow = getDay(e.start);
        expect(dow).toBeGreaterThanOrEqual(1);
        expect(dow).toBeLessThanOrEqual(5);
      });
    });

    it("creates 2 events for 'weekends' pattern", () => {
      const schedule = makeSchedule({ day_pattern: "weekends" });
      const events = scheduleToCalendarEvents(schedule, weekStart, mockPages);
      expect(events).toHaveLength(2);
      events.forEach((e) => {
        const dow = getDay(e.start);
        expect([0, 6]).toContain(dow);
      });
    });

    it("creates events for 'custom' days", () => {
      const schedule = makeSchedule({
        day_pattern: "custom",
        custom_days: ["monday", "wednesday", "friday"],
      });
      const events = scheduleToCalendarEvents(schedule, weekStart, mockPages);
      expect(events).toHaveLength(3);
    });

    it("handles custom days with no days gracefully", () => {
      const schedule = makeSchedule({
        day_pattern: "custom",
        custom_days: [],
      });
      const events = scheduleToCalendarEvents(schedule, weekStart, mockPages);
      expect(events).toHaveLength(0);
    });

    it("uses page name as event title", () => {
      const schedule = makeSchedule({ day_pattern: "weekends" });
      const events = scheduleToCalendarEvents(schedule, weekStart, mockPages);
      expect(events[0].title).toBe("Weather");
    });

    it("falls back to page_id when page not found", () => {
      const schedule = makeSchedule({ page_id: "unknown-page", day_pattern: "weekends" });
      const events = scheduleToCalendarEvents(schedule, weekStart, mockPages);
      expect(events[0].title).toBe("unknown-page");
    });

    it("sets correct start and end times", () => {
      const schedule = makeSchedule({
        start_time: "14:30",
        end_time: "18:45",
        day_pattern: "weekends",
      });
      const events = scheduleToCalendarEvents(schedule, weekStart, mockPages);
      const event = events[0];
      expect(event.start.getHours()).toBe(14);
      expect(event.start.getMinutes()).toBe(30);
      expect(event.end.getHours()).toBe(18);
      expect(event.end.getMinutes()).toBe(45);
    });

    it("populates resource fields correctly", () => {
      const schedule = makeSchedule({ day_pattern: "weekends" });
      const events = scheduleToCalendarEvents(schedule, weekStart, mockPages);
      const event = events[0];
      expect(event.resource.scheduleId).toBe("sched-1");
      expect(event.resource.pageId).toBe("page-1");
      expect(event.resource.pageName).toBe("Weather");
      expect(event.resource.enabled).toBe(true);
      expect(event.resource.dayPattern).toBe("weekends");
      expect(event.resource.originalSchedule).toBe(schedule);
    });

    it("handles midnight rollover by splitting into two events per day", () => {
      const schedule = makeSchedule({
        start_time: "22:00",
        end_time: "06:00",
        day_pattern: "weekends",
      });
      const events = scheduleToCalendarEvents(schedule, weekStart, mockPages);
      // 2 days × 2 splits = 4 events
      expect(events).toHaveLength(4);

      const eveningEvents = events.filter((e) => e.resource.splitPart === "evening");
      const morningEvents = events.filter((e) => e.resource.splitPart === "morning");
      expect(eveningEvents).toHaveLength(2);
      expect(morningEvents).toHaveLength(2);

      eveningEvents.forEach((e) => {
        expect(e.resource.isMidnightSplit).toBe(true);
        expect(e.start.getHours()).toBe(22);
        expect(e.end.getHours()).toBe(23); // endOfDay → 23:59:59.999
      });

      morningEvents.forEach((e) => {
        expect(e.resource.isMidnightSplit).toBe(true);
        expect(e.end.getHours()).toBe(6);
      });
    });

    it("defaults to all days for unknown day_pattern", () => {
      const schedule = makeSchedule({ day_pattern: "unknown" as any });
      const events = scheduleToCalendarEvents(schedule, weekStart, mockPages);
      expect(events).toHaveLength(7);
    });
  });

  describe("schedulesToCalendarEvents", () => {
    it("combines events from multiple schedules", () => {
      const schedules = [
        makeSchedule({ id: "s1", day_pattern: "weekdays" }),
        makeSchedule({ id: "s2", page_id: "page-2", day_pattern: "weekends" }),
      ];
      const events = schedulesToCalendarEvents(schedules, weekStart, mockPages);
      expect(events).toHaveLength(7); // 5 weekdays + 2 weekends
    });

    it("returns empty array for no schedules", () => {
      const events = schedulesToCalendarEvents([], weekStart, mockPages);
      expect(events).toHaveLength(0);
    });
  });

  describe("getCurrentWeekStart", () => {
    it("returns a Sunday", () => {
      const ws = getCurrentWeekStart();
      expect(getDay(ws)).toBe(0);
    });
  });

  describe("formatWeekRange", () => {
    it("formats same-month range", () => {
      const ws = new Date(2025, 0, 5); // Jan 5 2025 (Sunday)
      const result = formatWeekRange(ws);
      expect(result).toContain("January");
      expect(result).toContain("2025");
      expect(result).toContain("5");
      expect(result).toContain("11");
    });

    it("formats cross-month range", () => {
      const ws = new Date(2025, 0, 26); // Jan 26 2025 (Sunday)
      const result = formatWeekRange(ws);
      expect(result).toContain("January");
      expect(result).toContain("February");
      expect(result).toContain("2025");
    });
  });

  describe("formatDayPattern", () => {
    it("returns 'Every day' for all", () => {
      expect(formatDayPattern(makeSchedule({ day_pattern: "all" }))).toBe("Every day");
    });

    it("returns 'Weekdays' for weekdays", () => {
      expect(formatDayPattern(makeSchedule({ day_pattern: "weekdays" }))).toBe("Weekdays");
    });

    it("returns 'Weekends' for weekends", () => {
      expect(formatDayPattern(makeSchedule({ day_pattern: "weekends" }))).toBe("Weekends");
    });

    it("returns formatted custom days", () => {
      const schedule = makeSchedule({
        day_pattern: "custom",
        custom_days: ["monday", "wednesday"],
      });
      expect(formatDayPattern(schedule)).toBe("Mon, Wed");
    });

    it("returns 'No days selected' for empty custom days", () => {
      const schedule = makeSchedule({ day_pattern: "custom", custom_days: [] });
      expect(formatDayPattern(schedule)).toBe("No days selected");
    });

    it("returns 'No days selected' for undefined custom days", () => {
      const schedule = makeSchedule({ day_pattern: "custom" });
      delete (schedule as any).custom_days;
      expect(formatDayPattern(schedule)).toBe("No days selected");
    });

    it("returns empty string for unknown pattern", () => {
      expect(formatDayPattern(makeSchedule({ day_pattern: "unknown" as any }))).toBe("");
    });
  });

  describe("getPageColor", () => {
    it("returns a CSS variable reference", () => {
      const color = getPageColor("page-1");
      expect(color).toMatch(/^var\(--schedule-color-\d\)$/);
    });

    it("returns consistent colors for the same ID", () => {
      expect(getPageColor("page-1")).toBe(getPageColor("page-1"));
    });

    it("returns different colors for different IDs (most of the time)", () => {
      const colors = new Set([
        getPageColor("a"), getPageColor("b"), getPageColor("c"),
        getPageColor("d"), getPageColor("e"), getPageColor("f"),
      ]);
      expect(colors.size).toBeGreaterThan(1);
    });
  });

  describe("getPageColorLight", () => {
    it("returns a CSS variable reference for background", () => {
      const color = getPageColorLight("page-1");
      expect(color).toMatch(/^var\(--schedule-bg-\d\)$/);
    });

    it("returns consistent values", () => {
      expect(getPageColorLight("page-1")).toBe(getPageColorLight("page-1"));
    });
  });

  describe("isEventOnDay", () => {
    it("returns true when event is on the given date", () => {
      const event: CalendarEvent = {
        id: "e1",
        title: "Test",
        start: new Date(2025, 0, 6, 9, 0),
        end: new Date(2025, 0, 6, 17, 0),
        resource: {
          scheduleId: "s1",
          pageId: "p1",
          pageName: "Test",
          enabled: true,
          dayPattern: "all",
          originalSchedule: makeSchedule(),
        },
      };
      expect(isEventOnDay(event, new Date(2025, 0, 6))).toBe(true);
    });

    it("returns false when event is on a different date", () => {
      const event: CalendarEvent = {
        id: "e1",
        title: "Test",
        start: new Date(2025, 0, 6, 9, 0),
        end: new Date(2025, 0, 6, 17, 0),
        resource: {
          scheduleId: "s1",
          pageId: "p1",
          pageName: "Test",
          enabled: true,
          dayPattern: "all",
          originalSchedule: makeSchedule(),
        },
      };
      expect(isEventOnDay(event, new Date(2025, 0, 7))).toBe(false);
    });
  });

  describe("extractTimeFromDate", () => {
    it("extracts exact time with 1-minute precision", () => {
      expect(extractTimeFromDate(new Date(2025, 0, 1, 14, 0))).toBe("14:00");
      expect(extractTimeFromDate(new Date(2025, 0, 1, 14, 7))).toBe("14:07");
      expect(extractTimeFromDate(new Date(2025, 0, 1, 14, 15))).toBe("14:15");
      expect(extractTimeFromDate(new Date(2025, 0, 1, 14, 29))).toBe("14:29");
      expect(extractTimeFromDate(new Date(2025, 0, 1, 14, 30))).toBe("14:30");
      expect(extractTimeFromDate(new Date(2025, 0, 1, 14, 44))).toBe("14:44");
      expect(extractTimeFromDate(new Date(2025, 0, 1, 14, 45))).toBe("14:45");
      expect(extractTimeFromDate(new Date(2025, 0, 1, 14, 59))).toBe("14:59");
    });

    it("pads single-digit hours", () => {
      expect(extractTimeFromDate(new Date(2025, 0, 1, 9, 0))).toBe("09:00");
      expect(extractTimeFromDate(new Date(2025, 0, 1, 0, 0))).toBe("00:00");
    });
  });

  describe("getDayNameFromDate", () => {
    it("returns correct day names", () => {
      // Jan 5 2025 is a Sunday
      expect(getDayNameFromDate(new Date(2025, 0, 5))).toBe("sunday");
      expect(getDayNameFromDate(new Date(2025, 0, 6))).toBe("monday");
      expect(getDayNameFromDate(new Date(2025, 0, 7))).toBe("tuesday");
      expect(getDayNameFromDate(new Date(2025, 0, 8))).toBe("wednesday");
      expect(getDayNameFromDate(new Date(2025, 0, 9))).toBe("thursday");
      expect(getDayNameFromDate(new Date(2025, 0, 10))).toBe("friday");
      expect(getDayNameFromDate(new Date(2025, 0, 11))).toBe("saturday");
    });
  });
});
