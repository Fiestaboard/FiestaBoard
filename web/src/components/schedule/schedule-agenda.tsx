import { AgendaRow, Box, ListItem, ListRowGroup, Stack, Text } from "@fiestaboard/ui";
import { isSameDay, startOfWeek } from "date-fns";

import { useLocale, useTranslations } from "@/i18n/translations";
import type { Collection, Gap, Overlap, Page, ScheduleEntry } from "@/lib/api";
import { isCollectionId } from "@/lib/api";
import { type ResolvedSilenceSchedule, schedulesToCalendarEvents } from "@/lib/schedule-calendar";

export type ScheduleView = "day" | "list" | "calendar";
export function defaultScheduleView(width: number): ScheduleView {
  return width < 768 ? "day" : width < 1024 ? "list" : "calendar";
}
interface ScheduleAgendaProps {
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
  const time = (value: Date) => value.toLocaleTimeString(locale, { hour: "numeric", minute: "2-digit", hour12: true });
  const clock = (value: string) => {
    const [hour, minute] = value.split(":").map(Number);
    return time(new Date(2000, 0, 1, hour, minute));
  };
  const events = schedulesToCalendarEvents(schedules, startOfWeek(date), pages, collections, sunTimesMap)
    .filter((event) => isSameDay(event.start, date))
    .sort((a, b) => a.start.getTime() - b.start.getTime());
  const dayName = date.toLocaleDateString("en-US", { weekday: "long" }).toLowerCase();
  const dayGaps = gaps.filter((gap) => gap.days.some((day) => day.toLowerCase().slice(0, 3) === dayName.slice(0, 3)));
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
      <Text size="xs" tone="muted" className="font-mono uppercase">
        {date.toLocaleDateString(locale, { weekday: "long", month: "long", day: "numeric" })}
      </Text>
      {events.length || dayGaps.length || silenceSchedule?.enabled ? (
        <ListRowGroup>
          {timeline.map(({ key, event, gap }) =>
            event ? (
              <ListItem key={key}>
                <AgendaRow
                  title={event.title}
                  time={`${time(event.start)} – ${time(event.end)}`}
                  detail={isCollectionId(event.resource.pageId) ? t("collection") : t("page")}
                  kind={
                    overlaps.some(
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
                kind="gap"
                title={fallback}
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
            {t("gapUses", { name: fallback })}
          </Text>
        </Box>
      )}
    </Stack>
  );
}
