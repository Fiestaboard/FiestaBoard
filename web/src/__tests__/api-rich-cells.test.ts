/**
 * The API client's types for the rich-cell fields the server added (plan D15/D17):
 *
 * - `POST /templates/render` with a `board_id` answers that board's
 *   `charset` and every `charset_issues` cell the board draws differently;
 * - `GET /panel/{id}/frame` carries `cells` (FiestaUI `BoardToken[][]` JSON)
 *   for a frame that has rich cells, and omits the key otherwise.
 */
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { api, type BoardTokenJson, type CharsetIssue, type PanelFrame } from "@/lib/api";

import { server } from "./mocks/server";

const API_BASE = "/api";

describe("rich-cell API fields", () => {
  it("renderTemplate sends board_id and returns the board's charset issues", async () => {
    let body: unknown;
    const issue: CharsetIssue = {
      row: 0,
      col: 1,
      token: { type: "char", value: "i" },
      reason: "case",
      fallback: { type: "char", value: "I" },
    };
    server.use(
      http.post(`${API_BASE}/templates/render`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({
          rendered: "Hi",
          lines: ["Hi"],
          line_count: 1,
          charset: "vestaboard_v1",
          charset_issues: [issue],
        });
      }),
    );

    const result = await api.renderTemplate(["Hi"], undefined, undefined, undefined, undefined, undefined, "vb1");

    expect(body).toEqual({ template: ["Hi"], board_id: "vb1" });
    expect(result.charset).toBe("vestaboard_v1");
    expect(result.charset_issues).toEqual([issue]);
  });

  it("renderTemplate without a board sends no board_id", async () => {
    let body: unknown;
    server.use(
      http.post(`${API_BASE}/templates/render`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ rendered: "HI", lines: ["HI"], line_count: 1 });
      }),
    );

    const result = await api.renderTemplate(["HI"]);

    expect(body).toEqual({ template: ["HI"] });
    expect(result.charset).toBeUndefined();
  });

  it("getPanelFrame returns rich cells when the frame has them", async () => {
    const cells: BoardTokenJson[][] = [
      [
        { type: "char", value: "H", color: "red" },
        { type: "color", code: "65", icon: "sun" },
      ],
    ];
    server.use(
      http.get(`${API_BASE}/panel/abc123def456/frame`, () =>
        HttpResponse.json({ characters: [[8, 65]], cells, message: "H{65}", rows: 1, cols: 2, updated_at: null }),
      ),
    );

    const frame: PanelFrame = await api.getPanelFrame("abc123def456");

    expect(frame.cells).toEqual(cells);
  });
});
