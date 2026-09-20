/**
 * The templates API client carries note-array geometry (issue #2032).
 *
 * A note array has no fixed grid: it is `notes_wide` x `notes_tall` Notes, so
 * 15*notes_wide columns by 3*notes_tall rows. The render endpoints fall back to
 * a single 3x15 Note when that geometry is absent from the body, so a
 * `{{filled:-}}` line came back 15 tiles wide in the editor's preview pane
 * while the same page, sent to the board, filled all 30.
 */
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { api } from "@/lib/api";

import { server } from "./mocks/server";

const API_BASE = "/api";

describe("templates API client note-array geometry", () => {
  it("renderTemplate sends notes_wide and notes_tall", async () => {
    let body: unknown;
    server.use(
      http.post(`${API_BASE}/templates/render`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ rendered: "", lines: [""], line_count: 1 });
      }),
    );

    await api.renderTemplate(["{{filled:-}}"], undefined, "note_array", 2, 1);

    expect(body).toEqual({
      template: ["{{filled:-}}"],
      device_type: "note_array",
      notes_wide: 2,
      notes_tall: 1,
    });
  });

  it("renderTemplate omits the geometry when the caller has none", async () => {
    let body: unknown;
    server.use(
      http.post(`${API_BASE}/templates/render`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ rendered: "", lines: [""], line_count: 1 });
      }),
    );

    await api.renderTemplate(["HI"], undefined, "flagship");

    expect(body).toEqual({ template: ["HI"], device_type: "flagship" });
  });

  it("renderTemplateLive sends notes_wide and notes_tall alongside the board id", async () => {
    let body: unknown;
    server.use(
      http.post(`${API_BASE}/templates/render/live`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({
          rendered: "",
          lines: [""],
          line_count: 1,
          sent_to_board: false,
          paused: false,
          board_id: "board-1",
        });
      }),
    );

    await api.renderTemplateLive(["{{filled:-}}"], "board-1", undefined, "note_array", 4, 2);

    expect(body).toEqual({
      template: ["{{filled:-}}"],
      board_id: "board-1",
      device_type: "note_array",
      notes_wide: 4,
      notes_tall: 2,
    });
  });

  it("renderTemplateLive still forwards its abort signal after the geometry arguments", async () => {
    const controller = new AbortController();
    server.use(
      http.post(`${API_BASE}/templates/render/live`, async () => {
        controller.abort();
        return HttpResponse.json({
          rendered: "",
          lines: [""],
          line_count: 1,
          sent_to_board: false,
          paused: false,
          board_id: null,
        });
      }),
    );

    await expect(
      api.renderTemplateLive(["HI"], undefined, undefined, "note_array", 2, 1, controller.signal),
    ).rejects.toThrow();
  });
});
