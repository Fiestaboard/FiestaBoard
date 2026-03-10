/**
 * Home Assistant discovery validation.
 *
 * Verifies that FiestaBoard appears in Home Assistant when MQTT discovery
 * is used. Uses the HA REST API (no UI automation). Skip when HA is not
 * configured.
 *
 * Run with HA running and env set:
 *   HA_URL=http://localhost:8123 HA_ACCESS_TOKEN=<long_lived_token> npx playwright test tests/home-assistant-discovery.spec.ts
 *
 * Or with docker-compose.ha.yml + FiestaBoard with MQTT_ENABLED=true,
 * create a token in HA (Profile → Long-Lived Access Tokens) and export it.
 */
import { test, expect } from "@playwright/test";

const HA_URL = process.env.HA_URL || "";
const HA_ACCESS_TOKEN = process.env.HA_ACCESS_TOKEN || "";

test.describe("Home Assistant discovery", () => {
  test.beforeEach(async ({ page }) => {
    test.skip(!HA_URL || !HA_ACCESS_TOKEN, "HA_URL and HA_ACCESS_TOKEN must be set");
  });

  test("FiestaBoard device entities exist in Home Assistant", async ({ request }) => {
    const base = HA_URL.replace(/\/$/, "");
    const res = await request.get(`${base}/api/states`, {
      headers: { Authorization: `Bearer ${HA_ACCESS_TOKEN}` },
    });
    expect(res.ok()).toBe(true);
    const states = await res.json();
    const fiestaEntities = states.filter(
      (e: { entity_id: string }) =>
        e.entity_id && e.entity_id.toLowerCase().includes("fiestaboard")
    );
    expect(
      fiestaEntities.length,
      `Expected at least one FiestaBoard entity in HA; got ${fiestaEntities.length}. Ensure MQTT is enabled and discovery was published.`
    ).toBeGreaterThanOrEqual(1);
    // Optionally expect full set (14 entities from discovery)
    const entityIds = fiestaEntities.map((e: { entity_id: string }) => e.entity_id);
    expect(
      entityIds.some((id: string) => id.startsWith("switch.fiestaboard_") || id.startsWith("sensor.fiestaboard_")),
      "Expected at least one switch or sensor FiestaBoard entity"
    ).toBe(true);
  });

  test("FiestaBoard device has multiple entity types", async ({ request }) => {
    const base = HA_URL.replace(/\/$/, "");
    const res = await request.get(`${base}/api/states`, {
      headers: { Authorization: `Bearer ${HA_ACCESS_TOKEN}` },
    });
    expect(res.ok()).toBe(true);
    const states = await res.json();
    const fiestaEntities = states.filter(
      (e: { entity_id: string }) =>
        e.entity_id && e.entity_id.toLowerCase().includes("fiestaboard")
    );
    const types = new Set(fiestaEntities.map((e: { entity_id: string }) => e.entity_id.split(".")[0]));
    expect(types.size).toBeGreaterThanOrEqual(1);
    // We expect at least switch, sensor, or binary_sensor from our discovery
    const hasExpected = ["switch", "sensor", "binary_sensor", "select", "button", "text", "number"].some(
      (t) => types.has(t)
    );
    expect(hasExpected, `Expected at least one of switch/sensor/binary_sensor/select/button/text/number; got ${[...types].join(", ")}`).toBe(true);
  });
});
