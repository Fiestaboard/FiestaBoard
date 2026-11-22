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

  test("Use in a page… fits the phone and the settings sit above it (BB-FC-9)", async ({ page }) => {
    await page.goto(fixture("/integrations/random?from=installed", "de"));
    const button = page.getByRole("button", { name: "Auf einer Seite verwenden…" });
    await expect(button).toBeVisible();
    const box = (await button.boundingBox())!;
    expect(box.x + box.width).toBeLessThanOrEqual(360 - 16 + 1);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(360);
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

// BB-FC-9: the detail body against 07d `324:40267` (configured) and the
// setup-required state (`324:44888`).
const pane = (page: import("@playwright/test").Page) =>
  page.getByRole("complementary", { name: "Integration settings" });
const rect = (locator: import("@playwright/test").Locator) =>
  locator.evaluate((el) => el.getBoundingClientRect().toJSON());
const style = (locator: import("@playwright/test").Locator) =>
  locator.evaluate((el) => {
    const s = getComputedStyle(el);
    return { font: s.fontFamily, size: s.fontSize, transform: s.textTransform, border: s.borderTopWidth };
  });

async function openPane(page: import("@playwright/test").Page, name: string) {
  await page.goto(fixture("/integrations?tab=installed"));
  await page.locator("button[data-slot=list-row]", { hasText: name }).click();
  await expect(pane(page).getByRole("heading", { name, level: 2 })).toBeVisible();
  await expect(pane(page).getByLabel("Event Name")).toBeVisible();
}

test.describe("Integration detail pane at 1440 (BB-FC-9, Figma 324:40267)", () => {
  test.use({ viewport: { width: 1440, height: 1100 } });

  for (const name of ["Countdown", "Weather"]) {
    test(`${name}: sample, mono sections, Unlocks chips and Use in a page… in 07d order`, async ({ page }) => {
      await openPane(page, name);
      const board = pane(page).locator("[data-slot=board-viewport]");
      const caption = pane(page).getByText("Sample page using this integration");
      const settings = pane(page).getByRole("heading", { name: "Settings", level: 3 });
      const unlocks = pane(page).getByRole("heading", { name: "Unlocks 3 variables", level: 3 });
      const chips = pane(page).getByRole("list", { name: "Unlocks 3 variables" });
      const use = pane(page).getByRole("button", { name: "Use in a page…" });
      const [b, c, s, u, ch, us] = await Promise.all([board, caption, settings, unlocks, chips, use].map(rect));
      expect(c.top - b.bottom).toBeGreaterThanOrEqual(8);
      expect(c.top - b.bottom).toBeLessThanOrEqual(24);
      expect(s.top).toBeGreaterThan(c.bottom);
      expect(u.top).toBeGreaterThan(s.bottom);
      expect(ch.top).toBeGreaterThanOrEqual(u.bottom);
      expect(us.top).toBeGreaterThan(ch.bottom);
      // Labels, chips and the button share the content's left edge.
      for (const left of [s.left, u.left, ch.left, us.left]) expect(Math.abs(left - c.left)).toBeLessThan(2);
      for (const label of [settings, unlocks]) {
        const st = await style(label);
        expect(st.font).toMatch(/mono/i);
        expect(st.size).toBe("12px");
        expect(st.transform).toBe("uppercase");
      }
      expect((await style(use)).border).toBe("1px");
      const id = name.toLowerCase();
      await expect(chips.getByRole("listitem")).toHaveText([`${id}.days`, `${id}.label`, `${id}.time`]);
    });
  }
});

test.describe("Integration detail on a phone (BB-FC-9, Figma 324:51224)", () => {
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });

  for (const id of ["countdown", "weather"]) {
    test(`${id}: mono Unlocks section and Use in a page… on the 16 px gutter`, async ({ page }) => {
      await page.goto(fixture(`/integrations/${id}?from=installed`));
      const unlocks = page.getByRole("heading", { name: "Unlocks 3 variables", level: 3 });
      await expect(unlocks).toBeVisible();
      const st = await style(unlocks);
      expect(st.font).toMatch(/mono/i);
      expect(st.transform).toBe("uppercase");
      const use = await rect(page.getByRole("button", { name: "Use in a page…" }));
      expect(use.right).toBeLessThanOrEqual(390 - 16 + 1);
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
      if (id === "weather") {
        const banner = await rect(page.getByTestId("integration-attention-banner"));
        expect(banner.bottom).toBeLessThan((await rect(unlocks)).top);
      }
    });
  }
});
