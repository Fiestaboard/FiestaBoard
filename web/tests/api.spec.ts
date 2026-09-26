/**
 * FiestaBoard API Integration Tests – Core Endpoints
 *
 * Covers fundamental API contracts: version, config, settings,
 * basic CRUD for pages/schedules, plugins listing, templates,
 * displays, and debug endpoints.
 *
 * Extended endpoint tests live in api-extended.spec.ts.
 */
import { API_URL, configureBoard, expect, test } from "./helpers";

function API() {
  return API_URL;
}

// Ensure the board is configured before each API test
test.beforeEach(async () => {
  await configureBoard();
});

// ---------------------------------------------------------------------------
// Version & Config
// ---------------------------------------------------------------------------

test.describe("API – Version & Config", () => {
  test("returns version information", async () => {
    const res = await fetch(`${API()}/version`);
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data).toHaveProperty("package_version");
    expect(data).toHaveProperty("build_version");
    expect(data).toHaveProperty("is_dev");
  });

  test("returns configuration summary", async () => {
    const res = await fetch(`${API()}/config`);
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
    const res = await fetch(`${API()}/settings/all`);
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data).toHaveProperty("polling");
    expect(data).toHaveProperty("transitions");
    expect(data).toHaveProperty("output");
    expect(data).toHaveProperty("board");
    expect(data).toHaveProperty("status");
  });

  test("can update output target", async () => {
    const res = await fetch(`${API()}/settings/output`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target: "ui" }),
    });
    expect(res.ok).toBe(true);
    const data = await res.json();
    // Bare OutputSettings since the conventions pass (Phase 2, Task 8).
    expect(data.target).toBe("ui");

    // Reset to default
    await fetch(`${API()}/settings/output`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target: "board" }),
    });
  });

  test("can update polling interval", async () => {
    const res = await fetch(`${API()}/settings/polling`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ interval_seconds: 15 }),
    });
    expect(res.ok).toBe(true);
    const data = await res.json();
    // Bare PollingSettings + requires_restart since the conventions pass.
    expect(data.interval_seconds).toBe(15);
  });

  test("rejects invalid polling interval", async () => {
    const res = await fetch(`${API()}/settings/polling`, {
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
    const res = await fetch(`${API()}/pages`);
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data).toHaveProperty("pages");
    expect(data).toHaveProperty("total");
    expect(Array.isArray(data.pages)).toBe(true);
  });

  test("can create and delete a page", async () => {
    // Create
    const createRes = await fetch(`${API()}/pages`, {
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
    // 201 + the bare page since the Phase 2 conventions pass.
    expect(createRes.status).toBe(201);
    const pageId = created.id;
    expect(pageId).toBeTruthy();

    // Delete
    const deleteRes = await fetch(`${API()}/pages/${pageId}`, {
      method: "DELETE",
    });
    expect(deleteRes.ok).toBe(true);
    const deleted = await deleteRes.json();
    // The envelope's "status" is gone; the deleted id is the contract now.
    expect(deleted.id).toBe(pageId);
  });
});

// ---------------------------------------------------------------------------
// Schedules CRUD
// ---------------------------------------------------------------------------

test.describe("API – Schedules", () => {
  test("can list schedules", async () => {
    const res = await fetch(`${API()}/schedules`);
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data).toHaveProperty("schedules");
    expect(data).toHaveProperty("total");
    expect(Array.isArray(data.schedules)).toBe(true);
  });

  test("can create and delete a schedule", async () => {
    // Ensure at least one page exists to reference. The primary board is a
    // flagship, and since #1245 the backend rejects size-incompatible
    // schedule pages — so pick a FLAGSHIP page (pages[0] may be a
    // note/note-array page left behind by another spec).
    const pagesRes = await fetch(`${API()}/pages`);
    const pagesData = await pagesRes.json();
    let pageId: string;

    const flagshipPage = (pagesData.pages ?? []).find(
      (p: { device_type?: string }) => (p.device_type || "flagship") === "flagship",
    );
    if (flagshipPage) {
      pageId = flagshipPage.id;
    } else {
      // Create a temporary page
      const createPageRes = await fetch(`${API()}/pages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: "Schedule Test Page",
          type: "template",
          template: ["SCHEDULE TEST", "", "", "", "", ""],
        }),
      });
      const createdPage = await createPageRes.json();
      pageId = createdPage.id;
    }

    // Create a schedule
    const createRes = await fetch(`${API()}/schedules`, {
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
    const deleteRes = await fetch(`${API()}/schedules/${scheduleId}`, {
      method: "DELETE",
    });
    expect(deleteRes.ok).toBe(true);
    const deleted = await deleteRes.json();
    // Phase 2 conventions: delete answers with the deleted id, not a status
    // envelope — the HTTP status already carries success.
    expect(deleted.id).toBe(scheduleId);
  });
});

// ---------------------------------------------------------------------------
// Plugins
// ---------------------------------------------------------------------------

test.describe("API – Plugins", () => {
  test("can list plugins", async () => {
    const res = await fetch(`${API()}/plugins`);
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
    const res = await fetch(`${API()}/templates/variables`);
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data).toHaveProperty("variables");
    expect(data).toHaveProperty("colors");
    expect(data).toHaveProperty("symbols");
    expect(data).toHaveProperty("filters");
  });

  test("validates a correct template", async () => {
    const res = await fetch(`${API()}/templates/validate`, {
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
    const res = await fetch(`${API()}/displays`);
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data).toHaveProperty("displays");
    expect(data).toHaveProperty("total");
    expect(Array.isArray(data.displays)).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// Debug Endpoints
// ---------------------------------------------------------------------------

// Bodies are bare since the Phase 2 debug slice: no { status: "success" }
// envelope, and refusals are status codes (409 paused, 429 throttled,
// 503 unreachable) rather than a 200 carrying a word.
test.describe("API – Debug", () => {
  test("can test board connection", async () => {
    const res = await fetch(`${API()}/debug/test-connection`, {
      method: "POST",
    });
    // Connection may or may not succeed depending on board config state.
    // 503 = board configured but unreachable (#1887 made that a real status
    // instead of a 200 carrying { status: "error" }).
    expect([200, 400, 503]).toContain(res.status);
    if (res.ok) {
      const data = await res.json();
      expect(data.connected).toBe(true);
      expect(typeof data.latency_ms).toBe("number");
    }
  });

  test("returns system information", async () => {
    const res = await fetch(`${API()}/debug/system-info`);
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data).toHaveProperty("version");
    expect(data).toHaveProperty("connection_mode");
    expect(data).toHaveProperty("service_running");
  });

  test("can blank the board", async () => {
    const res = await fetch(`${API()}/debug/blank`, { method: "POST" });
    // 409 = the board is paused, which is a refusal, not a success.
    expect([200, 409]).toContain(res.status);
    const data = await res.json();
    expect(typeof (res.ok ? data.message : data.detail)).toBe("string");
  });

  test("rejects a character code outside the flap range", async () => {
    const res = await fetch(`${API()}/debug/fill`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ character_code: 99 }),
    });
    expect(res.status).toBe(422);
  });

  test("returns cache status", async () => {
    const res = await fetch(`${API()}/debug/cache-status`);
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data).toHaveProperty("has_cached_text");
    expect(data).toHaveProperty("skip_unchanged_enabled");
  });

  test("can clear message cache", async () => {
    const res = await fetch(`${API()}/debug/clear-cache`, { method: "POST" });
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(typeof data.message).toBe("string");
  });
});

// ---------------------------------------------------------------------------
// Deprecation notices on the internal surface
// ---------------------------------------------------------------------------

// These specs are, deliberately, the internal surface's contract tests — the
// web client itself moved onto /v1 wherever /v1 supersedes (#1934). A test
// caller does not save an endpoint from deprecation, but it does have to know
// what the endpoint now says: 25 of these paths carry RFC 9745 `Deprecation`,
// RFC 8594 `Sunset` and an RFC 8288 `successor-version` link on every
// successful response (#1941).
//
// This is the only layer that proves the headers survive nginx. The Python
// suite exercises the ASGI app directly; nginx is what a real caller talks to,
// and a proxy that dropped these would make the whole notice invisible.

const SUNSET = "Tue, 01 Dec 2026 00:00:00 GMT";

/** The v1 operation each of these announces as its replacement. */
const SUPERSEDED: Array<[string, string]> = [
  ["/pages", "/api/v1/pages"],
  ["/collections", "/api/v1/collections"],
  ["/schedules", "/api/v1/schedules"],
  ["/status", "/api/v1/status"],
  ["/templates/variables", "/api/v1/variables"],
  ["/templates/formula-functions", "/api/v1/functions"],
  ["/plugins/variables/all", "/api/v1/variables"],
];

/**
 * Endpoints in #1934's inventory of 33 that are deliberately NOT deprecated,
 * because their v1 equivalent still drops something. Asserting the absence is
 * what stops the cohort growing by a sweep instead of by an audit.
 */
const NOT_SUPERSEDED = ["/displays", "/schedules/enabled", "/schedules/default-page"];

test.describe("API – Deprecation notices", () => {
  for (const [path, successor] of SUPERSEDED) {
    test(`GET ${path} announces ${successor} on the wire`, async () => {
      const res = await fetch(`${API()}${path}`);
      expect(res.ok).toBe(true);
      expect(res.headers.get("deprecation")).toBe("true");
      expect(res.headers.get("sunset")).toBe(SUNSET);
      expect(res.headers.get("link")).toBe(`<${successor}>; rel="successor-version"`);
    });
  }

  for (const path of NOT_SUPERSEDED) {
    test(`GET ${path} sends no deprecation notice`, async () => {
      const res = await fetch(`${API()}${path}`);
      expect(res.ok).toBe(true);
      expect(res.headers.get("deprecation")).toBeNull();
      expect(res.headers.get("sunset")).toBeNull();
    });
  }

  test("the /v1 successors do not announce their own removal", async () => {
    for (const successor of ["/api/v1/pages", "/api/v1/collections", "/api/v1/status"]) {
      // API() already ends in /api, so strip the duplicate prefix.
      const res = await fetch(`${API()}${successor.replace(/^\/api/, "")}`);
      expect(res.ok).toBe(true);
      expect(res.headers.get("deprecation")).toBeNull();
    }
  });

  test("a deprecated write announces its successor too", async () => {
    const created = await fetch(`${API()}/pages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: `Deprecation Notice ${Date.now()}`,
        type: "template",
        template: ["HELLO"],
      }),
    });
    expect(created.status).toBe(201);
    expect(created.headers.get("deprecation")).toBe("true");
    expect(created.headers.get("link")).toBe('</api/v1/pages>; rel="successor-version"');

    const { id } = await created.json();
    const deleted = await fetch(`${API()}/pages/${id}`, { method: "DELETE" });
    expect(deleted.ok).toBe(true);
    expect(deleted.headers.get("link")).toBe('</api/v1/pages/{page_id}>; rel="successor-version"');
  });
});
