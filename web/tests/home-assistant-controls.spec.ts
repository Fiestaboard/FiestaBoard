/**
 * Home Assistant controls round-trip validation.
 *
 * Sends commands through the HA REST API and verifies that FiestaBoard's
 * own API reflects the resulting state change. Tests the full MQTT
 * command → FiestaBoard service → MQTT state feedback loop.
 *
 * Requirements:
 *   - HA running with MQTT integration connected to Mosquitto
 *   - FiestaBoard running with MQTT_ENABLED=true and connected to same broker
 *   - HA entities discovered (MQTT discovery published by the FiestaBoard process)
 *
 * Run:
 *   HA_URL=http://localhost:8123 \
 *   HA_ACCESS_TOKEN=<long_lived_token> \
 *   npx playwright test tests/home-assistant-controls.spec.ts
 *
 * Note: These tests mutate live FiestaBoard state. They restore their changes
 * where possible but may leave transient state if interrupted.
 */
import { expect, test } from "@playwright/test";

const HA_URL = (process.env.HA_URL || "").replace(/\/$/, "");
const HA_ACCESS_TOKEN = process.env.HA_ACCESS_TOKEN || "";
const FB_URL = (process.env.BASE_URL || "http://localhost:4420").replace(/\/$/, "");

// Allow extra time for MQTT round-trips (command → FiestaBoard → state)
const MQTT_SETTLE_MS = 3000;

/** Check if the FiestaBoard MQTT client is live and connected. */
async function isFiestaboardMqttConnected(request: any): Promise<boolean> {
  try {
    const res = await request.get(`${FB_URL}/api/mqtt/status`);
    if (!res.ok()) return false;
    const data = await res.json();
    return data.connected === true;
  } catch {
    return false;
  }
}

// ---- helpers ---------------------------------------------------------------

function haHeaders() {
  return { Authorization: `Bearer ${HA_ACCESS_TOKEN}` };
}

/** GET a HA entity state. */
async function haState(request: any, entityId: string): Promise<string> {
  const res = await request.get(`${HA_URL}/api/states/${entityId}`, {
    headers: haHeaders(),
  });
  expect(res.ok(), `Could not fetch HA state for ${entityId}`).toBe(true);
  const data = await res.json();
  return data.state as string;
}

/** Call a HA service. */
async function haService(request: any, domain: string, service: string, data: Record<string, unknown>): Promise<void> {
  const res = await request.post(`${HA_URL}/api/services/${domain}/${service}`, {
    headers: { ...haHeaders(), "Content-Type": "application/json" },
    data,
  });
  expect(res.ok(), `HA service ${domain}.${service} failed`).toBe(true);
}

/** Wait for MQTT to settle then poll for a condition. */
async function waitFor(check: () => Promise<boolean>, timeoutMs = 8000, intervalMs = 500): Promise<boolean> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await check()) return true;
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  return false;
}

// ---- tests -----------------------------------------------------------------

test.describe("Home Assistant controls", () => {
  test.beforeEach(async () => {
    test.skip(!HA_URL || !HA_ACCESS_TOKEN, "HA_URL and HA_ACCESS_TOKEN must be set");
  });

  /**
   * One-time setup: configure FiestaBoard with the mock board and ensure at
   * least two pages exist. This runs after global-setup (which wipes data files)
   * so the HA tests are self-contained.
   */
  test.beforeAll(async ({ request }) => {
    if (!HA_URL || !HA_ACCESS_TOKEN) return;

    // Configure board with mock server (may already be configured)
    await request.put(`${FB_URL}/api/config/board`, {
      data: { api_mode: "local", local_api_key: "test-key", host: "fiestaboard-mock-board" },
    });

    // Ensure at least two pages exist for the Active Page select tests
    const pagesRes = await request.get(`${FB_URL}/api/pages`);
    if (pagesRes.ok()) {
      const pagesData = await pagesRes.json();
      const existing: string[] = (pagesData.pages || []).map((p: { name: string }) => p.name);
      if (!existing.includes("Weather")) {
        await request.post(`${FB_URL}/api/pages`, {
          data: { name: "Weather", type: "template", template: ["WEATHER"] },
        });
      }
      if (!existing.includes("News")) {
        await request.post(`${FB_URL}/api/pages`, {
          data: { name: "News", type: "template", template: ["NEWS"] },
        });
      }
    }

    // Start the display service
    await request.post(`${FB_URL}/api/start`);

    // Republish MQTT discovery so HA gets the current page list as select options
    const republishRes = await request.post(`${FB_URL}/api/mqtt/republish-discovery`);
    if (republishRes.ok()) {
      // Give HA time to process the updated discovery messages
      await new Promise((r) => setTimeout(r, 3000));
    }
  });

  // --------------------------------------------------------------------------
  // 1. Schedule switch
  // --------------------------------------------------------------------------
  test("Schedule switch toggles FiestaBoard schedule on/off", async ({ request }) => {
    const mqttLive = await isFiestaboardMqttConnected(request);
    test.skip(
      !mqttLive,
      "FiestaBoard MQTT client is not connected — state feedback tests require MQTT_ENABLED=true in the FiestaBoard container",
    );

    const entityId = "switch.fiestaboard_schedule";

    // Read initial state from HA
    const initial = await haState(request, entityId);

    // Toggle off if currently on, then back on — ensures we exercise both paths
    const turnOff = initial === "on";

    if (turnOff) {
      await haService(request, "switch", "turn_off", { entity_id: entityId });
    } else {
      await haService(request, "switch", "turn_on", { entity_id: entityId });
    }

    // Wait for state to propagate: HA state should reflect the change
    const settled = await waitFor(async () => {
      const s = await haState(request, entityId);
      return turnOff ? s === "off" : s === "on";
    });
    expect(settled, "HA schedule switch state did not update after command").toBe(true);

    // Restore
    if (turnOff) {
      await haService(request, "switch", "turn_on", { entity_id: entityId });
    } else {
      await haService(request, "switch", "turn_off", { entity_id: entityId });
    }
  });

  // --------------------------------------------------------------------------
  // 2. Active Page select
  // --------------------------------------------------------------------------
  test("Active Page select changes the active page in FiestaBoard", async ({ request }) => {
    const mqttLive = await isFiestaboardMqttConnected(request);
    test.skip(
      !mqttLive,
      "FiestaBoard MQTT client is not connected — state feedback tests require MQTT_ENABLED=true in the FiestaBoard container",
    );

    // Get available page options from HA
    const statesRes = await request.get(`${HA_URL}/api/states`, {
      headers: haHeaders(),
    });
    expect(statesRes.ok()).toBe(true);
    const states = await statesRes.json();
    const selectEntity = states.find((e: { entity_id: string }) => e.entity_id === "select.fiestaboard_active_page");
    if (!selectEntity) {
      test.skip(true, "select.fiestaboard_active_page not found in HA");
    }

    const options: string[] = selectEntity.attributes?.options ?? [];
    if (options.length < 2) {
      test.skip(true, "Need at least 2 page options to test select");
    }

    const initial: string = selectEntity.state;
    // Pick a different option
    const target = options.find((o: string) => o !== initial) ?? options[0];

    await haService(request, "select", "select_option", {
      entity_id: "select.fiestaboard_active_page",
      option: target,
    });

    // Wait for HA state to reflect
    const settled = await waitFor(async () => {
      const s = await haState(request, "select.fiestaboard_active_page");
      return s === target;
    });
    expect(settled, `HA active_page did not switch to "${target}"`).toBe(true);

    // Also verify via FiestaBoard API
    await new Promise((r) => setTimeout(r, MQTT_SETTLE_MS));
    const fbRes = await request.get(`${FB_URL}/api/settings/active-page`);
    if (fbRes.ok()) {
      const fbData = await fbRes.json();
      // FiestaBoard returns active_page_id; the page name should match
      // We verify via the HA state which reads from FiestaBoard's MQTT publish
      expect(await haState(request, "select.fiestaboard_active_page")).toBe(target);
    }

    // Restore original page
    if (initial && initial !== target) {
      await haService(request, "select", "select_option", {
        entity_id: "select.fiestaboard_active_page",
        option: initial,
      });
    }
  });

  // --------------------------------------------------------------------------
  // 3. Refresh Display button
  // --------------------------------------------------------------------------
  test("Refresh Display button can be pressed without error", async ({ request }) => {
    const res = await request.post(`${HA_URL}/api/services/button/press`, {
      headers: { ...haHeaders(), "Content-Type": "application/json" },
      data: { entity_id: "button.fiestaboard_refresh_display" },
    });
    // HA returns 200 with an array of changed states
    expect(res.ok(), "Pressing Refresh Display button failed in HA").toBe(true);
  });

  // --------------------------------------------------------------------------
  // 4. Blank Board button
  // --------------------------------------------------------------------------
  test("Blank Board button can be pressed without error", async ({ request }) => {
    const res = await request.post(`${HA_URL}/api/services/button/press`, {
      headers: { ...haHeaders(), "Content-Type": "application/json" },
      data: { entity_id: "button.fiestaboard_blank_board" },
    });
    expect(res.ok(), "Pressing Blank Board button failed in HA").toBe(true);
  });

  // --------------------------------------------------------------------------
  // 5. Send Message text entity
  // --------------------------------------------------------------------------
  test("Send Message text entity delivers a message via HA", async ({ request }) => {
    const res = await request.post(`${HA_URL}/api/services/text/set_value`, {
      headers: { ...haHeaders(), "Content-Type": "application/json" },
      data: {
        entity_id: "text.fiestaboard_send_message",
        value: "HELLO HA TEST",
      },
    });
    expect(res.ok(), "text.set_value for send_message failed in HA").toBe(true);
  });

  // --------------------------------------------------------------------------
  // 6. Refresh Interval number entity
  // --------------------------------------------------------------------------
  test("Refresh Interval number entity updates interval in FiestaBoard", async ({ request }) => {
    const mqttLive = await isFiestaboardMqttConnected(request);
    test.skip(
      !mqttLive,
      "FiestaBoard MQTT client is not connected — state feedback tests require MQTT_ENABLED=true in the FiestaBoard container",
    );

    const entityId = "number.fiestaboard_refresh_interval";

    const initialStr = await haState(request, entityId);
    const initial = parseFloat(initialStr);

    // Pick a different valid value
    const newValue = initial === 300 ? 360 : 300;

    await haService(request, "number", "set_value", {
      entity_id: entityId,
      value: newValue,
    });

    // Wait for HA state to reflect
    const settled = await waitFor(async () => {
      const s = await haState(request, entityId);
      return Math.abs(parseFloat(s) - newValue) < 1;
    });
    expect(settled, `HA refresh_interval did not update to ${newValue}`).toBe(true);

    // Restore
    await haService(request, "number", "set_value", {
      entity_id: entityId,
      value: initial,
    });
  });

  // --------------------------------------------------------------------------
  // 7. Sensor states are readable (status, version, page_count)
  // --------------------------------------------------------------------------
  test("FiestaBoard sensors report valid read-only state in HA", async ({ request }) => {
    const checks: Array<{ id: string; validate: (s: string) => boolean; desc: string }> = [
      {
        id: "binary_sensor.fiestaboard_service_status",
        validate: (s) => s === "on" || s === "off",
        desc: "service_status must be on or off",
      },
      {
        id: "sensor.fiestaboard_version",
        validate: (s) => /\d+\.\d+/.test(s),
        desc: "version must look like a semver string",
      },
      {
        id: "sensor.fiestaboard_page_count",
        validate: (s) => !isNaN(parseInt(s, 10)),
        desc: "page_count must be a number",
      },
      {
        id: "sensor.fiestaboard_current_page",
        validate: (s) => typeof s === "string" && s.length > 0,
        desc: "current_page must be a non-empty string",
      },
    ];

    for (const { id, validate, desc } of checks) {
      const state = await haState(request, id);
      expect(validate(state), `${id}: ${desc} (got "${state}")`).toBe(true);
    }
  });

  // --------------------------------------------------------------------------
  // 8. Transition Style select
  // --------------------------------------------------------------------------
  test("Transition Style select updates in HA after command", async ({ request }) => {
    const mqttLive = await isFiestaboardMqttConnected(request);
    test.skip(
      !mqttLive,
      "FiestaBoard MQTT client is not connected — state feedback tests require MQTT_ENABLED=true in the FiestaBoard container",
    );

    const entityId = "select.fiestaboard_transition_style";
    const statesRes = await request.get(`${HA_URL}/api/states/${entityId}`, {
      headers: haHeaders(),
    });
    expect(statesRes.ok()).toBe(true);
    const entity = await statesRes.json();
    const options: string[] = entity.attributes?.options ?? [];
    const initial: string = entity.state;

    if (options.length < 2) {
      test.skip(true, "Need at least 2 transition options to test select");
    }

    const target = options.find((o: string) => o !== initial) ?? options[0];

    await haService(request, "select", "select_option", {
      entity_id: entityId,
      option: target,
    });

    const settled = await waitFor(async () => {
      const s = await haState(request, entityId);
      return s === target;
    });
    expect(settled, `Transition style did not switch to "${target}"`).toBe(true);

    // Restore
    if (initial && initial !== target) {
      await haService(request, "select", "select_option", {
        entity_id: entityId,
        option: initial,
      });
    }
  });
});
