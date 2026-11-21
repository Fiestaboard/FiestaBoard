/** BB-FP-19 (Figma 184:159319): the editor's timeline week runs Monday to Sunday. */
import { describe, expect, it } from "vitest";

import { timelineDayIndex, timelineWeekStart } from "@/components/ide/ide-timeline";
import { scheduleToCalendarEvents } from "@/lib/schedule-calendar";

describe("timeline week (BB-FP-19)", () => {
  it("starts on the Monday of the current week", () => {
    expect(timelineWeekStart(new Date(2026, 10, 22, 15)).getDay()).toBe(1); // a Sunday → Mon 16 Nov
    expect(timelineWeekStart(new Date(2026, 10, 22, 15)).getDate()).toBe(16);
    expect(timelineWeekStart(new Date(2026, 10, 16, 9)).getDate()).toBe(16);
  });

  it("places Monday first and Sunday last", () => {
    expect(timelineDayIndex(new Date(2026, 10, 16))).toBe(0); // Monday
    expect(timelineDayIndex(new Date(2026, 10, 22))).toBe(6); // Sunday
  });
});

describe("calendar events for a Monday-first week (BB-FP-19)", () => {
  it("still includes the week's Sunday", () => {
    const monday = timelineWeekStart(new Date(2025, 0, 8));
    const events = scheduleToCalendarEvents(
      {
        id: "s",
        page_id: "p",
        start_time: "09:00",
        end_time: "10:00",
        day_pattern: "all",
        enabled: true,
        created_at: "2025-01-01T00:00:00Z",
      },
      monday,
      [],
    );
    expect(events).toHaveLength(7);
    expect(events.map((event) => timelineDayIndex(event.start))).toEqual([0, 1, 2, 3, 4, 5, 6]);
  });
});
