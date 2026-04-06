"use client";

import { createContext, useContext, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { format, parse, parseISO, isValid } from "date-fns";
import { api } from "@/lib/api";

export type TimeFormat = "12h" | "24h";
export type DateFormat = "MM/DD/YYYY" | "DD/MM/YYYY" | "YYYY-MM-DD";

interface FormatPreferencesContextValue {
  timeFormat: TimeFormat;
  dateFormat: DateFormat;
  /** Format a Date or HH:MM string as a human-readable time string */
  formatTime: (value: Date | string) => string;
  /** Format a Date or ISO date string as a human-readable date string */
  formatDate: (value: Date | string) => string;
  /** Format a Date or ISO datetime string as date + time */
  formatDateTime: (value: Date | string) => string;
}

const FormatPreferencesContext = createContext<FormatPreferencesContextValue>({
  timeFormat: "12h",
  dateFormat: "MM/DD/YYYY",
  formatTime: (v) => (typeof v === "string" ? v : v.toLocaleTimeString()),
  formatDate: (v) => (typeof v === "string" ? v : v.toLocaleDateString()),
  formatDateTime: (v) => (typeof v === "string" ? v : v.toLocaleString()),
});

function toDate(value: Date | string): Date | null {
  if (value instanceof Date) return isValid(value) ? value : null;
  // HH:MM string (e.g. from time pickers / API time fields)
  if (/^\d{1,2}:\d{2}$/.test(value)) {
    const parsed = parse(value, "HH:mm", new Date());
    return isValid(parsed) ? parsed : null;
  }
  // ISO string
  try {
    const parsed = parseISO(value);
    return isValid(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

function buildFormatters(timeFormat: TimeFormat, dateFormat: DateFormat) {
  const timePattern = timeFormat === "24h" ? "HH:mm" : "h:mm a";
  const timePatternLong = timeFormat === "24h" ? "HH:mm:ss" : "h:mm:ss a";

  const dateFnsPattern =
    dateFormat === "DD/MM/YYYY"
      ? "dd/MM/yyyy"
      : dateFormat === "YYYY-MM-DD"
        ? "yyyy-MM-dd"
        : "MM/dd/yyyy";

  function formatTime(value: Date | string): string {
    const d = toDate(value);
    if (!d) return typeof value === "string" ? value : "";
    return format(d, timePattern);
  }

  function formatTimeLong(value: Date | string): string {
    const d = toDate(value);
    if (!d) return typeof value === "string" ? value : "";
    return format(d, timePatternLong);
  }

  function formatDate(value: Date | string): string {
    const d = toDate(value);
    if (!d) return typeof value === "string" ? value : "";
    return format(d, dateFnsPattern);
  }

  function formatDateTime(value: Date | string): string {
    const d = toDate(value);
    if (!d) return typeof value === "string" ? value : "";
    return `${format(d, dateFnsPattern)} ${format(d, timePattern)}`;
  }

  return { formatTime, formatTimeLong, formatDate, formatDateTime, timePattern, dateFnsPattern };
}

export function FormatPreferencesProvider({ children }: { children: React.ReactNode }) {
  const { data: allSettings } = useQuery({
    queryKey: ["all-settings"],
    queryFn: api.getAllSettings,
    staleTime: 1000 * 60 * 5,
  });

  const timeFormat: TimeFormat = (allSettings?.general?.time_format as TimeFormat) ?? "12h";
  const dateFormat: DateFormat = (allSettings?.general?.date_format as DateFormat) ?? "MM/DD/YYYY";

  const value = useMemo<FormatPreferencesContextValue>(() => {
    const { formatTime, formatDate, formatDateTime } = buildFormatters(timeFormat, dateFormat);
    return { timeFormat, dateFormat, formatTime, formatDate, formatDateTime };
  }, [timeFormat, dateFormat]);

  return (
    <FormatPreferencesContext.Provider value={value}>
      {children}
    </FormatPreferencesContext.Provider>
  );
}

export function useFormatPreferences() {
  return useContext(FormatPreferencesContext);
}

/** Standalone helper — usable outside React (e.g. in calendar localizer configs) */
export { buildFormatters };
