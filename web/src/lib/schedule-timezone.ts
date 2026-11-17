/** A missing or invalid hub zone is an explicit UTC fallback, never the browser zone. */
export function scheduleTimezone(value: unknown): { zone: string; fallback: boolean } {
  if (typeof value === "string" && value) {
    try {
      new Intl.DateTimeFormat("en", { timeZone: value }).format();
      return { zone: value, fallback: false };
    } catch {
      /* Config may predate timezone validation. */
    }
  }
  return { zone: "UTC", fallback: true };
}
