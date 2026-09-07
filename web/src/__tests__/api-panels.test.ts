import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import type { Panel, PanelFrame, PanelPublicConfig } from "@/lib/api";
import { api } from "@/lib/api";

import { server } from "./mocks/server";

const PANEL: Panel = {
  id: "abc123def456",
  short_code: 1,
  name: "Living Room TV",
  board_id: "vboard-1",
  screen_diagonal_inches: 55,
  calibration_scale: 1,
  animations_enabled: true,
  is_display: false,
  backdrop: "wall",
  auto_dim: { enabled: false, start: "22:00", end: "07:00" },
  created_at: "2026-08-25T00:00:00+00:00",
  updated_at: "2026-08-25T00:00:00+00:00",
  device_type: "note_array",
  board_missing: false,
  rows: 12,
  cols: 30,
};

describe("panels API client", () => {
  it("listPanels GETs /api/panels", async () => {
    server.use(http.get("/api/panels", () => HttpResponse.json({ panels: [PANEL], total: 1 })));
    const result = await api.listPanels();
    expect(result.total).toBe(1);
    expect(result.panels[0].name).toBe("Living Room TV");
  });

  it("createPanel POSTs the name and screen size and returns the created panel", async () => {
    let body: unknown;
    server.use(
      http.post("/api/panels", async ({ request }) => {
        body = await request.json();
        // 201 with the bare panel (Phase 2 slice 8).
        return HttpResponse.json(PANEL, { status: 201 });
      }),
    );
    const result = await api.createPanel({
      name: "Living Room TV",
      screen_diagonal_inches: 55,
    });
    expect(result.id).toBe("abc123def456");
    expect(result.name).toBe("Living Room TV");
    expect(body).toEqual({
      name: "Living Room TV",
      screen_diagonal_inches: 55,
    });
  });

  it("updatePanel PATCHes only provided fields", async () => {
    let body: unknown;
    server.use(
      http.patch("/api/panels/abc123def456", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ ...PANEL, incompatible_references: null });
      }),
    );
    const result = await api.updatePanel("abc123def456", { calibration_scale: 1.05 });
    expect(body).toEqual({ calibration_scale: 1.05 });
    expect(result.id).toBe("abc123def456");
    expect(result.incompatible_references).toBeNull();
  });

  it("deletePanel DELETEs the panel and reports the id that is gone", async () => {
    let called = false;
    server.use(
      http.delete("/api/panels/abc123def456", () => {
        called = true;
        return HttpResponse.json({ id: "abc123def456" });
      }),
    );
    const result = await api.deletePanel("abc123def456");
    expect(called).toBe(true);
    expect(result.id).toBe("abc123def456");
  });

  it("getPanel GETs the public viewer config", async () => {
    const config: PanelPublicConfig = {
      ...PANEL,
      board_color: "black",
      code62_glyph: "degree",
    };
    server.use(http.get("/api/panel/abc123def456", () => HttpResponse.json(config)));
    const result = await api.getPanel("abc123def456");
    expect(result.rows).toBe(12);
    expect(result.board_color).toBe("black");
  });

  it("getPanelFrame GETs the public frame", async () => {
    const frame: PanelFrame = {
      characters: [[1, 2, 3]],
      message: "ABC",
      rows: 6,
      cols: 22,
      updated_at: "2026-08-25T00:00:00+00:00",
    };
    server.use(http.get("/api/panel/abc123def456/frame", () => HttpResponse.json(frame)));
    const result = await api.getPanelFrame("abc123def456");
    expect(result.message).toBe("ABC");
  });

  it("getPanel surfaces the backend 404 detail", async () => {
    server.use(http.get("/api/panel/nope", () => HttpResponse.json({ detail: "Panel not found" }, { status: 404 })));
    await expect(api.getPanel("nope")).rejects.toThrow("Panel not found");
  });
});
