/**
 * FiestaBoard API Integration Tests – Core Endpoints
 *
 * Covers fundamental API contracts: version, config, settings,
 * basic CRUD for pages/schedules, plugins listing, templates,
 * displays, dev-mode toggle, and debug endpoints.
 *
 * Extended endpoint tests live in api-extended.spec.ts.
 */
import { test, expect, configureBoard, API_URL } from "./helpers";

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
      body: JSON.stringify({ interval_seconds: 15 }),
    });
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data.status).toBe("success");
    expect(data.settings.interval_seconds).toBe(15);
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

