import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { api } from "@/lib/api";

import { server } from "./mocks/server";

describe("Schedule H8 transport", () => {
  it("asks the hub for the selected display at the exact instant", async () => {
    let received = "";
    server.use(
      http.get("/api/schedules/active/page", ({ request }) => {
        received = request.url;
        return HttpResponse.json({ page_id: "hub-winner", at: "2026-11-17T15:00:00Z", silenced: true });
      }),
    );
    const result = await api.getActiveSchedule("board/2", "2026-11-17T15:00:00Z");
    expect(new URL(received).searchParams.get("board_id")).toBe("board/2");
    expect(new URL(received).searchParams.get("at")).toBe("2026-11-17T15:00:00Z");
    expect(result.page_id).toBe("hub-winner");
    expect(result.silenced).toBe(true);
  });
  it("runs a cached collection dry run with the same instant and sample values", async () => {
    let received: unknown;
    server.use(
      http.post("/api/collections/collection%3Atest/dry-run", async ({ request }) => {
        received = await request.json();
        return HttpResponse.json({ page_id: "rule-winner", rules: [{ matched: true }], timeline: [] });
      }),
    );
    const result = await api.dryRunCollection("collection:test", {
      at: "2026-11-17T15:00:00Z",
      values: { weather: { temp: 70 } },
      window_seconds: 86400,
    });
    expect(received).toEqual({
      at: "2026-11-17T15:00:00Z",
      data: "cached",
      values: { weather: { temp: 70 } },
      window_seconds: 86400,
    });
    expect(result.page_id).toBe("rule-winner");
  });
});

it("renders an H8 template preview at the same instant without calling the live send endpoint", async () => {
  let body: Record<string, unknown> = {};
  server.use(
    http.post("/api/templates/render", async ({ request }) => {
      body = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json({ lines: ["FUTURE"], rendered: "FUTURE", line_count: 1 });
    }),
  );
  const preview = await api.previewSchedulePage(
    { template: ["{{NOW()}}"], device_type: "panel", grid_rows: 8, grid_cols: 32 } as import("@/lib/api").Page,
    "2026-11-17T15:00:00Z",
    "display-2",
  );
  expect(body.preview).toEqual({ at: "2026-11-17T15:00:00Z", data: "cached" });
  expect(body.board_id).toBe("display-2");
  expect(body.grid_rows).toBe(8);
  expect(preview.lines).toEqual(["FUTURE"]);
});
