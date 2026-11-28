import { describe, expect, it } from "vitest";

import { editTimeTitle, formatEditTime } from "@/lib/edit-time";

const words = {
  justNow: () => "just now",
  minutesAgo: (count: number) => `${count} min ago`,
  yesterday: (time: string) => `yesterday ${time}`,
};
// 6:15 AM local on Nov 28.
const now = new Date(2026, 10, 28, 6, 15);
const at = (h: number, m: number, day = 28, month = 10, year = 2026) => new Date(year, month, day, h, m);
const fmt = (date: Date | string) => formatEditTime(date, { locale: "en-US", now, words });

describe("formatEditTime (UX-1-3)", () => {
  it("says just now inside a minute, and for a clock slightly ahead", () => {
    expect(fmt(new Date(now.getTime() - 20_000))).toBe("just now");
    expect(fmt(new Date(now.getTime() + 5_000))).toBe("just now");
  });

  it("counts minutes within the hour", () => {
    expect(fmt(at(6, 13))).toBe("2 min ago");
    expect(fmt(at(5, 16))).toBe("59 min ago");
  });

  it("gives the clock time earlier today", () => {
    expect(fmt(at(5, 10))).toBe("5:10 AM");
  });

  it("names yesterday, so yesterday's 7:16 AM never reads as later than now", () => {
    expect(fmt(at(7, 16, 27))).toBe("yesterday 7:16 AM");
  });

  it("gives a short date before yesterday, with the year only when it differs", () => {
    expect(fmt(at(7, 16, 20))).toBe("Nov 20, 7:16 AM");
    expect(fmt(at(7, 16, 20, 10, 2025))).toBe("Nov 20, 2025, 7:16 AM");
  });

  it("accepts an ISO string and returns an unparseable one as is", () => {
    expect(fmt(at(6, 13).toISOString())).toBe("2 min ago");
    expect(fmt("not a date")).toBe("not a date");
  });

  it("titles the time with the full date", () => {
    expect(editTimeTitle(at(7, 16, 27), "en-US")).toBe("Friday, November 27, 2026 at 7:16 AM");
  });
});
