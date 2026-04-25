import { describe, it, expect } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  buildFormatters,
  FormatPreferencesProvider,
  useFormatPreferences,
} from "@/hooks/use-format-preferences";

// ---------------------------------------------------------------------------
// buildFormatters — pure helper, no React needed
// ---------------------------------------------------------------------------

describe("buildFormatters", () => {
  describe("12h time format with MM/DD/YYYY dates", () => {
    const { formatTime, formatDate, formatDateTime } = buildFormatters(
      "12h",
      "MM/DD/YYYY"
    );

    it("formats a Date object as 12h time", () => {
      const d = new Date(2024, 0, 15, 14, 30, 0); // 2:30 PM
      expect(formatTime(d)).toBe("2:30 PM");
    });

    it("formats an HH:MM string as 12h time", () => {
      expect(formatTime("14:30")).toBe("2:30 PM");
      expect(formatTime("08:05")).toBe("8:05 AM");
    });

    it("returns the original string when value is not a valid date", () => {
      expect(formatTime("not-a-time")).toBe("not-a-time");
    });

    it("returns empty string when given an invalid Date", () => {
      expect(formatTime(new Date("invalid"))).toBe("");
    });

    it("formats a Date as MM/DD/YYYY", () => {
      const d = new Date(2024, 0, 15);
      expect(formatDate(d)).toBe("01/15/2024");
    });

    it("formats an ISO string as MM/DD/YYYY date", () => {
      expect(formatDate("2024-06-20T12:00:00Z")).toContain("2024");
    });

    it("returns original string for invalid date in formatDate", () => {
      expect(formatDate("not-a-date")).toBe("not-a-date");
    });

    it("returns empty string for invalid Date in formatDate", () => {
      expect(formatDate(new Date("invalid"))).toBe("");
    });

    it("formats a Date as datetime", () => {
      const d = new Date(2024, 0, 15, 14, 30, 0);
      const result = formatDateTime(d);
      expect(result).toContain("01/15/2024");
      expect(result).toContain("2:30 PM");
    });

    it("returns original string for invalid value in formatDateTime", () => {
      expect(formatDateTime("bad-value")).toBe("bad-value");
    });

    it("returns empty string for invalid Date in formatDateTime", () => {
      expect(formatDateTime(new Date("invalid"))).toBe("");
    });
  });

  describe("24h time format", () => {
    const { formatTime, formatTimeLong, formatDateTime } = buildFormatters(
      "24h",
      "MM/DD/YYYY"
    );

    it("formats a Date object as 24h time", () => {
      const d = new Date(2024, 0, 15, 14, 30, 0);
      expect(formatTime(d)).toBe("14:30");
    });

    it("formats an HH:MM string in 24h", () => {
      expect(formatTime("09:05")).toBe("09:05");
    });

    it("formats a Date as 24h long time (with seconds)", () => {
      const d = new Date(2024, 0, 15, 14, 30, 45);
      expect(formatTimeLong(d)).toBe("14:30:45");
    });

    it("includes 24h time in formatDateTime", () => {
      const d = new Date(2024, 0, 15, 14, 30, 0);
      expect(formatDateTime(d)).toContain("14:30");
    });
  });

  describe("formatTimeLong in 12h mode", () => {
    const { formatTimeLong } = buildFormatters("12h", "MM/DD/YYYY");

    it("formats a Date as 12h long time (with seconds)", () => {
      const d = new Date(2024, 0, 15, 14, 30, 45);
      expect(formatTimeLong(d)).toBe("2:30:45 PM");
    });

    it("returns original string for invalid value", () => {
      expect(formatTimeLong("bad")).toBe("bad");
    });

    it("returns empty string for invalid Date", () => {
      expect(formatTimeLong(new Date("invalid"))).toBe("");
    });
  });

  describe("DD/MM/YYYY date format", () => {
    const { formatDate } = buildFormatters("12h", "DD/MM/YYYY");

    it("formats a Date as DD/MM/YYYY", () => {
      const d = new Date(2024, 0, 15);
      expect(formatDate(d)).toBe("15/01/2024");
    });
  });

  describe("YYYY-MM-DD date format", () => {
    const { formatDate } = buildFormatters("12h", "YYYY-MM-DD");

    it("formats a Date as YYYY-MM-DD", () => {
      const d = new Date(2024, 0, 15);
      expect(formatDate(d)).toBe("2024-01-15");
    });
  });
});

// ---------------------------------------------------------------------------
// FormatPreferencesProvider + useFormatPreferences
// ---------------------------------------------------------------------------

function Consumer() {
  const { timeFormat, dateFormat, formatTime, formatDate, formatDateTime } =
    useFormatPreferences();
  return (
    <div>
      <span data-testid="time-format">{timeFormat}</span>
      <span data-testid="date-format">{dateFormat}</span>
      <span data-testid="formatted-time">{formatTime("14:30")}</span>
      <span data-testid="formatted-date">{formatDate("2024-01-15")}</span>
      <span data-testid="formatted-datetime">
        {formatDateTime(new Date(2024, 0, 15, 9, 0, 0))}
      </span>
    </div>
  );
}

function Wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return (
    <QueryClientProvider client={qc}>
      <FormatPreferencesProvider>{children}</FormatPreferencesProvider>
    </QueryClientProvider>
  );
}

describe("FormatPreferencesProvider", () => {
  it("provides default 12h / MM/DD/YYYY format values via context", async () => {
    render(<Consumer />, { wrapper: Wrapper });

    // MSW mock doesn't include time_format/date_format so defaults kick in
    await waitFor(() => {
      expect(screen.getByTestId("time-format").textContent).toBe("12h");
      expect(screen.getByTestId("date-format").textContent).toBe("MM/DD/YYYY");
    });
  });

  it("formatTime uses 12h format via context", async () => {
    render(<Consumer />, { wrapper: Wrapper });

    await waitFor(() => {
      expect(screen.getByTestId("formatted-time").textContent).toBe("2:30 PM");
    });
  });

  it("formatDate uses MM/DD/YYYY format via context", async () => {
    render(<Consumer />, { wrapper: Wrapper });

    await waitFor(() => {
      // ISO date string "2024-01-15" formatted as MM/DD/YYYY
      expect(screen.getByTestId("formatted-date").textContent).toContain("2024");
    });
  });

  it("formatDateTime produces a combined date+time string via context", async () => {
    render(<Consumer />, { wrapper: Wrapper });

    await waitFor(() => {
      const result = screen.getByTestId("formatted-datetime").textContent ?? "";
      expect(result).toContain("2024");
      expect(result).toContain("AM");
    });
  });
});

describe("useFormatPreferences outside provider (context defaults)", () => {
  function BareConsumer() {
    const { timeFormat, dateFormat } = useFormatPreferences();
    return (
      <div>
        <span data-testid="tf">{timeFormat}</span>
        <span data-testid="df">{dateFormat}</span>
      </div>
    );
  }

  it("returns default values when used outside the provider", () => {
    render(<BareConsumer />);
    expect(screen.getByTestId("tf").textContent).toBe("12h");
    expect(screen.getByTestId("df").textContent).toBe("MM/DD/YYYY");
  });
});
