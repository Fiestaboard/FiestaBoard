import { expect, type Page, test } from "@playwright/test";
import { injectAxe } from "axe-playwright";

import firstPartyOutputs from "../../src/__tests__/mocks/first-party-outputs.json" with { type: "json" };
import { checkSetupA11y } from "./setup-a11y";
import { expectSurfaceToken, expectViewportEdges } from "./setup-parity";

const shots = process.env.WEB212_SHOTS ?? "test-results/web212-shots";
// This API-contract fixture is rendered by the real output-schema form; it
// supplies no presentation markup and never calls a physical LED display.
const led = {
  id: "led-display",
  name: "LED display (Pixoo / TC001)",
  description: "Community LED display",
  icon: "monitor",
  builtin: false,
  beta_gated: false,
  available: true,
  output_api: 1,
  capabilities: { technology: "led", delivery: "push", animation: "none", native_transitions: [], charset: null },
  device_models: [
    { id: "tc001", label: "Ulanzi TC001" },
    { id: "pixoo64", label: "Divoom Pixoo 64" },
  ],
  settings_schema: { type: "object", required: ["host"], properties: { host: { type: "string", title: "Address" } } },
  actions: [
    {
      id: "test_connection",
      label: "Test connection",
      description: "Test the connection",
      builtin: true,
      input_schema: null,
      result_fields: {},
    },
  ],
};
const catalog = [...firstPartyOutputs, led].map((output) => ({
  id: output.id,
  name: output.name,
  description: output.description,
  icon: output.icon,
  source: "installed",
  installed: true,
  builtin: output.builtin,
  beta_gated: false,
  available: true,
  needs_network: false,
}));
async function shot(page: Page, state: string, width: number, theme: string) {
  await page.evaluate(() => document.fonts.ready);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await checkSetupA11y(page);
  await page.screenshot({ path: `${shots}/impl-${state}-${width}-${theme}.png`, fullPage: false });
}
async function setup(page: Page, width: number) {
  await page.setViewportSize({ width, height: 1000 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  const unexpected: string[] = [];
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (!path.startsWith("/api/")) return route.fallback();
    let json: unknown;
    if (path === "/api/config/board/existing") json = { existing: [] };
    else if (path === "/api/config/validate") json = { valid: true, is_first_run: false, missing_fields: [] };
    else if (path === "/api/settings/wizard") json = { state: null };
    else if (path === "/api/settings/board") json = { boards: [], active_board_id: "" };
    else if (path === "/api/config/general") json = { instance_name: "Example FiestaPi", timezone: "UTC" };
    else if (path === "/api/outputs/catalog") json = { outputs: catalog, registry_status: "available" };
    else if (path === "/api/outputs") json = [...firstPartyOutputs, led];
    else if (path === "/api/outputs/led-display/install") json = led;
    else if (/^\/api\/outputs\/(vestaboard|led-display)\/actions\/test_connection$/.test(path))
      json = {
        status: "ok",
        message: "Display responded",
        geometry: null,
        guidance: [],
        fields: {},
        devices: [],
      };
    else if (path === "/api/v1/pages") json = { pages: [], total: 0 };
    else if (path === "/api/silence-status")
      json = { active: false, enabled: false, holds_blocked_sends: false, held: null };
    else if (path === "/api/v1/boards/primary")
      json = { id: "primary", name: "", schedule_enabled: false, next_change: null };
    else {
      unexpected.push(`${route.request().method()} ${path}`);
      await route.fulfill({ status: 404, json: { detail: "Missing extended-fixture handler" } });
      return;
    }
    await route.fulfill({ json });
  });
  return unexpected;
}
for (const width of [390, 768, 1280]) {
  for (const theme of ["light", "dark"]) {
    test(`empty Home and two-step Add display ${width} ${theme}`, async ({ page }) => {
      const unexpected = await setup(page, width);
      await page.goto(`/tests/layout/setup-extended.html?mode=home&theme=${theme}`);
      await expect(page.getByRole("heading", { name: "No displays yet" })).toBeVisible();
      await injectAxe(page);
      await shot(page, "home-no-displays", width, theme);
      await page.getByRole("button", { name: "Add display", exact: true }).click();
      const dialog = page.getByRole("dialog");
      await expect(dialog.getByRole("radio", { name: /Vestaboard/ })).toBeVisible();
      await expectSurfaceToken(dialog, "popover");
      if (width === 390) {
        expect(Math.round((await dialog.boundingBox())!.width)).toBe(390);
        await expectViewportEdges(dialog);
      }
      const choices = await dialog.getByRole("radio").all();
      const first = await choices[0].boundingBox();
      const second = await choices[1].boundingBox();
      expect(Math.round(second!.x)).toBe(Math.round(first!.x));
      expect(second!.y).toBeGreaterThanOrEqual(first!.y + first!.height);
      await shot(page, "add-display-type", width, theme);
      await dialog.getByRole("radio", { name: /Vestaboard/ }).click();
      await dialog.getByRole("button", { name: "Next", exact: true }).click();
      await dialog.getByLabel("Board type", { exact: true }).click();
      await page.getByRole("option", { name: "Note Array", exact: true }).click();
      await expect(dialog.getByLabel("Notes wide", { exact: true })).toBeVisible();
      await dialog.getByLabel("Board type", { exact: true }).click();
      await page.getByRole("option", { name: "Flagship · 22 × 6", exact: true }).click();
      await dialog.getByRole("radio", { name: "Local API", exact: true }).click();
      await dialog.getByLabel("Display name", { exact: true }).fill("Hall board");
      await dialog.getByLabel("Address", { exact: true }).fill("192.0.2.60");
      await dialog.getByLabel("Local API key", { exact: true }).fill("test_key");
      await dialog.getByRole("button", { name: "Test connection", exact: true }).click();
      await expect(dialog.getByRole("button", { name: "Add display", exact: true })).toBeEnabled();
      await shot(page, "add-display-connect", width, theme);
      expect(unexpected).toEqual([]);
    });
    test(`Add Pixoo display after a successful test ${width} ${theme}`, async ({ page }) => {
      const unexpected = await setup(page, width);
      await page.goto(`/tests/layout/setup-extended.html?mode=home&theme=${theme}`);
      await page.getByRole("button", { name: "Add display", exact: true }).click();
      const dialog = page.getByRole("dialog");
      await dialog.getByRole("radio", { name: /LED display/ }).click();
      await dialog.getByRole("button", { name: "Next", exact: true }).click();
      await dialog.getByLabel("Device model", { exact: true }).click();
      await page.getByRole("option", { name: "Divoom Pixoo 64", exact: true }).click();
      await dialog.getByLabel("Board name", { exact: true }).fill("Desk Pixoo");
      await dialog.getByRole("textbox", { name: "Address *", exact: true }).fill("192.0.2.88");
      await expect(dialog.getByRole("button", { name: "Add display", exact: true })).toBeDisabled();
      await dialog.getByRole("button", { name: "Test connection", exact: true }).click();
      await expect(dialog.getByText("Connection verified", { exact: true })).toBeVisible();
      await expect(dialog.getByRole("button", { name: "Add display", exact: true })).toBeEnabled();
      await injectAxe(page);
      await shot(page, "add-pixoo-passed", width, theme);
      expect(unexpected).toEqual([]);
    });
    test(`Add community display explicit untested choice ${width} ${theme}`, async ({ page }) => {
      const unexpected = await setup(page, width);
      await page.goto(`/tests/layout/setup-extended.html?mode=home&theme=${theme}`);
      await page.getByRole("button", { name: "Add display", exact: true }).click();
      const dialog = page.getByRole("dialog");
      await dialog.getByRole("radio", { name: /LED display/ }).click();
      await dialog.getByRole("button", { name: "Next", exact: true }).click();
      await dialog.getByRole("textbox", { name: "Address *", exact: true }).fill("192.0.2.70");
      const add = dialog.getByRole("button", { name: "Add display", exact: true });
      await expect(add).toBeDisabled();
      await dialog
        .getByRole("checkbox", {
          name: "Skip the connection test and add this community display untested",
          exact: true,
        })
        .check();
      await expect(add).toBeEnabled();
      if (width === 390) expect((await add.boundingBox())!.height).toBeGreaterThanOrEqual(44);
      await injectAxe(page);
      await shot(page, "add-community-untested", width, theme);
      expect(unexpected).toEqual([]);
    });
    test(`wizard TV connection ${width} ${theme}`, async ({ page }) => {
      const unexpected = await setup(page, width);
      await page.goto(`/tests/layout/setup-extended.html?mode=tv&theme=${theme}`);
      await expect(page.getByLabel("TV name", { exact: true })).toBeVisible();
      await expect(
        page.getByText("Waiting for the TV · you can finish setup and connect it later.", { exact: true }),
      ).toBeVisible();
      await injectAxe(page);
      await shot(page, "wizard-tv-connect", width, theme);
      expect(unexpected).toEqual([]);
    });
    test(`wizard LED connection ${width} ${theme}`, async ({ page }) => {
      const unexpected = await setup(page, width);
      await page.goto(`/tests/layout/setup-extended.html?mode=led&theme=${theme}`);
      await expect(
        page.getByText("Community · TC001 untested on hardware. Report problems on its Integrations page.", {
          exact: true,
        }),
      ).toBeVisible();
      await page.getByRole("textbox", { name: "Address *", exact: true }).fill("192.0.2.70");
      await page.getByRole("button", { name: "Test connection", exact: true }).click();
      await expect(page.getByText("Connection verified", { exact: true })).toBeVisible();
      await injectAxe(page);
      await shot(page, "wizard-led-connect", width, theme);
      expect(unexpected).toEqual([]);
    });
    test(`QR localhost and expired ${width} ${theme}`, async ({ page }) => {
      const unexpected = await setup(page, width);
      let state = "pending";
      await page.route("**/api/auth/**", async (route) => {
        const path = new URL(route.request().url()).pathname;
        if (!path.startsWith("/api/")) return route.fallback();
        if (path === "/api/auth/sessions/context")
          await route.fulfill({ json: { csrf_token: "test_nonce", expires_in: 600 } });
        else if (path === "/api/auth/pairing" && route.request().method() === "POST") {
          expect(route.request().headers()["x-csrf-token"]).toBe("test_nonce");
          await route.fulfill({
            json: {
              pairing_id: "extended-offer",
              hub: "http://fiestapi.local",
              qr_payload: "fiestaboard://pair#v=1&hub=http%3A%2F%2Ffiestapi.local&code=fixture_only",
              hub_addresses: [
                { url: "http://fiestapi.local", kind: "mdns" },
                { url: "http://192.0.2.50", kind: "lan" },
              ],
              expires_in: 300,
            },
          });
        } else if (path === "/api/auth/pairing/extended-offer") await route.fulfill({ json: { state } });
        else if (path === "/api/auth/pairing" && route.request().method() === "DELETE")
          await route.fulfill({ json: { status: "ok" } });
        else {
          unexpected.push(`${route.request().method()} ${path}`);
          await route.fulfill({ status: 404, json: {} });
        }
      });
      await page.goto(`/tests/layout/setup-extended.html?mode=qr&theme=${theme}`);
      await expect(page.getByRole("img", { name: "Scan with the FiestaBoard app" })).toBeVisible();
      await expect(page.getByText("Use the address of your hub, not localhost", { exact: true })).toBeVisible();
      await injectAxe(page);
      await shot(page, "qr-localhost", width, theme);
      state = "expired";
      await expect(page.getByRole("heading", { name: "This code expired", exact: true })).toBeVisible();
      await expect(page.getByRole("img", { name: "Scan with the FiestaBoard app" })).toHaveCount(0);
      await expect(page.getByRole("button", { name: "Make a new code", exact: true })).toBeEnabled();
      await shot(page, "qr-expired", width, theme);
      expect(unexpected).toEqual([]);
    });
  }
}
