import {
  Box,
  Button,
  DayChip,
  EmptyState,
  Flex,
  ListRow,
  ListRowGroup,
  Stack,
  Switch,
  Text,
  WeekCalendar,
  type WeekCalendarEntry,
  WeekCalendarInspector,
  WeekStrip,
} from "@fiestaboard/ui";
import { useQuery } from "@tanstack/react-query";
import { addDays, format, isSameDay, startOfDay, startOfWeek } from "date-fns";
import { fromZonedTime, toZonedTime } from "date-fns-tz";
import { Calendar, ChevronLeft, ChevronRight } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";

import { useLocale, useTranslations } from "@/i18n/translations";
import { api, type Collection, type Gap, isCollectionId, type Overlap, type Page, type ScheduleEntry } from "@/lib/api";
import {
  type ResolvedSilenceSchedule,
  schedulesToCalendarEvents,
  silenceToCalendarEvents,
} from "@/lib/schedule-calendar";
import { weeklyConflictRepair } from "@/lib/schedule-conflict-repair";

import { ScheduleAgenda, type ScheduleView, supportsDatedGaps } from "./schedule-agenda";
import { ScheduleCopy } from "./schedule-copy";
import { ScheduleLookup } from "./schedule-lookup";
import { SchedulePagePreview } from "./schedule-page-preview";

interface Props {
  view: ScheduleView;
  /** Phone (07d `322:19169`): day chips first, the agenda next, week and lookup controls after it. */
  compact?: boolean;
  schedules: ScheduleEntry[];
  pages: Page[];
  collections: Collection[];
  boardId?: string;
  boardName?: string;
  timezone: string;
  defaultPageId?: string | null;
  gaps?: Gap[];
  overlaps?: Overlap[];
  silenceSchedule?: ResolvedSilenceSchedule | null;
  onEdit: (entry: ScheduleEntry) => void;
  onDelete: (id: string) => void;
  onToggleEnabled: (entry: ScheduleEntry, enabled: boolean) => void;
  onCreate: (start: Date, end: Date) => void;
  onSilenceClick: () => void;
  onRepair?: (entry: ScheduleEntry, startTime: string) => Promise<void>;
  legacyCalendar?: React.ReactNode;
}
export function ScheduleWorkspace({
  view,
  compact = false,
  schedules,
  pages,
  collections,
  boardId,
  boardName,
  timezone,
  defaultPageId,
  gaps = [],
  overlaps = [],
  silenceSchedule,
  onEdit,
  onDelete,
  onToggleEnabled,
  onCreate,
  onSilenceClick,
  onRepair,
  legacyCalendar,
}: Props) {
  const t = useTranslations("schedule.agenda");
  const tSchedule = useTranslations("schedule");
  const tCommon = useTranslations("common");
  const locale = useLocale();
  const [date, setDate] = useState(() => startOfDay(toZonedTime(new Date(), timezone)));
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [repairing, setRepairing] = useState(false);
  const [legacy, setLegacy] = useState(false);
  const [lookupOpen, setLookupOpen] = useState(false);
  const lookupId = useId();
  const weekStart = startOfWeek(date);
  const days = Array.from({ length: 7 }, (_, index) => addDays(weekStart, index));
  const needsSun = schedules.some(
    (entry) =>
      entry.start_type === "sunrise" ||
      entry.start_type === "sunset" ||
      entry.end_type === "sunrise" ||
      entry.end_type === "sunset",
  );
  const sun = useQuery({
    queryKey: ["schedule-sun-week", format(weekStart, "yyyy-MM-dd")],
    queryFn: () => api.getSunTimesWeek(format(weekStart, "yyyy-MM-dd")),
    enabled: needsSun,
    retry: false,
  });
  const sunTimesMap = sun.data?.location_configured ? sun.data.dates : undefined;
  const current = useQuery({
    queryKey: ["schedule-agenda-active", boardId],
    queryFn: () => api.getActiveSchedule(boardId),
    refetchInterval: 30000,
  });
  const events = schedulesToCalendarEvents(schedules, weekStart, pages, collections, sunTimesMap);
  const silence = silenceSchedule?.enabled ? silenceToCalendarEvents(silenceSchedule, weekStart, pages) : [];
  const minute = (value: Date, day: Date) =>
    isSameDay(value, day) ? value.getHours() * 60 + value.getMinutes() : 1440;
  const time = (value: number) =>
    new Date(2000, 0, 1, 0, value).toLocaleTimeString(locale, { hour: "numeric", minute: "2-digit", hour12: true });
  const entries: WeekCalendarEntry[] = events.map((event) => ({
    id: event.id,
    day: event.start.getDay(),
    start: minute(event.start, event.start),
    end: minute(event.end, event.start),
    title: event.title,
    meta: isCollectionId(event.resource.pageId) ? t("collection") : t("page"),
    conflict: (supportsDatedGaps(schedules) ? overlaps : []).some(
      (overlap) =>
        overlap.schedule1_id === event.resource.scheduleId || overlap.schedule2_id === event.resource.scheduleId,
    ),
    off: !event.resource.enabled,
  }));
  entries.push(
    ...silence.map((event) => ({
      id: event.id,
      day: event.start.getDay(),
      start: minute(event.start, event.start),
      end: minute(event.end, event.start),
      title: t("silence"),
      kind: "silence" as const,
    })),
  );
  const fallback =
    pages.find((page) => page.id === defaultPageId)?.name ??
    collections.find((collection) => collection.id === defaultPageId)?.name ??
    t("noDefault");
  for (const [index, day] of days.entries()) {
    const dayName = day.toLocaleDateString("en-US", { weekday: "long" }).toLowerCase();
    for (const [gapIndex, gap] of (supportsDatedGaps(schedules) ? gaps : []).entries()) {
      if (!gap.days.some((name) => name.toLowerCase().slice(0, 3) === dayName.slice(0, 3))) continue;
      const toMinute = (value: string) => {
        const [hour, minutes] = value.split(":").map(Number);
        return hour * 60 + minutes;
      };
      const start = toMinute(gap.start_time);
      const end = toMinute(gap.end_time);
      if (end > start)
        entries.push({
          id: `gap-${index}-${gapIndex}`,
          day: index,
          start,
          end,
          title: `${t("gap")} · ${fallback}`,
          kind: "gap",
        });
    }
  }
  const selected = events.find((event) => event.id === selectedId);
  const selectedEntry = selected?.resource.originalSchedule;
  const conflict = selectedEntry
    ? (supportsDatedGaps(schedules) ? overlaps : []).find(
        (overlap) => overlap.schedule1_id === selectedEntry.id || overlap.schedule2_id === selectedEntry.id,
      )
    : undefined;
  const repairStart =
    selectedEntry && supportsDatedGaps(schedules) ? weeklyConflictRepair(selectedEntry, schedules, overlaps) : null;
  const today = toZonedTime(new Date(), timezone);
  const hasTimeline = schedules.length > 0 || silenceSchedule?.enabled;
  // Keep the chosen day chip on screen when the strip scrolls sideways (BB-C-3).
  const strip = useRef<HTMLDivElement>(null);
  const chosenDay = format(date, "yyyy-MM-dd");
  useEffect(() => {
    strip.current
      ?.querySelector<HTMLElement>('[aria-checked="true"]')
      ?.scrollIntoView?.({ block: "nearest", inline: "center" });
  }, [chosenDay, view, lookupOpen]);
  const controls = (
    <Flex align="center" justify="between" gap="2" wrap>
      {!lookupOpen && hasTimeline && (
        <Flex gap="1" align="center">
          <Button size="icon" variant="outline" aria-label={t("previous")} onClick={() => setDate(addDays(date, -7))}>
            <ChevronLeft aria-hidden="true" />
          </Button>
          <Text size="sm" weight="semibold">
            {weekStart.toLocaleDateString(locale, { month: "long", day: "numeric" })} –{" "}
            {addDays(weekStart, 6).toLocaleDateString(locale, { month: "long", day: "numeric", year: "numeric" })}
          </Text>
          <Button size="icon" variant="outline" aria-label={t("next")} onClick={() => setDate(addDays(date, 7))}>
            <ChevronRight aria-hidden="true" />
          </Button>
        </Flex>
      )}
      <Flex gap="2" align="center" wrap>
        {!lookupOpen && hasTimeline && (
          <Button variant="outline" onClick={() => setDate(startOfDay(today))}>
            {t("today")}
          </Button>
        )}
        <Button
          variant="outline"
          aria-expanded={lookupOpen}
          aria-controls={lookupId}
          onClick={() => setLookupOpen(!lookupOpen)}
        >
          {lookupOpen && <ChevronLeft aria-hidden="true" />}
          {lookupOpen ? tCommon("back") : tSchedule("lookup.title")}
        </Button>
      </Flex>
    </Flex>
  );
  return (
    <Stack gap="4">
      {!compact && controls}
      {!lookupOpen && view === "day" && hasTimeline && (
        <Box ref={strip} className="min-w-0">
          <WeekStrip
            aria-label={t("days")}
            value={format(date, "yyyy-MM-dd")}
            onValueChange={(value) => {
              const day = days.find((candidate) => format(candidate, "yyyy-MM-dd") === value);
              if (day) setDate(day);
            }}
          >
            {days.map((day) => (
              <DayChip key={day.toISOString()} value={format(day, "yyyy-MM-dd")}>
                {day.toLocaleDateString(locale, { weekday: "short", day: "numeric" })}
              </DayChip>
            ))}
          </WeekStrip>
        </Box>
      )}
      {!lookupOpen && !supportsDatedGaps(schedules) && (gaps.length > 0 || overlaps.length > 0) && (
        <Text role="status" size="sm" tone="muted">
          {t("datedGapsUnavailable")}
        </Text>
      )}
      {!lookupOpen && needsSun && (sun.isError || (sun.data && !sun.data.location_configured)) && (
        <Text role="status" size="sm" tone="muted">
          {t("sunUnavailable")}
        </Text>
      )}
      {lookupOpen ? (
        <Box id={lookupId} className="min-w-0">
          <ScheduleLookup
            key={boardId ?? "default"}
            boardId={boardId}
            pages={pages}
            collections={collections}
            timezone={timezone}
          />
        </Box>
      ) : (
        <Box className={selectedEntry ? "grid gap-5 xl:grid-cols-[minmax(0,1.2fr)_minmax(20rem,1fr)]" : "min-w-0"}>
          <Stack gap="4" className="min-w-0">
            {schedules.length === 0 && (
              <EmptyState
                icon={Calendar}
                title={tSchedule("noSchedulesCreated")}
                description={t("gapUses", { name: fallback })}
                action={
                  <Stack gap="3" className="mx-auto w-full min-w-0 max-w-sm">
                    <SchedulePagePreview
                      pageId={defaultPageId}
                      pages={pages}
                      at={new Date().toISOString()}
                      boardId={boardId}
                      label={t("default")}
                    />
                    <Button
                      onClick={() => {
                        const start = new Date(date);
                        start.setHours(9, 0, 0, 0);
                        const end = new Date(date);
                        end.setHours(13, 0, 0, 0);
                        onCreate(start, end);
                      }}
                    >
                      {tSchedule("addSchedule")}
                    </Button>
                    <ScheduleCopy boardId={boardId} pages={pages} collections={collections} />
                  </Stack>
                }
                className="rounded-xl border bg-card py-10 [&>[data-slot=empty-state-action]]:w-full [&>[data-slot=empty-state-action]]:min-w-0"
              />
            )}
            {view === "calendar" && schedules.length > 0 ? (
              <>
                {legacy ? (
                  legacyCalendar
                ) : (
                  <WeekCalendar
                    aria-label={t("calendar")}
                    days={days.map((day) => ({
                      id: format(day, "yyyy-MM-dd"),
                      label: day.toLocaleDateString(locale, { weekday: "short", day: "numeric" }),
                      name: day.toLocaleDateString(locale, { weekday: "long", month: "long", day: "numeric" }),
                    }))}
                    entries={entries}
                    selectedId={selectedId}
                    startHour={entries.some((entry) => entry.start < 360) ? 0 : 6}
                    endHour={entries.some((entry) => entry.end > 1380) ? 24 : 23}
                    hourHeight={34}
                    formatTime={time}
                    formatHour={(hour) => time(hour * 60)}
                    labels={{ conflict: t("overlap"), off: t("off") }}
                    now={
                      days.some((day) => isSameDay(day, today))
                        ? { day: today.getDay(), minute: today.getHours() * 60 + today.getMinutes() }
                        : null
                    }
                    onSelect={(entry) => {
                      if (entry.kind === "silence") onSilenceClick();
                      else if (entry.kind !== "gap") setSelectedId(entry.id);
                    }}
                    onCreate={(range) => {
                      const start = new Date(days[range.day]);
                      start.setMinutes(range.start);
                      const end = new Date(days[range.day]);
                      end.setMinutes(range.end);
                      onCreate(start, end);
                    }}
                  />
                )}
                {legacyCalendar && (
                  <Button variant="ghost" onClick={() => setLegacy(!legacy)}>
                    {legacy ? t("calendar") : t("legacy")}
                  </Button>
                )}
              </>
            ) : view === "calendar" || !hasTimeline ? null : (
              (view === "day" ? [date] : days).map((day) => (
                <ScheduleAgenda
                  key={day.toISOString()}
                  date={day}
                  schedules={schedules}
                  pages={pages}
                  collections={collections}
                  gaps={gaps}
                  overlaps={supportsDatedGaps(schedules) ? overlaps : []}
                  defaultPageId={defaultPageId}
                  silenceSchedule={silenceSchedule}
                  sunTimesMap={sunTimesMap}
                  now={today}
                  activePageId={
                    current.data?.source === "schedule" && !current.data.temporary_override?.active
                      ? current.data.page_id
                      : null
                  }
                  onEdit={onEdit}
                  onSilenceClick={onSilenceClick}
                />
              ))
            )}
          </Stack>
          {selectedEntry && (
            <WeekCalendarInspector
              title={selected!.title}
              description={`${time(minute(selected!.start, selected!.start))} – ${time(minute(selected!.end, selected!.start))} · ${boardName ?? ""}`}
              conflict={conflict?.conflict_description}
              conflictActions={
                repairStart && onRepair ? (
                  <Stack gap="2">
                    <Button
                      variant="outline"
                      disabled={repairing}
                      onClick={async () => {
                        setRepairing(true);
                        try {
                          await onRepair(selectedEntry, repairStart);
                        } finally {
                          setRepairing(false);
                        }
                      }}
                    >
                      {t("repairStart", {
                        time: time(Number(repairStart.slice(0, 2)) * 60 + Number(repairStart.slice(3))),
                      })}
                    </Button>
                    <Text size="xs" tone="muted">
                      {t("repairRepeats")}
                    </Text>
                  </Stack>
                ) : undefined
              }
              preview={
                <SchedulePagePreview
                  pageId={selectedEntry.page_id}
                  pages={pages}
                  at={fromZonedTime(selected!.start, timezone).toISOString()}
                  boardId={boardId}
                  label={t("page")}
                />
              }
              actions={
                <Flex gap="2">
                  <Button variant="outline" onClick={() => onEdit(selectedEntry)}>
                    {t("edit")}
                  </Button>
                  <Button variant="ghost" onClick={() => onDelete(selectedEntry.id)}>
                    {t("delete")}
                  </Button>
                </Flex>
              }
            >
              <ListRowGroup>
                <ListRow title={t("page")} meta={selected!.title} />
                <ListRow title={t("display")} meta={boardName} />
                <ListRow
                  title={t("repeat")}
                  meta={tSchedule(
                    selectedEntry.recurrence_type === "annual_date"
                      ? "scheduleEntryForm.recurrenceAnnual"
                      : selectedEntry.recurrence_type === "one_off_date"
                        ? "scheduleEntryForm.recurrenceOneOff"
                        : "scheduleEntryForm.recurrenceWeekly",
                  )}
                />
                <ListRow
                  title={tSchedule("scheduleEntryForm.enabledLabel")}
                  trailing={
                    <Switch
                      checked={selectedEntry.enabled}
                      onCheckedChange={(enabled) => onToggleEnabled(selectedEntry, enabled)}
                      aria-label={tSchedule("toggleEnabledAriaLabel", { pageName: selected!.title })}
                    />
                  }
                />
              </ListRowGroup>
            </WeekCalendarInspector>
          )}
        </Box>
      )}
      {compact && controls}
    </Stack>
  );
}
