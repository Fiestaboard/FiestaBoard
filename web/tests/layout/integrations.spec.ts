import { expect, test } from "@playwright/test";

const fixture = (path: string, lang = "en") =>
  `/tests/layout/integrations.html?lang=${lang}&path=${encodeURIComponent(path)}`;

test.describe("Integrations list on a phone (BB-C-22, Figma 324:50158)", () => {
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });

  test("the first row sits under the title and the tab pair, not half way down", async ({ page }) => {
    await page.goto(fixture("/integrations?tab=installed"));
    const firstRow = page.locator('[data-slot="list-row"]').first();
    await expect(firstRow).toBeVisible();
    const top = await firstRow.evaluate((row) => row.getBoundingClientRect().top);
    // Figma puts it at y≈280; before the fix it was at y≈500.
    expect(top).toBeLessThan(360);
    const tabs = page.getByRole("tablist").first();
    const [tabsBox, outletBox] = await Promise.all([
      tabs.boundingBox(),
      page.locator('[data-slot="page-outlet"]').boundingBox(),
    ]);
    // The pair spans the content column (within its padding), as in Figma.
    expect(tabsBox!.width).toBeGreaterThan(outletBox!.width - 64);
  });
});

test.describe("Integration settings in German at 360 (BB-C-21)", () => {
  test.use({ viewport: { width: 360, height: 780 }, hasTouch: true, isMobile: true });

  test("the demo-page text keeps its width and the button wraps under it", async ({ page }) => {
    await page.goto(fixture("/integrations/random?from=installed", "de"));
    const button = page.getByRole("button", { name: "Demoseite erstellen" });
    await expect(button).toBeVisible();
    const text = page.getByText("sofort nutzbare Seite", { exact: false });
    const [textBox, buttonBox] = await Promise.all([text.boundingBox(), button.boundingBox()]);
    // Before the fix the text was ~65 px wide beside the button.
    expect(textBox!.width).toBeGreaterThan(200);
    expect(buttonBox!.y).toBeGreaterThanOrEqual(textBox!.y + textBox!.height - 1);
  });

  test("the settings start within the first screen and there is one way back", async ({ page }) => {
    await page.goto(fixture("/integrations/random?from=installed", "de"));
    const tab = page.getByRole("tab", { name: "Einstellungen" });
    await expect(tab).toBeVisible();
    const top = await tab.evaluate((el) => el.getBoundingClientRect().top + window.scrollY);
    // Before the fix the tabs started at y≈625 with a second Back link above.
    expect(top).toBeLessThan(560);
    await expect(page.getByRole("link", { name: "Zurück zu Integrationen" })).toHaveCount(0);
    await expect(
      page.getByRole("navigation", { name: "Navigationspfad" }).getByRole("link", { name: "Integrationen" }),
    ).toBeVisible();
  });
});

test.describe("Integrations sort chips on a touch tablet (BB-C-26 app half)", () => {
  test.use({ viewport: { width: 820, height: 1180 }, hasTouch: true, isMobile: true });

  test("each sort chip is a 44 px touch target", async ({ page }) => {
    await page.goto(fixture("/integrations?tab=installed"));
    const chips = page.getByRole("group", { name: "Sort installed integrations" }).getByRole("button");
    await expect(chips).toHaveCount(3);
    for (const chip of await chips.all()) {
      const box = await chip.boundingBox();
      expect(Math.round(box!.height)).toBeGreaterThanOrEqual(44);
    }
  });
});
