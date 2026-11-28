import type { ActiveScheduleResponse, BoardInstance, Collection, ScheduleEntry } from "@/lib/api";

export interface ShowsOnEntry {
  schedule: ScheduleEntry;
  boardId: string;
  boardName: string;
  /** Set when the entry schedules a collection that holds the page. */
  collection: Collection | null;
  /** The entry's window holds the current time on that board (H8 answered this page). */
  now: boolean;
}

export interface ShowsOnCollection {
  collection: Collection;
  /** 1-based place of the page in the collection. */
  position: number;
  size: number;
}

export interface ShowingNow {
  boardId: string;
  boardName: string;
  /** "HH:MM" end of the window showing it, or null when open-ended / manual. */
  until: string | null;
  /**
   * Set when a Show now (the display's H1 temporary override) is what shows it:
   * its ISO end, null when it runs until cancelled (W-2).
   */
  override?: { expiresAt: string | null };
}

export interface ShowsOnModel {
  entries: ShowsOnEntry[];
  collections: ShowsOnCollection[];
  showingNow: ShowingNow[];
  /** A schedule entry (direct or through a collection) can show this page. */
  scheduled: boolean;
}

export interface ShowsOnInput {
  pageId: string;
  schedules: readonly ScheduleEntry[];
  collections: readonly Collection[];
  boards: readonly BoardInstance[];
  /** H8 `GET /schedules/active/page` per board id, at the instant being asked about. */
  active: Readonly<Record<string, ActiveScheduleResponse | undefined>>;
  /** Fallback board for entries saved without one (the primary). */
  defaultBoardId?: string;
}

/** "HH:MM" on this device's clock for an ISO instant; null when absent or unreadable. */
function wallClock(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return null;
  return `${String(at.getHours()).padStart(2, "0")}:${String(at.getMinutes()).padStart(2, "0")}`;
}

const minutes = (hhmm: string | null | undefined): number | null => {
  if (!hhmm) return null;
  const match = /^(\d{1,2}):(\d{2})/.exec(hhmm);
  return match ? Number(match[1]) * 60 + Number(match[2]) : null;
};

/**
 * The displays that show the page, for the editor to preview it as (UX-6-1):
 * those showing it now, then those an enabled entry schedules it on, each once.
 */
export function pageDisplayIds(model: Pick<ShowsOnModel, "showingNow" | "entries">): string[] {
  const ids = [
    ...model.showingNow.map((showing) => showing.boardId),
    ...model.entries.filter((entry) => entry.schedule.enabled).map((entry) => entry.boardId),
  ];
  return [...new Set(ids.filter(Boolean))];
}

/** The entry's window (resolved sun times when present) holds `hhmm`. Overnight windows wrap. */
export function windowHolds(schedule: ScheduleEntry, hhmm: string | null): boolean {
  const now = minutes(hhmm);
  const start = minutes(schedule.resolved_start_time || schedule.start_time);
  if (now === null || start === null) return false;
  const endRaw = schedule.resolved_end_time !== undefined ? schedule.resolved_end_time : schedule.end_time;
  const end = minutes(endRaw);
  if (end === null) return now >= start;
  return start <= end ? now >= start && now < end : now >= start || now < end;
}

/**
 * "Shows on" for one page (04d 1.6b, H8): every schedule entry that can show
 * it, directly or through a collection; the collections that hold it; and the
 * boards the hub says show it at the asked instant.
 */
export function showsOnModel({
  pageId,
  schedules,
  collections,
  boards,
  active,
  defaultBoardId,
}: ShowsOnInput): ShowsOnModel {
  const holding = collections.filter((collection) => collection.page_ids.includes(pageId));
  const byId = new Map(holding.map((collection) => [collection.id, collection]));
  const boardName = (id: string) => boards.find((board) => board.id === id)?.name ?? id;

  const showingNow: ShowingNow[] = [];
  const entries: ShowsOnEntry[] = [];
  for (const schedule of schedules) {
    const collection = byId.get(schedule.page_id) ?? null;
    if (schedule.page_id !== pageId && !collection) continue;
    const boardId = schedule.board_id || defaultBoardId || "";
    const answer = active[boardId];
    // A running Show now holds the board over its schedule (H1).
    const answersThisPage =
      !!answer &&
      !answer.temporary_override?.active &&
      (answer.page_id === pageId || answer.resolved_page_id === pageId) &&
      answer.source === "schedule";
    const now = answersThisPage && schedule.enabled && windowHolds(schedule, answer.current_time);
    entries.push({ schedule, boardId, boardName: boardName(boardId), collection, now });
  }

  for (const [boardId, answer] of Object.entries(active)) {
    if (!answer || answer.silenced) continue;
    const override = answer.temporary_override;
    if (override?.active) {
      // W-2: the board shows the Show now page until it ends, whatever the schedule says.
      if (override.page_id === pageId) {
        showingNow.push({
          boardId,
          boardName: boardName(boardId),
          until: wallClock(override.expires_at),
          override: { expiresAt: override.expires_at ?? null },
        });
      }
      continue;
    }
    if (answer.page_id !== pageId && answer.resolved_page_id !== pageId) continue;
    const window = entries.find((entry) => entry.boardId === boardId && entry.now);
    const end = window
      ? window.schedule.resolved_end_time !== undefined
        ? window.schedule.resolved_end_time
        : window.schedule.end_time
      : null;
    showingNow.push({ boardId, boardName: boardName(boardId), until: end ?? null });
  }

  return {
    entries,
    collections: holding.map((collection) => ({
      collection,
      position: collection.page_ids.indexOf(pageId) + 1,
      size: collection.page_ids.length,
    })),
    showingNow,
    scheduled: entries.some((entry) => entry.schedule.enabled),
  };
}
