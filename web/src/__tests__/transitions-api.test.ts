/**
 * Tests for the transition plugin API client functions in @/lib/api.
 *
 * Mocks the backend with MSW and verifies the client posts the expected
 * payloads and parses the responses correctly.  The Transition Lab page
 * itself is exercised by Playwright against the dev container; these
 * tests cover the data contract that the page relies on.
 */

import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import type { TransitionPluginsResponse, TransitionPreviewResponse } from "@/lib/api";
import { api } from "@/lib/api";

import { server } from "./mocks/server";

const API_BASE = "/api";

describe("transition API client", () => {
  describe("listTransitionPlugins", () => {
    it("returns the plugin list as-is", async () => {
      const payload: TransitionPluginsResponse = {
        plugins: [
          {
            id: "typewriter",
            name: "Typewriter",
            description: "Left-to-right reveal",
            icon: "type",
            version: "1.0.0",
            author: "FiestaBoard",
            settings_schema: {
              type: "object",
              properties: {
                chars_per_frame: { type: "integer", default: 1 },
              },
            },
            transition_settings: {
              interruptible: true,
              min_interval_ms: 50,
              max_frames: 200,
              max_runtime_seconds: 60,
            },
            config: { chars_per_frame: 2 },
            strategy: "plugin:typewriter",
          },
        ],
      };
      server.use(http.get(`${API_BASE}/transitions/plugins`, () => HttpResponse.json(payload)));

      const result = await api.listTransitionPlugins();
      expect(result.plugins).toHaveLength(1);
      expect(result.plugins[0].id).toBe("typewriter");
      expect(result.plugins[0].strategy).toBe("plugin:typewriter");
      expect(result.plugins[0].transition_settings.max_frames).toBe(200);
    });

    it("surfaces backend errors", async () => {
      server.use(
        http.get(`${API_BASE}/transitions/plugins`, () => new HttpResponse(null, { status: 500, statusText: "boom" })),
      );
      await expect(api.listTransitionPlugins()).rejects.toThrow(/500/);
    });
  });

  describe("previewTransition", () => {
    it("POSTs the request body and parses the frame array", async () => {
      let capturedBody: unknown = null;
      const payload: TransitionPreviewResponse = {
        plugin_id: "typewriter",
        device_type: "flagship",
        frames: [
          { grid: Array.from({ length: 6 }, () => Array(22).fill(0)), delay_ms: 50 },
          { grid: Array.from({ length: 6 }, () => Array(22).fill(1)), delay_ms: 50 },
        ],
        frame_count: 2,
        total_delay_ms: 100,
        capped: false,
        from_grid: Array.from({ length: 6 }, () => Array(22).fill(0)),
        to_grid: Array.from({ length: 6 }, () => Array(22).fill(1)),
      };
      server.use(
        http.post(`${API_BASE}/transitions/preview`, async ({ request }) => {
          capturedBody = await request.json();
          return HttpResponse.json(payload);
        }),
      );

      const result = await api.previewTransition({
        plugin_id: "typewriter",
        to_text: "HI",
        from_text: "BYE",
        device_type: "flagship",
        config: { chars_per_frame: 2 },
      });

      expect(capturedBody).toEqual({
        plugin_id: "typewriter",
        to_text: "HI",
        from_text: "BYE",
        device_type: "flagship",
        config: { chars_per_frame: 2 },
      });
      expect(result.frames).toHaveLength(2);
      expect(result.frame_count).toBe(2);
      expect(result.total_delay_ms).toBe(100);
      expect(result.capped).toBe(false);
    });

    it("passes note-array geometry through", async () => {
      let capturedBody: Record<string, unknown> | null = null;
      server.use(
        http.post(`${API_BASE}/transitions/preview`, async ({ request }) => {
          capturedBody = (await request.json()) as Record<string, unknown>;
          return HttpResponse.json({
            plugin_id: "typewriter",
            device_type: "note_array",
            frames: [],
            frame_count: 0,
            total_delay_ms: 0,
            capped: false,
            from_grid: [[0]],
            to_grid: [[0]],
          });
        }),
      );
      await api.previewTransition({
        plugin_id: "typewriter",
        to_text: "X",
        device_type: "note_array",
        notes_wide: 2,
        notes_tall: 1,
      });
      expect(capturedBody).toMatchObject({ device_type: "note_array", notes_wide: 2, notes_tall: 1 });
    });

    it("surfaces 404 from an unknown plugin", async () => {
      server.use(
        http.post(
          `${API_BASE}/transitions/preview`,
          () => new HttpResponse(null, { status: 404, statusText: "Not Found" }),
        ),
      );
      await expect(api.previewTransition({ plugin_id: "ghost", to_text: "X" })).rejects.toThrow(/404/);
    });

    it("surfaces 400 for bad input", async () => {
      server.use(
        http.post(
          `${API_BASE}/transitions/preview`,
          () => new HttpResponse(null, { status: 400, statusText: "Bad Request" }),
        ),
      );
      await expect(api.previewTransition({ plugin_id: "", to_text: "X" })).rejects.toThrow(/400/);
    });

    it("preserves capped flag on overlarge previews", async () => {
      server.use(
        http.post(`${API_BASE}/transitions/preview`, () =>
          HttpResponse.json({
            plugin_id: "forever",
            device_type: "flagship",
            frames: [{ grid: [[0]], delay_ms: 50 }],
            frame_count: 1,
            total_delay_ms: 50,
            capped: true,
            from_grid: [[0]],
            to_grid: [[0]],
          }),
        ),
      );
      const result = await api.previewTransition({
        plugin_id: "forever",
        to_text: "X",
      });
      expect(result.capped).toBe(true);
    });
  });
});
