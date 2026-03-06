/**
 * Utilities for transforming schedule entries to react-big-calendar events
 */

import {
  startOfWeek,
  endOfWeek,
  eachDayOfInterval,
  endOfDay,
  addDays,
  setHours,
  setMinutes,
  format,
  getDay,
  isSameDay,
} from "date-fns";
import type { ScheduleEntry, Page, Carousel } from "./api";
import { isCarouselId } from "./api";

/**
 * Calendar event type for react-big-calendar
 */
export interface CalendarEvent {
  id: string;
  title: string;
  start: Date;
  end: Date;
  resource: {
    scheduleId: string;
    pageId: string;
    pageName: string;
    enabled: boolean;
    dayPattern: string;
    originalSchedule: ScheduleEntry;
    /** True when the event is one half of a midnight-split schedule */
    isMidnightSplit?: boolean;
    /** Which half of the split: "evening" ends at 00:00, "morning" starts at 00:00 */
    splitPart?: "evening" | "morning";
  };
}

/**
 * Map of day names to day-of-week numbers (0 = Sunday, 1 = Monday, etc.)
 */
const DAY_NAME_TO_NUMBER: Record<string, number> = {
  sunday: 0,
  monday: 1,
  tuesday: 2,
  wednesday: 3,
  thursday: 4,
  friday: 5,
  saturday: 6,
};

/**
 * Get weekday numbers (1-5 for Mon-Fri)
 */
const WEEKDAY_NUMBERS = [1, 2, 3, 4, 5];

/**
 * Get weekend numbers (0 for Sunday, 6 for Saturday)
 */
const WEEKEND_NUMBERS = [0, 6];

/**
 * All day numbers
 */
const ALL_DAY_NUMBERS = [0, 1, 2, 3, 4, 5, 6];

/**
 * Parse time string "HH:MM" to hours and minutes
 */
function parseTime(time: string): { hours: number; minutes: number } {
  const [hours, minutes] = time.split(":").map(Number);
  return { hours, minutes };
}

/**
 * Get applicable day numbers for a schedule entry
 */
function getApplicableDays(schedule: ScheduleEntry): number[] {
  switch (schedule.day_pattern) {
    case "all":
      return ALL_DAY_NUMBERS;
    case "weekdays":
      return WEEKDAY_NUMBERS;
    case "weekends":
      return WEEKEND_NUMBERS;
    case "custom":
      return (schedule.custom_days || [])
        .map((day) => DAY_NAME_TO_NUMBER[day.toLowerCase()])
        .filter((num) => num !== undefined);
    default:
      return ALL_DAY_NUMBERS;
  }
}

/**
 * Get page name by ID from pages array
 */
function getPageName(pageId: string, pages: Page[], carousels?: Carousel[]): string {
  if (isCarouselId(pageId) && carousels) {
    const carousel = carousels.find((c) => c.id === pageId);
    return carousel ? `${carousel.name}` : pageId;
  }
  const page = pages.find((p) => p.id === pageId);
  return page?.name || pageId;
}

/**
 * Transform a single schedule entry into calendar events for a given week
 */
export function scheduleToCalendarEvents(
  schedule: ScheduleEntry,
  weekStart: Date,
  pages: Page[],
  carousels?: Carousel[]
): CalendarEvent[] {
  const events: CalendarEvent[] = [];
  const applicableDays = getApplicableDays(schedule);
  const weekEnd = endOfWeek(weekStart, { weekStartsOn: 0 });
  const daysInWeek = eachDayOfInterval({ start: weekStart, end: weekEnd });

  const startTime = parseTime(schedule.start_time);
  const endTime = parseTime(schedule.end_time);
  const pageName = getPageName(schedule.page_id, pages, carousels);

  const isMidnightRollover =
    endTime.hours < startTime.hours ||
    (endTime.hours === startTime.hours && endTime.minutes <= startTime.minutes);

  for (const day of daysInWeek) {
    const dayOfWeek = getDay(day);

    if (applicableDays.includes(dayOfWeek)) {
      const eventStart = setMinutes(
        setHours(day, startTime.hours),
        startTime.minutes
      );

      if (isMidnightRollover) {
        // Split into two events at the midnight boundary
        const nextDay = addDays(day, 1);

        // For a repeating weekly schedule, Saturday's morning continuation
        // should wrap to this week's Sunday instead of next week's Sunday
        const morningDay = dayOfWeek === 6 ? weekStart : nextDay;

        // Evening part: start_time → end of day (23:59:59.999)
        // Use endOfDay instead of midnight-next-day so react-big-calendar
        // keeps the event within the same day column
        const eveningEnd = endOfDay(day);
        events.push({
          id: `${schedule.id}-${format(day, "yyyy-MM-dd")}-evening`,
          title: pageName,
          start: eventStart,
          end: eveningEnd,
          resource: {
            scheduleId: schedule.id,
            pageId: schedule.page_id,
            pageName,
            enabled: schedule.enabled,
            dayPattern: schedule.day_pattern,
            originalSchedule: schedule,
            isMidnightSplit: true,
            splitPart: "evening",
          },
        });

        // Morning part: midnight → end_time
        const morningStart = setMinutes(setHours(morningDay, 0), 0);
        const morningEnd = setMinutes(
          setHours(morningDay, endTime.hours),
          endTime.minutes
        );
        events.push({
          id: `${schedule.id}-${format(morningDay, "yyyy-MM-dd")}-morning`,
          title: pageName,
          start: morningStart,
          end: morningEnd,
          resource: {
            scheduleId: schedule.id,
            pageId: schedule.page_id,
            pageName,
            enabled: schedule.enabled,
            dayPattern: schedule.day_pattern,
            originalSchedule: schedule,
            isMidnightSplit: true,
            splitPart: "morning",
          },
        });
      } else {
        // Normal same-day event
        const eventEnd = setMinutes(
          setHours(day, endTime.hours),
          endTime.minutes
        );
        events.push({
          id: `${schedule.id}-${format(day, "yyyy-MM-dd")}`,
          title: pageName,
          start: eventStart,
          end: eventEnd,
          resource: {
            scheduleId: schedule.id,
            pageId: schedule.page_id,
            pageName,
            enabled: schedule.enabled,
            dayPattern: schedule.day_pattern,
            originalSchedule: schedule,
          },
        });
      }
    }
  }

  return events;
}

/**
 * Transform all schedule entries into calendar events for a given week
 */
export function schedulesToCalendarEvents(
  schedules: ScheduleEntry[],
  weekStart: Date,
  pages: Page[],
  carousels?: Carousel[]
): CalendarEvent[] {
  const allEvents: CalendarEvent[] = [];

  for (const schedule of schedules) {
    const events = scheduleToCalendarEvents(schedule, weekStart, pages, carousels);
    allEvents.push(...events);
  }

  return allEvents;
}

/**
 * Get the start of the current week (Sunday)
 */
export function getCurrentWeekStart(): Date {
  return startOfWeek(new Date(), { weekStartsOn: 0 });
}

/**
 * Format a date range for the calendar header
 */
export function formatWeekRange(weekStart: Date): string {
  const weekEnd = endOfWeek(weekStart, { weekStartsOn: 0 });
  const startMonth = format(weekStart, "MMMM");
  const endMonth = format(weekEnd, "MMMM");
  const year = format(weekStart, "yyyy");

  if (startMonth === endMonth) {
    return `${startMonth} ${format(weekStart, "d")}-${format(weekEnd, "d")}, ${year}`;
  }

  return `${format(weekStart, "MMMM d")} - ${format(weekEnd, "MMMM d")}, ${year}`;
}

/**
 * Format day pattern for display
 */
export function formatDayPattern(schedule: ScheduleEntry): string {
  switch (schedule.day_pattern) {
    case "all":
      return "Every day";
    case "weekdays":
      return "Weekdays";
    case "weekends":
      return "Weekends";
    case "custom":
      if (!schedule.custom_days || schedule.custom_days.length === 0) {
        return "No days selected";
      }
      return schedule.custom_days
        .map((d) => d.charAt(0).toUpperCase() + d.slice(1, 3))
        .join(", ");
    default:
      return "";
  }
}

/**
 * Number of brand colors available for schedule events.
 * Maps to CSS variables --schedule-color-0 through --schedule-color-5
 * defined in calendar.css with light/dark mode variants.
 */
const SCHEDULE_COLOR_COUNT = 6;

/**
 * Hash a string to a consistent integer
 */
function hashString(str: string): number {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash; // Convert to 32-bit integer
  }
  return Math.abs(hash);
}

/**
 * Generate a consistent brand color for a schedule based on its ID.
 * Returns a CSS variable reference that adapts to light/dark mode.
 * Text/border color - optimized for contrast in each mode.
 */
export function getPageColor(pageId: string): string {
  const index = hashString(pageId) % SCHEDULE_COLOR_COUNT;
  return `var(--schedule-color-${index})`;
}

/**
 * Get a lighter version of the brand color for event backgrounds.
 * Returns a CSS variable reference that adapts to light/dark mode.
 */
export function getPageColorLight(pageId: string): string {
  const index = hashString(pageId) % SCHEDULE_COLOR_COUNT;
  return `var(--schedule-bg-${index})`;
}

/**
 * Check if an event is on a specific day
 */
export function isEventOnDay(event: CalendarEvent, date: Date): boolean {
  return isSameDay(event.start, date);
}

/**
 * Extract time from a date for pre-filling the schedule form
 */
export function extractTimeFromDate(date: Date): string {
  const hours = date.getHours().toString().padStart(2, "0");
  const minutes = Math.floor(date.getMinutes() / 15) * 15;
  return `${hours}:${minutes.toString().padStart(2, "0")}`;
}

/**
 * Get the day name from a date
 */
export function getDayNameFromDate(date: Date): string {
  const dayNames = [
    "sunday",
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
  ];
  return dayNames[getDay(date)];
}
