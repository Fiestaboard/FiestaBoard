/**
 * FiestaBoard: when the install offer appears (slice 2.8, WEB-12; Figma 07
 * `58:33496`, note `58:34443` "Ask after value, never on load").
 *
 * Run against localhost (secure, like https). The browser's
 * `beforeinstallprompt` is simulated, because headless Chromium never fires
 * a real one.
 *
 *   1. Nothing on load, even with the browser offering to install.
 *   2. Nothing after the first and second sends; the card, with a real
 *      Install button, after the third.
 *   3. Install hands over to the browser's own prompt.
 *   4. Not now hides it and it stays hidden across reloads and more sends.
 *   5. a11y of the card.
 */
import type { Page } from "@playwright/test";
import { getViolations, injectAxe } from "axe-playwright";

import {
  API_URL,
  authHeaders,
  configureBoard,
  createPage,
  deleteAllPages,
  expect,
  setActivePage,
  suppressWizard,
  test,
} from "./helpers";

async function offerBrowserInstall(page: Page) {
  await page.evaluate(() => {
    const event = Object.assign(new Event("beforeinstallprompt", { cancelable: true }), {
      prompt: () => {
        (window as unknown as { __promptCalls: number }).__promptCalls =
          ((window as unknown as { __promptCalls?: number }).__promptCalls ?? 0) + 1;
        return Promise.resolve();
      },
      userChoice: Promise.resolve({ outcome: "dismissed" }),
    });
    window.dispatchEvent(event);
  });
}

async function changePageTo(page: Page, name: string, timed = false) {
  await page.getByRole("button", { name: /Change Page/i }).click();
  await page.getByRole("dialog").getByText(name, { exact: true }).first().click();
  if (timed) await page.getByRole("dialog").getByRole("radio", { name: "15 min", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Show now", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0, { timeout: 10_000 });
}

const offer = (page: Page) => page.getByTestId("install-offer");

test.describe("install offer timing (2.8, WEB-12)", () => {
  test.beforeEach(async ({ page }) => {
    await configureBoard();
    await fetch(`${API_URL}/schedules/enabled`, {
      method: "PUT",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ enabled: false }),
    });
    await deleteAllPages();
    const first = await createPage("Install Alpha");
    await createPage("Install Beta");
    await createPage("Install Gamma");
    await setActivePage(first);
    suppressWizard(page);
    await page.goto("/");
    await expect(page.getByRole("button", { name: /Change Page/i })).toBeVisible({ timeout: 15_000 });
    await offerBrowserInstall(page);
  });

  test("never shows on load, even when the browser offers to install", async ({ page }) => {
    await page.waitForTimeout(3_000);
    await expect(offer(page)).toHaveCount(0);
  });

  test("shows only after the third send, with a real Install button", async ({ page }) => {
    await changePageTo(page, "Install Beta");
    await changePageTo(page, "Install Gamma");
    await page.waitForTimeout(500);
    await expect(offer(page)).toHaveCount(0);

    await changePageTo(page, "Install Alpha", true);
    await expect(offer(page)).toBeVisible();
    await expect(offer(page).getByText(/You’ve sent 3 messages from here/)).toBeVisible();

    await offer(page).getByRole("button", { name: "Install", exact: true }).click();
    await expect
      .poll(() => page.evaluate(() => (window as unknown as { __promptCalls?: number }).__promptCalls))
      .toBe(1);
    await expect(offer(page)).toHaveCount(0);
  });

  test("Not now keeps it away across a reload and more sends", async ({ page }) => {
    for (const name of ["Install Beta", "Install Gamma", "Install Alpha"]) await changePageTo(page, name);
    await offer(page).getByRole("button", { name: "Not now" }).click();
    await expect(offer(page)).toHaveCount(0);

    await page.reload();
    await expect(page.getByRole("button", { name: /Change Page/i })).toBeVisible({ timeout: 15_000 });
    await offerBrowserInstall(page);
    for (const name of ["Install Beta", "Install Gamma", "Install Alpha"]) await changePageTo(page, name);
    await page.waitForTimeout(500);
    await expect(offer(page)).toHaveCount(0);
  });

  test("the card has no serious or critical axe violations", async ({ page }) => {
    for (const name of ["Install Beta", "Install Gamma", "Install Alpha"]) await changePageTo(page, name);
    await expect(offer(page)).toBeVisible();
    await injectAxe(page);
    const violations = (await getViolations(page, '[data-testid="install-offer"]')).filter(
      (v) => v.impact === "serious" || v.impact === "critical",
    );
    expect(violations.map((v) => `${v.id}: ${v.help}`)).toEqual([]);
  });
});
