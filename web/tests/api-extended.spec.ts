/**
 * FiestaBoard API Integration Tests – Extended Endpoints
 *
 * Covers deeper API contracts beyond basic CRUD:
 *   - Config (full, board, validate, test connection)
 *   - Pages (get, update, preview, send, batch preview)
 *   - Schedules (get, update, active page, validate, default page, enable/disable)
 *   - Plugins (get, enable/disable, config, variables)
 *   - Settings (transitions, active page, board display)
 *   - Templates (render)
 *   - Service control (status, start/stop)
 */
import { test, expect, configureBoard, API_URL, BOARD_HOST } from "./helpers";

/** Use API_URL directly (not a copy) so per-worker URL updates from the workerBackend fixture are visible. */
function API() { return API_URL; }

// Ensure the board is configured before each API test
test.beforeEach(async () => {
  await configureBoard();
});

// ---------------------------------------------------------------------------
// Extended Config Endpoints
// ---------------------------------------------------------------------------

test.describe("API – Config (extended)", () => {
  test("returns full masked configuration", async () => {
    const res = await fetch(`${API()}/config/full`);
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(typeof data).toBe("object");
  });

  test("returns board config with modes", async () => {
    const res = await fetch(`${API()}/config/board`);
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(typeof data).toBe("object");
  });

  test("tests board connection with provided credentials", async () => {
    const res = await fetch(`${API()}/config/board/test`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        api_mode: "local",
        local_api_key: "test-key",
        host: BOARD_HOST,
      }),
    });
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data).toHaveProperty("success");
    expect(data).toHaveProperty("message");
  });

  test("returns validation status", async () => {
    const res = await fetch(`${API()}/config/validate`);
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data).toHaveProperty("valid");
    expect(data).toHaveProperty("is_first_run");
  });
});

// ---------------------------------------------------------------------------
// Extended Pages Endpoints
// ---------------------------------------------------------------------------

test.describe("API – Pages (extended)", () => {
  let testPageId: string;

  test.beforeAll(async () => {
    const res = await fetch(`${API()}/pages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: "Extended API Test Page",
        type: "template",
        template: ["API EXTENDED", "", "", "", "", ""],
      }),
    });
    const data = await res.json();
    testPageId = data.page.id;
  });

  test.afterAll(async () => {
    if (testPageId) {
      await fetch(`${API()}/pages/${testPageId}`, { method: "DELETE" });
    }
  });

  test("can get a single page by ID", async () => {
    const res = await fetch(`${API()}/pages/${testPageId}`);
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data.id).toBe(testPageId);
    expect(data.name).toBe("Extended API Test Page");
  });

  test("can update a page", async () => {
    const res = await fetch(`${API()}/pages/${testPageId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: "Updated Page Name" }),
    });
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data.status).toBe("success");
  });

  test("can preview a page", async () => {
    const res = await fetch(`${API()}/pages/${testPageId}/preview`, {
      method: "POST",
    });
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data).toHaveProperty("page_id");
    expect(data).toHaveProperty("lines");
    expect(data).toHaveProperty("message");
  });

  test("can send a page to target", async () => {
    const res = await fetch(`${API()}/pages/${testPageId}/send`, {
      method: "POST",
    });
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data).toHaveProperty("status");
    expect(data).toHaveProperty("page_id");
  });

  test("can batch preview pages", async () => {
    const res = await fetch(`${API()}/pages/preview/batch`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ page_ids: [testPageId] }),
    });
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data).toHaveProperty("previews");
    expect(data).toHaveProperty("total");
    expect(data).toHaveProperty("successful");
  });
});

// ---------------------------------------------------------------------------
// Extended Schedules Endpoints
// ---------------------------------------------------------------------------

test.describe("API – Schedules (extended)", () => {
  let pageId: string;
  let scheduleId: string;

  test.beforeAll(async () => {
    const pRes = await fetch(`${API()}/pages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: "Schedule Extended Test Page",
        type: "template",
        template: ["SCHED EXT", "", "", "", "", ""],
      }),
    });
    const pData = await pRes.json();
    pageId = pData.page.id;

    const sRes = await fetch(`${API()}/schedules`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        page_id: pageId,
        day_pattern: "weekdays",
        start_time: "06:00",
        end_time: "10:00",
      }),
    });
    const sData = await sRes.json();
    scheduleId = sData.id;
  });

  test.afterAll(async () => {
    if (scheduleId) await fetch(`${API()}/schedules/${scheduleId}`, { method: "DELETE" });
    if (pageId) await fetch(`${API()}/pages/${pageId}`, { method: "DELETE" });
  });

  test("can get a single schedule by ID", async () => {
    const res = await fetch(`${API()}/schedules/${scheduleId}`);
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data.id).toBe(scheduleId);
  });

  test("can update a schedule", async () => {
    const res = await fetch(`${API()}/schedules/${scheduleId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ start_time: "07:00" }),
    });
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data.start_time).toBe("07:00");
  });

  test("returns active schedule page", async () => {
    const res = await fetch(`${API()}/schedules/active/page`);
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data).toHaveProperty("page_id");
    expect(data).toHaveProperty("source");
    expect(data).toHaveProperty("schedule_enabled");
  });

  test("validates schedules for overlaps", async () => {
    const res = await fetch(`${API()}/schedules/validate`, { method: "POST" });
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(typeof data).toBe("object");
  });

  test("can set default page", async () => {
    const res = await fetch(`${API()}/schedules/default-page`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ page_id: pageId }),
    });
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data.status).toBe("success");
    expect(data.default_page_id).toBe(pageId);
  });

  test("can enable and disable schedule mode", async () => {
    const enableRes = await fetch(`${API()}/schedules/enabled`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: true }),
    });
    expect(enableRes.ok).toBe(true);
    const enableData = await enableRes.json();
    expect(enableData.enabled).toBe(true);

    const disableRes = await fetch(`${API()}/schedules/enabled`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: false }),
    });
    expect(disableRes.ok).toBe(true);
    const disableData = await disableRes.json();
    expect(disableData.enabled).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// Extended Plugin Endpoints
// ---------------------------------------------------------------------------

test.describe("API – Plugins (extended)", () => {
  test("can get a specific plugin by ID", async () => {
    const res = await fetch(`${API()}/plugins/date_time`);
    if (res.ok) {
      const data = await res.json();
      expect(data).toHaveProperty("id", "date_time");
      expect(data).toHaveProperty("name");
      expect(data).toHaveProperty("enabled");
      expect(data).toHaveProperty("settings_schema");
    } else {
      expect(res.status).toBe(503);
    }
  });

  test("can enable and disable a plugin", async () => {
    const enableRes = await fetch(`${API()}/plugins/date_time/enable`, { method: "POST" });
    if (enableRes.ok) {
      const enableData = await enableRes.json();
      expect(enableData.enabled).toBe(true);

      const disableRes = await fetch(`${API()}/plugins/date_time/disable`, { method: "POST" });
      expect(disableRes.ok).toBe(true);
      const disableData = await disableRes.json();
      expect(disableData.enabled).toBe(false);
    } else {
      expect(enableRes.status).toBe(503);
    }
  });

  test("can update plugin config", async () => {
    const res = await fetch(`${API()}/plugins/date_time/config`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ config: { timezone: "UTC" } }),
    });
    if (res.ok) {
      const data = await res.json();
      expect(data.status).toBe("success");
      expect(data.plugin_id).toBe("date_time");
    } else {
      expect(res.status).toBe(503);
    }
  });

  test("can get plugin variables", async () => {
    const res = await fetch(`${API()}/plugins/date_time/variables`);
    if (res.ok) {
      const data = await res.json();
      expect(data).toHaveProperty("plugin_id", "date_time");
      expect(data).toHaveProperty("variables");
    } else {
      expect(res.status).toBe(503);
    }
  });
});

// ---------------------------------------------------------------------------
// Extended Settings Endpoints
// ---------------------------------------------------------------------------

test.describe("API – Settings (extended)", () => {
  test("returns transition settings", async () => {
    const res = await fetch(`${API()}/settings/transitions`);
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data).toHaveProperty("strategy");
    expect(data).toHaveProperty("step_interval_ms");
    expect(data).toHaveProperty("available_strategies");
  });

  test("can update transition settings", async () => {
    // First get valid strategies
    const getRes = await fetch(`${API()}/settings/transitions`);
    expect(getRes.ok).toBe(true);
    const current = await getRes.json();
    const strategies: string[] = current.available_strategies || [];
    const target = strategies.find((s: string) => s !== current.strategy) || current.strategy;

    const res = await fetch(`${API()}/settings/transitions`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ strategy: target }),
    });
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data.status).toBe("success");

    // Restore original
    await fetch(`${API()}/settings/transitions`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ strategy: current.strategy }),
    });
  });

  test("can get and set active page", async () => {
    const pRes = await fetch(`${API()}/pages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: "Active Page Test",
        type: "template",
        template: ["ACTIVE", "", "", "", "", ""],
      }),
    });
    const pData = await pRes.json();
    const pageId = pData.page.id;

    const setRes = await fetch(`${API()}/settings/active-page`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ page_id: pageId }),
    });
    expect(setRes.ok).toBe(true);

    const getRes = await fetch(`${API()}/settings/active-page`);
    expect(getRes.ok).toBe(true);
    const getData = await getRes.json();
    expect(getData.page_id).toBe(pageId);

    await fetch(`${API()}/pages/${pageId}`, { method: "DELETE" });
  });

  test("returns board display settings", async () => {
    const res = await fetch(`${API()}/settings/board`);
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data).toHaveProperty("board_type");
  });

  test("can update board display settings", async () => {
    const res = await fetch(`${API()}/settings/board`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ board_type: "black" }),
    });
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data.status).toBe("success");
  });

  test("board settings include boards and devices arrays", async () => {
    const res = await fetch(`${API()}/settings/board`);
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data).toHaveProperty("boards");
    expect(data).toHaveProperty("devices");
    expect(Array.isArray(data.boards)).toBe(true);
    expect(Array.isArray(data.devices)).toBe(true);
    expect(data.boards.length).toBeGreaterThan(0);
    expect(data.devices.length).toBeGreaterThan(0);
  });

  test("can add and remove a board instance", async () => {
    const addRes = await fetch(`${API()}/settings/board/add`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ device_type: "note", name: "My Note" }),
    });
    expect(addRes.ok).toBe(true);
    const addData = await addRes.json();
    expect(addData.status).toBe("success");
    const noteBoard = addData.settings.boards.find(
      (b: { device_type: string }) => b.device_type === "note",
    );
    expect(noteBoard).toBeDefined();
    expect(noteBoard.name).toBe("My Note");
    const boardId = noteBoard.id;

    const delRes = await fetch(`${API()}/settings/board/${boardId}`, {
      method: "DELETE",
    });
    expect(delRes.ok).toBe(true);
    const delData = await delRes.json();
    expect(delData.status).toBe("success");
    const stillThere = delData.settings.boards.find(
      (b: { id: string }) => b.id === boardId,
    );
    expect(stillThere).toBeUndefined();
  });

  test("can update devices via backward-compatible devices field", async () => {
    const res = await fetch(`${API()}/settings/board`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ devices: ["flagship", "note"] }),
    });
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data.status).toBe("success");
    expect(data.settings.devices).toContain("flagship");
    expect(data.settings.devices).toContain("note");

    // Reset to flagship only
    await fetch(`${API()}/settings/board`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ devices: ["flagship"] }),
    });
  });
});

// ---------------------------------------------------------------------------
// Extended Template Endpoints
// ---------------------------------------------------------------------------

test.describe("API – Templates (extended)", () => {
  test("can render a template with live data", async () => {
    const res = await fetch(`${API()}/templates/render`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ template: ["HELLO WORLD", "", "", "", "", ""] }),
    });
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data).toHaveProperty("rendered");
    expect(data).toHaveProperty("lines");
    expect(data).toHaveProperty("line_count");
  });
});

// ---------------------------------------------------------------------------
// Service Control
// ---------------------------------------------------------------------------

test.describe("API – Service Control", () => {
  test("can get service status", async () => {
    const res = await fetch(`${API()}/status`);
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(typeof data).toBe("object");
  });

  test("can start and stop the service", async () => {
    // Service start may fail in Docker (no display loop available).
    // We verify the endpoints respond and accept the request.
    const startRes = await fetch(`${API()}/start`, { method: "POST" });
    expect([200, 400, 500]).toContain(startRes.status);

    const stopRes = await fetch(`${API()}/stop`, { method: "POST" });
    expect([200, 400, 500]).toContain(stopRes.status);
  });
});
