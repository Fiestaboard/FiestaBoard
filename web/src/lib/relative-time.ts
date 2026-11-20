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

// One formatter per locale: constructing Intl objects is the expensive part
// and a History list asks for the same locale on every row.
const formatters = new Map<string, Intl.RelativeTimeFormat>();

function formatterFor(locale: string): Intl.RelativeTimeFormat {
  let rtf = formatters.get(locale);
  if (!rtf) {
    try {
      rtf = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });
    } catch {
      rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
    }
    formatters.set(locale, rtf);
  }
  return rtf;
}

/**
 * A relative phrase for `iso` as seen from `now`. The unit is chosen
 * *after* rounding — the largest unit that rounds to at least one — so
 * 59 minutes 40 seconds reads "1 hour ago", not "60 minutes ago"; inside
 * half a minute it is the language's word for "now". An unparseable value
 * is returned as-is rather than throwing — a list row is not the place
 * for a crash over one bad timestamp.
 */
export function formatRelativeTime(iso: string, locale: string, now: number = Date.now()): string {
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return iso;
  const elapsed = then - now; // negative in the past
  const sign = elapsed < 0 ? -1 : 1;
  const magnitude = Math.abs(elapsed);
  const rtf = formatterFor(locale);
  for (const [unit, ms] of UNITS) {
    const count = Math.round(magnitude / ms);
    if (count >= 1) return rtf.format(sign * count, unit);
  }
  return rtf.format(0, "second");
}

function startOfDay(ms: number): number {
  const d = new Date(ms);
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
}

/**
 * A clock-style time for a session row (07e `322:31855`): "just now",
 * "5:38 PM" (today; "today, 5:38 PM" with `nameToday`), "yesterday,
 * 9:12 PM", then the date alone ("Nov 2", with the year once it is not this
 * year's). Day words come from Intl ("yesterday" / "today" in every locale);
 * "just now" and the day-and-time joiner come from the caller's messages.
 */
export function formatSessionTime(
  iso: string,
  locale: string,
  labels: { justNow: string; dayTime: (day: string, time: string) => string },
  { now = Date.now(), nameToday = false }: { now?: number; nameToday?: boolean } = {},
): string {
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return iso;
  if (Math.abs(now - then) < 60_000) return labels.justNow;
  let time: string;
  let date: string;
  try {
    time = new Intl.DateTimeFormat(locale, { hour: "numeric", minute: "2-digit" }).format(then);
    date = new Intl.DateTimeFormat(locale, {
      month: "short",
      day: "numeric",
      year: new Date(then).getFullYear() === new Date(now).getFullYear() ? undefined : "numeric",
    }).format(then);
  } catch {
    return formatSessionTime(iso, "en", labels, { now, nameToday });
  }
  const days = Math.round((startOfDay(now) - startOfDay(then)) / (24 * 3600_000));
  if (days === 0) return nameToday ? labels.dayTime(formatterFor(locale).format(0, "day"), time) : time;
  if (days === 1) return labels.dayTime(formatterFor(locale).format(-1, "day"), time);
  return date;
}
