import { useEffect, useState } from "react";

/**
 * When an edit was saved, the way Docs says it (UX-1-3): "just now", "2 min
 * ago" within the hour, "6:15 AM" today, "yesterday 7:16 AM", else
 * "Nov 20, 7:16 AM". One helper for every "Saved …" / "Draft saved …" the
 * editor shows; `editTimeTitle` is the full timestamp for a `title`.
 */
export interface EditTimeWords {
  justNow: () => string;
  minutesAgo: (count: number) => string;
  yesterday: (time: string) => string;
}

const MINUTE = 60_000;

function clock(date: Date, locale: string): string {
  return date.toLocaleTimeString(locale, { hour: "numeric", minute: "2-digit" });
}

function startOfDay(date: Date): number {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
}

export function formatEditTime(
  at: Date | string,
  { locale, now = new Date(), words }: { locale: string; now?: Date; words: EditTimeWords },
): string {
  const date = typeof at === "string" ? new Date(at) : at;
  if (Number.isNaN(date.getTime())) return typeof at === "string" ? at : "";
  const elapsed = now.getTime() - date.getTime();
  // A clock a little ahead of the hub's still reads "just now".
  if (elapsed < MINUTE) return words.justNow();
  if (elapsed < 60 * MINUTE) return words.minutesAgo(Math.floor(elapsed / MINUTE));
  const days = Math.round((startOfDay(now) - startOfDay(date)) / (24 * 60 * MINUTE));
  if (days === 0) return clock(date, locale);
  if (days === 1) return words.yesterday(clock(date, locale));
  return date.toLocaleString(locale, {
    month: "short",
    day: "numeric",
    ...(date.getFullYear() !== now.getFullYear() && { year: "numeric" }),
    hour: "numeric",
    minute: "2-digit",
  });
}

/** The full timestamp, for the `title` of a relative time. */
export function editTimeTitle(at: Date | string, locale: string): string {
  const date = typeof at === "string" ? new Date(at) : at;
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString(locale, { dateStyle: "full", timeStyle: "short" });
}

/** The current time, re-read every `intervalMs`, so "2 min ago" keeps counting. */
export function useNow(intervalMs = 30_000): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), intervalMs);
    return () => clearInterval(timer);
  }, [intervalMs]);
  return now;
}
