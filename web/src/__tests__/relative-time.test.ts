import { describe, expect, it } from "vitest";

import { formatRelativeTime } from "@/lib/relative-time";

const NOW = Date.parse("2026-09-19T12:00:00Z");

describe("formatRelativeTime", () => {
  it("says 'now' inside a minute", () => {
    expect(formatRelativeTime("2026-09-19T11:59:40Z", "en", NOW)).toBe("now");
  });

  it("picks the largest whole unit", () => {
    expect(formatRelativeTime("2026-09-19T11:55:00Z", "en", NOW)).toBe("5 minutes ago");
    expect(formatRelativeTime("2026-09-19T09:00:00Z", "en", NOW)).toBe("3 hours ago");
    expect(formatRelativeTime("2026-09-16T12:00:00Z", "en", NOW)).toBe("3 days ago");
    expect(formatRelativeTime("2026-08-19T12:00:00Z", "en", NOW)).toBe("last month");
  });

  it("speaks the given locale", () => {
    expect(formatRelativeTime("2026-09-19T11:55:00Z", "de", NOW)).toBe("vor 5 Minuten");
  });

  it("falls back to the raw value for an unparseable timestamp", () => {
    expect(formatRelativeTime("not a date", "en", NOW)).toBe("not a date");
  });
});
