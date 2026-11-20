import { describe, expect, it } from "vitest";

import type { Overlap, ScheduleEntry } from "@/lib/api";
import { weeklyConflictFix } from "@/lib/schedule-conflict-repair";
import { describeOverlap, orderScheduleDays } from "@/lib/schedule-overlap";

const clock = {
  id: "clock",
  page_id: "p-clock",
  start_time: "09:00",
  end_time: "12:00",
  enabled: true,
} as ScheduleEntry;
const blank = {
  id: "blank",
  page_id: "p-blank",
  start_time: "10:00",
  end_time: "11:00",
  enabled: true,
} as ScheduleEntry;
const overlap: Overlap = {
  schedule1_id: "clock",
  schedule2_id: "blank",
  conflict_description: "Schedules overlap on monday, …",
  days: ["friday", "monday", "thursday", "tuesday", "wednesday"],
  start_time: "10:00",
  end_time: "11:00",
  winner_id: "blank",
};
const names: Record<string, string> = { "p-clock": "Clock & Date", "p-blank": "Blank" };
const t = (key: string, values: Record<string, string> = {}) =>
  ({
    conflictWith: `Overlaps ${values.name} (${values.days}, ${values.start} – ${values.end}).`,
    conflictBetween: `${values.first} and ${values.second} overlap (${values.days}, ${values.start} – ${values.end}).`,
    conflictShows: `${values.name} shows then.`,
  })[key] ?? key;
const labels = {
  everyDay: "Every day",
  weekdays: "Mon–Fri",
  weekends: "Sat–Sun",
  day: (day: string) => day.slice(0, 1).toUpperCase() + day.slice(1, 3),
};
const twelve = (value: string) => {
  const [hour, minute] = value.split(":").map(Number);
  return `${hour % 12 || 12}:${String(minute).padStart(2, "0")} ${hour < 12 ? "AM" : "PM"}`;
};

describe("Overlap text (BB-C-2)", () => {
  it("orders days Monday first, not alphabetically", () =>
    expect(orderScheduleDays(["sunday", "friday", "monday"])).toEqual(["monday", "friday", "sunday"]));

  it("names the other entry, the days, the window in the reader's time format and who shows", () => {
    const text = describeOverlap(overlap, "clock", {
      entries: [clock, blank],
      nameOf: (pageId) => names[pageId],
      formatTime: twelve,
      locale: "en",
      labels,
      t,
    });
    expect(text).toBe("Overlaps Blank (Mon–Fri, 10:00 AM – 11:00 AM). Blank shows then.");
  });

  it("lists odd days in week order and uses a 24-hour clock when asked", () => {
    const text = describeOverlap({ ...overlap, days: ["sunday", "monday"], winner_id: "clock" }, "blank", {
      entries: [clock, blank],
      nameOf: (pageId) => names[pageId],
      formatTime: (value) => value,
      locale: "en",
      labels,
      t,
    });
    expect(text).toBe("Overlaps Clock & Date (Mon and Sun, 10:00 – 11:00). Clock & Date shows then.");
  });

  it("describes an unsaved candidate with the draft's page", () => {
    const text = describeOverlap({ ...overlap, schedule2_id: "candidate", winner_id: "candidate" }, "candidate", {
      entries: [clock, { ...blank, id: "candidate" }],
      nameOf: (pageId) => names[pageId],
      formatTime: twelve,
      locale: "en",
      labels,
      t,
    });
    expect(text).toBe("Overlaps Clock & Date (Mon–Fri, 10:00 AM – 11:00 AM). Blank shows then.");
  });

  it("names both entries in a list of every overlap", () => {
    const text = describeOverlap(overlap, null, {
      entries: [clock, blank],
      nameOf: (pageId) => names[pageId],
      formatTime: twelve,
      locale: "en",
      labels,
      t,
    });
    expect(text).toBe("Clock & Date and Blank overlap (Mon–Fri, 10:00 AM – 11:00 AM). Blank shows then.");
  });

  it("falls back to the hub's text when the hub sent no structured fields", () => {
    const legacy = { schedule1_id: "clock", schedule2_id: "blank", conflict_description: "Old text" };
    expect(
      describeOverlap(legacy, null, {
        entries: [clock, blank],
        nameOf: (pageId) => names[pageId],
        formatTime: twelve,
        locale: "en",
        labels,
        t,
      }),
    ).toBe("Old text");
  });
});

describe("One-tap weekly fix (BB-C-1)", () => {
  const overlaps = [overlap];
  it("starts after the other entry when that keeps the entry non-empty", () =>
    expect(weeklyConflictFix(clock, [clock, blank], overlaps)).toEqual({ field: "start_time", time: "11:00" }));
  it("otherwise ends before the other entry starts", () =>
    expect(weeklyConflictFix({ ...clock, start_time: "08:00", end_time: "10:30" }, [clock, blank], overlaps)).toEqual({
      field: "end_time",
      time: "10:00",
    }));
  it("offers nothing when the entry sits inside the other one", () =>
    expect(weeklyConflictFix(blank, [clock, blank], overlaps)).toBeNull());
});
