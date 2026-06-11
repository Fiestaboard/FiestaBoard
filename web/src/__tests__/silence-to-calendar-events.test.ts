import { startOfWeek } from "date-fns";
import { describe, expect, it } from "vitest";

import type { Page } from "@/lib/api";
import { type ResolvedSilenceSchedule, silenceToCalendarEvents } from "@/lib/schedule-calendar";

// Fixed reference date: a known Sunday
const WEEK_START = startOfWeek(new Date(2025, 0, 5), { weekStartsOn: 0 }); // Sun Jan 5 2025

const MOCK_PAGES: Page[] = [
  {
    id: "page1",
    name: "Night Page",
    type: "template",
    device_type: "flagship",
    duration_seconds: 30,
    created_at: "2025-01-01T00:00:00Z",
  },
];

function makeSilence(overrides: Partial<ResolvedSilenceSchedule> = {}): ResolvedSilenceSchedule {
  return {
    enabled: true,
    startTimeLocal: "13:00",
    endTimeLocal: "14:00",
    mode: "indicator",
    indicatorText: "SNOOZING",
    pageId: null,
    ...overrides,
  };
}

describe("silenceToCalendarEvents", () => {
  it("returns no events when silence is null", () => {
    expect(silenceToCalendarEvents(null, WEEK_START, MOCK_PAGES)).toEqual([]);
  });

  it("returns no events when silence is disabled", () => {
    expect(silenceToCalendarEvents(makeSilence({ enabled: false }), WEEK_START, MOCK_PAGES)).toEqual([]);
  });

  it("returns no events when start and end are identical (no real window)", () => {
    const events = silenceToCalendarEvents(
      makeSilence({ startTimeLocal: "10:00", endTimeLocal: "10:00" }),
      WEEK_START,
      MOCK_PAGES,
    );
    expect(events).toEqual([]);
  });

  it("creates one block per day for a same-day window", () => {
    const events = silenceToCalendarEvents(makeSilence(), WEEK_START, MOCK_PAGES);
    expect(events).toHaveLength(7);
    expect(events.every((e) => e.resource.kind === "silence")).toBe(true);
    expect(events.every((e) => e.title === "Silence")).toBe(true);
    expect(events.every((e) => !e.resource.isMidnightSplit)).toBe(true);
  });

  it("splits a midnight-crossing window into evening + morning halves", () => {
    const silence = makeSilence({ startTimeLocal: "22:00", endTimeLocal: "06:00" });
    const events = silenceToCalendarEvents(silence, WEEK_START, MOCK_PAGES);
    // 7 days × 2 halves each = 14 events
    expect(events).toHaveLength(14);
    const evening = events.filter(
      (e) => e.resource.kind === "silence" && e.resource.isMidnightSplit && e.resource.splitPart === "evening",
    );
    const morning = events.filter(
      (e) => e.resource.kind === "silence" && e.resource.isMidnightSplit && e.resource.splitPart === "morning",
    );
    expect(evening).toHaveLength(7);
    expect(morning).toHaveLength(7);
  });

  it("wraps Saturday's morning continuation back to the same week's Sunday", () => {
    const silence = makeSilence({ startTimeLocal: "22:00", endTimeLocal: "06:00" });
    const events = silenceToCalendarEvents(silence, WEEK_START, MOCK_PAGES);
    // The last morning block (Saturday's continuation) should be on the
    // week-start (Sunday Jan 5), not the next Sunday (Jan 12).
    const morningIds = events
      .filter((e) => e.resource.kind === "silence" && e.resource.splitPart === "morning")
      .map((e) => e.id);
    expect(morningIds).toContain("silence-2025-01-05-morning");
  });

  it("resolves the page name when mode is 'page'", () => {
    const silence = makeSilence({ mode: "page", pageId: "page1" });
    const events = silenceToCalendarEvents(silence, WEEK_START, MOCK_PAGES);
    expect(events[0]?.resource.kind).toBe("silence");
    if (events[0]?.resource.kind === "silence") {
      expect(events[0].resource.pageName).toBe("Night Page");
    }
  });

  it("falls back to null pageName when the configured page is missing", () => {
    const silence = makeSilence({ mode: "page", pageId: "missing-id" });
    const events = silenceToCalendarEvents(silence, WEEK_START, MOCK_PAGES);
    if (events[0]?.resource.kind === "silence") {
      expect(events[0].resource.pageName).toBeNull();
    }
  });

  it("leaves pageName null for non-page modes", () => {
    const events = silenceToCalendarEvents(makeSilence({ mode: "freeze" }), WEEK_START, MOCK_PAGES);
    if (events[0]?.resource.kind === "silence") {
      expect(events[0].resource.pageName).toBeNull();
    }
  });
});
