"use client";

import {
  Button,
  Flex,
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
import { Link } from "react-router";

import { useLocale, useTranslations } from "@/i18n/translations";
import type { Collection, Page, ScheduleEntry } from "@/lib/api";
import type { ShowsOnEntry } from "@/lib/ide/shows-on";
import { schedulesToCalendarEvents } from "@/lib/schedule-calendar";

import { formatDays, formatWindow } from "./ide-format";
import type { CreatorIdeState } from "./use-creator-ide";

/** The timeline week runs Monday to Sunday, as Figma 184:159319 draws it (BB-FP-19). */
export const timelineWeekStart = (date: Date) => startOfWeek(date, { weekStartsOn: 1 });
/** A date's column in that week: Monday 0 … Sunday 6. */
export const timelineDayIndex = (date: Date) => (date.getDay() + 6) % 7;

const minuteOf = (date: Date, dayStart: Date) =>
  Math.max(0, Math.min(1440, Math.round((date.getTime() - dayStart.getTime()) / 60000)));

/**
 * When the page next starts showing (this week or next): the earliest
 * enabled window that starts after `now`, with the entry it comes from.
 */
export function nextShowing(
  entries: readonly ShowsOnEntry[],
  pages: Page[],
  collections: Collection[],
  now: Date = new Date(),
): { at: Date; entry: ShowsOnEntry } | null {
  const enabled = entries.filter((entry) => entry.schedule.enabled);
  if (!enabled.length) return null;
  const schedules: ScheduleEntry[] = enabled.map((entry) => entry.schedule);
  const thisWeek = timelineWeekStart(now);
  const events = [thisWeek, addDays(thisWeek, 7)].flatMap((weekStart) =>
    schedulesToCalendarEvents(schedules, weekStart, pages, collections),
  );
  let best: { at: Date; entry: ShowsOnEntry } | null = null;
  for (const event of events) {
    // The 00:00 half of an overnight window continues it; it is not a start.
    if (event.resource.splitPart === "morning") continue;
    const at = new Date(event.start);
    if (at.getTime() <= now.getTime() || (best && at.getTime() >= best.at.getTime())) continue;
    const entry = enabled.find((candidate) => candidate.schedule.id === event.resource.scheduleId);
    if (entry) best = { at, entry };
  }
  return best;
}

/** "Mon 7:30 AM" for the next start, in the reader's locale. */
export function formatNext(at: Date, locale: string): string {
  return at.toLocaleString(locale, { weekday: "short", hour: "numeric", minute: "2-digit" });
}

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

/**
 * The Timeline slot until the kit's 80 px WeekStrip ships (UX-6-3, M1): one
 * line, "Weekdays 7:30 AM–8:30 AM · next Mon", or "Not scheduled this week ·
 * Add to schedule".
 */
export function IdeWeekLine({ ide, pageId }: { ide: CreatorIdeState; pageId: string }) {
  const t = useTranslations("creatorIde");
  const tq = useTranslations("ideQuiet");
  const locale = useLocale();
  const { entries } = useWeekEntries(ide);
  // Recomputed with the hub refresh (showsOn), so "next …" does not go stale for long.
  const next = nextShowing(ide.showsOn.entries, ide.pages, ide.collections);
  const first = next?.entry ?? ide.showsOn.entries.find((entry) => entry.schedule.enabled);
  if (!first || (!entries.length && !next)) {
    return (
      <Flex align="center" gap="1" data-slot="ide-week-line" className="min-w-0 flex-nowrap whitespace-nowrap">
        <Text as="span" size="sm" tone="muted" className="truncate">
          {tq("notThisWeek")} ·
        </Text>
        <Button asChild variant="link" size="sm" className="h-auto shrink-0 p-0">
          <Link to={`/schedule?prefill_page_id=${encodeURIComponent(pageId)}`}>{tq("addToSchedule")}</Link>
        </Button>
      </Flex>
    );
  }
  const more = ide.showsOn.entries.filter((entry) => entry.schedule.enabled).length - 1;
  // One line that truncates: "+N more" goes last, so it is the first thing cut, never "next …".
  const parts = [
    tq("weekLine", { days: formatDays(first.schedule, t, locale), window: formatWindow(first.schedule, locale) }),
    next
      ? tq("nextAt", {
          // Later today reads as a time, so "next Fri" on a Friday never means a week out.
          when:
            next.at.toDateString() === new Date().toDateString()
              ? next.at.toLocaleTimeString(locale, { hour: "numeric", minute: "2-digit" })
              : next.at.toLocaleDateString(locale, { weekday: "short" }),
        })
      : null,
    more > 0 ? tq("weekMore", { count: more }) : null,
  ];
  return (
    <Text as="p" size="sm" tone="muted" data-slot="ide-week-line" className="truncate">
      {parts.filter(Boolean).join(" · ")}
    </Text>
  );
}
