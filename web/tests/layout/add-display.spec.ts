/**
 * BB-C-14: the display choice and the Connect step at 390 × 844 (Figma
 * 325:34531 setup, 335:59549 / 335:60687 Add a display): the real catalog's
 * cards are short enough that Continue / Next is on screen without scrolling,
 * and step 2 is "Connect <device>" with a back arrow and a full-width Test connection.
 */
import { expect, type Page, test } from "@playwright/test";

const shots = process.env.BBFIX_SHOTS ?? "test-results/bbfix-c14-shots";

const output = (o: Record<string, unknown>) => ({
  icon: "grid-3x3",
  source: "installed",
  installed: true,
  builtin: false,
  beta_gated: false,
  available: true,
  needs_network: false,
  output_api: 1,
  ...o,
});

// The v11 catalog as GET /outputs/catalog serves it (bundled seed + one registry plugin).
const CATALOG = {
  registry_status: "available",
  outputs: [
    output({
      id: "vestaboard",
      name: "Vestaboard",
      icon: "layout-grid",
      builtin: true,
      description: "A Vestaboard Flagship, Note or Note array, over the Local API or the cloud.",
      display: {
        category: "Split-flap displays",
        manufacturer: "",
        models: ["Vestaboard Flagship", "Vestaboard Note", "Vestaboard Note array"],
        keywords: [],
      },
    }),
    output({
      id: "fiestapanel",
      name: "FiestaPanel",
      icon: "monitor",
      builtin: true,
      description: "Any TV or browser: a full-screen board FiestaBoard draws itself.",
      display: { category: "TV & browser", manufacturer: "", models: ["Virtual panel"], keywords: [] },
    }),
    output({
      id: "divoom_pixoo",
      name: "Divoom Pixoo 64",
      source: "seed",
      installed: false,
      description: "Show your FiestaBoard pages on a Divoom Pixoo 64 LED matrix over your local network.",
      display: { category: "LED displays", manufacturer: "", models: ["Divoom Pixoo 64"], keywords: [] },
    }),
    output({
      id: "ulanzi_tc002",
      name: "Ulanzi TC002",
      source: "registry",
      installed: false,
      needs_network: true,
      output_api: null,
      description:
        "Show your FiestaBoard pages on a Ulanzi TC002 running AWTRIX NG, as an app in its rotation, over your local network. 3 rows of 13 in the 3x5 font, colours and LED transitions. Optionally the clock rotates a collection's pages itself, switchable with its buttons.",
      display: { category: "LED matrices", manufacturer: "", models: [], keywords: ["Ulanzi", "TC002"] },
    }),
  ],
};

async function mockApi(page: Page) {
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (!path.startsWith("/api/")) return route.fallback();
    if (path === "/api/outputs/catalog") await route.fulfill({ json: CATALOG });
    else if (path === "/api/config/board/existing") await route.fulfill({ json: { existing: [] } });
    else if (path === "/api/config/general")
      await route.fulfill({ json: { instance_name: "Example FiestaPi", timezone: "UTC" } });
    else if (path === "/api/settings/board") await route.fulfill({ json: { boards: [], active_board_id: "" } });
    else if (path === "/api/settings/wizard") await route.fulfill({ json: { state: null } });
    else if (path === "/api/plugins") await route.fulfill({ json: { plugins: [] } });
    else await route.fulfill({ json: {} });
  });
}

/** *name*'s button lies wholly inside the viewport, with nothing scrolled. */
async function onScreen(page: Page, name: string) {
  const box = (await page.getByRole("button", { name, exact: true }).boundingBox())!;
  const viewport = page.viewportSize()!;
  expect(box.y).toBeGreaterThanOrEqual(0);
  expect(box.y + box.height).toBeLessThanOrEqual(viewport.height);
}

for (const theme of ["light", "dark"]) {
  test(`Add a display at 390: four choices with Next on screen, then Connect ${theme}`, async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.emulateMedia({ reducedMotion: "reduce" });
    await mockApi(page);
    await page.goto(`/tests/layout/setup.html?mode=add-display&theme=${theme}`);
    const dialog = page.getByRole("dialog", { name: "Add a display" });
    await expect(dialog.getByRole("radio", { name: /Ulanzi TC002/ })).toBeVisible();
    await dialog.getByRole("radio", { name: /Vestaboard/ }).click();
    await onScreen(page, "Next");
    await onScreen(page, "Cancel");
    await page.screenshot({ path: `${shots}/after-add-step1-390-${theme}.png` });

    await page.getByRole("button", { name: "Next", exact: true }).click();
    const connect = page.getByRole("dialog", { name: "Connect Vestaboard" });
    await expect(connect.getByText("Step 2 of 2 · Only what this display needs", { exact: true })).toBeVisible();
    await expect(connect.getByRole("button", { name: "Back to display types" })).toBeVisible();
    const test = (await connect.getByRole("button", { name: "Test connection" }).boundingBox())!;
    const field = (await connect.getByLabel("Display name").boundingBox())!;
    expect(Math.round(test.x)).toBe(Math.round(field.x));
    expect(Math.round(test.width)).toBe(Math.round(field.width));
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: `${shots}/after-add-step2-390-${theme}.png` });
  });

  test(`setup Choose output at 390: the catalog fits with Continue on screen ${theme}`, async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.emulateMedia({ reducedMotion: "reduce" });
    await mockApi(page);
    await page.goto(`/tests/layout/setup.html?mode=wizard&theme=${theme}`);
    await page.getByRole("button", { name: "Get started", exact: true }).click();
    await page.getByRole("radio", { name: /Vestaboard/ }).click();
    await expect(page.getByRole("radio", { name: /Ulanzi TC002/ })).toBeVisible();
    await onScreen(page, "Continue");
    await page.screenshot({ path: `${shots}/after-setup-output-390-${theme}.png` });
  });
}
