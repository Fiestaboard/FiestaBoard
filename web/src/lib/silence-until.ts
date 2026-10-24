import type { SilenceStatus } from "@/lib/api";

/**
 * The instant the board's current silence window ends, or null (#1943).
 *
 * Prefers the server's `ends_at_utc`; an older API without it still reports
 * `seconds_until_next_change`, which counts down to the same boundary. Null
 * when the board is not silenced, so callers never quote a time for a window
 * that is not running.
 */
export function silenceEndsAt(status?: SilenceStatus | null, now: number = Date.now()): Date | null {
  if (!status?.active) return null;
  if (status.ends_at_utc) {
    const at = new Date(status.ends_at_utc);
    if (!Number.isNaN(at.getTime())) return at;
  }
  if (
    typeof status.seconds_until_next_change === "number" &&
    Number.isFinite(status.seconds_until_next_change) &&
    status.seconds_until_next_change >= 0
  ) {
    return new Date(now + status.seconds_until_next_change * 1000);
  }
  return null;
}

/**
 * "7:00 AM" / "07:00" — when silence ends, in the viewer's own locale and
 * time zone. Every silence notice, toast and button reads its time from here
 * so they can never disagree.
 */
export function silenceEndsAtLabel(
  status?: SilenceStatus | null,
  now: number = Date.now(),
  locale?: string,
): string | null {
  const at = silenceEndsAt(status, now);
  return at ? at.toLocaleTimeString(locale, { hour: "numeric", minute: "2-digit" }) : null;
}
