/**
 * Tests for multi-instance plugin API client methods.
 *
 * Covers: listPluginInstances, createPluginInstance, deletePluginInstance
 * and verifies the MSW handlers respond correctly.
 */
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { api } from "@/lib/api";

import { server } from "./mocks/server";

const API_BASE = "/api";

describe("Plugin Instance API", () => {
  // ── listPluginInstances ────────────────────────────────────────────────

  describe("listPluginInstances", () => {
    it("returns empty instances list for a plugin with no instances", async () => {
      const result = await api.listPluginInstances("weather");
      expect(result.plugin_id).toBe("weather");
      expect(Array.isArray(result.instances)).toBe(true);
      expect(result.instances).toHaveLength(0);
    });

    it("returns instances when handler responds with data", async () => {
      server.use(
        http.get(`${API_BASE}/plugins/:pluginId/instances`, ({ params }) => {
          return HttpResponse.json({
            plugin_id: params.pluginId,
            instances: [
              { id: "weather:sf", instance_label: "sf", enabled: false },
              { id: "weather:nyc", instance_label: "nyc", enabled: true },
            ],
          });
        }),
      );
      const result = await api.listPluginInstances("weather");
      expect(result.instances).toHaveLength(2);
      expect(result.instances[0].instance_label).toBe("sf");
      expect(result.instances[1].instance_label).toBe("nyc");
    });

    it("throws on error response", async () => {
      server.use(
        http.get(
          `${API_BASE}/plugins/:pluginId/instances`,
          () => new HttpResponse(null, { status: 503, statusText: "Service Unavailable" }),
        ),
      );
      await expect(api.listPluginInstances("weather")).rejects.toThrow("503");
    });
  });

  // ── createPluginInstance ───────────────────────────────────────────────

  describe("createPluginInstance", () => {
    it("creates an instance and returns correct shape", async () => {
      const result = await api.createPluginInstance("weather", "sf");
      expect(result.status).toBe("success");
      expect(result.plugin_id).toBe("weather");
      expect(result.instance_label).toBe("sf");
      expect(result.instance_key).toBe("weather:sf");
    });

    it("sends the label in the request body", async () => {
      let capturedBody: unknown = null;
      server.use(
        http.post(`${API_BASE}/plugins/:pluginId/instances`, async ({ request, params }) => {
          capturedBody = await request.json();
          const body = capturedBody as { label: string };
          return HttpResponse.json({
            status: "success",
            plugin_id: params.pluginId,
            instance_label: body.label,
            instance_key: `${params.pluginId}:${body.label}`,
            message: "created",
          });
        }),
      );
      await api.createPluginInstance("weather", "prod");
      expect(capturedBody).toEqual({ label: "prod" });
    });

    it("throws on validation error (400)", async () => {
      server.use(
        http.post(
          `${API_BASE}/plugins/:pluginId/instances`,
          () =>
            new HttpResponse(JSON.stringify({ detail: "Label already exists" }), {
              status: 400,
              headers: { "Content-Type": "application/json" },
            }),
        ),
      );
      await expect(api.createPluginInstance("weather", "sf")).rejects.toThrow("Label already exists");
    });

    it("throws when plugin system unavailable (503)", async () => {
      server.use(
        http.post(
          `${API_BASE}/plugins/:pluginId/instances`,
          () => new HttpResponse(null, { status: 503, statusText: "Service Unavailable" }),
        ),
      );
      await expect(api.createPluginInstance("weather", "sf")).rejects.toThrow("503");
    });
  });

  // ── deletePluginInstance ───────────────────────────────────────────────

  describe("deletePluginInstance", () => {
    it("deletes an instance and returns correct shape", async () => {
      const result = await api.deletePluginInstance("weather", "sf");
      expect(result.status).toBe("success");
      expect(result.plugin_id).toBe("weather");
      expect(result.instance_label).toBe("sf");
      expect(result.instance_key).toBe("weather:sf");
    });

    it("passes instance label as path parameter", async () => {
      let capturedLabel = "";
      server.use(
        http.delete(`${API_BASE}/plugins/:pluginId/instances/:instanceLabel`, ({ params }) => {
          capturedLabel = params.instanceLabel as string;
          return HttpResponse.json({
            status: "success",
            plugin_id: params.pluginId,
            instance_label: params.instanceLabel,
            instance_key: `${params.pluginId}:${params.instanceLabel}`,
            message: "deleted",
          });
        }),
      );
      await api.deletePluginInstance("weather", "nyc");
      expect(capturedLabel).toBe("nyc");
    });

    it("throws on not-found error (400)", async () => {
      server.use(
        http.delete(
          `${API_BASE}/plugins/:pluginId/instances/:instanceLabel`,
          () =>
            new HttpResponse(JSON.stringify({ detail: "Instance not found" }), {
              status: 400,
              headers: { "Content-Type": "application/json" },
            }),
        ),
      );
      await expect(api.deletePluginInstance("weather", "sf")).rejects.toThrow("Instance not found");
    });

    it("throws when plugin system unavailable (503)", async () => {
      server.use(
        http.delete(
          `${API_BASE}/plugins/:pluginId/instances/:instanceLabel`,
          () => new HttpResponse(null, { status: 503, statusText: "Service Unavailable" }),
        ),
      );
      await expect(api.deletePluginInstance("weather", "sf")).rejects.toThrow("503");
    });
  });
});
