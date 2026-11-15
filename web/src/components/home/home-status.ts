/**
 * Pure helpers behind the canonical Home (slice 2.2): the shared duration
 * step of both verbs, and what the Now showing card may claim.
 *
 * The web never computes the Schedule. Everything time-shaped here comes from
 * the hub: H2's `next_change_at` / `next_change_reason` / `next_page_id` on
 * `GET /v1/boards/{board}`, and H1's per-display override.
 */
import type { BoardDetail } from "@/lib/api";

/** The DurationChipGroup values (`buildDurationOptions` in @fiestaboard/ui). */
export type DurationChoice = "15m" | "1h" | "next-change" | "until-cancel";

/** `TEMPORARY_OVERRIDE_DURATION_MAX` in src/settings/service.py: an override holds at most 8 h. */
export const MAX_OVERRIDE_MINUTES = 480;

const MINUTE = 60_000;

const FIXED_MINUTES: Partial<Record<DurationChoice, number>> = { "15m": 15, "1h": 60 };

/** The Schedule's next hand-over on a display, as the hub predicts it. */
export interface ScheduleNextChange {
  at: Date;
  /** The page or collection in force after it, when the hub can know it. */
  pageId: string | null;
}

/**
 * The "Until 9:00 PM" chip's target: H2's next change, but only when it is a
 * Schedule hand-over (07a: "the next Schedule change on this display") that an
 * override can actually hold until. Quiet hours, a collection's rotation and
 * an override's own end are not Schedule changes; while an override runs H2
 * reports `override_ends`, so the chip is left out then.
 */
export function scheduleNextChange(
  detail: Pick<BoardDetail, "next_change_at" | "next_change_reason" | "next_page_id"> | undefined | null,
  now: Date,
): ScheduleNextChange | null {
  if (!detail?.next_change_at || detail.next_change_reason !== "schedule") return null;
  const at = new Date(detail.next_change_at);
  const ms = at.getTime() - now.getTime();
  if (Number.isNaN(ms) || ms <= 0 || ms > MAX_OVERRIDE_MINUTES * MINUTE) return null;
  return { at, pageId: detail.next_page_id ?? null };
}

/**
 * `duration_minutes` for a choice; `undefined` means none is sent (an
 * indefinite override, or no override at all).
 */
export function durationMinutes(
  choice: DurationChoice,
  next: ScheduleNextChange | null,
  now: Date,
): number | undefined {
  const fixed = FIXED_MINUTES[choice];
  if (fixed !== undefined) return fixed;
  if (choice === "next-change" && next) {
    const minutes = Math.ceil((next.at.getTime() - now.getTime()) / MINUTE);
    return Math.min(MAX_OVERRIDE_MINUTES, Math.max(1, minutes));
  }
  return undefined;
}

/** When the hold a choice asks for ends; null when it never ends on its own. */
export function holdEndsAt(choice: DurationChoice, next: ScheduleNextChange | null, now: Date): Date | null {
  const fixed = FIXED_MINUTES[choice];
  if (fixed !== undefined) return new Date(now.getTime() + fixed * MINUTE);
  if (choice === "next-change" && next) return next.at;
  return null;
}

/** "2h 44m", "1h", "15m". A started minute counts, like Countdown's "left" copy. */
export function formatSpan(ms: number): string {
  const minutes = Math.max(0, Math.ceil(ms / MINUTE));
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (h === 0) return `${m}m`;
  return m === 0 ? `${h}h` : `${h}h ${m}m`;
}

/** "9:00 PM" in the app's selected locale (pass `useLocale()`), not the browser's. */
export function formatClock(date: Date, locale: string | undefined): string {
  return new Intl.DateTimeFormat(locale, { hour: "numeric", minute: "2-digit" }).format(date);
}

/**
 * Whether the override is what the display shows right now. A plugin trigger
 * (a doorbell, a delivery) drives the PRIMARY display only and beats an
 * override, and while it shows the hub still reports the override as active
 * (H1 review carry). The card must not claim the override is on screen then.
 */
export function overrideOnScreen({
  overrideActive,
  isPrimary,
  triggerActive,
}: {
  overrideActive: boolean;
  isPrimary: boolean;
  triggerActive: boolean;
}): boolean {
  return overrideActive && !(isPrimary && triggerActive);
}
