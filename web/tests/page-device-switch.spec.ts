/**
 * Page creator device/size switching E2E.
 *
 * A new page's device type used to be locked to the Pages tab the user came
 * from (`/pages/new?device=…`). The editor now offers a board-size switcher
 * for NEW pages, so starting on the wrong tab is recoverable without
 * recreating the page. Existing pages stay locked (converting saved content
 * between 6×22 and 3×15 is lossy).
 */
import {
  API_URL,
  authHeaders,
  configureBoard,
  createPage,
  deleteAllPages,
  deletePagesByDevice,
  ensureAuthForFetch,
  expect,
  suppressWizard,
  test,
} from "./helpers";

test.describe("Page creator board-size switching", () => {
  test.beforeEach(async ({ page }) => {
    await ensureAuthForFetch();
    await configureBoard();
    await suppressWizard(page);
    await deleteAllPages();
  });

  test.afterAll(async () => {
    // This suite creates a NOTE page on a flagship-only setup; clear it (note
    // pages first, so the auto-Welcome regenerates as flagship) so later
    // suites' device-tab assertions aren't polluted.
    await deletePagesByDevice("note");
    await deleteAllPages();
  });

  test("a page started on the Flagship tab can be saved as a Note page", async ({ page }) => {
    const name = `Switched Note ${Date.now() % 1_000_000}`;

    // Enter the editor the flagship way.
    await page.goto("/pages/new?device=flagship");
    await expect(page.getByText("6 × 22").first()).toBeVisible({ timeout: 15_000 });

    // Switch the size to Note before saving.
    await page.getByLabel("Change board size").click();
    await page.getByRole("option", { name: "Note", exact: true }).click();
    await expect(page.getByText("3 × 15").first()).toBeVisible({ timeout: 10_000 });

    // Name it and save.
    await page.getByPlaceholder("My Custom Page").fill(name);
    await page.getByRole("button", { name: "Save Page" }).first().click();

    // The saved page is a NOTE page.
    await expect
      .poll(
        async () => {
          const res = await fetch(`${API_URL}/pages`, { headers: authHeaders() });
          const data = await res.json();
          const saved = (data.pages ?? []).find((p: { name: string }) => p.name === name);
          return saved?.device_type ?? null;
        },
        { timeout: 10_000 },
      )
      .toBe("note");
  });

  test("editing an existing page offers no size switcher", async ({ page }) => {
    const id = await createPage(`Locked Page ${Date.now() % 1_000_000}`, ["LOCKED", "", "", "", "", ""]);

    await page.goto(`/pages/edit/${id}`);
    await expect(page.getByText("6 × 22").first()).toBeVisible({ timeout: 15_000 });
    await expect(page.getByLabel("Change board size")).toHaveCount(0);
  });
});
