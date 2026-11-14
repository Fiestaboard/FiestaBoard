import { describe, expect, it } from "vitest";

import {
  durationMinutes,
  formatSpan,
  holdEndsAt,
  MAX_OVERRIDE_MINUTES,
  overrideOnScreen,
  scheduleNextChange,
} from "@/components/home/home-status";

const NOW = new Date("2026-11-13T18:16:00Z");

describe("scheduleNextChange", () => {
  it("returns the schedule's next change and the page that follows it", () => {
    const next = scheduleNextChange(
      { next_change_at: "2026-11-13T21:00:00+00:00", next_change_reason: "schedule", next_page_id: "good-night" },
      NOW,
    );
    expect(next).toEqual({ at: new Date("2026-11-13T21:00:00Z"), pageId: "good-night" });
  });

  it("ignores a change that is not a Schedule hand-over", () => {
    for (const reason of ["override_ends", "silence_starts", "silence_ends", "collection"] as const) {
      expect(
        scheduleNextChange({ next_change_at: "2026-11-13T21:00:00Z", next_change_reason: reason, next_page_id: null }, NOW),
      ).toBeNull();
    }
  });

  it("drops a change further away than an override can hold", () => {
    const at = new Date(NOW.getTime() + (MAX_OVERRIDE_MINUTES + 1) * 60_000).toISOString();
    expect(scheduleNextChange({ next_change_at: at, next_change_reason: "schedule", next_page_id: null }, NOW)).toBeNull();
  });

  it("drops a change already in the past, and a missing one", () => {
    expect(
      scheduleNextChange({ next_change_at: "2026-11-13T18:00:00Z", next_change_reason: "schedule", next_page_id: null }, NOW),
    ).toBeNull();
    expect(scheduleNextChange(undefined, NOW)).toBeNull();
    expect(scheduleNextChange({ next_change_at: null, next_change_reason: null, next_page_id: null }, NOW)).toBeNull();
  });
});

describe("durationMinutes", () => {
  const next = { at: new Date("2026-11-13T21:00:00Z"), pageId: null };

  it("maps the fixed chips to their minutes", () => {
    expect(durationMinutes("15m", next, NOW)).toBe(15);
    expect(durationMinutes("1h", next, NOW)).toBe(60);
  });

  it("holds Until the next change for the whole minutes left, rounded up", () => {
    expect(durationMinutes("next-change", next, NOW)).toBe(164);
    expect(durationMinutes("next-change", next, new Date("2026-11-13T18:16:30Z"))).toBe(164);
  });

  it("never asks for less than one minute or more than the cap", () => {
    expect(durationMinutes("next-change", { at: new Date(NOW.getTime() + 5_000), pageId: null }, NOW)).toBe(1);
    expect(
      durationMinutes("next-change", { at: new Date(NOW.getTime() + 10 * 60 * 60_000), pageId: null }, NOW),
    ).toBe(MAX_OVERRIDE_MINUTES);
  });

  it("sends no duration for Until I cancel, or for Until next change with no next change", () => {
    expect(durationMinutes("until-cancel", next, NOW)).toBeUndefined();
    expect(durationMinutes("next-change", null, NOW)).toBeUndefined();
  });
});

describe("holdEndsAt", () => {
  it("is now plus the chip, the next change itself, or never", () => {
    const next = { at: new Date("2026-11-13T21:00:00Z"), pageId: null };
    expect(holdEndsAt("15m", next, NOW)).toEqual(new Date("2026-11-13T18:31:00Z"));
    expect(holdEndsAt("1h", next, NOW)).toEqual(new Date("2026-11-13T19:16:00Z"));
    expect(holdEndsAt("next-change", next, NOW)).toEqual(next.at);
    expect(holdEndsAt("until-cancel", next, NOW)).toBeNull();
    expect(holdEndsAt("next-change", null, NOW)).toBeNull();
  });
});

describe("formatSpan", () => {
  it("prints hours and minutes, rounding a started minute up", () => {
    expect(formatSpan(164 * 60_000)).toBe("2h 44m");
    expect(formatSpan(60 * 60_000)).toBe("1h");
    expect(formatSpan(15 * 60_000)).toBe("15m");
    expect(formatSpan(14 * 60_000 + 1)).toBe("15m");
    expect(formatSpan(0)).toBe("0m");
  });
});

describe("overrideOnScreen", () => {
  it("is true while an override is active and no trigger covers it", () => {
    expect(overrideOnScreen({ overrideActive: true, isPrimary: true, triggerActive: false })).toBe(true);
  });

  it("is false while a plugin trigger shows on the primary display", () => {
    expect(overrideOnScreen({ overrideActive: true, isPrimary: true, triggerActive: true })).toBe(false);
  });

  it("ignores triggers on a non-primary display, which they never drive", () => {
    expect(overrideOnScreen({ overrideActive: true, isPrimary: false, triggerActive: true })).toBe(true);
  });

  it("is false with no override", () => {
    expect(overrideOnScreen({ overrideActive: false, isPrimary: true, triggerActive: false })).toBe(false);
  });
});
