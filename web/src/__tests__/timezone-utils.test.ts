import { describe, expect, it, vi } from "vitest";

import {
  formatLogTimestamp,
  formatLogTimestampFull,
  formatTimestampLocal,
  getTimezoneAbbreviation,
  getTimezoneOffsetString,
  localTimeToUTC,
  utcToLocalTime,
} from "@/lib/timezone-utils";

describe("timezone-utils", () => {
  describe("localTimeToUTC", () => {
    it("converts PST local time to UTC", () => {
      const result = localTimeToUTC("20:00", "America/Los_Angeles");
      // PST is UTC-8, so 20:00 PST = 04:00 UTC (next day during standard time)
      // The exact result depends on DST, but it should be a valid time format
      expect(result).toMatch(/^\d{2}:\d{2}\+00:00$/);
    });

    it("converts EST local time to UTC", () => {
      const result = localTimeToUTC("09:00", "America/New_York");
      expect(result).toMatch(/^\d{2}:\d{2}\+00:00$/);
    });

    it("handles midnight correctly", () => {
      const result = localTimeToUTC("00:00", "America/Los_Angeles");
      expect(result).toMatch(/^\d{2}:\d{2}\+00:00$/);
    });

    it("handles invalid time gracefully", () => {
      const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
      const result = localTimeToUTC("invalid", "America/Los_Angeles");
      // Should return fallback value when parsing fails
      expect(result).toBe("00:00+00:00");
      consoleSpy.mockRestore();
    });

    it("handles invalid timezone gracefully", () => {
      const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
      const result = localTimeToUTC("20:00", "Invalid/Timezone");
      // Should return fallback value when timezone is invalid
      expect(result).toBe("00:00+00:00");
      consoleSpy.mockRestore();
    });
  });

  describe("utcToLocalTime", () => {
    it("converts UTC time to PST local time", () => {
      const result = utcToLocalTime("04:00+00:00", "America/Los_Angeles");
      expect(result).toMatch(/^\d{2}:\d{2}$/);
    });

    it("converts UTC time to EST local time", () => {
      const result = utcToLocalTime("14:00+00:00", "America/New_York");
      expect(result).toMatch(/^\d{2}:\d{2}$/);
    });

    it("handles midnight UTC correctly", () => {
      const result = utcToLocalTime("00:00+00:00", "America/Los_Angeles");
      expect(result).toMatch(/^\d{2}:\d{2}$/);
    });

    it("handles negative offset format", () => {
      const result = utcToLocalTime("04:00-00:00", "America/Los_Angeles");
      expect(result).toMatch(/^\d{2}:\d{2}$/);
    });

    it("handles invalid UTC time gracefully", () => {
      const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
      const result = utcToLocalTime("invalid", "America/Los_Angeles");
      // Should return fallback time value
      expect(result).toBe("00:00");
      consoleSpy.mockRestore();
    });

    it("handles invalid timezone gracefully", () => {
      const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
      const result = utcToLocalTime("04:00+00:00", "Invalid/Timezone");
      // Should return fallback time value
      expect(result).toBe("00:00");
      consoleSpy.mockRestore();
    });
  });

  describe("formatTimestampLocal", () => {
    it("formats UTC timestamp to local timezone", () => {
      const result = formatTimestampLocal("2025-12-26T22:30:00+00:00", "America/Los_Angeles");
      expect(result).toContain("2025");
      expect(result).toContain("PST");
    });

    it("uses custom format string", () => {
      const result = formatTimestampLocal("2025-12-26T22:30:00+00:00", "America/Los_Angeles", "HH:mm:ss");
      expect(result).toMatch(/^\d{2}:\d{2}:\d{2}$/);
    });

    it("handles invalid timestamp gracefully", () => {
      const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
      const result = formatTimestampLocal("invalid", "America/Los_Angeles");
      expect(result).toBe("invalid");
      consoleSpy.mockRestore();
    });
  });

  describe("formatLogTimestamp", () => {
    it("formats timestamp as time only", () => {
      const result = formatLogTimestamp("2025-12-26T22:30:45+00:00", "America/Los_Angeles");
      expect(result).toMatch(/^\d{2}:\d{2}:\d{2}$/);
    });
  });

  describe("formatLogTimestampFull", () => {
    it("formats timestamp with full date", () => {
      const result = formatLogTimestampFull("2025-12-26T22:30:45+00:00", "America/Los_Angeles");
      expect(result).toContain("Dec");
      expect(result).toContain("2025");
      expect(result).toContain("PST");
    });
  });

  describe("getTimezoneAbbreviation", () => {
    it("returns PST for Pacific timezone", () => {
      const result = getTimezoneAbbreviation("America/Los_Angeles");
      // Could be PST or PDT depending on time of year
      expect(result).toMatch(/PST|PDT/);
    });

    it("returns EST for Eastern timezone", () => {
      const result = getTimezoneAbbreviation("America/New_York");
      expect(result).toMatch(/EST|EDT/);
    });

    it("handles invalid timezone gracefully", () => {
      const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
      const result = getTimezoneAbbreviation("Invalid/Timezone");
      expect(result).toBe("Invalid/Timezone");
      consoleSpy.mockRestore();
    });
  });

  describe("getTimezoneOffsetString", () => {
    it("returns UTC offset for PST", () => {
      const result = getTimezoneOffsetString("America/Los_Angeles");
      // PST is UTC-8 or UTC-7 (PDT)
      expect(result).toMatch(/UTC[+-]\d+/);
    });

    it("returns UTC offset for EST", () => {
      const result = getTimezoneOffsetString("America/New_York");
      // EST is UTC-5 or UTC-4 (EDT)
      expect(result).toMatch(/UTC[+-]\d+/);
    });

    it("returns UTC for UTC timezone", () => {
      const result = getTimezoneOffsetString("UTC");
      // UTC should have no offset or show as UTC or UTC+0
      expect(result).toMatch(/^UTC(\+0)?$/);
    });

    it("handles invalid timezone gracefully", () => {
      const result = getTimezoneOffsetString("Invalid/Timezone");
      // Should return UTC as fallback
      expect(result).toMatch(/^UTC/);
    });
  });

  describe("timezone conversions round-trip", () => {
    it("converts local -> UTC -> local and gets same result", () => {
      const timezone = "America/Los_Angeles";
      const originalTime = "14:30";

      const utcTime = localTimeToUTC(originalTime, timezone);
      const convertedBack = utcToLocalTime(utcTime, timezone);

      expect(convertedBack).toBe(originalTime);
    });

    it("works for different timezones", () => {
      const testCases = [
        { time: "09:00", timezone: "America/New_York" },
        { time: "15:45", timezone: "Europe/London" },
        { time: "23:59", timezone: "Asia/Tokyo" },
      ];

      testCases.forEach(({ time, timezone }) => {
        const utcTime = localTimeToUTC(time, timezone);
        const convertedBack = utcToLocalTime(utcTime, timezone);
        expect(convertedBack).toBe(time);
      });
    });
  });
});
