/**
 * Times the out-of-sync banner writes (issue #1945), in the app's locale and
 * the viewer's own zone.
 */

/**
 * When the silence window ends, as a Date. `/silence-status` reports
 * `end_time_utc` as a UTC wall time ("07:00+00:00"); a full ISO timestamp is
 * accepted too. Null when it cannot be read.
 */
export function silenceEndDate(endTimeUtc: string | null | undefined, now: Date = new Date()): Date | null {
  if (!endTimeUtc) return null;
  const wallTime = /^(\d{1,2}):(\d{2})(?::\d{2})?(?:Z|[+-]00:?00)?$/.exec(endTimeUtc.trim());
  if (wallTime) {
    const hours = Number(wallTime[1]);
    const minutes = Number(wallTime[2]);
    if (hours > 23 || minutes > 59) return null;
    return new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate(), hours, minutes));
  }
  const parsed = new Date(endTimeUtc);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

/** "7:00 AM" / "07:00" — the end of silence, short time in *locale*. */
export function formatSilenceEnd(endTimeUtc: string | null | undefined, locale: string): string {
  const end = silenceEndDate(endTimeUtc);
  return end ? new Intl.DateTimeFormat(locale, { timeStyle: "short" }).format(end) : (endTimeUtc ?? "");
}

function sameLocalDay(a: Date, b: Date): boolean {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

/**
 * When another app wrote to the board: the short time when that was today in
 * the viewer's zone, else the medium date and short time.
 */
export function formatDetectedAt(iso: string | null | undefined, locale: string, now: Date = new Date()): string {
  if (!iso) return "";
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return iso;
  const options: Intl.DateTimeFormatOptions = sameLocalDay(at, now)
    ? { timeStyle: "short" }
    : { dateStyle: "medium", timeStyle: "short" };
  return new Intl.DateTimeFormat(locale, options).format(at);
}
