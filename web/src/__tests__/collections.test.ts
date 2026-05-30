import { startOfWeek } from "date-fns";
import { describe, expect, it } from "vitest";

import type { Collection, Page, ScheduleEntry } from "@/lib/api";
import { api, COLLECTION_ID_PREFIX, isCollectionId } from "@/lib/api";
import { scheduleToCalendarEvents } from "@/lib/schedule-calendar";

// =============================================================================
// isCollectionId utility
// =============================================================================

describe("isCollectionId", () => {
  it("returns true for collection-prefixed IDs", () => {
    expect(isCollectionId("collection:abc-123")).toBe(true);
    expect(isCollectionId("collection:")).toBe(true);
  });

  it("returns false for regular page IDs", () => {
    expect(isCollectionId("abc-123")).toBe(false);
    expect(isCollectionId("page-uuid-here")).toBe(false);
  });

  it("returns false for empty string", () => {
    expect(isCollectionId("")).toBe(false);
  });

  it("returns false for undefined and null", () => {
    expect(isCollectionId(undefined)).toBe(false);
    expect(isCollectionId(null)).toBe(false);
  });
});

// =============================================================================
// COLLECTION_ID_PREFIX constant
// =============================================================================

describe("COLLECTION_ID_PREFIX", () => {
  it("equals 'collection:'", () => {
    expect(COLLECTION_ID_PREFIX).toBe("collection:");
  });
});

// =============================================================================
// Collection type shape
// =============================================================================

describe("Collection type", () => {
  it("matches expected shape (time mode)", () => {
    const collection: Collection = {
      id: "collection:test-id",
      name: "Test Collection",
      page_ids: ["p1", "p2", "p3"],
      selection_mode: "time",
      time: { interval_seconds: 30 },
      variable: null,
      created_at: "2025-01-01T00:00:00Z",
    };
    expect(collection.id.startsWith("collection:")).toBe(true);
    expect(collection.page_ids).toHaveLength(3);
    expect(collection.time.interval_seconds).toBe(30);
  });

  it("supports optional updated_at and variable mode", () => {
    const collection: Collection = {
      id: "collection:test-id",
      name: "Updated Collection",
      page_ids: ["p1", "p2"],
      selection_mode: "variable",
      time: { interval_seconds: 30 },
      variable: {
        rules: [{ expression: "weather.temp > 70", page_id: "p1" }],
        default_page_id: "p2",
        poll_seconds: 10,
      },
      created_at: "2025-01-01T00:00:00Z",
      updated_at: "2025-06-01T00:00:00Z",
    };
    expect(collection.updated_at).toBe("2025-06-01T00:00:00Z");
    expect(collection.variable?.default_page_id).toBe("p2");
    expect(collection.variable?.rules).toHaveLength(1);
  });
});

// =============================================================================
// Calendar events with collection names
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

const MOCK_COLLECTIONS: Collection[] = [
  {
    id: "collection:c1",
    name: "My Rotation",
    page_ids: ["page1"],
    selection_mode: "time",
    time: { interval_seconds: 30 },
    variable: null,
    created_at: "2025-01-01T00:00:00Z",
  },
];

// =============================================================================
// Collection API methods (through MSW)
// =============================================================================

describe("Collection API methods", () => {
  it("getCollections returns collection list", async () => {
    const result = await api.getCollections();
    expect(result).toHaveProperty("collections");
    expect(result).toHaveProperty("total");
    expect(Array.isArray(result.collections)).toBe(true);
  });
});

// =============================================================================
// Calendar events with collection names
// =============================================================================

describe("scheduleToCalendarEvents with collections", () => {
  it("resolves collection name when collections array is provided", () => {
    const schedule: ScheduleEntry = {
      id: "sched-1",
      page_id: "collection:c1",
      start_time: "09:00",
      end_time: "17:00",
      day_pattern: "all",
      enabled: true,
      created_at: "2025-01-01T00:00:00Z",
    };

    const events = scheduleToCalendarEvents(schedule, WEEK_START, MOCK_PAGES, MOCK_COLLECTIONS);
    expect(events.length).toBeGreaterThan(0);
    expect(events[0].title).toBe("My Rotation");
  });

  it("falls back to raw ID when collection is not found", () => {
    const schedule: ScheduleEntry = {
      id: "sched-2",
      page_id: "collection:unknown",
      start_time: "10:00",
      end_time: "11:00",
      day_pattern: "weekdays",
      enabled: true,
      created_at: "2025-01-01T00:00:00Z",
    };

    const events = scheduleToCalendarEvents(schedule, WEEK_START, MOCK_PAGES, MOCK_COLLECTIONS);
    expect(events.length).toBeGreaterThan(0);
    expect(events[0].title).toBe("collection:unknown");
  });

  it("resolves regular page name without collections", () => {
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
