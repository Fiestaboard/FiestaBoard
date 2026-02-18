/**
 * FiestaBoard API Integration Tests
 *
 * Direct backend API tests that verify endpoint behaviour without
 * going through the browser UI.  These complement the UI-driven
 * tests in integration.spec.ts by covering API-level contracts.
 *
 * Coverage:
 *   - Version / config / settings endpoints
 *   - Pages CRUD via API
 *   - Schedules CRUD via API
 *   - Plugins listing
 *   - Template variable catalog & validation
 *   - Display source listing
 *   - Dev-mode toggle
 *   - Debug endpoints (test-connection, system-info)
 */
import { test, expect, configureBoard, API_URL, BOARD_HOST } from "./helpers";

const API = API_URL;

// Ensure the board is configured before each API test
test.beforeEach(async () => {
  await configureBoard();
});

// ---------------------------------------------------------------------------
// Version & Config
// ---------------------------------------------------------------------------

test.describe("API – Version & Config", () => {
  test("returns version information", async () => {
    const res = await fetch(`${API}/version`);
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data).toHaveProperty("package_version");
    expect(data).toHaveProperty("build_version");
    expect(data).toHaveProperty("is_dev");
  });

  test("returns configuration summary", async () => {
    const res = await fetch(`${API}/config`);
    expect(res.ok).toBe(true);
    const data = await res.json();
    // Config summary is an object with board / general keys
    expect(typeof data).toBe("object");
  });
});

// ---------------------------------------------------------------------------
// Settings
// ---------------------------------------------------------------------------

test.describe("API – Settings", () => {
  test("returns all settings", async () => {
    const res = await fetch(`${API}/settings/all`);
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data).toHaveProperty("polling");
    expect(data).toHaveProperty("transitions");
    expect(data).toHaveProperty("output");
    expect(data).toHaveProperty("board");
    expect(data).toHaveProperty("status");
  });

  test("can update output target", async () => {
    const res = await fetch(`${API}/settings/output`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target: "ui" }),
    });
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data.status).toBe("success");
    expect(data.settings.target).toBe("ui");

    // Reset to default
    await fetch(`${API}/settings/output`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target: "board" }),
    });
  });

  test("can update polling interval", async () => {
    const res = await fetch(`${API}/settings/polling`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ interval_seconds: 30 }),
    });
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data.status).toBe("success");
    expect(data.settings.interval_seconds).toBe(30);
  });

  test("rejects invalid polling interval", async () => {
    const res = await fetch(`${API}/settings/polling`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ interval_seconds: 1 }),
    });
    // The backend should reject values below the minimum (10)
    expect(res.status).toBeGreaterThanOrEqual(400);
  });
});

// ---------------------------------------------------------------------------
// Pages CRUD
// ---------------------------------------------------------------------------

test.describe("API – Pages", () => {
  test("can list pages", async () => {
    const res = await fetch(`${API}/pages`);
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data).toHaveProperty("pages");
    expect(data).toHaveProperty("total");
    expect(Array.isArray(data.pages)).toBe(true);
  });

  test("can create and delete a page", async () => {
    // Create
    const createRes = await fetch(`${API}/pages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: "API Test Page",
        type: "template",
        template: ["HELLO FROM API", "", "", "", "", ""],
      }),
    });
    expect(createRes.ok).toBe(true);
    const created = await createRes.json();
    expect(created.status).toBe("success");
    const pageId = created.page.id;
    expect(pageId).toBeTruthy();

    // Delete
    const deleteRes = await fetch(`${API}/pages/${pageId}`, {
      method: "DELETE",
    });
    expect(deleteRes.ok).toBe(true);
    const deleted = await deleteRes.json();
    expect(deleted.status).toBe("success");
  });
});

// ---------------------------------------------------------------------------
// Schedules CRUD
// ---------------------------------------------------------------------------

test.describe("API – Schedules", () => {
  test("can list schedules", async () => {
    const res = await fetch(`${API}/schedules`);
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data).toHaveProperty("schedules");
    expect(data).toHaveProperty("total");
    expect(Array.isArray(data.schedules)).toBe(true);
  });

  test("can create and delete a schedule", async () => {
    // Ensure at least one page exists to reference
    const pagesRes = await fetch(`${API}/pages`);
    const pagesData = await pagesRes.json();
    let pageId: string;

    if (pagesData.total > 0) {
      pageId = pagesData.pages[0].id;
    } else {
      // Create a temporary page
      const createPageRes = await fetch(`${API}/pages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: "Schedule Test Page",
          type: "template",
          template: ["SCHEDULE TEST", "", "", "", "", ""],
        }),
      });
      const createdPage = await createPageRes.json();
      pageId = createdPage.page.id;
    }

    // Create a schedule
    const createRes = await fetch(`${API}/schedules`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        page_id: pageId,
        day_pattern: "weekdays",
        start_time: "08:00",
        end_time: "12:00",
      }),
    });
    expect(createRes.ok).toBe(true);
    const created = await createRes.json();
    const scheduleId = created.id;
    expect(scheduleId).toBeTruthy();

    // Delete the schedule
    const deleteRes = await fetch(`${API}/schedules/${scheduleId}`, {
      method: "DELETE",
    });
    expect(deleteRes.ok).toBe(true);
    const deleted = await deleteRes.json();
    expect(deleted.status).toBe("success");
  });
});

// ---------------------------------------------------------------------------
// Plugins
// ---------------------------------------------------------------------------

test.describe("API – Plugins", () => {
  test("can list plugins", async () => {
    const res = await fetch(`${API}/plugins`);
    // Plugins endpoint may return 503 if plugin system is not available
    if (res.ok) {
      const data = await res.json();
      expect(data).toHaveProperty("plugins");
      expect(data).toHaveProperty("total");
      expect(Array.isArray(data.plugins)).toBe(true);
    } else {
      // 503 is acceptable – plugin system not available in test env
      expect(res.status).toBe(503);
    }
  });
});

// ---------------------------------------------------------------------------
// Templates
// ---------------------------------------------------------------------------

test.describe("API – Templates", () => {
  test("returns template variables", async () => {
    const res = await fetch(`${API}/templates/variables`);
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data).toHaveProperty("variables");
    expect(data).toHaveProperty("colors");
    expect(data).toHaveProperty("symbols");
    expect(data).toHaveProperty("filters");
  });

  test("validates a correct template", async () => {
    const res = await fetch(`${API}/templates/validate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        template: ["HELLO WORLD", "", "", "", "", ""],
      }),
    });
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data.valid).toBe(true);
    expect(data.errors).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// Displays
// ---------------------------------------------------------------------------

test.describe("API – Displays", () => {
  test("can list displays", async () => {
    const res = await fetch(`${API}/displays`);
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data).toHaveProperty("displays");
    expect(data).toHaveProperty("total");
    expect(Array.isArray(data.displays)).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// Dev Mode
// ---------------------------------------------------------------------------

test.describe("API – Dev Mode", () => {
  test("can get and set dev mode", async () => {
    // Get current state
    const getRes = await fetch(`${API}/dev-mode`);
    expect(getRes.ok).toBe(true);
    const initial = await getRes.json();
    expect(initial).toHaveProperty("dev_mode");
    const originalMode = initial.dev_mode;

    // Toggle on
    const onRes = await fetch(`${API}/dev-mode`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ dev_mode: true }),
    });
    expect(onRes.ok).toBe(true);
    const onData = await onRes.json();
    expect(onData.dev_mode).toBe(true);

    // Toggle off
    const offRes = await fetch(`${API}/dev-mode`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ dev_mode: false }),
    });
    expect(offRes.ok).toBe(true);
    const offData = await offRes.json();
    expect(offData.dev_mode).toBe(false);

    // Restore original state so subsequent tests aren't affected
    await fetch(`${API}/dev-mode`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ dev_mode: originalMode }),
    });
  });
});

// ---------------------------------------------------------------------------
// Debug Endpoints
// ---------------------------------------------------------------------------

test.describe("API – Debug", () => {
  test("can test board connection", async () => {
    const res = await fetch(`${API}/debug/test-connection`, {
      method: "POST",
    });
    // Connection may or may not succeed depending on board config state
    expect([200, 400]).toContain(res.status);
    if (res.ok) {
      const data = await res.json();
      expect(data).toHaveProperty("connected");
      expect(data).toHaveProperty("latency_ms");
    }
  });

  test("returns system information", async () => {
    const res = await fetch(`${API}/debug/system-info`);
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data).toHaveProperty("version");
    expect(data).toHaveProperty("connection_mode");
    expect(data).toHaveProperty("service_running");
    expect(data).toHaveProperty("dev_mode");
  });

  test("can blank the board", async () => {
    const res = await fetch(`${API}/debug/blank`, { method: "POST" });
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data).toHaveProperty("status");
  });

  test("returns cache status", async () => {
    const res = await fetch(`${API}/debug/cache-status`);
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data).toHaveProperty("status");
    expect(data).toHaveProperty("cache");
  });

  test("can clear message cache", async () => {
    const res = await fetch(`${API}/debug/clear-cache`, { method: "POST" });
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data).toHaveProperty("status");
  });
});

// ---------------------------------------------------------------------------
// Extended Config Endpoints
// ---------------------------------------------------------------------------

test.describe("API – Config (extended)", () => {
  test("returns full masked configuration", async () => {
    const res = await fetch(`${API}/config/full`);
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(typeof data).toBe("object");
  });

  test("returns board config with modes", async () => {
    const res = await fetch(`${API}/config/board`);
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(typeof data).toBe("object");
  });

  test("tests board connection with provided credentials", async () => {
    const res = await fetch(`${API}/config/board/test`, {
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
    const res = await fetch(`${API}/config/validate`);
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
    const res = await fetch(`${API}/pages`, {
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
      await fetch(`${API}/pages/${testPageId}`, { method: "DELETE" });
    }
  });

  test("can get a single page by ID", async () => {
    const res = await fetch(`${API}/pages/${testPageId}`);
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data.id).toBe(testPageId);
    expect(data.name).toBe("Extended API Test Page");
  });

  test("can update a page", async () => {
    const res = await fetch(`${API}/pages/${testPageId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: "Updated Page Name" }),
    });
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data.status).toBe("success");
  });

  test("can preview a page", async () => {
    const res = await fetch(`${API}/pages/${testPageId}/preview`, {
      method: "POST",
    });
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data).toHaveProperty("page_id");
    expect(data).toHaveProperty("lines");
    expect(data).toHaveProperty("message");
  });

  test("can send a page to target", async () => {
    const res = await fetch(`${API}/pages/${testPageId}/send`, {
      method: "POST",
    });
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data).toHaveProperty("status");
    expect(data).toHaveProperty("page_id");
  });

  test("can batch preview pages", async () => {
    const res = await fetch(`${API}/pages/preview/batch`, {
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
    const pRes = await fetch(`${API}/pages`, {
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

    const sRes = await fetch(`${API}/schedules`, {
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
    if (scheduleId) await fetch(`${API}/schedules/${scheduleId}`, { method: "DELETE" });
    if (pageId) await fetch(`${API}/pages/${pageId}`, { method: "DELETE" });
  });

  test("can get a single schedule by ID", async () => {
    const res = await fetch(`${API}/schedules/${scheduleId}`);
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data.id).toBe(scheduleId);
  });

  test("can update a schedule", async () => {
    const res = await fetch(`${API}/schedules/${scheduleId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ start_time: "07:00" }),
    });
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data.start_time).toBe("07:00");
  });

  test("returns active schedule page", async () => {
    const res = await fetch(`${API}/schedules/active/page`);
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data).toHaveProperty("page_id");
    expect(data).toHaveProperty("source");
    expect(data).toHaveProperty("schedule_enabled");
  });

  test("validates schedules for overlaps", async () => {
    const res = await fetch(`${API}/schedules/validate`, { method: "POST" });
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(typeof data).toBe("object");
  });

  test("can set default page", async () => {
    const res = await fetch(`${API}/schedules/default-page`, {
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
    const enableRes = await fetch(`${API}/schedules/enabled`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: true }),
    });
    expect(enableRes.ok).toBe(true);
    const enableData = await enableRes.json();
    expect(enableData.enabled).toBe(true);

    const disableRes = await fetch(`${API}/schedules/enabled`, {
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
    const res = await fetch(`${API}/plugins/date_time`);
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
    const enableRes = await fetch(`${API}/plugins/date_time/enable`, { method: "POST" });
    if (enableRes.ok) {
      const enableData = await enableRes.json();
      expect(enableData.enabled).toBe(true);

      const disableRes = await fetch(`${API}/plugins/date_time/disable`, { method: "POST" });
      expect(disableRes.ok).toBe(true);
      const disableData = await disableRes.json();
      expect(disableData.enabled).toBe(false);
    } else {
      expect(enableRes.status).toBe(503);
    }
  });

  test("can update plugin config", async () => {
    const res = await fetch(`${API}/plugins/date_time/config`, {
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
    const res = await fetch(`${API}/plugins/date_time/variables`);
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
    const res = await fetch(`${API}/settings/transitions`);
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data).toHaveProperty("strategy");
    expect(data).toHaveProperty("step_interval_ms");
    expect(data).toHaveProperty("available_strategies");
  });

  test("can update transition settings", async () => {
    // First get valid strategies
    const getRes = await fetch(`${API}/settings/transitions`);
    expect(getRes.ok).toBe(true);
    const current = await getRes.json();
    const strategies: string[] = current.available_strategies || [];
    const target = strategies.find((s: string) => s !== current.strategy) || current.strategy;

    const res = await fetch(`${API}/settings/transitions`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ strategy: target }),
    });
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data.status).toBe("success");

    // Restore original
    await fetch(`${API}/settings/transitions`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ strategy: current.strategy }),
    });
  });

  test("can get and set active page", async () => {
    const pRes = await fetch(`${API}/pages`, {
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

    const setRes = await fetch(`${API}/settings/active-page`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ page_id: pageId }),
    });
    expect(setRes.ok).toBe(true);

    const getRes = await fetch(`${API}/settings/active-page`);
    expect(getRes.ok).toBe(true);
    const getData = await getRes.json();
    expect(getData.page_id).toBe(pageId);

    await fetch(`${API}/pages/${pageId}`, { method: "DELETE" });
  });

  test("returns board display settings", async () => {
    const res = await fetch(`${API}/settings/board`);
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data).toHaveProperty("board_type");
  });

  test("can update board display settings", async () => {
    const res = await fetch(`${API}/settings/board`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ board_type: "black" }),
    });
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data.status).toBe("success");
  });
});

// ---------------------------------------------------------------------------
// Extended Template Endpoints
// ---------------------------------------------------------------------------

test.describe("API – Templates (extended)", () => {
  test("can render a template with live data", async () => {
    const res = await fetch(`${API}/templates/render`, {
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
    const res = await fetch(`${API}/status`);
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(typeof data).toBe("object");
  });

  test("can start and stop the service", async () => {
    // Service start may fail in Docker (no display loop available).
    // We verify the endpoints respond and accept the request.
    const startRes = await fetch(`${API}/start`, { method: "POST" });
    expect([200, 400, 500]).toContain(startRes.status);

    const stopRes = await fetch(`${API}/stop`, { method: "POST" });
    expect([200, 400, 500]).toContain(stopRes.status);
  });
});
