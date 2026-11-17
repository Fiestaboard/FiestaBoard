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

test("07c parity evidence at four widths in both themes and every mode", async ({
  page,
  browser,
  baseURL,
}, testInfo) => {
  test.setTimeout(240_000);
  const { ids, collection } = await seed();
  const storageState = await page.context().storageState();
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
      for (const theme of ["light", "dark"] as const) {
        // A fresh context establishes real touch and theme before React mounts.
        // Repeated addInitScript calls have undefined ordering across navigations.
        const context = await browser.newContext({
          baseURL,
          storageState,
          viewport: { width, height: 1000 },
          hasTouch: width === 390,
          isMobile: width === 390,
          colorScheme: theme,
          reducedMotion: "reduce",
        });
        try {
          const capture = await context.newPage();
          await suppressWizard(capture);
          await capture.addInitScript((value) => {
            localStorage.setItem("theme", value);
            localStorage.setItem("fiestaboard_animations_enabled", "false");
          }, theme);
          await capture.goto(`/collections/${encodeURIComponent(collection.id)}`);
          await expect(capture.getByRole("button", { name: "Save", exact: true })).toBeVisible();
          await expect
            .poll(() => capture.evaluate(() => document.documentElement.classList.contains("dark")))
            .toBe(theme === "dark");
          await expect.poll(() => capture.evaluate(() => matchMedia("(pointer: coarse)").matches)).toBe(width === 390);
          await expect(capture.getByTestId("collection-preview-board")).toHaveAttribute("aria-busy", "false");
          if (width === 390) {
            await expect(capture.getByText(/Saved Collection · cached data/)).toBeAttached();
            await expect(capture.getByRole("button", { name: "Collection settings", exact: true })).toBeVisible();
            if (mode === "time") await expect(capture.getByText(/Drag the handle, or use/)).toBeVisible();
          } else await expect(capture.getByText(/Saved Collection · cached data/)).toBeVisible();
          if ((width === 768 || width === 900) && mode === "time") {
            const preview = capture.getByRole("region", { name: "Now in this Collection", exact: true });
            const board = await preview.getByRole("img").boundingBox();
            const caption = await preview.getByText(/^Selected:/).boundingBox();
            expect(board).not.toBeNull();
            expect(caption).not.toBeNull();
            expect(caption!.x).toBeGreaterThan(board!.x + board!.width);
          }
          if (width === 768 || width === 900)
            await expect(capture.getByRole("heading", { name: "Weekday mornings", exact: true })).toHaveCSS(
              "font-size",
              "20px",
            );
          if (width === 390 && mode !== "variable") {
            const action = capture.getByRole("button", {
              name: mode === "time" ? "More actions for Morning commute" : "Remove Morning commute",
              exact: true,
            });
            const bounds = await action.boundingBox();
            expect(bounds?.width).toBe(44);
            expect(bounds?.height).toBe(44);
          }
          expect(await capture.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
          // Let layout/style settle before measuring contrast; never audit a transition frame.
          await capture.evaluate(
            () => new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))),
          );
          await injectAxe(capture);
          expect(
            await getViolations(capture, undefined, {
              runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21aa"] },
            }),
          ).toEqual([]);
          const name = `impl-${width}-${theme}-${mode}.png`;
          const path = testInfo.outputPath(name);
          await capture.screenshot({ path, fullPage: true, animations: "disabled" });
          await testInfo.attach(name, { path, contentType: "image/png" });
          if (width === 1280 && theme === "dark" && mode === "variable") {
            await capture.getByRole("button", { name: "More actions for rule 1", exact: true }).click();
            await capture.getByRole("menuitem", { name: "Edit rule 1", exact: true }).click();
            await capture.getByRole("button", { name: "Show expression syntax help", exact: true }).click();
            expect(
              await getViolations(capture, undefined, {
                runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21aa"] },
              }),
            ).toEqual([]);
            const edit = testInfo.outputPath("impl-1280-dark-variable-edit.png");
            await capture.screenshot({ path: edit, fullPage: true, animations: "disabled" });
            await testInfo.attach("impl-1280-dark-variable-edit.png", { path: edit, contentType: "image/png" });
          }
          if (width === 390 && theme === "light") {
            await capture.getByRole("button", { name: "Collection settings", exact: true }).click();
            await expect(capture.getByLabel("Collection name")).toBeVisible();
            await capture.getByRole("button", { name: "Now in this Collection", exact: true }).click();
            await expect(capture.getByText(/Saved Collection · cached data/)).toBeVisible();
            const expanded = testInfo.outputPath(`impl-390-light-${mode}-expanded.png`);
            await capture.screenshot({ path: expanded, fullPage: true, animations: "disabled" });
            await testInfo.attach(`impl-390-light-${mode}-expanded.png`, { path: expanded, contentType: "image/png" });
          }
        } finally {
          await context.close();
        }
      }
    }
  }
});
