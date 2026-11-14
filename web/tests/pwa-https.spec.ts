/**
 * FiestaBoard on plain http (slice 2.8, WEB-12; Figma 07 note `58:34443`
 * "HTTPS or nothing, said plainly", 07e `329:49323` Requires HTTPS).
 *
 * Run against a LAN-style http host (BASE_URL=http://<host>:<port>, not
 * localhost), which the browser treats as insecure. Skipped on localhost,
 * which browsers treat as secure.
 *
 *   1. No service worker is registered.
 *   2. Settings says "Requires HTTPS", with the fix.
 *   3. After the third send the install card says it needs a secure address
 *      and draws no Install button.
 */
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

const host = new URL(process.env.BASE_URL || "http://localhost:4420").hostname;

test.describe("plain http: honest about install and offline (2.8)", () => {
  test.skip(host === "localhost" || host === "127.0.0.1", "localhost is a secure context");

  test.beforeEach(async ({ page }) => {
    await configureBoard();
    suppressWizard(page);
  });

  test("registers no service worker", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("main")).toBeVisible({ timeout: 15_000 });
    expect(await page.evaluate(() => window.isSecureContext)).toBe(false);
    expect(await page.evaluate(() => "serviceWorker" in navigator)).toBe(false);
  });

  test("Settings says Requires HTTPS, with how to fix it", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.getByText("Requires HTTPS")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole("link", { name: "How to set up HTTPS" })).toHaveAttribute(
      "href",
      /fiestaboard\.app\/docs\/deployment\/production/,
    );
    // Let the route's entrance fade finish: axe reads mid-fade text as low contrast.
    await page.evaluate(() => Promise.all(document.getAnimations().map((a) => a.finished)));
    await injectAxe(page);
    const violations = (await getViolations(page)).filter((v) => v.impact === "serious" || v.impact === "critical");
    expect(violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`)).toEqual([]);
  });

  test("after the third send the card says install needs a secure address, with no Install button", async ({
    page,
  }) => {
    await fetch(`${API_URL}/schedules/enabled`, {
      method: "PUT",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ enabled: false }),
    });
    await deleteAllPages();
    const first = await createPage("Http Alpha");
    await createPage("Http Beta");
    await setActivePage(first);
    await page.goto("/");
    for (const name of ["Http Beta", "Http Alpha", "Http Beta"]) {
      await page.getByRole("button", { name: /Change Page/i }).click();
      await page.getByRole("dialog").getByText(name, { exact: true }).first().click();
      await expect(page.getByRole("dialog")).toHaveCount(0, { timeout: 10_000 });
    }
    const offer = page.getByTestId("install-offer");
    await expect(offer).toBeVisible({ timeout: 15_000 });
    await expect(offer.getByRole("region", { name: "Install needs a secure address" })).toBeVisible();
    await expect(offer.getByRole("button", { name: "Install", exact: true })).toHaveCount(0);
    await expect(offer.getByRole("button", { name: "Not now" })).toBeVisible();
  });
});
