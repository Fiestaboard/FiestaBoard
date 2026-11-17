/** DD-W12 / slice 2.14: canonical groups, responsive reusable setup, compact results. */
import type { Page } from "@playwright/test";
import { getViolations, injectAxe } from "axe-playwright";

import { configureBoard, expect, suppressWizard, test } from "../helpers";

async function expectAccessible(page: Page) {
  await injectAxe(page);
  const violations = await getViolations(page, undefined, {
    runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21aa"] },
  });
  expect(violations.filter((violation) => ["serious", "critical"].includes(violation.impact ?? ""))).toEqual([]);
}

for (const width of [390, 768, 1280]) {
  for (const colorScheme of ["light", "dark"] as const) {
    test.describe(`Integrations canonical ${width} ${colorScheme}`, () => {
      test.use({ viewport: { width, height: 900 }, colorScheme });
      test("groups fixes, saves the existing schema and shows compact Marketplace results", async ({ page }) => {
        await configureBoard();
        await suppressWizard(page);
        await page.addInitScript((theme) => localStorage.setItem("theme", theme), colorScheme);
        let configured = false;
        let saved: unknown;
        const base = {
          category: "utility",
          version: "1.0.0",
          author: "Example",
          enabled: true,
          icon: "cloud",
          source: { source_type: "builtin" },
        };
        const plugins = () => [
          { ...base, id: "cx-weather", name: "CX Weather", configured: true },
          { ...base, id: "cx-transit", name: "CX Transit", configured },
          { ...base, id: "cx-calendar", name: "CX Calendar", configured: true },
        ];
        await page.route("**/api/plugins", (route) =>
          route.fulfill({ json: { plugins: plugins(), total: 3, enabled_count: 3, plugin_system_enabled: true } }),
        );
        await page.route("**/api/oauth/connections", (route) =>
          route.fulfill({
            json: {
              connections: [
                {
                  id: "cx-calendar",
                  plugin_id: "cx-calendar",
                  plugin_name: "CX Calendar",
                  provider_name: "Example Calendar",
                  status: "reauthorization_required",
                  configured: true,
                  flows: ["relay"],
                  user_app: false,
                  shared_app: true,
                  scopes: [],
                  device: null,
                },
              ],
              redirect_uri: "https://example.com/return",
            },
          }),
        );
        await page.route("**/api/plugins/registry", (route) =>
          route.fulfill({
            json: {
              entries: [
                {
                  id: "cx-arrivals",
                  name: "CX Arrivals",
                  description: "Upcoming departures",
                  category: "transit",
                  author: "Example",
                  icon: "train",
                  repository: "https://example.com/cx-arrivals",
                  installed: false,
                },
              ],
            },
          }),
        );
        await page.route("**/api/v1/plugins/*/data", (route) =>
          route.fulfill({ json: { available: false, data: {} } }),
        );
        await page.route("**/api/v1/plugins/*", async (route) => {
          const id = route.request().url().split("/").pop();
          if (route.request().method() === "PATCH") {
            saved = route.request().postDataJSON();
            configured = true;
            return route.fulfill({ json: { ...base, id, configured } });
          }
          return route.fulfill({
            json: {
              ...plugins().find((plugin) => plugin.id === id),
              config: { stop: "Central" },
              settings_schema: { type: "object", properties: { stop: { type: "string", title: "Stop" } } },
              variables: {},
              env_vars: [],
            },
          });
        });
        await page.goto("/integrations");
        const attention = page.getByRole("list", { name: "Needs attention" });
        await expect(attention.getByText("CX Calendar", { exact: true })).toBeVisible();
        await expect(attention.getByRole("button", { name: "Reconnect", exact: true })).toBeVisible();
        await attention.getByRole("button", { name: "Set up", exact: true }).click();
        const settings =
          width >= 768 ? page.getByRole("complementary", { name: "Integration settings" }) : page.getByRole("dialog");
        await expect(settings.getByLabel("Stop", { exact: true })).toHaveValue("Central");
        await settings.getByLabel("Stop", { exact: true }).fill("Museum");
        await expectAccessible(page);
        await settings.getByRole("button", { name: "Save Changes", exact: true }).click();
        await expect.poll(() => saved).toEqual({ config: { stop: "Museum" } });
        await expect(attention.getByText("CX Transit", { exact: true })).toHaveCount(0);
        await page.getByRole("tab", { name: /Marketplace/ }).click();
        if (width >= 768) await page.getByRole("button", { name: "List view", exact: true }).click();
        const card = page
          .locator('[data-slot="plugin-card"][data-variant="compact"]')
          .filter({ hasText: "CX Arrivals" });
        await expect(card.getByRole("button", { name: "Install", exact: true })).toBeVisible();
        await expectAccessible(page);
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
        await test.info().attach(`integrations-${width}-${colorScheme}.png`, {
          body: await page.screenshot(),
          contentType: "image/png",
        });
      });
    });
  }
}
