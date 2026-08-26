import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import type { Panel, PanelFrame, PanelPublicConfig } from "@/lib/api";
import { api } from "@/lib/api";

import { server } from "./mocks/server";

const PANEL: Panel = {
  id: "abc123def456",
  name: "Living Room TV",
  board_id: "vboard-1",
  screen_diagonal_inches: 55,
  calibration_scale: 1,
  backdrop: "wall",
  auto_dim: { enabled: false, start: "22:00", end: "07:00" },
  created_at: "2026-08-25T00:00:00+00:00",
  updated_at: "2026-08-25T00:00:00+00:00",
  device_type: "flagship",
  board_missing: false,
};

describe("panels API client", () => {
  it("listPanels GETs /api/panels", async () => {
    server.use(http.get("/api/panels", () => HttpResponse.json({ panels: [PANEL], total: 1 })));
    const result = await api.listPanels();
    expect(result.total).toBe(1);
    expect(result.panels[0].name).toBe("Living Room TV");
  });

  it("createPanel POSTs the chosen shape and size", async () => {
    let body: unknown;
    server.use(
      http.post("/api/panels", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ status: "success", panel: PANEL });
      }),
    );
    const result = await api.createPanel({
      name: "Living Room TV",
      device_type: "flagship",
      screen_diagonal_inches: 55,
    });
    expect(result.status).toBe("success");
    expect(body).toEqual({
      name: "Living Room TV",
      device_type: "flagship",
      screen_diagonal_inches: 55,
    });
  });

  it("updatePanel PATCHes only provided fields", async () => {
    let body: unknown;
    server.use(
      http.patch("/api/panels/abc123def456", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ status: "success", panel: PANEL });
      }),
    );
    await api.updatePanel("abc123def456", { calibration_scale: 1.05 });
    expect(body).toEqual({ calibration_scale: 1.05 });
  });

  it("deletePanel DELETEs the panel", async () => {
    let called = false;
    server.use(
      http.delete("/api/panels/abc123def456", () => {
        called = true;
        return HttpResponse.json({ status: "success" });
      }),
    );
    await api.deletePanel("abc123def456");
    expect(called).toBe(true);
  });

  it("getPanel GETs the public viewer config", async () => {
    const config: PanelPublicConfig = {
      ...PANEL,
      rows: 6,
      cols: 22,
      board_color: "black",
      code62_glyph: "degree",
    };
    server.use(http.get("/api/panel/abc123def456", () => HttpResponse.json(config)));
    const result = await api.getPanel("abc123def456");
    expect(result.rows).toBe(6);
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
