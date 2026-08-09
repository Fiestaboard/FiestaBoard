import { describe, expect, it } from "vitest";

import type { ScheduleEntry } from "@/lib/api";
import { sortSchedulesByStart } from "@/lib/schedule-sort";

// Pinned reference point so "next occurrence" ordering is deterministic.
const TODAY = new Date(2026, 7, 8); // Sat Aug 8 2026

function makeSchedule(overrides: Partial<ScheduleEntry> & { id: string }): ScheduleEntry {
  return {
    page_id: "page1",
    start_time: "09:00",
    end_time: "17:00",
    day_pattern: "all",
    enabled: true,
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function annual(id: string, annual_date: string, extra: Partial<ScheduleEntry> = {}): ScheduleEntry {
  return makeSchedule({ id, recurrence_type: "annual_date", annual_date, ...extra });
}

function oneOff(id: string, one_off_date: string, extra: Partial<ScheduleEntry> = {}): ScheduleEntry {
  return makeSchedule({ id, recurrence_type: "one_off_date", one_off_date, ...extra });
}

const ids = (schedules: ScheduleEntry[]) => schedules.map((s) => s.id);

describe("sortSchedulesByStart", () => {
  it("orders weekly entries by start time rather than creation order", () => {
    const schedules = [
      makeSchedule({ id: "evening", start_time: "18:00" }),
      makeSchedule({ id: "morning", start_time: "06:30" }),
      makeSchedule({ id: "noon", start_time: "12:00" }),
    ];

    expect(ids(sortSchedulesByStart(schedules, TODAY))).toEqual(["morning", "noon", "evening"]);
  });

  it("uses the resolved time for sun-based entries", () => {
    const schedules = [
      makeSchedule({ id: "fixed-seven", start_time: "07:00" }),
      makeSchedule({
        id: "sunrise",
        start_time: "06:00",
        start_type: "sunrise",
        resolved_start_time: "05:12",
      }),
      makeSchedule({
        id: "sunset",
        start_time: "18:00",
        start_type: "sunset",
        resolved_start_time: "20:41",
      }),
    ];

    expect(ids(sortSchedulesByStart(schedules, TODAY))).toEqual(["sunrise", "fixed-seven", "sunset"]);
  });

  it("puts every weekly entry ahead of the dated ones", () => {
    const schedules = [
      oneOff("one-off", "2026-08-10", { start_time: "08:00" }),
      annual("annual", "12-25", { start_time: "08:00" }),
      makeSchedule({ id: "weekly", start_time: "23:00" }),
    ];

    expect(ids(sortSchedulesByStart(schedules, TODAY))).toEqual(["weekly", "one-off", "annual"]);
  });

  it("interleaves annual and one-off entries by next occurrence", () => {
    const schedules = [
      annual("christmas", "12-25"),
      oneOff("next-week", "2026-08-15"),
      annual("halloween", "10-31"),
      oneOff("tomorrow", "2026-08-09"),
    ];

    expect(ids(sortSchedulesByStart(schedules, TODAY))).toEqual(["tomorrow", "next-week", "halloween", "christmas"]);
  });

  it("rolls an annual date that has already passed into next year", () => {
    const schedules = [
      annual("new-year", "01-01"), // already passed in 2026 → Jan 1 2027
      annual("christmas", "12-25"), // still ahead in 2026
    ];

    expect(ids(sortSchedulesByStart(schedules, TODAY))).toEqual(["christmas", "new-year"]);
  });

  it("sorts an in-progress entry as happening today", () => {
    const schedules = [
      oneOff("upcoming", "2026-08-20"),
      oneOff("in-progress", "2026-08-01", { one_off_end_date: "2026-08-12" }),
    ];

    expect(ids(sortSchedulesByStart(schedules, TODAY))).toEqual(["in-progress", "upcoming"]);
  });

  it("treats an annual window spanning the year boundary as active", () => {
    const newYearsEve = new Date(2026, 11, 31); // Dec 31 2026
    const schedules = [annual("upcoming", "01-15"), annual("holidays", "12-30", { annual_end_date: "01-02" })];

    expect(ids(sortSchedulesByStart(schedules, newYearsEve))).toEqual(["holidays", "upcoming"]);
  });

  it("sinks expired one-offs below everything else, most recent first", () => {
    const schedules = [
      oneOff("last-year", "2025-06-01"),
      oneOff("upcoming", "2026-09-01"),
      oneOff("last-month", "2026-07-04"),
      makeSchedule({ id: "weekly" }),
    ];

    expect(ids(sortSchedulesByStart(schedules, TODAY))).toEqual(["weekly", "upcoming", "last-month", "last-year"]);
  });

  it("keeps creation order for entries that start at the same moment", () => {
    const schedules = [
      makeSchedule({ id: "first", start_time: "09:00" }),
      makeSchedule({ id: "second", start_time: "09:00" }),
      makeSchedule({ id: "third", start_time: "09:00" }),
    ];

    expect(ids(sortSchedulesByStart(schedules, TODAY))).toEqual(["first", "second", "third"]);
  });

  it("orders same-day dated entries by start time", () => {
    const schedules = [
      oneOff("evening", "2026-08-09", { start_time: "19:00" }),
      annual("morning", "08-09", { start_time: "07:00" }),
    ];

    expect(ids(sortSchedulesByStart(schedules, TODAY))).toEqual(["morning", "evening"]);
  });

  it("does not mutate the input array", () => {
    const schedules = [
      makeSchedule({ id: "later", start_time: "18:00" }),
      makeSchedule({ id: "earlier", start_time: "06:00" }),
    ];

    sortSchedulesByStart(schedules, TODAY);

    expect(ids(schedules)).toEqual(["later", "earlier"]);
  });
});
