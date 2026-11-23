"use client";

import {
  formatWeekCalendarHour,
  formatWeekCalendarTime,
  List,
  ListItem,
  Stack,
  Text,
  WeekCalendar,
  type WeekCalendarEntry,
} from "@fiestaboard/ui";
import { addDays, format, startOfWeek } from "date-fns";
import { useMemo } from "react";

import { useLocale, useTranslations } from "@/i18n/translations";
import { schedulesToCalendarEvents } from "@/lib/schedule-calendar";

import { formatDays, formatWindow } from "./ide-format";
import type { CreatorIdeState } from "./use-creator-ide";

/** The timeline week runs Monday to Sunday, as Figma 184:159319 draws it (BB-FP-19). */
export const timelineWeekStart = (date: Date) => startOfWeek(date, { weekStartsOn: 1 });
/** A date's column in that week: Monday 0 … Sunday 6. */
export const timelineDayIndex = (date: Date) => (date.getDay() + 6) % 7;

const minuteOf = (date: Date, dayStart: Date) =>
  Math.max(0, Math.min(1440, Math.round((date.getTime() - dayStart.getTime()) / 60000)));

/** This week's blocks for the page's entries (direct and through collections), as WeekCalendar entries. */
export function useWeekEntries(ide: CreatorIdeState): { entries: WeekCalendarEntry[]; weekStart: Date } {
  return useMemo(() => {
    const weekStart = timelineWeekStart(new Date());
    const schedules = ide.showsOn.entries.map((entry) => entry.schedule);
    const events = schedulesToCalendarEvents(schedules, weekStart, ide.pages, ide.collections);
    const entries = events.map((event) => {
      const dayStart = new Date(event.start);
      dayStart.setHours(0, 0, 0, 0);
      return {
        id: event.id,
        day: timelineDayIndex(event.start),
        start: minuteOf(event.start, dayStart),
        end: Math.max(minuteOf(event.end, dayStart), minuteOf(event.start, dayStart) + 1),
        // Blocks are about 60 px wide here: a page name truncates to "Kitc…",
        // so the block shows its start time and the legend below names it.
        title: formatWeekCalendarTime(minuteOf(event.start, dayStart)),
        off: !event.resource.enabled,
      };
    });
    return { entries, weekStart };
  }, [ide.showsOn, ide.pages, ide.collections]);
}

/**
 * The page's week (04d 4.3 timeline strip; 1.6b Shows on week block): the
 * kit WeekCalendar cropped to the hours the page is scheduled.
 */
export function IdeWeek({ ide }: { ide: CreatorIdeState }) {
  const t = useTranslations("creatorIde");
  const locale = useLocale();
  const { entries, weekStart } = useWeekEntries(ide);
  if (!entries.length) {
    return (
      <Text size="sm" tone="muted" data-slot="ide-week-empty">
        {t("notThisWeek")}
      </Text>
    );
  }
  const startHour = Math.max(0, Math.floor(Math.min(...entries.map((entry) => entry.start)) / 60));
  const endHour = Math.min(24, Math.max(startHour + 1, Math.ceil(Math.max(...entries.map((entry) => entry.end)) / 60)));
  const today = new Date();
  const days = Array.from({ length: 7 }, (_, index) => addDays(weekStart, index));
  return (
    <Stack gap="1.5">
      <WeekCalendar
        aria-label={t("weekLabel")}
        data-slot="ide-week"
        days={days.map((day) => ({
          id: format(day, "yyyy-MM-dd"),
          label: day.toLocaleDateString(locale, { weekday: "short" }),
          name: day.toLocaleDateString(locale, { weekday: "long", month: "long", day: "numeric" }),
        }))}
        entries={entries}
        startHour={startHour}
        endHour={endHour}
        hourHeight={28}
        formatTime={formatWeekCalendarTime}
        formatHour={formatWeekCalendarHour}
        labels={{ conflict: t("overlap"), off: t("entryOff") }}
        now={{ day: timelineDayIndex(today), minute: today.getHours() * 60 + today.getMinutes() }}
      />
      <List gap="0" role="list" aria-label={t("legendLabel")} data-slot="ide-week-legend">
        {ide.showsOn.entries.map((entry) => (
          <ListItem key={entry.schedule.id}>
            <Text size="xs" tone="muted">
              {[
                `${formatDays(entry.schedule, t, locale)} ${formatWindow(entry.schedule, locale)}`,
                entry.collection ? t("throughCollection", { name: entry.collection.name }) : entry.boardName,
              ].join(" · ")}
            </Text>
          </ListItem>
        ))}
      </List>
    </Stack>
  );
}
