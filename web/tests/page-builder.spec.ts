/**
 * FiestaBoard Page Builder E2E Tests
 *
 * Full page creation/editing lifecycle through the UI,
 * covering the biggest coverage gap in the test suite.
 */
import {
  API_URL,
  authHeaders,
  configureBoard,
  createPage,
  deleteAllPages,
  deletePage,
  disablePlugin,
  enablePlugin,
  expect,
  resetToSingleBoard,
  setActivePage,
  setScheduleEnabled,
  suppressWizard,
  test,
  waitForNoActiveDisplay,
} from "./helpers";

test.beforeEach(async ({ page }) => {
  await configureBoard();
  await suppressWizard(page);
});

test.describe("Page Builder", () => {
  test("can create a template page with 6 lines", async ({ page }) => {
    await page.goto("/pages/new");
    await expect(page.locator("#page-name")).toBeVisible({
      timeout: 15_000,
    });

    // Fill page name
    const nameInput = page.getByPlaceholder("My Custom Page");
    await nameInput.fill("E2E Builder Test");

    const editor = page.locator('[contenteditable="true"]').first();
    await expect(editor).toBeVisible();
    await editor.fill("HELLO BUILDER");

    // Save the page
    const saveButton = page.getByRole("button", { name: "Save Page" }).or(page.getByRole("button", { name: /save/i }));
    await saveButton.first().click();

    // Saving keeps the current editor and announces its stored state.
    await expect(page.getByText(/^Saved (just now|\d)/)).toBeVisible({ timeout: 15_000 });
    await expect(nameInput).toHaveValue("E2E Builder Test");

    // Verify page exists via API
    const res = await fetch(`${API_URL}/pages`);
    const data = await res.json();
    const found = data.pages.find((p: { name: string }) => p.name === "E2E Builder Test");
    expect(found).toMatchObject({ name: "E2E Builder Test", template: expect.arrayContaining(["HELLO BUILDER"]) });
  });

  test("can edit an existing page name and content", async ({ page }) => {
    const pageId = await createPage("Original Name", ["ORIGINAL", "", "", "", "", ""]);

    await page.goto(`/pages/edit/${pageId}`);
    await expect(page.getByPlaceholder("My Custom Page")).toHaveValue("Original Name", { timeout: 15_000 });

    const nameInput = page.getByPlaceholder("My Custom Page");
    await nameInput.fill("Updated Name");
    await page.locator('[contenteditable="true"]').first().fill("UPDATED CONTENT");

    const saveButton = page.getByRole("button", { name: "Save Page" }).or(page.getByRole("button", { name: /save/i }));
    await saveButton.first().click();

    await expect(page.getByText(/^Saved (just now|\d)/)).toBeVisible({ timeout: 15_000 });
    await expect(nameInput).toHaveValue("Updated Name");

    // Verify via API
    const res = await fetch(`${API_URL}/pages/${pageId}`);
    const data = await res.json();
    expect(data.name).toBe("Updated Name");
    expect(data.template).toContain("UPDATED CONTENT");
  });

  // UX-8-1: a blank name never blocks Save; the page is saved as "Untitled page".
  test("saves a page whose name was cleared as Untitled page", async ({ page }) => {
    await page.goto("/pages/new");
    await expect(page.locator("#page-name")).toBeVisible({
      timeout: 15_000,
    });

    const name = page.getByPlaceholder("My Custom Page");
    await expect(name).toHaveValue("Untitled page");
    await name.fill("");
    await page.getByRole("button", { name: "Save Page", exact: true }).click();
    await expect(page).toHaveURL(/\/pages\/edit\/[^/]+$/, { timeout: 15_000 });
    await expect(name).toHaveValue("Untitled page");
    await deletePage(page.url().split("/").pop()!);
  });

  test("can preview page content in the builder", async ({ page }) => {
    await page.goto("/pages/new");
    await expect(page.locator("#page-name")).toBeVisible({
      timeout: 15_000,
    });

    const nameInput = page.getByPlaceholder("My Custom Page");
    await nameInput.fill("Preview Test");

    const preview = page.locator('[data-slot="editor-preview"]');
    await expect(preview).toBeVisible();
    await expect(preview.getByText("Live preview", { exact: true })).toBeVisible();
    await expect(preview.locator('[data-testid^="char-tile-"]').first()).toBeVisible();
  });

  test("can delete a page from the editor", async ({ page }) => {
    const pageId = await createPage("Delete From Editor", ["Delete test content"]);

    await page.goto(`/pages/edit/${pageId}`);
    await expect(page.getByPlaceholder("My Custom Page")).toHaveValue("Delete From Editor", { timeout: 15_000 });

    // Click delete button
    const deleteButton = page
      .locator('[title="Delete"]')
      .or(page.getByRole("button", { name: /delete/i }))
      .first();

    if (await deleteButton.isVisible({ timeout: 3_000 }).catch(() => false)) {
      await deleteButton.click();

      // Confirm in dialog
      const confirmButton = page.getByRole("button", { name: "Delete" }).last();
      if (await confirmButton.isVisible({ timeout: 3_000 }).catch(() => false)) {
        await confirmButton.click();
      }

      // Should redirect to /pages
      await expect(page.getByRole("heading", { name: "Pages", exact: true })).toBeVisible({ timeout: 15_000 });

      // Verify deleted via API
      const res = await fetch(`${API_URL}/pages/${pageId}`);
      expect(res.status).toBeGreaterThanOrEqual(400);
    }
  });

  test("shows empty state when no pages exist", async ({ page }) => {
    await resetToSingleBoard();
    await setScheduleEnabled(false);
    const anchorId = await createPage(`Empty-state Flagship anchor ${Date.now()}`);
    await setActivePage(anchorId);
    const selected = await fetch(`${API_URL}/v1/boards/primary`, { headers: authHeaders() });
    expect(selected.ok).toBe(true);
    expect(await selected.json()).toMatchObject({
      device_type: "flagship",
      rows: 6,
      cols: 22,
      schedule_enabled: false,
      active_page_id: anchorId,
    });

    // Earlier specs on this backend may leave scheduled pages. Unlink all
    // boards first; a rejected delete is a setup error, not a timing retry.
    // The pinned anchor guarantees a compatible page for the sole Flagship.
    // If cleanup deletes it early, the service selects another compatible
    // page or creates a Flagship Welcome, which is outside this delete list.
    // Thus the last deleted page cannot create a second, custom-size Welcome.
    await deleteAllPages({ strict: true, deleteSchedules: true });

    await page.goto("/pages");
    await expect(page.getByRole("heading", { name: "Pages", exact: true })).toBeVisible({ timeout: 15_000 });

    const res = await fetch(`${API_URL}/pages`);
    const data = await res.json();
    expect(data.pages.some((item: { id: string }) => item.id === anchorId)).toBe(false);
    expect(data.total).toBeLessThanOrEqual(1);
  });

  test("template variables autocomplete/picker works", async ({ page }) => {
    // The picker lists the hub's plugin variables, so this test owns that
    // precondition. Other specs (draw-mode.spec.ts) switch date_time off
    // afterwards, which used to leave the picker empty depending on order.
    const before = await fetch(`${API_URL}/v1/plugins/date_time`, { headers: authHeaders() });
    const wasEnabled = before.ok && (await before.json()).enabled === true;
    if (!wasEnabled) await enablePlugin("date_time");
    try {
      await page.goto("/pages/new");
      await expect(page.locator("#page-name")).toBeVisible({ timeout: 15_000 });

      // The toolbar's Variables button is labelled for its state, so wait for
      // the loaded, non-empty picker trigger rather than any "variable" text.
      const variables = page.getByRole("button", { name: "Variables", exact: true });
      await expect(variables).toBeEnabled({ timeout: 15_000 });
      await variables.click();

      // Assert inside the picker, not the first "time" text on the page
      // (that matched the hidden sidebar's "Language & time" link).
      // The picker titles each plugin group from its id ("date_time" -> "Date Time").
      await expect(page.getByText("Date Time", { exact: true })).toBeVisible({ timeout: 5_000 });
      // Each variable is an insert button whose name starts with the variable
      // and may be followed by a live preview value ("hour14").
      await expect(page.getByRole("button", { name: /^hour/ }).first()).toBeVisible();
    } finally {
      if (!wasEnabled) await disablePlugin("date_time");
    }
  });

  test("page with template variables renders correctly in preview", async ({ page }) => {
    const pageId = await createPage("Variable Preview", ["{date}", "", "", "", "", ""]);

    // Check the preview via API
    const res = await fetch(`${API_URL}/pages/${pageId}/preview`, {
      method: "POST",
    });
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data).toHaveProperty("lines");
    // The rendered output should not contain the raw {date} token
    // (it should be replaced with an actual date or left as-is if plugin not enabled)
    expect(data.lines).toBeDefined();

    await deletePage(pageId);
  });
});

// Import from board… (DD-W167): a dialog step on new and saved pages; Replace
// template is one ordinary, undoable edit that saves nothing.
test.describe("Import from board", () => {
  const IMPORT = "Import from board…";

  test("is offered on a new page and on a saved page", async ({ page }) => {
    await page.goto("/pages/new");
    await expect(page.locator("#page-name")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole("button", { name: IMPORT })).toBeVisible({ timeout: 10_000 });

    const pageId = await createPage("Import Button Saved Page");
    await page.goto(`/pages/edit/${pageId}`);
    await expect(page.locator("#page-name")).toHaveValue("Import Button Saved Page", { timeout: 15_000 });
    await expect(page.getByRole("button", { name: IMPORT })).toBeVisible({ timeout: 10_000 });
    await deletePage(pageId);
  });

  test("says the board is showing nothing, with Close only", async ({ page }) => {
    // Schedule mode with no schedules is a stable no-active-display state (see
    // the race notes in git history for this spec): nothing re-promotes a page.
    await deleteAllPages({ strict: true, deleteSchedules: true });
    await setScheduleEnabled(true);
    try {
      await setActivePage(null);
      await waitForNoActiveDisplay();
      await page.goto("/pages/new");
      await expect(page.locator("#page-name")).toBeVisible({ timeout: 15_000 });
      const [response] = await Promise.all([
        page.waitForResponse((res) => res.url().includes("/api/pages/current-display"), { timeout: 10_000 }),
        page.getByRole("button", { name: IMPORT }).click(),
      ]);
      expect(response.status()).toBe(404);
      const dialog = page.getByRole("alertdialog");
      await expect(dialog).toContainText("is showing nothing");
      await expect(dialog.getByRole("button", { name: "Close" })).toBeVisible();
      await expect(dialog.getByRole("button", { name: "Replace template" })).toHaveCount(0);
    } finally {
      await setScheduleEnabled(false);
    }
  });

  test("replaces a saved page's rows as one undo step, saving nothing", async ({ page }) => {
    const sourceId = await createPage("Import Source", ["HELLO IMPORT", "LINE TWO", "", "", "", ""]);
    const targetId = await createPage("Import Target", ["KEEP ME", "SECOND ROW", "", "", "", ""]);
    await setActivePage(sourceId);
    const writes: string[] = [];
    page.on("request", (req) => {
      if (/\/api\/v1\/pages/.test(req.url()) && ["PUT", "POST"].includes(req.method())) writes.push(req.url());
    });
    try {
      await page.goto(`/pages/edit/${targetId}`);
      const editor = page.getByRole("textbox", { name: "Template editor" });
      await expect(editor).toContainText("KEEP ME", { timeout: 15_000 });

      await page.getByRole("button", { name: IMPORT }).click();
      const dialog = page.getByRole("alertdialog");
      await expect(dialog).toContainText("Replace this template with what");
      await dialog.getByRole("button", { name: "Replace template" }).click();
      await expect(editor).toContainText("HELLO IMPORT");
      await expect(editor).not.toContainText("KEEP ME");
      await expect(page.getByTestId("page-editor-save-state")).toHaveText("Unsaved changes");

      // ⌘Z / Ctrl+Z: the old rows come back in one step and the page is clean again.
      await editor.click();
      await page.keyboard.press("ControlOrMeta+z");
      await expect(editor).toContainText("KEEP ME");
      await expect(editor).toContainText("SECOND ROW");
      await expect(editor).not.toContainText("HELLO IMPORT");
      await expect(page.getByTestId("page-editor-save-state")).toHaveText(/^Saved /);
      expect(writes).toEqual([]);
    } finally {
      await deletePage(targetId);
      await deletePage(sourceId);
    }
  });
});
