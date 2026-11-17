import {
  api,
  type BoardInstance,
  type Collection,
  isCollectionId,
  type Page,
  type ScheduleCreate,
  type ScheduleEntry,
  type ScheduleWriteResponse,
} from "./api";
import { pagesCompatibleWithBoard } from "./board-dimensions";
export class ScheduleCopyError extends Error {
  constructor(
    message: string,
    readonly remainingIds: string[] = [],
    readonly incompatible = false,
  ) {
    super(message);
  }
}
/** Refuse incompatible batches before writing; failure rolls back only this operation's creations. */
export async function copyScheduleEntries(
  entries: ScheduleEntry[],
  target: BoardInstance,
  pages: Page[],
  collections: Collection[],
): Promise<void> {
  const fits = (id: string) => {
    const page = pages.find((item) => item.id === id);
    return !!page && pagesCompatibleWithBoard(page, target);
  };
  const incompatible = entries.some((entry) => {
    if (!isCollectionId(entry.page_id)) return !fits(entry.page_id);
    const collection = collections.find((item) => item.id === entry.page_id);
    return !collection || !collection.page_ids.length || !collection.page_ids.every(fits);
  });
  if (incompatible) throw new ScheduleCopyError("incompatible", [], true);
  const created: ScheduleWriteResponse[] = [];
  try {
    for (const entry of entries) {
      const data: ScheduleCreate = {
        board_id: target.id,
        page_id: entry.page_id,
        start_time: entry.start_time,
        end_time: entry.end_time,
        day_pattern: entry.day_pattern,
        custom_days: entry.custom_days,
        enabled: entry.enabled,
        recurrence_type: entry.recurrence_type,
        annual_date: entry.annual_date,
        annual_end_date: entry.annual_end_date,
        one_off_date: entry.one_off_date,
        one_off_end_date: entry.one_off_end_date,
        start_type: entry.start_type,
        end_type: entry.end_type,
        start_sun_offset: entry.start_sun_offset,
        end_sun_offset: entry.end_sun_offset,
      };
      created.push(await api.createSchedule(data));
    }
  } catch (error) {
    const remaining: string[] = [];
    for (const entry of created.reverse()) {
      try {
        await api.deleteSchedule(entry.id, entry.edit_protocol === "schedule-revision-v1" ? entry.revision : undefined);
      } catch {
        remaining.push(entry.id);
      }
    }
    throw new ScheduleCopyError(error instanceof Error ? error.message : String(error), remaining);
  }
}
