import { startOfWeek } from "date-fns";
import { describe, expect, it } from "vitest";

import type { Carousel, Page, ScheduleEntry } from "@/lib/api";
import { api, CAROUSEL_ID_PREFIX, isCarouselId } from "@/lib/api";
import { scheduleToCalendarEvents } from "@/lib/schedule-calendar";

// =============================================================================
// isCarouselId utility
// =============================================================================

describe("isCarouselId", () => {
  it("returns true for carousel-prefixed IDs", () => {
    expect(isCarouselId("carousel:abc-123")).toBe(true);
    expect(isCarouselId("carousel:")).toBe(true);
  });

  it("returns false for regular page IDs", () => {
    expect(isCarouselId("abc-123")).toBe(false);
    expect(isCarouselId("page-uuid-here")).toBe(false);
  });

  it("returns false for empty string", () => {
    expect(isCarouselId("")).toBe(false);
  });

  it("returns false for undefined and null", () => {
    expect(isCarouselId(undefined)).toBe(false);
    expect(isCarouselId(null)).toBe(false);
  });
});

// =============================================================================
// CAROUSEL_ID_PREFIX constant
// =============================================================================

describe("CAROUSEL_ID_PREFIX", () => {
  it("equals 'carousel:'", () => {
    expect(CAROUSEL_ID_PREFIX).toBe("carousel:");
  });
});

// =============================================================================
// Carousel type shape
// =============================================================================

describe("Carousel type", () => {
  it("matches expected shape", () => {
    const carousel: Carousel = {
      id: "carousel:test-id",
      name: "Test Carousel",
      page_ids: ["p1", "p2", "p3"],
      interval_seconds: 30,
      created_at: "2025-01-01T00:00:00Z",
    };
    expect(carousel.id.startsWith("carousel:")).toBe(true);
    expect(carousel.page_ids).toHaveLength(3);
    expect(carousel.interval_seconds).toBe(30);
  });

  it("supports optional updated_at", () => {
    const carousel: Carousel = {
      id: "carousel:test-id",
      name: "Updated Carousel",
      page_ids: ["p1"],
      interval_seconds: 10,
      created_at: "2025-01-01T00:00:00Z",
      updated_at: "2025-06-01T00:00:00Z",
    };
    expect(carousel.updated_at).toBe("2025-06-01T00:00:00Z");
  });
});

// =============================================================================
// Calendar events with carousel names
// =============================================================================

const WEEK_START = startOfWeek(new Date(2025, 0, 5), { weekStartsOn: 0 });

const MOCK_PAGES: Page[] = [
  {
    id: "page1",
    name: "Page One",
    type: "template",
    device_type: "flagship",
    duration_seconds: 30,
    created_at: "2025-01-01T00:00:00Z",
  },
];

const MOCK_CAROUSELS: Carousel[] = [
  {
    id: "carousel:c1",
    name: "My Rotation",
    page_ids: ["page1"],
    interval_seconds: 30,
    created_at: "2025-01-01T00:00:00Z",
  },
];

// =============================================================================
// Carousel API methods (through MSW)
// =============================================================================

describe("Carousel API methods", () => {
  it("getCarousels returns carousel list", async () => {
    const result = await api.getCarousels();
    expect(result).toHaveProperty("carousels");
    expect(result).toHaveProperty("total");
    expect(Array.isArray(result.carousels)).toBe(true);
  });
});

// =============================================================================
// Calendar events with carousel names
// =============================================================================

describe("scheduleToCalendarEvents with carousels", () => {
  it("resolves carousel name when carousels array is provided", () => {
    const schedule: ScheduleEntry = {
      id: "sched-1",
      page_id: "carousel:c1",
      start_time: "09:00",
      end_time: "17:00",
      day_pattern: "all",
      enabled: true,
      created_at: "2025-01-01T00:00:00Z",
    };

    const events = scheduleToCalendarEvents(schedule, WEEK_START, MOCK_PAGES, MOCK_CAROUSELS);
    expect(events.length).toBeGreaterThan(0);
    expect(events[0].title).toBe("My Rotation");
  });

  it("falls back to raw ID when carousel is not found", () => {
    const schedule: ScheduleEntry = {
      id: "sched-2",
      page_id: "carousel:unknown",
      start_time: "10:00",
      end_time: "11:00",
      day_pattern: "weekdays",
      enabled: true,
      created_at: "2025-01-01T00:00:00Z",
    };

    const events = scheduleToCalendarEvents(schedule, WEEK_START, MOCK_PAGES, MOCK_CAROUSELS);
    expect(events.length).toBeGreaterThan(0);
    expect(events[0].title).toBe("carousel:unknown");
  });

  it("resolves regular page name without carousels", () => {
    const schedule: ScheduleEntry = {
      id: "sched-3",
      page_id: "page1",
      start_time: "09:00",
      end_time: "17:00",
      day_pattern: "all",
      enabled: true,
      created_at: "2025-01-01T00:00:00Z",
    };

    const events = scheduleToCalendarEvents(schedule, WEEK_START, MOCK_PAGES);
    expect(events.length).toBeGreaterThan(0);
    expect(events[0].title).toBe("Page One");
  });
});
