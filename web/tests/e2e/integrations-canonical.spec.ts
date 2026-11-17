/** Slice 2.14/DD-W12: full phone detail, supported reconnect, README and whole-row navigation. */
import type { Locator, Page } from "@playwright/test";
import { getViolations, injectAxe } from "axe-playwright";

import { configureBoard, expect, suppressWizard, test } from "../helpers";

async function expectAccessible(page: Page, theme: "light" | "dark") {
  await expect
    .poll(() => page.locator("html").evaluate((html) => html.classList.contains("dark")))
    .toBe(theme === "dark");
  // Visibility can become true partway through the kit's header/outlet fades.
  // Audit the settled colors, including on navigation and after opening a dialog.
  await page.evaluate(async () => {
    const finiteAnimations = document
      .getAnimations()
      .filter((animation) => Number.isFinite(animation.effect?.getComputedTiming().endTime ?? Infinity));
    await Promise.all(finiteAnimations.map((animation) => animation.finished.catch(() => {})));
  });
  await injectAxe(page);
  const violations = await getViolations(page, undefined, {
    runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"] },
  });
  expect(violations, `Integrations a11y violations:\n${JSON.stringify(violations, null, 2)}`).toEqual([]);
}
async function capture(page: Page, state: string, width: number, theme: string) {
  await test.info().attach(`integrations-${state}-${width}-${theme}.png`, {
    body: await page.screenshot({ fullPage: true, animations: "disabled" }),
    contentType: "image/png",
  });
}

async function expectPreviewReachable(page: Page, preview: Locator) {
  const scroller = preview.locator('[data-slot="board-viewport-scroller"]');
  const row = scroller.locator("[data-note-row]").first();
  const tiles = row.locator("[data-note-tile]");
  await expect(scroller).toBeVisible();
  const viewportWidth = await page.evaluate(() => document.documentElement.clientWidth);
  const scrollerBounds = await scroller.boundingBox();
  expect(scrollerBounds).not.toBeNull();
  expect(scrollerBounds!.x).toBeGreaterThanOrEqual(0);
  expect(scrollerBounds!.x + scrollerBounds!.width).toBeLessThanOrEqual(viewportWidth);
  const scrolls = (await scroller.getAttribute("tabindex")) === "0";
  if (scrolls) {
    await scroller.focus();
    await page.keyboard.press("Home");
  }
  await expect
    .poll(async () => {
      const edge = await tiles.first().boundingBox();
      const slot = await scroller.boundingBox();
      return !!edge && !!slot && edge.x >= slot.x - 1;
    })
    .toBe(true);
  if (scrolls) await page.keyboard.press("End");
  await expect
    .poll(async () => {
      const edge = await tiles.last().boundingBox();
      const slot = await scroller.boundingBox();
      return !!edge && !!slot && edge.x + edge.width <= slot.x + slot.width + 1;
    })
    .toBe(true);
  if (scrolls) await page.keyboard.press("Home");
}

for (const width of [390, 768, 1280]) {
  for (const colorScheme of ["light", "dark"] as const) {
    test.describe(`Integrations canonical ${width} ${colorScheme}`, () => {
      test.use({ viewport: { width, height: 900 }, colorScheme, reducedMotion: "reduce" });
      test("opens whole rows, reconnects in the same tab, saves settings and reads Variables/README", async ({
        page,
      }) => {
        test.slow();
        await configureBoard();
        await suppressWizard(page);
        await page.addInitScript((theme) => localStorage.setItem("theme", theme), colorScheme);
        await page.addInitScript(() => sessionStorage.setItem("fiestaboard:boardPreviewMode", "actual"));
        await page.addInitScript(() => localStorage.setItem("fiestaboard_current_board", "selected"));
        let boardWrites = 0;
        await page.route("**/api/settings/board", (route) => {
          if (route.request().method() !== "GET") boardWrites++;
          return route.fulfill({
            json: {
              board_type: "black",
              devices: ["flagship"],
              boards: [
                {
                  id: "primary",
                  name: "Primary",
                  device_type: "flagship",
                  board_color: "black",
                  code62_glyph: "degree",
                  enabled: true,
                },
                {
                  id: "selected",
                  name: "Selected",
                  device_type: "flagship",
                  board_color: "white",
                  code62_glyph: "heart",
                  enabled: true,
                },
              ],
            },
          });
        });
        let configured = false;
        let connected = false;
        let saved: unknown;
        let reconnects = 0;
        const base = {
          category: "utility",
          version: "1.2.0",
          author: "Example",
          enabled: true,
          icon: "cloud",
          source: { source_type: "registry", repository_url: "https://github.com/example/cx-integrations" },
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
                  status: connected ? "connected" : "reauthorization_required",
                  status_reason: connected ? "" : "refresh_refused",
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
        await page.route("**/api/oauth/connections/cx-calendar/authorize", (route) => {
          reconnects++;
          connected = true;
          return route.fulfill({
            json: {
              flow: "relay",
              authorization_url: `${new URL(page.url()).origin}/integrations?tab=installed&oauth=connected&plugin=cx-calendar`,
              device: null,
            },
          });
        });
        await page.route("**/api/plugins/registry", (route) =>
          route.fulfill({
            json: {
              entries: [
                {
                  id: "cx-calendar",
                  name: "CX Calendar",
                  description: "Calendar events on your display",
                  category: "utility",
                  author: "Example",
                  icon: "calendar",
                  repository: "https://github.com/example/cx-integrations",
                  installed: true,
                  previews: [
                    { device_type: "flagship", rows: ["52 °F CLEAR"] },
                    { device_type: "note", rows: ["NOTE FORECAST"] },
                  ],
                },
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
          route.fulfill({ json: { available: true, data: { next_title: "CX departure" } } }),
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
              config: { stop: configured ? "Museum" : "Central" },
              settings_schema: { type: "object", properties: { stop: { type: "string", title: "Stop" } } },
              variables: { simple: { next_title: { description: "Next departure", max_length: 40 } } },
              env_vars: [
                {
                  name: "CX_TRANSIT_STOP_NAME",
                  description: "Name of the transit stop to display (can also be set in Settings)",
                  required: false,
                },
              ],
              documentation:
                "# CX integration guide\n\nUse this integration in your pages.\n\n[Setup guide](docs/SETUP.md)\n\n```\n{{cx-transit.next_title}}\n```",
            },
          });
        });
        await page.goto("/integrations");
        const attention = page.getByRole("list", { name: "Needs attention" });
        await expect(attention.getByText("CX Calendar", { exact: true })).toBeVisible();
        await expect(attention.getByText("Reconnect", { exact: true })).toBeVisible();
        await expectAccessible(page, colorScheme);
        await capture(page, "installed", width, colorScheme);

        // The icon is part of the one primary row target, rather than a small title button.
        await attention
          .getByRole(width >= 768 ? "button" : "link", { name: /^CX Calendar/ })
          .locator('[data-slot="list-row-leading"]')
          .click();
        const settings =
          width >= 768
            ? page.getByRole("complementary", { name: "Integration settings" })
            : page.locator('[data-slot="page-outlet"]');
        if (width < 768) {
          await expect(page).toHaveURL(/\/integrations\/cx-calendar\?from=installed/);
          await expect(page.getByRole("link", { name: "Back to Integrations", exact: true })).toBeVisible();
          await expect(page.getByRole("dialog")).toHaveCount(0);
        }
        await expect(settings.getByTestId("integration-attention-banner")).toContainText(
          "Data for pages using this integration may be unavailable or out of date until you reconnect.",
        );
        await expectAccessible(page, colorScheme);
        await capture(page, "detail-reconnect", width, colorScheme);
        const pageCount = page.context().pages().length;
        await settings.getByTestId("oauth-connection").getByRole("button", { name: "Reconnect", exact: true }).click();
        await expect.poll(() => reconnects).toBe(1);
        await expect(page).toHaveURL(/\/integrations\/cx-calendar\?from=installed/);
        await expect(page.getByTestId("oauth-connection").getByText("Connected", { exact: true })).toBeVisible();
        await expect(page.getByText("Account connected.", { exact: true })).toBeVisible();
        expect(page.context().pages()).toHaveLength(pageCount);
        const preview = page.locator('[data-slot="board-showcase"]');
        await expect(preview.getByRole("img", { name: /Board display:/i })).toContainText("52♥FCLEAR");
        const colors = preview.getByRole("group", { name: "Board color" });
        await expect(colors.getByRole("button", { name: "White Board" })).toHaveAttribute("aria-pressed", "true");
        await expectPreviewReachable(page, preview);
        const recovery = page.getByRole("button", { name: /Sign-in didn't come back\? Paste the address/ });
        await expect(recovery).toBeVisible();
        const recoveryBounds = await recovery.boundingBox();
        const connectionBounds = await page.getByTestId("oauth-connection").boundingBox();
        expect(recoveryBounds).not.toBeNull();
        expect(connectionBounds).not.toBeNull();
        expect(recoveryBounds!.x).toBeGreaterThanOrEqual(connectionBounds!.x);
        expect(recoveryBounds!.x + recoveryBounds!.width).toBeLessThanOrEqual(
          connectionBounds!.x + connectionBounds!.width,
        );
        expect(recoveryBounds!.height).toBeGreaterThanOrEqual(44);
        await capture(page, "detail-connected-preview", width, colorScheme);
        await colors.getByRole("button", { name: "Black Board" }).click();
        await expect(colors.getByRole("button", { name: "Black Board" })).toHaveAttribute("aria-pressed", "true");
        await preview.getByRole("tab", { name: /Note/ }).click();
        await expect(preview.getByRole("img", { name: /Board display:/i })).toContainText("NOTEFORECAST");
        expect(boardWrites).toBe(0);
        await expectAccessible(page, colorScheme);
        await page.getByRole("link", { name: "Back to Integrations", exact: true }).click();

        if (width >= 768) {
          await page
            .getByRole("list", { name: "Installed" })
            .getByRole("button", { name: /^CX Calendar/ })
            .click();
          await expect(settings.locator('[data-slot="board-showcase"]')).toBeVisible();
          await expectPreviewReachable(page, settings.locator('[data-slot="board-showcase"]'));
          await expectAccessible(page, colorScheme);
          await capture(page, "connected-pane", width, colorScheme);
        }

        await page
          .getByRole("list", { name: "Needs attention" })
          .getByRole(width >= 768 ? "button" : "link", { name: /^CX Transit/ })
          .locator('[data-slot="list-row-trailing"]')
          .click();
        await expect(settings.getByLabel("Stop", { exact: true })).toHaveValue("Central");
        const environmentTable = settings.getByRole("table", { name: "Environment Variables", exact: true });
        await settings.getByLabel("Stop", { exact: true }).focus();
        await page.keyboard.press("Tab");
        await expect(environmentTable).toBeFocused();
        await expectAccessible(page, colorScheme);
        await capture(page, "detail-setup", width, colorScheme);
        if (width >= 768) {
          await page.goto("/integrations/cx-transit?from=installed");
          await expect(page.getByLabel("Stop", { exact: true })).toHaveValue("Central");
          await expect(page.getByTestId("integration-attention-banner")).toBeVisible();
          await expectAccessible(page, colorScheme);
          await capture(page, "full-detail-setup", width, colorScheme);
          await page.getByRole("link", { name: "Back to Integrations", exact: true }).click();
          await page
            .getByRole("list", { name: "Needs attention" })
            .getByRole("button", { name: /^CX Transit/ })
            .click();
        }
        await settings.getByLabel("Stop", { exact: true }).fill("Museum");
        await settings.getByRole("button", { name: "Save Changes", exact: true }).click();
        await expect.poll(() => saved).toEqual({ config: { stop: "Museum" } });
        await expect(
          page.getByRole("list", { name: "Needs attention" }).getByText("CX Transit", { exact: true }),
        ).toHaveCount(0);
        await page
          .getByRole("list", { name: "Installed" })
          .getByRole(width >= 768 ? "button" : "link", { name: /^CX Transit/ })
          .locator('[data-slot="list-row-description"]')
          .click();
        await settings.getByRole("tab", { name: "Variables", exact: true }).click();
        await expect(settings.getByText("CX departure", { exact: true })).toBeVisible();
        await settings.getByRole("tab", { name: "README", exact: true }).click();
        const documentView = page.locator('[data-slot="page-outlet"]');
        await expect(
          documentView.locator('[data-slot="prose"]').getByRole("heading", { name: "CX integration guide" }),
        ).toBeVisible();
        await expect(
          documentView.getByRole("region", { name: "About" }).getByText("1.2.0", { exact: true }),
        ).toBeVisible();
        await expect(documentView.getByRole("link", { name: "Setup guide" })).toHaveAttribute(
          "href",
          "https://github.com/example/cx-integrations/blob/main/docs/SETUP.md",
        );
        await expectAccessible(page, colorScheme);
        await capture(page, "detail-readme", width, colorScheme);
        await page.getByRole("link", { name: "Back to Integrations", exact: true }).click();
        await page.getByRole("tab", { name: /Marketplace/ }).click();
        if (width >= 768) await page.getByRole("button", { name: "List view", exact: true }).click();
        const card = page
          .locator('[data-slot="plugin-card"][data-variant="compact"]')
          .filter({ hasText: "CX Arrivals" });
        await expect(card.getByRole("button", { name: "Install", exact: true })).toBeVisible();
        await expectAccessible(page, colorScheme);
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
        await capture(page, "marketplace", width, colorScheme);
        await page.getByRole("button", { name: "More options", exact: true }).click();
        await page.getByRole("menuitem", { name: "Add from Git", exact: true }).click();
        await expect(page.getByRole("dialog", { name: "Install Plugin from Git", exact: true })).toBeVisible();
        await expectAccessible(page, colorScheme);
        await capture(page, "git-install", width, colorScheme);
      });
    });
  }
}
