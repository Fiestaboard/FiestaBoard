/** BB-FP-19 (Figma 184:159319): the editor's timeline week runs Monday to Sunday. */
import { describe, expect, it } from "vitest";

import { nextShowing, timelineDayIndex, timelineWeekStart } from "@/components/ide/ide-timeline";
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

describe("overnight entries in a Monday-first week (BB-FP-19)", () => {
  it("draws Saturday night's after-midnight part on Sunday, not Monday", () => {
    const monday = timelineWeekStart(new Date(2025, 0, 8));
    const events = scheduleToCalendarEvents(
      {
        id: "s",
        page_id: "p",
        start_time: "22:00",
        end_time: "02:00",
        day_pattern: "custom",
        custom_days: ["saturday"],
        enabled: true,
        created_at: "2025-01-01T00:00:00Z",
      },
      monday,
      [],
    );
    const morning = events.find((event) => event.start.getHours() === 0);
    expect(morning && timelineDayIndex(morning.start)).toBe(6);
  });

  it("wraps the last day's after-midnight part to the week's first day", () => {
    const monday = timelineWeekStart(new Date(2025, 0, 8));
    const events = scheduleToCalendarEvents(
      {
        id: "s",
        page_id: "p",
        start_time: "22:00",
        end_time: "02:00",
        day_pattern: "custom",
        custom_days: ["sunday"],
        enabled: true,
        created_at: "2025-01-01T00:00:00Z",
      },
      monday,
      [],
    );
    const morning = events.find((event) => event.start.getHours() === 0);
    expect(morning && timelineDayIndex(morning.start)).toBe(0);
  });
});

describe("nextShowing (FP-2 status line)", () => {
  const overnight = {
    schedule: {
      id: "night",
      page_id: "p",
      board_id: "b",
      start_time: "22:00",
      end_time: "06:00",
      day_pattern: "all",
      enabled: true,
      created_at: "",
    },
    boardId: "b",
    boardName: "Kitchen",
    collection: null,
    now: true,
  } as Parameters<typeof nextShowing>[0][number];

  it("does not take the 00:00 half of an overnight window for a start", () => {
    // Friday 27 Nov 2026, 23:00, inside Friday's 22:00–06:00 window.
    const next = nextShowing([overnight], [], [], new Date(2026, 10, 27, 23, 0));
    expect(next?.at).toEqual(new Date(2026, 10, 28, 22, 0));
  });
});
