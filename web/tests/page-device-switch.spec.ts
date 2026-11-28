/**
 * Page creator device/size switching E2E.
 *
 * A new page's device type used to be locked to the Pages tab the user came
 * from (`/pages/new?device=…`). The editor now offers a board-size switcher
 * for NEW pages, so starting on the wrong tab is recoverable without
 * recreating the page. A SAVED page keeps its size: #1250's in-place resize
 * is retired (D3, DD-W159) for Inspector › Shows on › "Make a copy sized for
 * X" (regression/multi-board-e2e.spec.ts drives that copy), so its preview
 * meta is plain text and its board colour moves into ⋯ View.
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
    await expect(page.getByText("22 × 6").first()).toBeVisible({ timeout: 15_000 });

    // Switch the size to Note before saving.
    // BB-E-6: size and target live behind the preview header's meta.
    await page.getByTestId("preview-target-trigger").click();
    await page.getByLabel("Change board size").click();
    await page.getByRole("option", { name: "Note", exact: true }).click();
    await expect(page.getByText("15 × 3").first()).toBeVisible({ timeout: 10_000 });

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

  test("a saved page keeps its size: plain-text meta, no size switcher, board colour in View", async ({ page }) => {
    const id = await createPage(`Fixed Size Page ${Date.now() % 1_000_000}`, ["FIXED", "", "", "", "", ""]);

    await page.goto(`/pages/edit/${id}`);
    const preview = page.locator("#page-editor-preview");
    const meta = preview.getByTestId("preview-target-meta");
    await expect(meta).toContainText("22 × 6", { timeout: 15_000 });
    await expect(page.getByTestId("preview-target-trigger")).toHaveCount(0);
    await expect(page.getByLabel("Change board size")).toHaveCount(0);

    await preview.getByRole("button", { name: "View", exact: true }).click();
    await page.getByRole("group", { name: "Board color" }).getByRole("menuitemradio", { name: "White" }).click();
    await expect(page.getByRole("menu")).toHaveCount(0);
    await preview.getByRole("button", { name: "View", exact: true }).click();
    await expect(
      page.getByRole("group", { name: "Board color" }).getByRole("menuitemradio", { name: "White" }),
    ).toHaveAttribute("aria-checked", "true");
    await page.keyboard.press("Escape");
  });
});
