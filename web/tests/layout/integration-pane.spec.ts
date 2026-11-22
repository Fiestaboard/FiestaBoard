import { expect, type Locator, type Page, test } from "@playwright/test";

// BB-FC-9: the integration detail's chrome against 07d `324:40267` (a
// configured plugin) and `324:44888` (setup required). Same harness as
// integrations.spec.ts: Random is configured, Weather needs setup.
const fixture = (path: string) => `/tests/layout/integrations.html?lang=en&path=${encodeURIComponent(path)}`;
const pane = (page: Page) => page.getByRole("complementary", { name: "Integration settings" });
const rect = (locator: Locator) => locator.evaluate((el) => el.getBoundingClientRect().toJSON() as DOMRect);

const states = [
  ["Random", "Configured"],
  ["Weather", "Setup Required"],
] as const;

test.describe("Integration detail pane at 1440 (BB-FC-9, Figma 324:40267)", () => {
  test.use({ viewport: { width: 1440, height: 1000 } });

  for (const [name, status] of states) {
    test(`${name}: the title carries a mono ${status} badge at the pane's right edge`, async ({ page }) => {
      await page.goto(fixture("/integrations?tab=installed"));
      await page.locator("button[data-slot=list-row]", { hasText: name }).click();
      const title = pane(page).getByRole("heading", { name, level: 2 });
      await expect(title).toBeVisible();
      const badge = pane(page).locator("[data-slot=badge]", { hasText: status });
      const card = pane(page).locator("[data-slot=card]").first();
      const [cardBox, titleBox, badgeBox] = await Promise.all([rect(card), rect(title), rect(badge)]);
      // One row: the title left, the badge on the content's right edge (padding 20).
      expect(Math.abs(titleBox.y + titleBox.height / 2 - (badgeBox.y + badgeBox.height / 2))).toBeLessThan(3);
      expect(Math.abs(cardBox.right - 20 - badgeBox.right)).toBeLessThan(3);
      expect(Math.round(badgeBox.height)).toBe(22);
      // 07d: the sample starts 12 under the title row (Figma 11).
      const body = await rect(pane(page).locator("[data-slot=card] > :nth-child(2)").first());
      expect(Math.abs(body.top - Math.max(titleBox.bottom, badgeBox.bottom) - 12)).toBeLessThanOrEqual(2);
      expect(await badge.evaluate((el) => getComputedStyle(el).fontFamily)).toMatch(/mono/i);
      // No switch, "…", version chips or tab strip in the pane.
      await expect(pane(page).getByRole("tablist")).toHaveCount(0);
      await expect(pane(page).getByRole("switch", { name: `Toggle ${name}` })).toHaveCount(0);
      await expect(pane(page).getByRole("button", { name: "More options" })).toHaveCount(0);
      await expect(pane(page).getByText("v1.0.0")).toHaveCount(0);
    });

    test(`${name}: the header's Integration options holds the version and the switch`, async ({ page }) => {
      await page.goto(fixture("/integrations?tab=installed"));
      await page.locator("button[data-slot=list-row]", { hasText: name }).click();
      await expect(pane(page).getByRole("heading", { name, level: 2 })).toBeVisible();
      await page.getByRole("button", { name: "Integration options" }).click();
      const menu = page.getByRole("menu");
      await expect(menu.getByText(`${name} · v1.0.0 · Core`)).toBeVisible();
      await expect(menu.getByRole("menuitemcheckbox", { name: "Enabled" })).toHaveAttribute("aria-checked", "true");
      await expect(menu.getByRole("menuitem", { name: "README" })).toBeVisible();
      // The menu opens under its button, inside the window.
      const box = await rect(menu);
      expect(box.right).toBeLessThanOrEqual(1440);
    });
  }
});

test.describe("Integration detail on a phone (BB-FC-9)", () => {
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });

  for (const [name] of states) {
    test(`${name}: the integration's own page keeps its switch and tabs`, async ({ page }) => {
      await page.goto(fixture(`/integrations/${name.toLowerCase()}?from=installed`));
      const toggle = page.getByRole("switch", { name: `Toggle ${name}` });
      await expect(toggle).toBeVisible();
      await expect(page.getByRole("tab", { name: "README" })).toBeVisible();
      expect((await rect(toggle)).right).toBeLessThanOrEqual(390 - 16 + 1);
      // The section header's menu is a desktop control; the phone has none.
      await expect(page.getByRole("button", { name: "Integration options" })).toHaveCount(0);
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
    });
  }
});
