"use client";

import {
  formatWeekCalendarHour,
  formatWeekCalendarTime,
  Text,
  WeekCalendar,
  type WeekCalendarEntry,
} from "@fiestaboard/ui";
import { addDays, format, startOfWeek } from "date-fns";
import { useMemo } from "react";

import { useLocale, useTranslations } from "@/i18n/translations";
import { schedulesToCalendarEvents } from "@/lib/schedule-calendar";

import type { CreatorIdeState } from "./use-creator-ide";

const minuteOf = (date: Date, dayStart: Date) =>
  Math.max(0, Math.min(1440, Math.round((date.getTime() - dayStart.getTime()) / 60000)));

/** This week's blocks for the page's entries (direct and through collections), as WeekCalendar entries. */
export function useWeekEntries(ide: CreatorIdeState): { entries: WeekCalendarEntry[]; weekStart: Date } {
  const t = useTranslations("creatorIde");
  return useMemo(() => {
    const weekStart = startOfWeek(new Date(), { weekStartsOn: 0 });
    const schedules = ide.showsOn.entries.map((entry) => entry.schedule);
    const events = schedulesToCalendarEvents(schedules, weekStart, ide.pages, ide.collections);
    const entries = events.map((event) => {
      const dayStart = new Date(event.start);
      dayStart.setHours(0, 0, 0, 0);
      const showsOn = ide.showsOn.entries.find((entry) => entry.schedule.id === event.resource.scheduleId);
      return {
        id: event.id,
        day: event.start.getDay(),
        start: minuteOf(event.start, dayStart),
        end: Math.max(minuteOf(event.end, dayStart), minuteOf(event.start, dayStart) + 1),
        title: event.title,
        meta: showsOn?.collection ? t("throughCollection", { name: showsOn.collection.name }) : showsOn?.boardName,
        off: !event.resource.enabled,
      } satisfies WeekCalendarEntry;
    });
    return { entries, weekStart };
  }, [ide.showsOn, ide.pages, ide.collections, t]);
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
      now={{ day: today.getDay(), minute: today.getHours() * 60 + today.getMinutes() }}
    />
  );
}
