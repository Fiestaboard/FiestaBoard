/**
 * Chronological ordering for schedule entries.
 *
 * The Schedule Entries list is read top-to-bottom to answer "when does what
 * run?", so entries are ordered by when they next matter rather than by when
 * they were created.
 *
 * Two groups:
 *   1. Weekly entries — the everyday baseline, ordered by start time. They have
 *      no start date, so there is nothing to order them against.
 *   2. Dated entries — annual and one-off together, ordered by next occurrence,
 *      so the section reads as a queue of what is coming up. One-offs whose
 *      window has already passed sink to the bottom, most recent first.
 */

import { format } from "date-fns";

import type { ScheduleEntry } from "./api";

const WEEKLY = 0;
const DATED = 1;
const PAST = 2;

interface SortKey {
  /** WEEKLY | DATED | PAST */
  group: number;
  /** YYYY-MM-DD of the next occurrence; "" for weekly entries. */
  date: string;
  /** HH:MM start time. */
  time: string;
}

/**
 * Start time as HH:MM. Sun-based entries use the server-resolved time for today
 * so a sunrise entry sorts where it actually fires, not where its fallback sits.
 */
function startTime(schedule: ScheduleEntry): string {
  return schedule.resolved_start_time || schedule.start_time;
}

/** Next occurrence of an annual MM-DD relative to `today` (YYYY-MM-DD). */
function nextAnnualDate(schedule: ScheduleEntry, today: string): SortKey {
  const start = schedule.annual_date;
  if (!start) return { group: DATED, date: today, time: startTime(schedule) };

  const todayMmdd = today.slice(5);
  const end = schedule.annual_end_date || start;
  // A window that wraps the year boundary (12-30 → 01-02) is active when today
  // is past the start OR before the end; a normal window needs both.
  const active = start <= end ? todayMmdd >= start && todayMmdd <= end : todayMmdd >= start || todayMmdd <= end;
  if (active) return { group: DATED, date: today, time: startTime(schedule) };

  const year = Number(today.slice(0, 4));
  const nextYear = todayMmdd <= start ? year : year + 1;
  return { group: DATED, date: `${nextYear}-${start}`, time: startTime(schedule) };
}

/** Where a one-off date sits relative to `today` (YYYY-MM-DD). */
function oneOffDate(schedule: ScheduleEntry, today: string): SortKey {
  const start = schedule.one_off_date;
  if (!start) return { group: DATED, date: today, time: startTime(schedule) };

  const end = schedule.one_off_end_date || start;
  if (end < today) return { group: PAST, date: start, time: startTime(schedule) };
  // In progress: started before today but still running.
  return { group: DATED, date: start < today ? today : start, time: startTime(schedule) };
}

function sortKey(schedule: ScheduleEntry, today: string): SortKey {
  if (schedule.recurrence_type === "annual_date") return nextAnnualDate(schedule, today);
  if (schedule.recurrence_type === "one_off_date") return oneOffDate(schedule, today);
  return { group: WEEKLY, date: "", time: startTime(schedule) };
}

function compareKeys(a: SortKey, b: SortKey): number {
  if (a.group !== b.group) return a.group - b.group;

  const dateDiff = a.date.localeCompare(b.date);
  // Expired entries read newest-first, so the most recently finished sits
  // closest to the live entries above it.
  if (dateDiff !== 0) return a.group === PAST ? -dateDiff : dateDiff;

  return a.time.localeCompare(b.time);
}

/**
 * Return a new array of schedules ordered by when they next run.
 *
 * `today` defaults to the current local date and exists so callers (and tests)
 * can pin the reference point — the ordering of dated entries shifts as days
 * pass, which is the point.
 *
 * Sorting is stable, so entries that start at the same moment keep their
 * existing (creation) order.
 */
export function sortSchedulesByStart(schedules: ScheduleEntry[], today: Date = new Date()): ScheduleEntry[] {
  const todayIso = format(today, "yyyy-MM-dd");
  return schedules
    .map((schedule) => ({ schedule, key: sortKey(schedule, todayIso) }))
    .sort((a, b) => compareKeys(a.key, b.key))
    .map(({ schedule }) => schedule);
}
