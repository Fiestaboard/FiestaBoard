import { expect, test } from "@playwright/test";
import { checkA11y, injectAxe } from "axe-playwright";

const shots = process.env.WEB212_SHOTS ?? "test-results/web212-shots";
for (const width of [390, 768, 1280]) {
  for (const theme of ["light", "dark"]) {
    test(`first-run welcome, output, connection and review ${width} ${theme}`, async ({ page }) => {
      await page.setViewportSize({ width, height: 1000 });
      let passed = false;
      const writes: string[] = [];
      const board = {
        id: "kitchen",
        name: "Kitchen board",
        device_type: "flagship",
        output: "vestaboard",
        output_config: { api_mode: "local", host: "192.0.2.60", local_api_key: "***" },
        enabled: true,
      };
      await page.route("**/api/**", async (route) => {
        const path = new URL(route.request().url()).pathname;
        if (path === "/api/config/general")
          await route.fulfill({ json: { instance_name: "Example FiestaPi", timezone: "UTC" } });
        else if (path === "/api/outputs/catalog")
          await route.fulfill({
            json: {
              registry_status: "available",
              outputs: [
                {
                  id: "vestaboard",
                  name: "Vestaboard",
                  description: "Split-flap board",
                  icon: "grid",
                  source: "installed",
                  installed: true,
                  builtin: true,
                  available: true,
                  needs_network: false,
                },
                {
                  id: "fiestapanel",
                  name: "FiestaPanel TV",
                  description: "Show panels on your TV",
                  icon: "tv",
                  source: "installed",
                  installed: true,
                  builtin: true,
                  available: true,
                  needs_network: false,
                },
              ],
            },
          });
        else if (path === "/api/settings/board")
          await route.fulfill({
            json: { boards: writes.length ? [board] : [], active_board_id: writes.length ? "kitchen" : "" },
          });
        else if (path === "/api/outputs/vestaboard/actions/test_connection")
          await route.fulfill({
            json: {
              status: passed ? "ok" : "error",
              message: passed ? "Board responded" : "No response from the board",
              geometry: passed ? { device_type: "flagship" } : null,
              guidance: [],
              fields: {},
              devices: [],
            },
          });
        else if (path === "/api/settings/board/add") {
          writes.push(path);
          await route.fulfill({ json: { boards: [board], active_board_id: "kitchen" } });
        } else if (path === "/api/settings/wizard") await route.fulfill({ json: { state: "completed" } });
        else if (path === "/api/plugins") await route.fulfill({ json: { plugins: [] } });
        else await route.fulfill({ json: {} });
      });
      await page.goto(`/tests/layout/setup.html?mode=wizard&theme=${theme}`);
      await expect(page.getByLabel("Name this hub")).toHaveValue("Example FiestaPi");
      await injectAxe(page);
      const axe = async () =>
        checkA11y(page, undefined, {
          axeOptions: { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21aa"] } },
        });
      const shot = async (state: string) => {
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await axe();
        await page.screenshot({ path: `${shots}/impl-wizard-${state}-${width}-${theme}.png`, fullPage: true });
      };
      await shot("welcome");
      await page.getByRole("button", { name: "Get started", exact: true }).click();
      await page.getByRole("radio", { name: /Vestaboard/ }).click();
      await shot("output");
      await page.getByRole("button", { name: "Continue", exact: true }).click();
      await page.getByLabel("Display name", { exact: true }).fill("Kitchen board");
      await page.getByLabel("Address", { exact: true }).fill("192.0.2.60");
      await page.getByLabel("Local API key", { exact: true }).fill("test_key");
      await page.getByRole("button", { name: "Test connection", exact: true }).click();
      await expect(page.getByRole("button", { name: "Continue", exact: true })).toBeDisabled();
      await expect(page.getByText("Try this", { exact: true })).toBeVisible();
      await shot("failed");
      passed = true;
      await page.getByRole("button", { name: "Test again", exact: true }).click();
      await expect(page.getByRole("button", { name: "Continue", exact: true })).toBeEnabled();
      await shot("passed");
      await page.getByRole("button", { name: "Continue", exact: true }).click();
      await expect(page.getByText("Step 3 of 4", { exact: true })).toBeVisible();
      await shot("sources");
      await page.getByRole("button", { name: "Continue", exact: true }).click();
      await expect(page.getByRole("button", { name: "Finish setup", exact: true })).toBeVisible();
      await shot("review");
      expect(writes).toEqual(["/api/settings/board/add"]);
    });
  }
}
