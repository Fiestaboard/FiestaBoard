import type { Overlap, ScheduleEntry } from "./api";

const WEEK = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"];

/** Day names in week order (Monday first), whatever order the hub sent them in. */
export function orderScheduleDays(days: readonly string[]): string[] {
  return WEEK.filter((day) => days.some((name) => name.toLowerCase() === day));
}

export interface OverlapTextOptions {
  /** Saved entries, plus the unsaved draft under its candidate id when there is one. */
  entries: readonly ScheduleEntry[];
  /** Page or collection name for an entry's page_id. */
  nameOf: (pageId: string) => string;
  /** "HH:MM" in the reader's 12/24-hour preference. */
  formatTime: (time: string) => string;
  locale: string;
  labels: { everyDay: string; weekdays: string; weekends: string; day: (day: string) => string };
  /**
   * schedule.agenda messages: conflictWith {name, days, start, end},
   * conflictBetween {first, second, days, start, end}, conflictShows {name}.
   */
  t: (key: "conflictWith" | "conflictBetween" | "conflictShows", values: Record<string, string>) => string;
}

function dayLabel(days: string[], { locale, labels }: OverlapTextOptions): string {
  const key = days.join(",");
  if (days.length === 7) return labels.everyDay;
  if (key === WEEK.slice(0, 5).join(",")) return labels.weekdays;
  if (key === WEEK.slice(5).join(",")) return labels.weekends;
  return new Intl.ListFormat(locale, { style: "long", type: "conjunction" }).format(days.map(labels.day));
}

/**
 * The reader's sentence for one overlap: the other entry, the shared days and
 * minutes, and the entry the hub shows then (`winner_id`, the hub's own
 * precedence rule). `selfId` is the entry being looked
 * at; null (a list of every overlap) names both.
 * A hub without the structured fields keeps its English description.
 */
export function describeOverlap(overlap: Overlap, selfId: string | null, options: OverlapTextOptions): string {
  const { days, start_time: start, end_time: end, winner_id: winnerId } = overlap;
  if (!days?.length || !start || !end || !winnerId) return overlap.conflict_description;
  const name = (id: string) => {
    const entry = options.entries.find((candidate) => candidate.id === id);
    return entry ? options.nameOf(entry.page_id) : id;
  };
  const when = {
    days: dayLabel(orderScheduleDays(days), options),
    start: options.formatTime(start),
    end: options.formatTime(end),
  };
  const otherId = overlap.schedule1_id === selfId ? overlap.schedule2_id : overlap.schedule1_id;
  const first =
    selfId === null
      ? options.t("conflictBetween", { first: name(overlap.schedule1_id), second: name(overlap.schedule2_id), ...when })
      : options.t("conflictWith", { name: name(otherId), ...when });
  return `${first} ${options.t("conflictShows", { name: name(winnerId) })}`;
}
