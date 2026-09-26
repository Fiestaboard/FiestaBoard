import { beforeEach, describe, expect, it } from "vitest";

import { clearRememberedToolDetails, rememberedToolDetail } from "@/hooks/use-target-caches";
import type { ToolCall } from "@/lib/ai-chat-types";
import { resolveToolDetail, type TargetCaches } from "@/lib/ai-target-names";

import enMessages from "../../messages/en.json";

// The English catalogue itself, so a renamed key fails here rather than
// silently changing what the card says.
const t = (key: string, params?: Record<string, unknown>): string => {
  const value = key
    .split(".")
    .reduce<unknown>((acc, part) => (acc as Record<string, unknown>)?.[part], enMessages.aiChatPanel);
  const text = typeof value === "string" ? value : key;
  return params ? text.replace(/\{(\w+)\}/g, (_m, name: string) => String(params[name] ?? "")) : text;
};

const SCHEDULE_ID = "289204ec-4306-41f0-b37b-4341cfe68783";

const CACHES: TargetCaches = {
  pages: {
    pages: [
      { id: "p-night", name: "Goodnight" },
      { id: "p-morning", name: "Weekend Good Morning" },
    ],
  },
  schedules: {
    schedules: [
      {
        id: SCHEDULE_ID,
        page_id: "p-night",
        start_time: "21:00",
        end_time: "23:00",
        day_pattern: "all",
        enabled: true,
      },
    ],
  },
  collections: { collections: [{ id: "c1", name: "Morning rotation" }] },
  plugins: { plugins: [{ id: "weather", name: "Weather" }] },
  panels: { panels: [{ id: "panel-1", name: "Kitchen TV" }] },
};

function call(name: string, args: Record<string, unknown>): Pick<ToolCall, "name" | "args"> {
  return { name, args };
}

describe("resolveToolDetail", () => {
  it("names a deleted schedule by its page, window and day pattern", () => {
    expect(resolveToolDetail(call("delete_schedule", { schedule_id: SCHEDULE_ID }), CACHES, t)).toBe(
      "Goodnight · 21:00–23:00 · every day",
    );
  });

  it("falls back to the raw id when the schedule cache has no match", () => {
    expect(resolveToolDetail(call("delete_schedule", { schedule_id: SCHEDULE_ID }), {}, t)).toBe(SCHEDULE_ID);
  });

  it("names a deleted page by its page name", () => {
    expect(resolveToolDetail(call("delete_page", { page_id: "p-morning" }), CACHES, t)).toBe("Weekend Good Morning");
  });

  it("falls back to the raw page id when the page cache is empty", () => {
    expect(resolveToolDetail(call("delete_page", { page_id: "p-morning" }), { pages: { pages: [] } }, t)).toBe(
      "p-morning",
    );
  });

  it("names a deleted collection by its collection name", () => {
    expect(resolveToolDetail(call("delete_collection", { collection_id: "c1" }), CACHES, t)).toBe("Morning rotation");
  });

  it("names an uninstalled plugin by its display name", () => {
    expect(resolveToolDetail(call("uninstall_plugin", { plugin_id: "weather" }), CACHES, t)).toBe("Weather");
  });

  it("names a deleted panel by its panel name", () => {
    expect(resolveToolDetail(call("delete_panel", { panel_id: "panel-1" }), CACHES, t)).toBe("Kitchen TV");
  });

  it("names a created schedule by the page it shows and its window", () => {
    expect(
      resolveToolDetail(
        call("create_schedule", { page_id: "p-morning", start_time: "07:00", end_time: "09:00", day_pattern: "all" }),
        CACHES,
        t,
      ),
    ).toBe("Weekend Good Morning · 07:00–09:00 · every day");
  });

  it("keeps the window when the schedule's page is gone from the cache", () => {
    const orphan: TargetCaches = { ...CACHES, pages: { pages: [] } };
    expect(resolveToolDetail(call("delete_schedule", { schedule_id: SCHEDULE_ID }), orphan, t)).toBe(
      "21:00–23:00 · every day",
    );
  });

  it("reads an open-ended schedule as a start time alone", () => {
    const openEnded: TargetCaches = {
      ...CACHES,
      schedules: {
        schedules: [{ id: "s2", page_id: "p-night", start_time: "21:00", day_pattern: "weekends", enabled: true }],
      },
    };
    expect(resolveToolDetail(call("delete_schedule", { schedule_id: "s2" }), openEnded, t)).toBe(
      "Goodnight · 21:00 · weekends",
    );
  });

  it("leaves a tool it knows nothing about to the plain detail", () => {
    expect(resolveToolDetail(call("send_message", { text: "HELLO" }), CACHES, t)).toBe("HELLO");
  });

  it("returns nothing for a tool with no detail at all", () => {
    expect(resolveToolDetail(call("list_pages", {}), CACHES, t)).toBeUndefined();
  });
});

describe("rememberedToolDetail", () => {
  beforeEach(() => {
    clearRememberedToolDetails();
  });

  it("keeps naming a target that the delete itself removed from the cache", () => {
    const deletion = { id: "tc9", ...call("delete_schedule", { schedule_id: SCHEDULE_ID }) };

    // While the approval card is up, the schedule is still there.
    expect(rememberedToolDetail(deletion, CACHES, t)).toBe("Goodnight · 21:00–23:00 · every day");

    // The delete runs; the schedules cache no longer holds it. The settled
    // card must not fall back to the uuid it just avoided showing.
    const afterDelete: TargetCaches = { ...CACHES, schedules: { schedules: [] } };
    expect(rememberedToolDetail(deletion, afterDelete, t)).toBe("Goodnight · 21:00–23:00 · every day");
  });

  it("still falls back to the id for a call it never managed to resolve", () => {
    const deletion = { id: "tc10", ...call("delete_schedule", { schedule_id: SCHEDULE_ID }) };
    expect(rememberedToolDetail(deletion, {}, t)).toBe(SCHEDULE_ID);
  });

  it("does not confuse two calls that touched different things", () => {
    const first = { id: "tc11", ...call("delete_page", { page_id: "p-night" }) };
    const second = { id: "tc12", ...call("delete_page", { page_id: "p-morning" }) };
    expect(rememberedToolDetail(first, CACHES, t)).toBe("Goodnight");
    expect(rememberedToolDetail(second, CACHES, t)).toBe("Weekend Good Morning");

    const emptied: TargetCaches = { pages: { pages: [] } };
    expect(rememberedToolDetail(first, emptied, t)).toBe("Goodnight");
    expect(rememberedToolDetail(second, emptied, t)).toBe("Weekend Good Morning");
  });
});
