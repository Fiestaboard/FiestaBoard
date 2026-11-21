import type { Overlap, ScheduleEntry } from "./api";
/** An explicit edit proposal for simple weekly windows, never a playback winner calculation. */
export function weeklyConflictRepair(
  selected: ScheduleEntry,
  entries: ScheduleEntry[],
  overlaps: Overlap[],
): string | null {
  const simple = (entry: ScheduleEntry) =>
    entry.enabled &&
    (!entry.recurrence_type || entry.recurrence_type === "weekly") &&
    (!entry.start_type || entry.start_type === "fixed") &&
    (!entry.end_type || entry.end_type === "fixed") &&
    !!entry.end_time &&
    entry.start_time < entry.end_time;
  if (!simple(selected)) return null;
  const related = overlaps
    .filter((item) => item.schedule1_id === selected.id || item.schedule2_id === selected.id)
    .map((item) =>
      entries.find((entry) => entry.id === (item.schedule1_id === selected.id ? item.schedule2_id : item.schedule1_id)),
    );
  if (!related.length || related.some((entry) => !entry || !simple(entry))) return null;
  const after = related
    .map((entry) => entry!.end_time!)
    .sort()
    .at(-1)!;
  return after > selected.start_time && after < selected.end_time! ? after : null;
}

/**
 * The one-tap fix for an entry being edited: start after the overlapping
 * entries end, or else end before they start. Null when neither leaves a
 * non-empty window (the entry sits inside another) or the windows are not
 * simple weekly fixed times.
 */
export function weeklyConflictFix(
  selected: ScheduleEntry,
  entries: ScheduleEntry[],
  overlaps: Overlap[],
): { field: "start_time" | "end_time"; time: string } | null {
  const start = weeklyConflictRepair(selected, entries, overlaps);
  if (start) return { field: "start_time", time: start };
  if (!selected.end_time || selected.start_time >= selected.end_time) return null;
  const related = overlaps
    .filter((item) => item.schedule1_id === selected.id || item.schedule2_id === selected.id)
    .map((item) =>
      entries.find((entry) => entry.id === (item.schedule1_id === selected.id ? item.schedule2_id : item.schedule1_id)),
    );
  if (
    !related.length ||
    related.some((entry) => !entry || entry.start_type === "sunrise" || entry.start_type === "sunset")
  )
    return null;
  const before = related.map((entry) => entry!.start_time).sort()[0];
  return before > selected.start_time && before < selected.end_time ? { field: "end_time", time: before } : null;
}
