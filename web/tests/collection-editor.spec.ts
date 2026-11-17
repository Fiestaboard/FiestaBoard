/** Collection editor 07c: saved-state evaluation, mode changes and parity evidence. */
import { getViolations, injectAxe } from "axe-playwright";

import {
  API_URL,
  authHeaders,
  configureBoard,
  createCollection,
  createPage,
  deleteAllCollections,
  deleteAllPages,
  ensureAuthForFetch,
  expect,
  loginIfNeeded,
  suppressWizard,
  test,
} from "./helpers";

const names = ["Morning commute", "Market open", "Weather and surf", "Good morning"];
async function seed() {
  const ids = [];
  for (const name of names) ids.push(await createPage(name));
  return { ids, collection: await createCollection("Weekday mornings", ids, 600) };
}
test.beforeEach(async ({ context, page }) => {
  await ensureAuthForFetch();
  await loginIfNeeded(context);
  await configureBoard();
  await suppressWizard(page);
  await deleteAllCollections();
});
test.afterEach(async () => {
  await deleteAllCollections();
  await deleteAllPages();
});

test("mode chips save random selection without an invented no-repeat flag", async ({ page }) => {
  const { collection } = await seed();
  await page.goto(`/collections/${encodeURIComponent(collection.id)}`);
  await expect(page.getByRole("heading", { name: "Weekday mornings" })).toBeVisible();
  await expect(page.getByText(/Saved Collection · cached data/)).toBeVisible();
  await page.getByRole("radio", { name: "Random selection", exact: true }).click();
  await expect(page.getByText("Save your changes to evaluate this Collection.")).toBeVisible();
  await expect(page.getByRole("switch")).toHaveCount(0);
  await expect(page.getByLabel("Change every", { exact: true })).toBeVisible();
  const update = page.waitForRequest((r) => r.method() === "PUT" && r.url().includes("/v1/collections/"));
  await page.getByRole("button", { name: "Save", exact: true }).click();
  const body = (await update).postDataJSON();
  expect(body.random).toEqual({ interval_seconds: 600 });
  expect(body.selection_mode).toBe("random");
  await expect(page).toHaveURL(/\/collections$/);
  await page.goto(`/collections/${encodeURIComponent(collection.id)}`);
  await expect(page.getByRole("radio", { name: "Random selection", exact: true })).toBeChecked();
  await injectAxe(page);
  expect(
    await getViolations(page, undefined, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21aa"] } }),
  ).toEqual([]);
});

test("07c parity evidence at three widths in both themes and every mode", async ({ page }, testInfo) => {
  test.setTimeout(180_000);
  const { ids, collection } = await seed();
  const cdp = await page.context().newCDPSession(page);
  for (const mode of ["time", "random", "variable"] as const) {
    const response = await fetch(`${API_URL}/v1/collections/${encodeURIComponent(collection.id)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({
        selection_mode: mode,
        random: mode === "random" ? { interval_seconds: 900 } : null,
        variable:
          mode === "variable"
            ? {
                rules: [
                  { expression: "1 == 0", page_id: ids[0] },
                  { expression: "2 == 0", page_id: ids[1] },
                ],
                default_page_id: ids[3],
                poll_seconds: 10,
              }
            : null,
      }),
    });
    expect(response.ok).toBe(true);
    for (const width of [390, 768, 900, 1280]) {
      await page.setViewportSize({ width, height: 1000 });
      await cdp.send("Emulation.setTouchEmulationEnabled", { enabled: width === 390, maxTouchPoints: 1 });
      for (const theme of ["light", "dark"]) {
        await page.addInitScript((value) => {
          localStorage.setItem("theme", value);
          localStorage.setItem("fiestaboard_animations_enabled", "false");
        }, theme);
        await page.goto(`/collections/${encodeURIComponent(collection.id)}`);
        await page.reload();
        await expect(page.getByRole("button", { name: "Save", exact: true })).toBeVisible();
        if (width === 390) {
          await expect.poll(() => page.evaluate(() => matchMedia("(pointer: coarse)").matches)).toBe(true);
          await expect(page.getByText(/Saved Collection · cached data/)).toBeAttached();
          await expect(page.getByRole("button", { name: "Collection settings", exact: true })).toBeVisible();
        } else await expect(page.getByText(/Saved Collection · cached data/)).toBeVisible();
        await expect(page.getByTestId("collection-preview-board")).toHaveAttribute("aria-busy", "false");
        await page.evaluate((value) => {
          document.documentElement.classList.toggle("dark", value === "dark");
          document.documentElement.classList.add("reduce-motion");
        }, theme);
        await expect(page.locator("form")).toBeVisible();
        if ((width === 768 || width === 900) && mode === "time") {
          const preview = page.getByRole("region", { name: "Now in this Collection", exact: true });
          const board = await preview.getByRole("img").boundingBox();
          const caption = await preview.getByText(/^Selected:/).boundingBox();
          expect(board).not.toBeNull();
          expect(caption).not.toBeNull();
          expect(caption!.x).toBeGreaterThan(board!.x + board!.width);
        }
        const overflowing = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
        expect(overflowing).toBe(false);
        if (width === 1280) {
          await injectAxe(page);
          expect(
            await getViolations(page, undefined, {
              runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21aa"] },
            }),
          ).toEqual([]);
        }
        const name = `impl-${width}-${theme}-${mode}.png`;
        const path = testInfo.outputPath(name);
        await page.screenshot({ path, fullPage: true, animations: "disabled" });
        await testInfo.attach(name, { path, contentType: "image/png" });
        if (width === 390 && theme === "light") {
          await page.getByRole("button", { name: "Collection settings", exact: true }).click();
          await expect(page.getByLabel("Collection name")).toBeVisible();
          await page.getByRole("button", { name: "Now in this Collection", exact: true }).click();
          await expect(page.getByText(/Saved Collection · cached data/)).toBeVisible();
          const expanded = testInfo.outputPath(`impl-390-light-${mode}-expanded.png`);
          await page.screenshot({ path: expanded, fullPage: true, animations: "disabled" });
          await testInfo.attach(`impl-390-light-${mode}-expanded.png`, { path: expanded, contentType: "image/png" });
        }
      }
    }
  }
});
