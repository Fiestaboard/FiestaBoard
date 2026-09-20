// "5 minutes ago" / "last month" for a timestamp, in the UI's language.
//
// Intl.RelativeTimeFormat speaks every locale the app ships without a
// per-language table, which is why this is not date-fns's
// formatDistanceToNow (that one needs a locale object imported per
// language). `numeric: "auto"` gives "yesterday" / "last month" / "now"
// where the language has such words, so no string here needs translating.

const UNITS: Array<[Intl.RelativeTimeFormatUnit, number]> = [
  ["year", 365 * 24 * 3600_000],
  ["month", 30 * 24 * 3600_000],
  ["week", 7 * 24 * 3600_000],
  ["day", 24 * 3600_000],
  ["hour", 3600_000],
  ["minute", 60_000],
];

/**
 * A relative phrase for `iso` as seen from `now`, in the largest whole
 * unit; inside a minute it is the language's word for "now". An
 * unparseable value is returned as-is rather than throwing — a list row
 * is not the place for a crash over one bad timestamp.
 */
export function formatRelativeTime(iso: string, locale: string, now: number = Date.now()): string {
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return iso;
  const elapsed = then - now; // negative in the past
  const magnitude = Math.abs(elapsed);
  let rtf: Intl.RelativeTimeFormat;
  try {
    rtf = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });
  } catch {
    rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  }
  for (const [unit, ms] of UNITS) {
    if (magnitude >= ms) return rtf.format(Math.round(elapsed / ms), unit);
  }
  return rtf.format(0, "second");
}
