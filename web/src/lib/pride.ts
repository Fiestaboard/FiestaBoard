/**
 * Single source of truth for whether Pride Month UI flourishes are
 * active — combines the calendar (June) with the opt-out cookie set
 * by Settings → Advanced → Festive Months.
 *
 * Both the CSS gate (`pride-month` class on `<html>`, applied by
 * `web/app/root.tsx::Layout`) and the JS gate (`usePrideActive`,
 * which reads the same logic) derive from this function so the
 * cookie toggle reliably hides everything.
 */

export const HIDE_FESTIVE_COOKIE = "hide_festive_months";

const PRIDE_MONTH_INDEX = 5; // June (Date.getMonth is 0-indexed)

export function shouldShowPride(now: Date = new Date(), cookieString = ""): boolean {
  if (now.getMonth() !== PRIDE_MONTH_INDEX) return false;
  const optedOut = cookieString.split("; ").some((c) => c === `${HIDE_FESTIVE_COOKIE}=true`);
  return !optedOut;
}

export function readCookieString(): string {
  return typeof document !== "undefined" ? document.cookie : "";
}
