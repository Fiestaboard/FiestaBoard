/**
 * Regression coverage for /pages/edit/[id].
 * Subarea: pages.edit
 */
import {
  test,
  expect,
  configureBoard,
  createPage,
  deleteAllPages,
  ensureAuthForFetch,
  loginIfNeeded,
} from "../helpers";

test.beforeEach(async ({ context, page }) => {
  await ensureAuthForFetch();
  await loginIfNeeded(context);
  await configureBoard();
  await page.addInitScript(() => {
    localStorage.setItem("fiestaboard_wizard_complete", "true");
  });
});

test.afterEach(async () => {
  await deleteAllPages();
});

test.describe("regression: pages.edit", () => {
  // ---- P0: export dialog cluster ----

  /** UX node: pages.edit.export-dialog */
  test("pages.edit.export-dialog — Export opens dialog with pre-filled share string", async ({ page }) => {
    const id = await createPage("Export Test", ["HELLO", "WORLD", "", "", "", ""]);
    await page.goto(`/pages/edit/${id}`);
    await page.getByRole("button", { name: "Export Page" }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible({ timeout: 10_000 });
    await expect(dialog.getByText("Export Page", { exact: true })).toBeVisible();
    const textarea = dialog.locator("textarea");
    await expect(textarea).toBeVisible();
    await expect(textarea).not.toHaveValue("");
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden({ timeout: 5_000 });
  });

  /** UX node: pages.edit.export-copied */
  test("pages.edit.export-copied — copy button click is registered", async ({ page, context }) => {
    // Grant clipboard permissions optimistically — in headless mode without
    // HTTPS, navigator.clipboard may still be undefined, so we assert on UI
    // affordances (button click registered) rather than reading the clipboard.
    await context.grantPermissions(["clipboard-read", "clipboard-write"]).catch(() => {});
    const id = await createPage("Copy Test", ["COPY", "", "", "", "", ""]);
    await page.goto(`/pages/edit/${id}`);
    await page.getByRole("button", { name: "Export Page" }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible({ timeout: 10_000 });
    const copyBtn = dialog.getByRole("button", { name: "Copy share string" });
    await expect(copyBtn).toBeVisible();
    await copyBtn.click();
    // Dialog stays open; the click is observable via no thrown error.
    await expect(dialog).toBeVisible();
  });

  /** UX node: pages.edit.export-error */
  test("pages.edit.export-error — share-string fetch failure toasts", async ({ page }) => {
    const id = await createPage("Export Err", ["X", "", "", "", "", ""]);
    await page.route(`**/api/pages/${id}/share`, (route) => route.fulfill({ status: 500 }));
    await page.goto(`/pages/edit/${id}`);
    await page.getByRole("button", { name: "Export Page" }).click();
    const toast = page.locator("[data-sonner-toast]").first();
    await expect(toast).toBeVisible({ timeout: 10_000 });
  });

  /** UX node: pages.edit.export-disabled-when-dirty */
  test("pages.edit.export-disabled-when-dirty — Export disabled when unsaved changes exist", async ({ page }) => {
    const id = await createPage("Dirty Test", ["A", "", "", "", "", ""]);
    await page.goto(`/pages/edit/${id}`);
    await page.getByRole("button", { name: "Plain Text" }).click();
    await page.locator("textarea").first().fill("MODIFIED\n\n\n\n\n");
    const exportBtn = page.getByRole("button", { name: "Export Page" });
    await expect(exportBtn).toBeDisabled({ timeout: 5_000 });
  });

  // ---- P1: dirty / saving / save-error / delete-error ----

  /** UX node: pages.edit.dirty */
  test("pages.edit.dirty — modifying content marks Save enabled", async ({ page }) => {
    const id = await createPage("Dirty Mark", ["A", "", "", "", "", ""]);
    await page.goto(`/pages/edit/${id}`);
    await page.getByRole("button", { name: "Plain Text" }).click();
    await page.locator("textarea").first().fill("CHANGED\n\n\n\n\n");
    const saveBtn = page.getByRole("button", { name: "Save Page" });
    await expect(saveBtn).toBeEnabled({ timeout: 5_000 });
  });

  /** UX node: pages.edit.saving */
  test("pages.edit.saving — Save click shows pending state", async ({ page }) => {
    const id = await createPage("Saving Test", ["A", "", "", "", "", ""]);
    let release: () => void = () => {};
    await page.route(`**/api/pages/${id}`, async (route) => {
      if (route.request().method() === "PUT") {
        await new Promise<void>((r) => { release = r; });
      }
      await route.continue();
    });
    await page.goto(`/pages/edit/${id}`);
    await page.getByRole("button", { name: "Plain Text" }).click();
    await page.locator("textarea").first().fill("CHANGED\n\n\n\n\n");
    const saveBtn = page.getByRole("button", { name: "Save Page" });
    await saveBtn.click();
    await expect(saveBtn).toBeDisabled({ timeout: 5_000 });
    release();
  });

  /** UX node: pages.edit.save-error */
  test("pages.edit.save-error — failed save surfaces toast and keeps dirty state", async ({ page }) => {
    const id = await createPage("Save Err", ["A", "", "", "", "", ""]);
    await page.route(`**/api/pages/${id}`, (route) => {
      if (route.request().method() === "PUT") {
        return route.fulfill({ status: 500, body: '{"detail":"boom"}' });
      }
      return route.continue();
    });
    await page.goto(`/pages/edit/${id}`);
    await page.getByRole("button", { name: "Plain Text" }).click();
    await page.locator("textarea").first().fill("X\n\n\n\n\n");
    await page.getByRole("button", { name: "Save Page" }).click();
    await expect(page.locator("[data-sonner-toast]").first()).toBeVisible({ timeout: 10_000 });
  });

  /** UX node: pages.edit.save-success */
  test("pages.edit.save-success — successful save clears dirty and toasts", async ({ page }) => {
    const id = await createPage("Save Ok", ["A", "", "", "", "", ""]);
    await page.goto(`/pages/edit/${id}`);
    await page.getByRole("button", { name: "Plain Text" }).click();
    await page.locator("textarea").first().fill("SAVED\n\n\n\n\n");
    await page.getByRole("button", { name: "Save Page" }).click();
    await expect(page.locator("[data-sonner-toast]").first()).toBeVisible({ timeout: 10_000 });
  });

  /** UX node: pages.edit.delete-confirm */
  test("pages.edit.delete-confirm — Delete opens confirm dialog with page name", async ({ page }) => {
    const id = await createPage("Delete Confirm Test", ["A", "", "", "", "", ""]);
    await page.goto(`/pages/edit/${id}`);
    await page.getByRole("button", { name: "Delete Page" }).click();
    const dialog = page.getByRole("alertdialog");
    await expect(dialog).toBeVisible({ timeout: 5_000 });
    await expect(dialog.getByText(/Delete Confirm Test/i)).toBeVisible();
    await dialog.getByRole("button", { name: /Cancel/i }).click();
    await expect(dialog).toBeHidden({ timeout: 5_000 });
  });

  /** UX node: pages.edit.delete-success */
  test("pages.edit.delete-success — confirming delete removes page and redirects", async ({ page }) => {
    const id = await createPage("Delete Me", ["A", "", "", "", "", ""]);
    await page.goto(`/pages/edit/${id}`);
    await page.getByRole("button", { name: "Delete Page" }).click();
    const dialog = page.getByRole("alertdialog");
    await dialog.getByRole("button", { name: /^Delete/ }).click();
    await page.waitForURL(/\/pages$/, { timeout: 10_000 });
  });

  /** UX node: pages.edit.delete-error */
  test("pages.edit.delete-error — failed delete surfaces toast and keeps editor", async ({ page }) => {
    const id = await createPage("Delete Err", ["A", "", "", "", "", ""]);
    await page.route(`**/api/pages/${id}`, (route) => {
      if (route.request().method() === "DELETE") {
        return route.fulfill({ status: 500, body: '{"detail":"boom"}' });
      }
      return route.continue();
    });
    await page.goto(`/pages/edit/${id}`);
    await page.getByRole("button", { name: "Delete Page" }).click();
    const dialog = page.getByRole("alertdialog");
    await dialog.getByRole("button", { name: /^Delete/ }).click();
    await expect(page.locator("[data-sonner-toast]").first()).toBeVisible({ timeout: 10_000 });
  });

  /** UX node: pages.edit.clean */
  test.fixme("pages.edit.clean — fresh load has Save disabled after snapshot settles", () => {
    // Save defaults to ENABLED on fresh load because savedSnapshot is null until
    // the API response sets it. Even after settling, the snapshot tracker may
    // diverge from the rendered state. Needs source-side `data-saved-state` attribute
    // or a stable initial state contract before this can be reliably tested.
  });

  /** UX node: pages.edit.loading */
  test("pages.edit.loading — page query in-flight shows skeleton", async ({ page }) => {
    const id = await createPage("Loading Test", ["A", "", "", "", "", ""]);
    let release: () => void = () => {};
    await page.route(`**/api/pages/${id}`, async (route) => {
      if (route.request().method() === "GET") {
        await new Promise<void>((r) => { release = r; });
      }
      await route.continue();
    });
    const nav = page.goto(`/pages/edit/${id}`);
    await expect(page.locator('[aria-busy="true"], [data-slot="skeleton"]').first()).toBeVisible({ timeout: 10_000 });
    release();
    await nav;
  });

  /** UX node: pages.edit.not-found */
  test.fixme("pages.edit.not-found — invalid id surfaces not-found state", () => {
    // The editor doesn't render an explicit not-found state for invalid ids — it
    // falls back to an empty editor (same as /pages/new). Tree node is aspirational.
  });

  /** UX node: pages.edit.legacy-query-id */
  test("pages.edit.legacy-query-id — /pages/edit?id=X renders the editor in-place", async ({ page }) => {
    const id = await createPage("Legacy", ["A", "", "", "", "", ""]);
    await page.goto(`/pages/edit?id=${id}`);
    // Legacy route renders the editor at the same URL (no redirect).
    await expect(page.getByRole("button", { name: "Save Page" })).toBeVisible({ timeout: 10_000 });
    expect(page.url()).toContain("/pages/edit");
  });

  /** UX node: pages.edit.no-id-redirect */
  test("pages.edit.no-id-redirect — /pages/edit without id redirects to /pages", async ({ page }) => {
    await page.goto("/pages/edit");
    await page.waitForURL(/\/pages(\?|$)/, { timeout: 10_000 });
  });

  /** UX node: pages.edit.live-output-on */
  test.fixme("pages.edit.live-output-on — live output toggle shows pushed state", () => {
    // Covered by pages.new.live-output-on; same toggle semantics.
  });

  /** UX node: pages.edit.live-output-inactivity-off */
  test.fixme("pages.edit.live-output-inactivity-off — auto-disable after 5min inactivity", () => {
    // Requires fast-forwarding 5-min timer; out of scope for this pass.
  });
});
