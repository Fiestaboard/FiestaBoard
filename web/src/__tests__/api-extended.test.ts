import { describe, it, expect, beforeEach } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "./mocks/server";
import { api } from "@/lib/api";

const API_BASE = "/api";

describe("API Extended Tests", () => {
  describe("fetchApi error handling", () => {
    it("throws on non-ok response", async () => {
      server.use(
        http.get(`${API_BASE}/status`, () =>
          new HttpResponse(null, { status: 500, statusText: "Internal Server Error" })
        )
      );
      await expect(api.getStatus()).rejects.toThrow("API error: 500 Internal Server Error");
    });

    it("throws on 404", async () => {
      server.use(
        http.get(`${API_BASE}/config`, () =>
          new HttpResponse(null, { status: 404, statusText: "Not Found" })
        )
      );
      await expect(api.getConfig()).rejects.toThrow("API error: 404 Not Found");
    });
  });

  describe("Service control endpoints", () => {
    it("startService sends POST", async () => {
      const result = await api.startService();
      expect(result.status).toBe("started");
      expect(result.message).toContain("started");
    });

    it("stopService sends POST", async () => {
      const result = await api.stopService();
      expect(result.status).toBe("stopped");
      expect(result.message).toContain("stopped");
    });

  });

  describe("Display endpoints", () => {
    it("getDisplays returns display list", async () => {
      const result = await api.getDisplays();
      expect(result.displays).toBeDefined();
      expect(result.total).toBeGreaterThan(0);
    });

    it("getDisplay returns formatted display", async () => {
      const result = await api.getDisplay("weather");
      expect(result.display_type).toBe("weather");
      expect(result.lines).toBeDefined();
    });

    it("getDisplayRaw returns raw data", async () => {
      const result = await api.getDisplayRaw("weather");
      expect(result.display_type).toBe("weather");
      expect(result.data).toBeDefined();
    });

    it("getDisplaysRawBatch sends display_types and enabled_only", async () => {
      let capturedBody: any;
      server.use(
        http.post(`${API_BASE}/displays/raw/batch`, async ({ request }) => {
          capturedBody = await request.json();
          return HttpResponse.json({ displays: {}, total: 0, successful: 0 });
        })
      );

      await api.getDisplaysRawBatch(["weather", "datetime"]);
      expect(capturedBody).toEqual({ display_types: ["weather", "datetime"], enabled_only: true });

      await api.getDisplaysRawBatch(["weather"], false);
      expect(capturedBody).toEqual({ display_types: ["weather"], enabled_only: false });
    });

    it("sendDisplay appends target query param", async () => {
      let capturedUrl = "";
      server.use(
        http.post(`${API_BASE}/displays/:type/send`, ({ request }) => {
          capturedUrl = request.url;
          return HttpResponse.json({ status: "success", message: "sent" });
        })
      );

      await api.sendDisplay("weather", "board");
      expect(capturedUrl).toContain("target=board");

      await api.sendDisplay("weather");
      expect(capturedUrl).not.toContain("target=");
    });
  });

  describe("Active page endpoints", () => {
    it("getActivePage returns page_id", async () => {
      const result = await api.getActivePage();
      expect(result).toHaveProperty("page_id");
    });

    it("setActivePage sends page_id in body", async () => {
      let capturedBody: any;
      server.use(
        http.put(`${API_BASE}/settings/active-page`, async ({ request }) => {
          capturedBody = await request.json();
          return HttpResponse.json({
            status: "success",
            page_id: capturedBody.page_id,
            sent_to_board: true,
          });
        })
      );

      await api.setActivePage("page-1");
      expect(capturedBody).toEqual({ page_id: "page-1" });

      await api.setActivePage(null);
      expect(capturedBody).toEqual({ page_id: null });
    });
  });

  describe("Page CRUD endpoints", () => {
    it("getPages returns pages array", async () => {
      const result = await api.getPages();
      expect(result.pages).toBeDefined();
      expect(result.total).toBeGreaterThanOrEqual(0);
    });

    it("getPage returns single page", async () => {
      const result = await api.getPage("page-1");
      expect(result.id).toBe("page-1");
      expect(result.name).toBeDefined();
    });

    it("updatePage sends correct body", async () => {
      let capturedBody: any;
      server.use(
        http.put(`${API_BASE}/pages/:id`, async ({ request }) => {
          capturedBody = await request.json();
          return HttpResponse.json({ status: "success", page: { ...capturedBody, id: "page-1" } });
        })
      );

      await api.updatePage("page-1", { name: "Updated", duration_seconds: 120 });
      expect(capturedBody).toEqual({ name: "Updated", duration_seconds: 120 });
    });

    it("deletePage sends DELETE", async () => {
      const result = await api.deletePage("page-1");
      expect(result.status).toBe("success");
    });

    it("previewPage sends POST", async () => {
      const result = await api.previewPage("page-1");
      expect(result.page_id).toBe("page-1");
      expect(result.lines).toBeDefined();
    });

    it("previewPagesBatch sends page_ids", async () => {
      let capturedBody: any;
      server.use(
        http.post(`${API_BASE}/pages/preview/batch`, async ({ request }) => {
          capturedBody = await request.json();
          return HttpResponse.json({ previews: {}, total: 0, successful: 0 });
        })
      );

      await api.previewPagesBatch(["page-1", "page-2"]);
      expect(capturedBody).toEqual({ page_ids: ["page-1", "page-2"] });
    });

    it("sendPage appends target query param", async () => {
      let capturedUrl = "";
      server.use(
        http.post(`${API_BASE}/pages/:id/send`, ({ request }) => {
          capturedUrl = request.url;
          return HttpResponse.json({
            status: "success", page_id: "page-1",
            message: "sent", sent_to_board: true, target: "both",
          });
        })
      );

      await api.sendPage("page-1", "both");
      expect(capturedUrl).toContain("target=both");

      await api.sendPage("page-1");
      expect(capturedUrl).not.toContain("target=");
    });
  });

  describe("Template endpoints", () => {
    it("getTemplateVariables returns variables", async () => {
      const result = await api.getTemplateVariables();
      expect(result.variables).toBeDefined();
      expect(result.colors).toBeDefined();
    });

    it("validateTemplate sends template string", async () => {
      let capturedBody: any;
      server.use(
        http.post(`${API_BASE}/templates/validate`, async ({ request }) => {
          capturedBody = await request.json();
          return HttpResponse.json({ valid: true, errors: [] });
        })
      );

      await api.validateTemplate("{{weather.temperature}}");
      expect(capturedBody).toEqual({ template: "{{weather.temperature}}" });
    });

    it("validateTemplate sends template array", async () => {
      let capturedBody: any;
      server.use(
        http.post(`${API_BASE}/templates/validate`, async ({ request }) => {
          capturedBody = await request.json();
          return HttpResponse.json({ valid: true, errors: [] });
        })
      );

      await api.validateTemplate(["Line 1", "Line 2"]);
      expect(capturedBody).toEqual({ template: ["Line 1", "Line 2"] });
    });

    it("renderTemplate returns rendered output", async () => {
      const result = await api.renderTemplate(["Hello", "World"]);
      expect(result.rendered).toBeDefined();
      expect(result.lines).toBeDefined();
    });

    it("renderTemplateLive sends board_id when provided", async () => {
      let capturedBody: any;
      server.use(
        http.post(`${API_BASE}/templates/render/live`, async ({ request }) => {
          capturedBody = await request.json();
          return HttpResponse.json({
            rendered: "", lines: [""], line_count: 1,
            sent_to_board: true, board_id: capturedBody.board_id || null,
          });
        })
      );

      await api.renderTemplateLive(["Test"], "board-1");
      expect(capturedBody).toEqual({ template: ["Test"], board_id: "board-1" });

      await api.renderTemplateLive(["Test"]);
      expect(capturedBody).toEqual({ template: ["Test"] });
    });

    it("forceRefresh sends POST", async () => {
      const result = await api.forceRefresh();
      expect(result.status).toBe("success");
    });
  });

  describe("Schedule endpoints", () => {
    beforeEach(() => {
      server.use(
        http.get(`${API_BASE}/schedules`, ({ request }) => {
          const url = new URL(request.url);
          const boardId = url.searchParams.get("board_id");
          return HttpResponse.json({
            schedules: [], total: 0,
            default_page_id: null, enabled: true,
            ...(boardId && { board_id: boardId }),
          });
        }),
        http.post(`${API_BASE}/schedules`, async ({ request }) => {
          const body = await request.json() as any;
          return HttpResponse.json({
            id: "sched-1", ...body,
            enabled: body.enabled ?? true,
            created_at: new Date().toISOString(),
          });
        }),
        http.get(`${API_BASE}/schedules/active/page`, ({ request }) => {
          const url = new URL(request.url);
          return HttpResponse.json({
            page_id: "page-1", source: "schedule",
            schedule_enabled: true,
            ...(url.searchParams.get("board_id") && { board_id: url.searchParams.get("board_id") }),
          });
        }),
        http.post(`${API_BASE}/schedules/validate`, async ({ request }) => {
          const body = await request.json() as any;
          return HttpResponse.json({ valid: true, overlaps: [], gaps: [], ...body });
        }),
        http.get(`${API_BASE}/schedules/default-page`, () =>
          HttpResponse.json({ default_page_id: null })
        ),
        http.put(`${API_BASE}/schedules/default-page`, async ({ request }) => {
          const body = await request.json() as any;
          return HttpResponse.json({ status: "success", default_page_id: body.page_id });
        }),
        http.get(`${API_BASE}/schedules/enabled`, () =>
          HttpResponse.json({ enabled: true })
        ),
        http.put(`${API_BASE}/schedules/enabled`, async ({ request }) => {
          const body = await request.json() as any;
          return HttpResponse.json({ status: "success", enabled: body.enabled, message: "ok" });
        }),
        http.get(`${API_BASE}/schedules/:id`, ({ params }) =>
          HttpResponse.json({
            id: params.id, page_id: "page-1",
            start_time: "09:00", end_time: "17:00",
            day_pattern: "all", enabled: true,
            created_at: new Date().toISOString(),
          })
        ),
        http.put(`${API_BASE}/schedules/:id`, async ({ request, params }) => {
          const body = await request.json() as any;
          return HttpResponse.json({ id: params.id, ...body });
        }),
        http.delete(`${API_BASE}/schedules/:id`, () =>
          HttpResponse.json({ status: "success", message: "Schedule deleted" })
        )
      );
    });

    it("getSchedules without boardId", async () => {
      const result = await api.getSchedules();
      expect(result.schedules).toBeDefined();
      expect(result.enabled).toBe(true);
    });

    it("getSchedules with boardId includes query param", async () => {
      const result = await api.getSchedules("board-1");
      expect(result).toBeDefined();
    });

    it("createSchedule sends correct payload", async () => {
      const result = await api.createSchedule({
        page_id: "page-1",
        start_time: "09:00",
        end_time: "17:00",
        day_pattern: "weekdays",
      });
      expect(result.page_id).toBe("page-1");
      expect(result.day_pattern).toBe("weekdays");
    });

    it("getSchedule returns single entry", async () => {
      const result = await api.getSchedule("sched-1");
      expect(result.id).toBe("sched-1");
    });

    it("updateSchedule sends partial update", async () => {
      const result = await api.updateSchedule("sched-1", { enabled: false });
      expect(result.enabled).toBe(false);
    });

    it("deleteSchedule sends DELETE", async () => {
      const result = await api.deleteSchedule("sched-1");
      expect(result.status).toBe("success");
    });

    it("getActiveSchedule without boardId", async () => {
      const result = await api.getActiveSchedule();
      expect(result.page_id).toBeDefined();
      expect(result.source).toBe("schedule");
    });

    it("getActiveSchedule with boardId", async () => {
      const result = await api.getActiveSchedule("board-1");
      expect(result).toBeDefined();
    });

    it("validateSchedules sends board_id when provided", async () => {
      let capturedBody: any;
      server.use(
        http.post(`${API_BASE}/schedules/validate`, async ({ request }) => {
          capturedBody = await request.json();
          return HttpResponse.json({ valid: true, overlaps: [], gaps: [] });
        })
      );

      await api.validateSchedules("board-1");
      expect(capturedBody).toEqual({ board_id: "board-1" });

      await api.validateSchedules();
      expect(capturedBody).toEqual({});
    });

    it("getDefaultPage returns default_page_id", async () => {
      const result = await api.getDefaultPage();
      expect(result).toHaveProperty("default_page_id");
    });

    it("setDefaultPage sends page_id and optional board_id", async () => {
      let capturedBody: any;
      server.use(
        http.put(`${API_BASE}/schedules/default-page`, async ({ request }) => {
          capturedBody = await request.json();
          return HttpResponse.json({ status: "success", default_page_id: capturedBody.page_id });
        })
      );

      await api.setDefaultPage("page-1");
      expect(capturedBody).toEqual({ page_id: "page-1" });

      await api.setDefaultPage("page-1", "board-1");
      expect(capturedBody).toEqual({ page_id: "page-1", board_id: "board-1" });

      await api.setDefaultPage(null);
      expect(capturedBody).toEqual({ page_id: null });
    });

    it("getScheduleEnabled returns enabled state", async () => {
      const result = await api.getScheduleEnabled();
      expect(result.enabled).toBe(true);
    });

    it("setScheduleEnabled sends enabled and optional board_id", async () => {
      let capturedBody: any;
      server.use(
        http.put(`${API_BASE}/schedules/enabled`, async ({ request }) => {
          capturedBody = await request.json();
          return HttpResponse.json({ status: "success", enabled: capturedBody.enabled, message: "ok" });
        })
      );

      await api.setScheduleEnabled(false);
      expect(capturedBody).toEqual({ enabled: false });

      await api.setScheduleEnabled(true, "board-1");
      expect(capturedBody).toEqual({ enabled: true, board_id: "board-1" });
    });
  });

  describe("Configuration endpoints", () => {
    it("getFullConfig returns full config", async () => {
      server.use(
        http.get(`${API_BASE}/config/full`, () =>
          HttpResponse.json({
            board: { api_mode: "local", local_api_key: "key", cloud_key: "", host: "192.168.1.1" },
            general: { timezone: "UTC", refresh_interval_seconds: 300, output_target: "board" },
            plugins: {},
          })
        )
      );
      const result = await api.getFullConfig();
      expect(result.board).toBeDefined();
      expect(result.general).toBeDefined();
    });

    it("getBoardConfig returns config with api_modes", async () => {
      server.use(
        http.get(`${API_BASE}/config/board`, () =>
          HttpResponse.json({
            config: { api_mode: "local", local_api_key: "", cloud_key: "", host: "" },
            api_modes: ["local", "cloud"],
          })
        )
      );
      const result = await api.getBoardConfig();
      expect(result.config).toBeDefined();
      expect(result.api_modes).toContain("local");
    });

    it("updateBoardConfig sends partial config", async () => {
      let capturedBody: any;
      server.use(
        http.put(`${API_BASE}/config/board`, async ({ request }) => {
          capturedBody = await request.json();
          return HttpResponse.json({ status: "success", config: capturedBody });
        })
      );
      await api.updateBoardConfig({ host: "192.168.1.100" });
      expect(capturedBody).toEqual({ host: "192.168.1.100" });
    });

    it("validateConfig returns validation result", async () => {
      server.use(
        http.get(`${API_BASE}/config/validate`, () =>
          HttpResponse.json({ valid: true, is_first_run: false, errors: [], missing_fields: [] })
        )
      );
      const result = await api.validateConfig();
      expect(result.valid).toBe(true);
    });

    it("backward compat aliases work", async () => {
      server.use(
        http.get(`${API_BASE}/config/board`, () =>
          HttpResponse.json({
            config: { api_mode: "local", local_api_key: "", cloud_key: "", host: "" },
            api_modes: ["local"],
          })
        )
      );
      const result = await api.getFiestaboardConfig();
      expect(result.config).toBeDefined();
    });
  });

  describe("BayWheels endpoints", () => {
    beforeEach(() => {
      server.use(
        http.get(`${API_BASE}/baywheels/stations`, () =>
          HttpResponse.json({ stations: [], total: 0 })
        ),
        http.get(`${API_BASE}/baywheels/stations/nearby`, ({ request }) => {
          const url = new URL(request.url);
          return HttpResponse.json({
            stations: [],
            count: 0,
            search_location: {
              lat: parseFloat(url.searchParams.get("lat") || "0"),
              lng: parseFloat(url.searchParams.get("lng") || "0"),
            },
            radius_km: parseFloat(url.searchParams.get("radius") || "1"),
          });
        }),
        http.get(`${API_BASE}/baywheels/stations/search`, ({ request }) => {
          const url = new URL(request.url);
          return HttpResponse.json({
            stations: [],
            count: 0,
            search_address: url.searchParams.get("address"),
            geocoded_location: { lat: 40.7128, lng: -74.006, display_name: "Test" },
            radius_km: 1,
          });
        })
      );
    });

    it("listBayWheelsStations returns stations", async () => {
      const result = await api.listBayWheelsStations();
      expect(result.stations).toBeDefined();
    });

    it("findNearbyBayWheelsStations sends lat/lng params", async () => {
      const result = await api.findNearbyBayWheelsStations(40.7128, -74.006, 2, 5);
      expect(result.search_location.lat).toBe(40.7128);
    });

    it("searchBayWheelsStationsByAddress sends address param", async () => {
      const result = await api.searchBayWheelsStationsByAddress("123 Main St", 2, 5);
      expect(result.search_address).toBe("123 Main St");
    });
  });

  describe("MUNI endpoints", () => {
    beforeEach(() => {
      server.use(
        http.get(`${API_BASE}/muni/stops`, () =>
          HttpResponse.json({ stops: [], total: 0 })
        ),
        http.get(`${API_BASE}/muni/stops/nearby`, ({ request }) => {
          const url = new URL(request.url);
          return HttpResponse.json({
            stops: [],
            count: 0,
            search_location: {
              lat: parseFloat(url.searchParams.get("lat") || "0"),
              lng: parseFloat(url.searchParams.get("lng") || "0"),
            },
            radius_km: 1,
          });
        }),
        http.get(`${API_BASE}/muni/stops/search`, ({ request }) => {
          const url = new URL(request.url);
          return HttpResponse.json({
            stops: [],
            count: 0,
            search_address: url.searchParams.get("address"),
            geocoded_location: { lat: 40.7128, lng: -74.006, display_name: "Test" },
            radius_km: 1,
          });
        })
      );
    });

    it("listMuniStops returns stops", async () => {
      const result = await api.listMuniStops();
      expect(result.stops).toBeDefined();
    });

    it("findNearbyMuniStops sends params", async () => {
      const result = await api.findNearbyMuniStops(40.7128, -74.006);
      expect(result.search_location.lat).toBe(40.7128);
    });

    it("searchMuniStopsByAddress sends address", async () => {
      const result = await api.searchMuniStopsByAddress("Market St");
      expect(result.search_address).toBe("Market St");
    });
  });

  describe("Traffic endpoints", () => {
    beforeEach(() => {
      server.use(
        http.post(`${API_BASE}/traffic/routes/geocode`, async ({ request }) => {
          const body = await request.json() as any;
          return HttpResponse.json({
            lat: 40.7128, lng: -74.006, formatted_address: body.address,
          });
        }),
        http.post(`${API_BASE}/traffic/routes/validate`, async ({ request }) => {
          const body = await request.json() as any;
          return HttpResponse.json({
            valid: true,
            distance_km: 10,
            static_duration_minutes: 15,
          });
        })
      );
    });

    it("geocodeAddress sends address in body", async () => {
      const result = await api.geocodeAddress("123 Main St");
      expect(result.lat).toBeDefined();
      expect(result.formatted_address).toBe("123 Main St");
    });

    it("validateTrafficRoute sends route params", async () => {
      let capturedBody: any;
      server.use(
        http.post(`${API_BASE}/traffic/routes/validate`, async ({ request }) => {
          capturedBody = await request.json();
          return HttpResponse.json({ valid: true });
        })
      );

      await api.validateTrafficRoute("origin", "dest", "Work", "DRIVE");
      expect(capturedBody).toEqual({
        origin: "origin",
        destination: "dest",
        destination_name: "Work",
        travel_mode: "DRIVE",
      });
    });
  });

  describe("Stocks endpoints", () => {
    beforeEach(() => {
      server.use(
        http.get(`${API_BASE}/stocks/search`, ({ request }) => {
          const url = new URL(request.url);
          return HttpResponse.json({
            symbols: [{ symbol: "AAPL", name: "Apple Inc." }],
            count: 1,
            query: url.searchParams.get("query"),
          });
        }),
        http.post(`${API_BASE}/stocks/validate`, async ({ request }) => {
          const body = await request.json() as any;
          return HttpResponse.json({
            valid: true, symbol: body.symbol, name: "Apple Inc.",
          });
        })
      );
    });

    it("searchStockSymbols sends query", async () => {
      const result = await api.searchStockSymbols("AAPL");
      expect(result.query).toBe("AAPL");
      expect(result.symbols).toHaveLength(1);
    });

    it("searchStockSymbols with limit", async () => {
      const result = await api.searchStockSymbols("AA", 5);
      expect(result).toBeDefined();
    });

    it("validateStockSymbol sends symbol", async () => {
      const result = await api.validateStockSymbol("AAPL");
      expect(result.valid).toBe(true);
      expect(result.symbol).toBe("AAPL");
    });
  });

  describe("General config endpoints", () => {
    it("getGeneralConfig returns config", async () => {
      const result = await api.getGeneralConfig();
      expect(result.timezone).toBeDefined();
      expect(result.refresh_interval_seconds).toBeDefined();
    });

    it("updateGeneralConfig sends partial config", async () => {
      let capturedBody: any;
      server.use(
        http.put(`${API_BASE}/config/general`, async ({ request }) => {
          capturedBody = await request.json();
          return HttpResponse.json({ status: "success", general: capturedBody });
        })
      );
      await api.updateGeneralConfig({ timezone: "UTC" });
      expect(capturedBody).toEqual({ timezone: "UTC" });
    });
  });

  describe("Silence and polling endpoints", () => {
    it("getSilenceStatus returns status", async () => {
      const result = await api.getSilenceStatus();
      expect(result).toHaveProperty("enabled");
      expect(result).toHaveProperty("active");
    });

    it("getPollingSettings returns interval", async () => {
      const result = await api.getPollingSettings();
      expect(result.interval_seconds).toBeDefined();
    });

    it("updatePollingSettings sends interval", async () => {
      const result = await api.updatePollingSettings(600);
      expect(result.status).toBe("success");
      expect(result.settings.interval_seconds).toBe(600);
    });
  });

  describe("Board settings endpoints", () => {
    it("getBoardSettings returns settings", async () => {
      const result = await api.getBoardSettings();
      expect(result.boards).toBeDefined();
    });

    it("updateBoardSettings sends body", async () => {
      const result = await api.updateBoardSettings({ board_type: "white" });
      expect(result.status).toBe("success");
    });

    it("addBoard sends board data", async () => {
      const result = await api.addBoard({ device_type: "note", name: "My Note" });
      expect(result.status).toBe("success");
    });

    it("removeBoard sends DELETE", async () => {
      const result = await api.removeBoard("board-1");
      expect(result.status).toBe("success");
    });

    it("getAllSettings returns combined settings", async () => {
      server.use(
        http.get(`${API_BASE}/settings/all`, () =>
          HttpResponse.json({
            general: { timezone: "UTC", refresh_interval_seconds: 300, output_target: "board" },
            silence_schedule: {},
            polling: { interval_seconds: 300 },
            transitions: { strategy: "column", step_interval_ms: 500, step_size: 2 },
            output: { target: "board", effective_target: "board", available_targets: [] },
            board: { board_type: "black", boards: [], devices: [] },
            mqtt: { enabled: false, broker_host: "localhost", broker_port: 1883, username: "", password: "", external_url: "" },
            status: { running: true },
          })
        )
      );
      const result = await api.getAllSettings();
      expect(result.general).toBeDefined();
      expect(result.board).toBeDefined();
      expect(result.mqtt).toBeDefined();
      expect(result.mqtt.enabled).toBe(false);
    });
  });

  describe("Home Assistant endpoints", () => {
    it("getHomeAssistantEntities returns entities", async () => {
      server.use(
        http.get(`${API_BASE}/home-assistant/entities`, () =>
          HttpResponse.json({ entities: [] })
        )
      );
      const result = await api.getHomeAssistantEntities();
      expect(result.entities).toBeDefined();
    });
  });

  describe("Queue-Times endpoints", () => {
    beforeEach(() => {
      server.use(
        http.get(`${API_BASE}/queue-times/parks`, () =>
          HttpResponse.json([{ id: 1, name: "Test Park" }])
        ),
        http.get(`${API_BASE}/queue-times/parks/:parkId/rides`, () =>
          HttpResponse.json([{ id: 10, name: "Test Ride" }])
        )
      );
    });

    it("getQueueTimesParks returns parks", async () => {
      const result = await api.getQueueTimesParks();
      expect(result).toHaveLength(1);
      expect(result[0].name).toBe("Test Park");
    });

    it("getQueueTimesRides returns rides", async () => {
      const result = await api.getQueueTimesRides(1);
      expect(result).toHaveLength(1);
      expect(result[0].name).toBe("Test Ride");
    });
  });

  describe("Plugin endpoints", () => {
    it("listPlugins returns plugin list", async () => {
      server.use(
        http.get(`${API_BASE}/plugins`, () =>
          HttpResponse.json({ plugins: [], plugin_system_enabled: true, total: 0, enabled_count: 0 })
        )
      );
      const result = await api.listPlugins();
      expect(result.plugins).toBeDefined();
      expect(result.plugin_system_enabled).toBe(true);
    });

    it("getPlugin returns plugin detail", async () => {
      const result = await api.getPlugin("silence_schedule");
      expect(result.id).toBe("silence_schedule");
    });

    it("getPluginManifest returns manifest", async () => {
      const result = await api.getPluginManifest("weather");
      expect(result.id).toBe("weather");
    });

    it("updatePluginConfig sends config body", async () => {
      let capturedBody: any;
      server.use(
        http.put(`${API_BASE}/plugins/:pluginId/config`, async ({ request }) => {
          capturedBody = await request.json();
          return HttpResponse.json({ status: "success", plugin_id: "test", config: {} });
        })
      );
      await api.updatePluginConfig("test", { key: "value" });
      expect(capturedBody).toEqual({ config: { key: "value" } });
    });

    it("enablePlugin sends POST", async () => {
      server.use(
        http.post(`${API_BASE}/plugins/:pluginId/enable`, () =>
          HttpResponse.json({ status: "success", plugin_id: "test", enabled: true })
        )
      );
      const result = await api.enablePlugin("test");
      expect(result.enabled).toBe(true);
    });

    it("disablePlugin sends POST", async () => {
      server.use(
        http.post(`${API_BASE}/plugins/:pluginId/disable`, () =>
          HttpResponse.json({ status: "success", plugin_id: "test", enabled: false })
        )
      );
      const result = await api.disablePlugin("test");
      expect(result.enabled).toBe(false);
    });

    it("getPluginData returns data", async () => {
      server.use(
        http.get(`${API_BASE}/plugins/:pluginId/data`, () =>
          HttpResponse.json({ plugin_id: "test", available: true, data: { foo: "bar" } })
        )
      );
      const result = await api.getPluginData("test");
      expect(result.available).toBe(true);
    });

    it("getPluginVariables returns variables", async () => {
      server.use(
        http.get(`${API_BASE}/plugins/:pluginId/variables`, () =>
          HttpResponse.json({ plugin_id: "test", variables: {}, max_lengths: {}, color_rules_schema: {} })
        )
      );
      const result = await api.getPluginVariables("test");
      expect(result.plugin_id).toBe("test");
    });

    it("getAllPluginVariables returns all variables", async () => {
      server.use(
        http.get(`${API_BASE}/plugins/variables/all`, () =>
          HttpResponse.json({ variables: {}, max_lengths: {}, plugin_system_enabled: true })
        )
      );
      const result = await api.getAllPluginVariables();
      expect(result.plugin_system_enabled).toBe(true);
    });

    it("getPluginErrors returns errors", async () => {
      server.use(
        http.get(`${API_BASE}/plugins/errors`, () =>
          HttpResponse.json({ errors: {}, plugin_system_enabled: true })
        )
      );
      const result = await api.getPluginErrors();
      expect(result.plugin_system_enabled).toBe(true);
    });
  });

  describe("Setup wizard endpoints", () => {
    it("validateSetup returns validation", async () => {
      server.use(
        http.get(`${API_BASE}/config/validate`, () =>
          HttpResponse.json({ valid: false, is_first_run: true, errors: ["missing board config"], missing_fields: ["host"] })
        )
      );
      const result = await api.validateSetup();
      expect(result.is_first_run).toBe(true);
    });

    it("testBoardConnection sends request body", async () => {
      let capturedBody: any;
      server.use(
        http.post(`${API_BASE}/config/board/test`, async ({ request }) => {
          capturedBody = await request.json();
          return HttpResponse.json({ success: true, message: "Connected" });
        })
      );
      await api.testBoardConnection({ api_mode: "local", local_api_key: "test-key", host: "192.168.1.1" });
      expect(capturedBody.api_mode).toBe("local");
      expect(capturedBody.host).toBe("192.168.1.1");
    });

    it("sendWelcomeMessage sends POST", async () => {
      server.use(
        http.post(`${API_BASE}/send-welcome-message`, () =>
          HttpResponse.json({ status: "success", message: "Welcome sent" })
        )
      );
      const result = await api.sendWelcomeMessage();
      expect(result.status).toBe("success");
    });

    it("enableLocalApi sends request body", async () => {
      let capturedBody: any;
      server.use(
        http.post(`${API_BASE}/config/board/enable-local-api`, async ({ request }) => {
          capturedBody = await request.json();
          return HttpResponse.json({ success: true, api_key: "new-key", message: "Enabled" });
        })
      );
      await api.enableLocalApi({ host: "192.168.1.1", enablement_token: "token-123" });
      expect(capturedBody).toEqual({ host: "192.168.1.1", enablement_token: "token-123" });
    });
  });

  describe("Debug endpoints", () => {
    beforeEach(() => {
      server.use(
        http.post(`${API_BASE}/debug/blank`, () =>
          HttpResponse.json({ status: "success", message: "Board blanked" })
        ),
        http.post(`${API_BASE}/debug/fill`, async ({ request }) => {
          const body = await request.json() as any;
          return HttpResponse.json({ status: "success", message: `Filled with ${body.character_code}` });
        }),
        http.post(`${API_BASE}/debug/info`, () =>
          HttpResponse.json({ status: "success", message: "Debug info shown" })
        ),
        http.post(`${API_BASE}/debug/test-connection`, () =>
          HttpResponse.json({ status: "success", message: "Connected", connected: true, latency_ms: 5 })
        ),
        http.post(`${API_BASE}/debug/clear-cache`, () =>
          HttpResponse.json({ status: "success", message: "Cache cleared" })
        ),
        http.get(`${API_BASE}/debug/cache-status`, () =>
          HttpResponse.json({
            status: "success",
            cache: { has_cached_text: true, has_cached_characters: false, skip_unchanged_enabled: true, cached_text_preview: "Hello" },
          })
        ),
        http.get(`${API_BASE}/debug/system-info`, () =>
          HttpResponse.json({
            board_ip: "192.168.1.1", server_ip: "192.168.1.2",
            uptime_seconds: 3600, uptime_formatted: "1h 0m",
            connection_mode: "local", version: "2.0.0",
            timestamp: new Date().toISOString(),
            cache_status: null, board_configured: true,
            service_running: true,
          })
        )
      );
    });

    it("blankBoard sends POST", async () => {
      const result = await api.blankBoard();
      expect(result.status).toBe("success");
    });

    it("fillBoard sends character_code", async () => {
      const result = await api.fillBoard(65);
      expect(result.message).toContain("65");
    });

    it("showDebugInfo sends POST", async () => {
      const result = await api.showDebugInfo();
      expect(result.status).toBe("success");
    });

    it("testDebugConnection returns connection status", async () => {
      const result = await api.testDebugConnection();
      expect(result.connected).toBe(true);
      expect(result.latency_ms).toBe(5);
    });

    it("clearBoardCache sends POST", async () => {
      const result = await api.clearBoardCache();
      expect(result.status).toBe("success");
    });

    it("getBoardCacheStatus returns cache info", async () => {
      const result = await api.getBoardCacheStatus();
      expect(result.cache.has_cached_text).toBe(true);
    });

    it("getDebugSystemInfo returns system info", async () => {
      const result = await api.getDebugSystemInfo();
      expect(result.board_configured).toBe(true);
      expect(result.version).toBe("2.0.0");
    });
  });

  describe("Version and update endpoints", () => {
    it("getVersion returns version info", async () => {
      const result = await api.getVersion();
      expect(result.package_version).toBeDefined();
      expect(result.is_dev).toBe(true);
    });

    it("checkForUpdate returns update status", async () => {
      const result = await api.checkForUpdate();
      expect(result.current_version).toBeDefined();
      expect(typeof result.update_available).toBe("boolean");
    });
  });

  describe("Debug endpoints", () => {
    it("getNetworkDiagnostics returns diagnostics result", async () => {
      server.use(
        http.get(`${API_BASE}/debug/network-diagnostics`, () =>
          HttpResponse.json({
            diagnostics: {
              overall_ok: true,
              dns: { ok: true, ip: "142.250.80.46", hostname: "google.com" },
              internet: { ok: true, url: "https://google.com", latency_ms: 42 },
              vestaboard: { ok: true, mode: "cloud", steps: { cloud_api: { ok: true, latency_ms: 120, status_code: 200 } }, error: null },
              recommendations: [],
            },
          })
        )
      );
      const result = await api.getNetworkDiagnostics();
      expect(result.diagnostics.overall_ok).toBe(true);
      expect(result.diagnostics.dns.ok).toBe(true);
    });
  });
});
