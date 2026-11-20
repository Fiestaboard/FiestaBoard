import {
  Alert,
  AlertDescription,
  Button,
  normalizeScheduleEntry,
  type ScheduleEntryValue,
  Text,
  validateScheduleEntry,
} from "@fiestaboard/ui";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useCallback } from "react";

import { useFormatPreferences } from "@/hooks/use-format-preferences";
import { useLocale, useTranslations } from "@/i18n/translations";
import {
  api,
  CANDIDATE_SCHEDULE_ID,
  type Collection,
  isCollectionId,
  type Overlap,
  type Page,
  type ScheduleEntry,
} from "@/lib/api";
import { weeklyConflictFix } from "@/lib/schedule-conflict-repair";
import { describeOverlap } from "@/lib/schedule-overlap";

/** Localized overlap sentences (BB-C-2): names, week-ordered days, the reader's 12/24 h clock. */
export function useOverlapText(pages: readonly Page[], collections: readonly Collection[]) {
  const t = useTranslations("schedule.agenda");
  const ts = useTranslations("schedule");
  const ta = useTranslations("schedule.adapter");
  const td = useTranslations("daySelector");
  const locale = useLocale();
  const { formatTime } = useFormatPreferences();
  return useCallback(
    (overlap: Overlap, selfId: string | null, entries: readonly ScheduleEntry[]) =>
      describeOverlap(overlap, selfId, {
        entries,
        nameOf: (pageId) =>
          (isCollectionId(pageId)
            ? collections.find((collection) => collection.id === pageId)?.name
            : pages.find((page) => page.id === pageId)?.name) ?? pageId,
        formatTime,
        locale,
        labels: {
          everyDay: ts("everyDay"),
          weekdays: ta("weekdaysShort"),
          weekends: ta("weekendsShort"),
          day: (day) => td(`dayLabels.${day}`),
        },
        t: (key, values) => t(key, values),
      }),
    [pages, collections, formatTime, locale, t, ts, ta, td],
  );
}

interface Props {
  /** The sheet's current, unsaved value. */
  draft: ScheduleEntryValue;
  /** The saved entry being edited; absent for a new entry. */
  editingId?: string;
  boardId?: string;
  schedules: readonly ScheduleEntry[];
  pages: readonly Page[];
  collections: readonly Collection[];
  /** Applies the one-tap fix to the draft (nothing is saved until Save). */
  onFix: (field: "start_time" | "end_time", time: string) => void;
}

/**
 * BB-C-1: the entry sheet says, before save, that the draft overlaps another
 * entry, which one the hub shows then, and offers the one-tap fix. The hub
 * evaluates the unsaved draft (`POST /schedules/validate` with a candidate),
 * so the overlap and its winner are the hub's own answer.
 */
export function ScheduleEntryConflict({ draft, editingId, boardId, schedules, pages, collections, onFix }: Props) {
  const t = useTranslations("schedule.agenda");
  const { formatTime } = useFormatPreferences();
  const describe = useOverlapText(pages, collections);
  const normalized = normalizeScheduleEntry(draft);
  const candidate = { ...normalized, custom_days: normalized.custom_days ?? undefined };
  const checkable =
    draft.enabled && draft.recurrence_type === "weekly" && Object.keys(validateScheduleEntry(draft)).length === 0;
  const selfId = editingId ?? CANDIDATE_SCHEDULE_ID;
  const { data } = useQuery({
    queryKey: ["schedules", "validation", boardId ?? "default", "candidate", selfId, candidate],
    queryFn: () => api.validateSchedules(boardId, candidate, editingId),
    enabled: checkable,
    placeholderData: keepPreviousData,
    retry: false,
  });
  if (!checkable || !data) return null;
  const mine = data.overlaps.filter((item) => item.schedule1_id === selfId || item.schedule2_id === selfId);
  if (!mine.length) return null;
  const self = { ...candidate, id: selfId, end_time: candidate.end_time ?? null } as ScheduleEntry;
  const entries = [...schedules.filter((entry) => entry.id !== selfId), self];
  const fix = weeklyConflictFix(self, entries, mine);
  return (
    <Alert variant="destructive" politeness="polite" data-testid="schedule-entry-conflict">
      <AlertDescription className="flex flex-col items-start gap-2">
        {mine.map((overlap) => (
          <Text as="p" size="sm" key={`${overlap.schedule1_id}:${overlap.schedule2_id}`}>
            {describe(overlap, selfId, entries)}
          </Text>
        ))}
        {fix && (
          <Button type="button" size="sm" variant="outline" onClick={() => onFix(fix.field, fix.time)}>
            {fix.field === "start_time"
              ? t("repairStart", { time: formatTime(fix.time) })
              : t("repairEnd", { time: formatTime(fix.time) })}
          </Button>
        )}
      </AlertDescription>
    </Alert>
  );
}
