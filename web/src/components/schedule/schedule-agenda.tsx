import { AgendaRow, Box, ListItem, ListRowGroup, Stack, Text } from "@fiestaboard/ui";
import { addDays, isSameDay, startOfDay, startOfWeek } from "date-fns";

import { useLocale, useTranslations } from "@/i18n/translations";
import type { Collection, Gap, Overlap, Page, ScheduleEntry } from "@/lib/api";
import { isCollectionId } from "@/lib/api";
import { type ResolvedSilenceSchedule, schedulesToCalendarEvents } from "@/lib/schedule-calendar";

export type ScheduleView = "day" | "list" | "calendar";
export function defaultScheduleView(width: number): ScheduleView {
  return width < 768 ? "day" : width < 1024 ? "list" : "calendar";
}
/** Validation is weekly and uses today's solar times, not an ordered dated playback answer. */
export function supportsDatedGaps(schedules: ScheduleEntry[]): boolean {
  return !schedules.some(
    (entry) =>
      entry.enabled &&
      ((entry.recurrence_type && entry.recurrence_type !== "weekly") ||
        (entry.start_type && entry.start_type !== "fixed") ||
        (entry.end_type && entry.end_type !== "fixed")),
  );
}
interface ScheduleAgendaProps {
  /** The mono date line over the list; off where a day tray already names the day. @default true */
  showDate?: boolean;
  schedules: ScheduleEntry[];
  pages: Page[];
  collections?: Collection[];
  date: Date;
  onEdit: (entry: ScheduleEntry) => void;
  onSilenceClick?: () => void;
  silenceSchedule?: ResolvedSilenceSchedule | null;
  gaps?: Gap[];
  overlaps?: Overlap[];
  defaultPageId?: string | null;
  activePageId?: string | null;
  now?: Date;
  sunTimesMap?: Record<string, { sunrise: string; sunset: string }>;
}
export function ScheduleAgenda({
  showDate = true,
  schedules,
  pages,
  collections = [],
  date,
  onEdit,
  silenceSchedule,
  onSilenceClick,
  gaps = [],
  overlaps = [],
  defaultPageId,
  sunTimesMap,
  activePageId,
  now,
}: ScheduleAgendaProps) {
  const t = useTranslations("schedule.agenda");
  const tSchedule = useTranslations("schedule");
  const locale = useLocale();
  // An end at the end of the day (the calendar's 23:59:59.999, the hub's
  // "23:59" gap end) is midnight: "11:00 PM – 12:00 AM", not "11:59 PM" (BB-C-6).
  const time = (value: Date) =>
    (value.getHours() === 23 && value.getMinutes() === 59 ? startOfDay(addDays(value, 1)) : value).toLocaleTimeString(
      locale,
      { hour: "numeric", minute: "2-digit", hour12: true },
    );
  const clock = (value: string) => {
    const [hour, minute] = value.split(":").map(Number);
    return time(new Date(2000, 0, 1, hour, minute));
  };
  const week = schedulesToCalendarEvents(schedules, startOfWeek(date), pages, collections, sunTimesMap);
  const events = week
    .filter((event) => isSameDay(event.start, date))
    .sort((a, b) => a.start.getTime() - b.start.getTime());
  // Both halves of an overnight entry read as the entry: "11:30 PM – 2:00 AM".
  const range = (event: (typeof week)[number]) => {
    const half = event.resource.splitPart;
    const other = half
      ? week.find(
          (candidate) =>
            candidate.resource.scheduleId === event.resource.scheduleId &&
            candidate.resource.splitPart === (half === "evening" ? "morning" : "evening"),
        )
      : undefined;
    const start = half === "morning" && other ? other.start : event.start;
    const end = half === "evening" && other ? other.end : event.end;
    return `${time(start)} – ${time(end)}`;
  };
  const today = now && isSameDay(now, date) ? now.getHours() * 60 + now.getMinutes() : null;
  const datedOverlaps = supportsDatedGaps(schedules) ? overlaps : [];
  const dayName = date.toLocaleDateString("en-US", { weekday: "long" }).toLowerCase();
  const dayGaps = (supportsDatedGaps(schedules) ? gaps : []).filter((gap) =>
    gap.days.some((day) => day.toLowerCase().slice(0, 3) === dayName.slice(0, 3)),
  );
  const fallback =
    pages.find((page) => page.id === defaultPageId)?.name ??
    collections.find((collection) => collection.id === defaultPageId)?.name ??
    t("noDefault");
  const minute = (value: string) => {
    const [hour, minutes] = value.split(":").map(Number);
    return hour * 60 + minutes;
  };
  const timeline = [
    ...events.map((event) => ({
      key: event.id,
      start: event.start.getHours() * 60 + event.start.getMinutes(),
      event,
      gap: null,
      silence: false,
    })),
    ...dayGaps.map((gap, index) => ({
      key: `gap-${index}`,
      start: minute(gap.start_time),
      event: null,
      gap,
      silence: false,
    })),
    ...(silenceSchedule?.enabled
      ? [{ key: "silence", start: minute(silenceSchedule.startTimeLocal), event: null, gap: null, silence: true }]
      : []),
  ].sort((a, b) => a.start - b.start);
  const labels = { now: t("now"), gap: t("gap"), conflict: t("overlap") };
  return (
    <Stack gap="2">
      {showDate && (
        <Text size="xs" tone="muted" className="font-mono uppercase">
          {date.toLocaleDateString(locale, { weekday: "long", month: "long", day: "numeric" })}
        </Text>
      )}
      {events.length || dayGaps.length || silenceSchedule?.enabled ? (
        <ListRowGroup>
          {timeline.map(({ key, event, gap }) =>
            event ? (
              <ListItem key={key}>
                <AgendaRow
                  title={event.title}
                  time={range(event)}
                  detail={isCollectionId(event.resource.pageId) ? t("collection") : t("page")}
                  kind={
                    datedOverlaps.some(
                      (overlap) =>
                        overlap.schedule1_id === event.resource.scheduleId ||
                        overlap.schedule2_id === event.resource.scheduleId,
                    )
                      ? "conflict"
                      : now && activePageId === event.resource.pageId && now >= event.start && now < event.end
                        ? "now"
                        : "entry"
                  }
                  status={event.resource.enabled ? undefined : t("off")}
                  labels={labels}
                  className="min-h-14 w-full text-left"
                  render={<button type="button" onClick={() => onEdit(event.resource.originalSchedule)} />}
                />
              </ListItem>
            ) : gap ? (
              <AgendaRow
                key={key}
                // The gap the board is in now is the current row; it keeps its "Gap ·" title (BB-C-3).
                {...(today !== null &&
                today >= minute(gap.start_time) &&
                today < (gap.end_time === "23:59" ? 1440 : minute(gap.end_time))
                  ? { kind: "now" as const, title: `${t("gap")} · ${fallback}` }
                  : { kind: "gap" as const, title: fallback })}
                time={`${clock(gap.start_time)} – ${clock(gap.end_time)}`}
                detail={t("default")}
                labels={labels}
                trailing={null}
                className="min-h-14"
              />
            ) : silenceSchedule ? (
              <ListItem key={key}>
                <AgendaRow
                  title={t("silence")}
                  aria-label={tSchedule("silenceEventAriaLabel", {
                    range: `${clock(silenceSchedule.startTimeLocal)} – ${clock(silenceSchedule.endTimeLocal)}`,
                  })}
                  time={`${clock(silenceSchedule.startTimeLocal)} – ${clock(silenceSchedule.endTimeLocal)}`}
                  labels={labels}
                  className="min-h-14 w-full text-left"
                  render={<button type="button" onClick={onSilenceClick} />}
                />
              </ListItem>
            ) : null,
          )}
        </ListRowGroup>
      ) : (
        <Box className="rounded-xl border bg-card p-5">
          <Text size="sm">{t("empty")}</Text>
          <Text size="sm" tone="muted">
            {supportsDatedGaps(schedules) ? t("gapUses", { name: fallback }) : t("datedGapsUnavailable")}
          </Text>
        </Box>
      )}
    </Stack>
  );
}
