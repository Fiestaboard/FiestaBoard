import type { ScheduleEntry } from "@/lib/api";

/** "7:44 AM" in the reader's locale for an ISO instant. */
export function formatClock(iso: string, locale: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleTimeString(locale, { hour: "numeric", minute: "2-digit" });
}

/** "7:44 AM" today, else "Mon 7:44 AM" this week, else a short date and time. */
export function formatSavedAt(iso: string, locale: string, now: Date = new Date()): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const sameDay = date.toDateString() === now.toDateString();
  if (sameDay) return formatClock(iso, locale);
  const withinWeek = Math.abs(now.getTime() - date.getTime()) < 6 * 24 * 3600 * 1000;
  return date.toLocaleString(locale, {
    ...(withinWeek ? { weekday: "short" } : { month: "short", day: "numeric" }),
    hour: "numeric",
    minute: "2-digit",
  });
}

/** "7:30 AM" for an "HH:MM" wall time. */
export function formatWallTime(hhmm: string | null | undefined, locale: string): string | null {
  const match = hhmm ? /^(\d{1,2}):(\d{2})/.exec(hhmm) : null;
  if (!match) return null;
  const date = new Date(2000, 0, 1, Number(match[1]), Number(match[2]));
  return date.toLocaleTimeString(locale, { hour: "numeric", minute: "2-digit" });
}

/** "7:30 AM–8:30 AM" (or just the start for an open-ended entry), using resolved sun times. */
export function formatWindow(schedule: ScheduleEntry, locale: string): string {
  const start = formatWallTime(schedule.resolved_start_time || schedule.start_time, locale) ?? schedule.start_time;
  const endRaw = schedule.resolved_end_time !== undefined ? schedule.resolved_end_time : schedule.end_time;
  const end = formatWallTime(endRaw, locale);
  return end ? `${start}–${end}` : start;
}

const WEEKDAY_INDEX: Record<string, number> = {
  sunday: 0,
  monday: 1,
  tuesday: 2,
  wednesday: 3,
  thursday: 4,
  friday: 5,
  saturday: 6,
};

/** "Weekdays", "Sat, Sun", or the entry's date, localized. */
export function formatDays(schedule: ScheduleEntry, t: (key: string) => string, locale: string): string {
  if (schedule.recurrence_type === "one_off_date" && schedule.one_off_date) return schedule.one_off_date;
  if (schedule.recurrence_type === "annual_date" && schedule.annual_date) return schedule.annual_date;
  if (schedule.day_pattern === "all") return t("daysAll");
  if (schedule.day_pattern === "weekdays") return t("daysWeekdays");
  if (schedule.day_pattern === "weekends") return t("daysWeekends");
  const base = new Date(2023, 0, 1); // a Sunday
  return (schedule.custom_days ?? [])
    .map((day) => WEEKDAY_INDEX[day.toLowerCase()])
    .filter((index) => index !== undefined)
    .map((index) => new Date(base.getTime() + index * 86_400_000).toLocaleDateString(locale, { weekday: "short" }))
    .join(", ");
}
