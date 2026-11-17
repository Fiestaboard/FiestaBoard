import { describe, expect, it } from "vitest";

import { upcomingSilenceEnd } from "@/lib/silence-until";

describe("formatting a hub silence window's UTC end on its actual date", () => {
  it.each([
    ["2026-07-15T05:00:00Z", "2026-07-15T13:30:00.000Z", "6:30 AM"],
    ["2026-01-15T06:00:00Z", "2026-01-15T13:30:00.000Z", "5:30 AM"],
    ["2026-07-15T22:00:00Z", "2026-07-16T13:30:00.000Z", "6:30 AM"],
    ["2026-03-08T06:00:00Z", "2026-03-08T13:30:00.000Z", "6:30 AM"],
  ])("uses the occurrence after %s, including DST and midnight", (start, expected, local) => {
    const end = upcomingSilenceEnd("13:30+00:00", new Date(start));
    expect(end?.toISOString()).toBe(expected);
    expect(
      new Intl.DateTimeFormat("en-US", { timeZone: "America/Los_Angeles", hour: "numeric", minute: "2-digit" }).format(
        end!,
      ),
    ).toBe(local);
  });
  it.each([null, "bad", "25:00", "13:99"])("does not invent an end for %s", (clock) => {
    expect(upcomingSilenceEnd(clock, new Date("2026-07-15T05:00:00Z"))).toBeNull();
  });
});
