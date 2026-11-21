import { useQuery } from "@tanstack/react-query";

import { splitInterval } from "@/components/collection-form";
import { formatDays, formatWindow } from "@/components/ide/ide-format";
import { queryKeys } from "@/hooks/use-board";
import type { ScheduleEntry } from "@/lib/api";
import { api } from "@/lib/api";

type Translate = (key: string, params?: Record<string, string | number>) => string;

/** "40 min" / "1 hr" in the reader's locale, from whole seconds. */
export function formatDurationLabel(seconds: number, locale: string): string {
  const { amount, unit } = splitInterval(seconds);
  return new Intl.NumberFormat(locale, { style: "unit", unit: unit.slice(0, -1), unitDisplay: "short" }).format(amount);
}

/** Every board's schedule entries (the hub answers "*" with all of them). */
export function useAllSchedules() {
  return useQuery({
    queryKey: queryKeys.schedules("*"),
    queryFn: () => api.getSchedules("*"),
    retry: false,
    staleTime: 60_000,
  });
}

/**
 * "Weekdays 6:00 AM–9:00 AM" for the enabled entries that schedule this
 * Collection (the first one, plus "+N more"), or null when none do.
 * `tIde` is the creatorIde namespace, which owns the day-pattern words.
 */
export function collectionScheduleSummary(
  collectionId: string,
  schedules: readonly ScheduleEntry[] | undefined,
  t: Translate,
  tIde: Translate,
  locale: string,
): string | null {
  const entries = (schedules ?? []).filter((entry) => entry.enabled && entry.page_id === collectionId);
  if (entries.length === 0) return null;
  const first = `${formatDays(entries[0], tIde, locale)} ${formatWindow(entries[0], locale)}`;
  return entries.length > 1 ? t("scheduleSummaryMore", { summary: first, count: entries.length - 1 }) : first;
}
