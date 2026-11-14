/**
 * Slice 2.2: the canonical Home (WEB-08/11/18).
 *
 * - One Compose entry, in the PageHeader; Change Page is the card's secondary.
 * - Both verbs end in the one DurationChipGroup step and Show now.
 * - A timed Change Page holds an Override: badge, countdown, outcome, Cancel
 *   override (with Undo).
 * - The board context menu (right-click, Shift+F10, the ⋯ button).
 * - Phone: Change Page is a two-step bottom sheet.
 * - axe on each state.
 */
import type { Page } from "@playwright/test";
import { getViolations, injectAxe } from "axe-playwright";

import {
  API_URL,
  authHeaders,
  configureBoard,
  createPage,
  deleteAllPages,
  deleteAllSchedules,
  expect,
  resetToSingleBoard,
  setActivePage,
  setScheduleEnabled,
  suppressWizard,
  test,
} from "../helpers";

async function expectNoSeriousAxe(page: Page, label: string) {
  await injectAxe(page);
  const violations = await getViolations(page, undefined, {
    runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "best-practice"] },
    rules: { "color-contrast": { enabled: false } },
  });
  const failing = violations
    .filter((v) => v.impact === "critical" || v.impact === "serious")
    .map((v) => ({ id: v.id, help: v.help, targets: v.nodes.slice(0, 3).map((n) => n.target) }));
  expect(failing, `${label} a11y violations:\n${JSON.stringify(failing, null, 2)}`).toEqual([]);
}

async function clearOverride() {
  await fetch(`${API_URL}/settings/temporary-override`, { method: "DELETE", headers: authHeaders() }).catch(() => {});
}

test.beforeEach(async ({ page }) => {
  await configureBoard();
  await resetToSingleBoard();
  await suppressWizard(page);
  await deleteAllSchedules();
  await deleteAllPages();
  await setScheduleEnabled(false);
  await clearOverride();
});

test.afterEach(async () => {
  await clearOverride();
});

test.describe("Home (2.2)", () => {
  test("has one Compose entry, in the PageHeader, and Change Page on the card", async ({ page }) => {
    const id = await createPage("Evening commute", ["GOOD EVENING", "", "", "", "", ""]);
    await setActivePage(id);
    await page.goto("/");

    await expect(page.getByRole("heading", { name: "Home", exact: true })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole("button", { name: "Compose a message" })).toHaveCount(1);
    const card = page.getByTestId("now-showing");
    await expect(card.getByText("Manual Mode")).toBeVisible({ timeout: 10_000 });
    await expect(card.getByRole("heading", { level: 2, name: "Evening commute" })).toBeVisible();
    await expect(card.getByRole("button", { name: "Change Page", exact: true })).toBeVisible();
    await expect(card.getByRole("link", { name: "Edit page" })).toHaveAttribute("href", /\/pages\/edit\//);
    await expectNoSeriousAxe(page, "Home");
  });

  test("Change Page with 15 min holds an Override with a countdown; Cancel override has Undo", async ({ page }) => {
    const base = await createPage("Evening commute", ["GOOD EVENING", "", "", "", "", ""]);
    await createPage("Taco Tuesday", ["TACO TUESDAY", "", "", "", "", ""]);
    await setActivePage(base);
    await page.goto("/");

    await page.getByRole("button", { name: "Change Page", exact: true }).click();
    const dialog = page.getByRole("dialog", { name: "Change Page" });
    await dialog.getByRole("button", { name: /Taco Tuesday/ }).click();
    await expect(dialog.getByText("Not sent yet · Taco Tuesday on")).toBeVisible();
    await dialog.getByRole("radio", { name: "15 min" }).click();
    await expect(dialog.getByText(/^Holds until .+ \(15m\), then Evening commute comes back\.$/)).toBeVisible();
    await expectNoSeriousAxe(page, "Change Page dialog");
    await dialog.getByRole("button", { name: "Show now" }).click();
    await expect(dialog).toHaveCount(0, { timeout: 10_000 });

    const card = page.getByTestId("now-showing");
    await expect(card.getByText("Override", { exact: true })).toBeVisible({ timeout: 10_000 });
    await expect(card.getByRole("heading", { level: 2, name: "Taco Tuesday" })).toBeVisible();
    await expect(card.getByRole("timer")).toHaveText(/1[45]m left/);
    await expect(card.getByText(/^Holds until .+, then Evening commute comes back\.$/)).toBeVisible();
    await expectNoSeriousAxe(page, "Home · Override");

    await card.getByRole("button", { name: "Cancel override" }).click();
    const toast = page.locator("[data-sonner-toast]").filter({ hasText: "Override canceled" });
    await expect(toast).toBeVisible();
    await expect(card.getByText("Manual Mode")).toBeVisible({ timeout: 10_000 });
    await toast.getByRole("button", { name: "Undo" }).click();
    await expect(card.getByText("Override", { exact: true })).toBeVisible({ timeout: 10_000 });
  });

  test("in Manual Mode during an Override, Until I cancel replaces the Override and pins the page", async ({
    page,
  }) => {
    const base = await createPage("Evening commute", ["GOOD EVENING", "", "", "", "", ""]);
    const dinner = await createPage("Dinner note", ["DINNER AT 7", "", "", "", "", ""]);
    await createPage("Taco Tuesday", ["TACO TUESDAY", "", "", "", "", ""]);
    await setActivePage(base);
    const set = await fetch(`${API_URL}/settings/temporary-override`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ page_id: dinner, duration_minutes: 60, revert_mode: "schedule" }),
    });
    expect(set.ok).toBe(true);
    await page.goto("/");
    const card = page.getByTestId("now-showing");
    await expect(card.getByRole("heading", { level: 2, name: "Dinner note" })).toBeVisible({ timeout: 15_000 });

    await card.getByRole("button", { name: "Change Page", exact: true }).click();
    const dialog = page.getByRole("dialog", { name: "Change Page" });
    await dialog.getByRole("button", { name: /Taco Tuesday/ }).click();
    await expect(dialog.getByRole("radio", { name: "Until I cancel" })).toHaveAttribute("aria-checked", "true");
    await expect(dialog.getByText(/Replaces the Dinner note Override\.$/)).toBeVisible();
    await dialog.getByRole("button", { name: "Show now" }).click();
    await expect(dialog).toHaveCount(0, { timeout: 10_000 });

    await expect
      .poll(
        async () =>
          (await (await fetch(`${API_URL}/settings/temporary-override`, { headers: authHeaders() })).json()).active,
        {
          timeout: 10_000,
        },
      )
      .toBe(false);
    await page.reload();
    await expect(card.getByRole("heading", { level: 2, name: "Taco Tuesday" })).toBeVisible({ timeout: 15_000 });
    await expect(card.getByText("Manual Mode")).toBeVisible();
    await expect(card.getByText("Override", { exact: true })).toHaveCount(0);
  });

  test("Compose a message ends in the same duration step and shows an Override", async ({ page }) => {
    const base = await createPage("Evening commute", ["GOOD EVENING", "", "", "", "", ""]);
    await setActivePage(base);
    await page.goto("/");

    await page.getByRole("button", { name: "Compose a message" }).click();
    const dialog = page.getByRole("dialog", { name: "Compose a message" });
    await dialog.getByRole("textbox", { name: /^Message$/ }).fill("DINNER AT 7");
    await dialog.getByRole("radio", { name: "1 hr" }).click();
    await dialog.getByRole("button", { name: "Show now" }).click();
    await expect(dialog).toHaveCount(0, { timeout: 10_000 });

    const card = page.getByTestId("now-showing");
    await expect(card.getByRole("heading", { level: 2, name: "Composed message" })).toBeVisible({ timeout: 10_000 });
    await expect(card.getByRole("timer")).toHaveText(/(59m|1h) left/);
  });

  test("the board menu opens on right-click and on Shift+F10, with 07a's items", async ({ page }) => {
    const base = await createPage("Evening commute", ["GOOD EVENING", "", "", "", "", ""]);
    await setActivePage(base);
    await page.goto("/");

    const board = page.getByTestId("home-board");
    await board.click({ button: "right" });
    const menu = page.getByRole("menu");
    await expect(menu.getByRole("menuitem", { name: /Change Page…/ })).toBeVisible();
    await expect(menu.getByRole("menuitem", { name: /Compose a message…/ })).toBeVisible();
    await expect(menu.getByRole("menuitem", { name: /Refresh board/ })).toBeVisible();
    await expect(menu.getByRole("menuitem", { name: /^Pause / })).toBeVisible();
    await expectNoSeriousAxe(page, "Board menu");
    await page.keyboard.press("Escape");
    await expect(menu).toHaveCount(0);

    await board.focus();
    await page.keyboard.press("Shift+F10");
    await expect(page.getByRole("menuitem", { name: /Change Page…/ })).toBeVisible();
    await page.getByRole("menuitem", { name: /Change Page…/ }).click();
    await expect(page.getByRole("dialog", { name: "Change Page" })).toBeVisible();
  });

  test.describe("on a phone", () => {
    test.use({ viewport: { width: 390, height: 844 }, hasTouch: true });

    test("Change Page is a two-step sheet: pick, then how long", async ({ page }) => {
      const base = await createPage("Evening commute", ["GOOD EVENING", "", "", "", "", ""]);
      await createPage("Taco Tuesday", ["TACO TUESDAY", "", "", "", "", ""]);
      await setActivePage(base);
      await page.goto("/");

      await page.getByRole("button", { name: "Change Page", exact: true }).click();
      const step1 = page.getByRole("dialog", { name: "Change Page" });
      await expect(step1.getByText(/^Step 1 of 2/)).toBeVisible();
      await step1.getByRole("button", { name: /Taco Tuesday/ }).click();

      const step2 = page.getByRole("dialog", { name: "Taco Tuesday" });
      await expect(step2.getByText(/^Step 2 of 2/)).toBeVisible();
      await expect(step2.getByRole("radiogroup", { name: "How long should Taco Tuesday stay up?" })).toBeVisible();
      await expectNoSeriousAxe(page, "Change Page sheet step 2");
      await step2.getByRole("button", { name: "Back" }).click();
      await expect(page.getByRole("dialog", { name: "Change Page" })).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    });
  });
});
