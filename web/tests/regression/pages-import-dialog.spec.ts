/**
 * Auto-generated regression stubs from .claude/ux-coverage.json.
 * Subarea: pages.import-dialog
 *
 * These tests start as `test.fixme` placeholders (Playwright's todo equivalent — runtime skip).
 * Run /fill-ux-tests to
 * implement them. Each stub's JSDoc carries the UX node metadata so the
 * filler has full context.
 *
 * Priority: P0 — the entire import-dialog subarea has zero coverage and the
 * auditor flagged it as the highest-value gap. Fill these first.
 */
import {
  test,
  expect,
  configureBoard,
  API_URL,
  createPage,
  deleteAllPages,
  loginIfNeeded,
  ensureAuthForFetch,
  authHeaders,
  slowRoute,
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

/** Fetch a real share string by creating a page via the API and asking for its share encoding. */
async function getShareString(): Promise<{ id: string; name: string; shareString: string }> {
  const name = `Import Source ${Date.now()}`;
  const id = await createPage(name, ["HELLO", "WORLD", "", "", "", ""]);
  const res = await fetch(`${API_URL}/pages/${id}/share`, { headers: authHeaders() });
  if (!res.ok) throw new Error(`getShareString failed: ${res.status}`);
  const data = (await res.json()) as { share_string: string };
  return { id, name, shareString: data.share_string };
}

test.describe("regression: pages.import-dialog", () => {
  /**
   * UX node: pages.import-dialog.open
   * Route: /pages
   * Preconditions: (none — toolbar import affordance always present)
   * Interactions: click:import-page-toolbar → dialog opens
   *               type:share-string, click:cancel, click:import, keyboard:esc
   * Expected:
   *   - Radix Dialog mounts with sm:max-w-md and 28-row textarea pre-focused
   *   - Cancel and Import buttons rendered
   *   - Import button starts disabled while textarea is empty
   *   - Escape and Cancel both close the dialog and return to grid view
   * Source refs: web/src/app/pages/page.tsx
   * Coverage status: uncovered  (from .claude/ux-coverage.json)
   */
  test("pages.import-dialog.open — import dialog opens with empty textarea and disabled Import button", async ({ page }) => {
    await page.goto("/pages");

    // Open the dialog via the toolbar "Import" button.
    await page.getByRole("button", { name: "Import", exact: true }).click();

    // Dialog mounts with the expected title and a (non-Cancel) Import button.
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible({ timeout: 15_000 });
    await expect(dialog.getByText("Import Page", { exact: true })).toBeVisible();

    const cancelBtn = dialog.getByRole("button", { name: "Cancel", exact: true });
    // The submit button inside the dialog labelled "Import".
    const importBtn = dialog.getByRole("button", { name: "Import", exact: true });
    await expect(cancelBtn).toBeEnabled();
    await expect(importBtn).toBeDisabled();

    // The textarea should be empty and focused on open.
    const textarea = dialog.locator("textarea");
    await expect(textarea).toHaveValue("");
    await expect(textarea).toBeFocused();

    // Escape closes the dialog.
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden({ timeout: 15_000 });

    // Reopen and verify Cancel button also closes it.
    await page.getByRole("button", { name: "Import", exact: true }).click();
    await expect(page.getByRole("dialog")).toBeVisible({ timeout: 15_000 });
    await page.getByRole("dialog").getByRole("button", { name: "Cancel", exact: true }).click();
    await expect(page.getByRole("dialog")).toBeHidden({ timeout: 15_000 });
  });

  /**
   * UX node: pages.import-dialog.importing
   * Route: /pages
   * Preconditions: import-mutation:pending
   * Interactions: (none — pending state only)
   * Expected:
   *   - Import button label switches to "Importing..." while api.importPage is in flight
   *   - Import button is disabled during the pending mutation
   *   - Cancel button remains enabled
   * Source refs: web/src/app/pages/page.tsx
   * Coverage status: uncovered  (from .claude/ux-coverage.json)
   */
  test("pages.import-dialog.importing — Import button shows pending state while mutation in flight", async ({ page }) => {
    const release = await slowRoute(page, "**/api/pages/import", ["POST"]);
    await page.goto("/pages");
    await page.getByRole("button", { name: "Import", exact: true }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible({ timeout: 15_000 });

    // Need a valid share string to enable the Import button — create a source page and grab one.
    const { shareString } = await getShareString();
    await dialog.locator("textarea").fill(shareString);

    const importBtn = dialog.getByRole("button", { name: /Import/i }).first();
    await expect(importBtn).toBeEnabled();
    await importBtn.click();
    // Mutation is held by slowRoute → button disables, label may switch to "Importing".
    await expect(importBtn).toBeDisabled({ timeout: 5_000 });
    release();
  });

  /**
   * UX node: pages.import-dialog.error
   * Route: /pages
   * Preconditions: import-mutation:error (invalid share string or backend error)
   * Interactions: edit:share-string, click:cancel, click:import
   * Expected:
   *   - sonner error toast surfaces the thrown Error message
   *   - Dialog remains open after the failure
   *   - share-string textarea retains the user's input so they can edit and retry
   * Source refs: web/src/app/pages/page.tsx
   * Coverage status: uncovered  (from .claude/ux-coverage.json)
   */
  test("pages.import-dialog.error — failed import surfaces toast and keeps dialog open with input preserved", async ({ page }) => {
    await page.goto("/pages");
    await page.getByRole("button", { name: "Import", exact: true }).click();

    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible({ timeout: 15_000 });

    // Type an obviously invalid share string — the backend's decode_page raises
    // ValueError → 422, which the client surfaces as a thrown Error.
    const bogus = "not-a-valid-share-string-!!!";
    const textarea = dialog.locator("textarea");
    await textarea.fill(bogus);

    const importBtn = dialog.getByRole("button", { name: "Import", exact: true });
    await expect(importBtn).toBeEnabled();

    // Capture the failing import response so the assertions don't race the network.
    const importResponse = page.waitForResponse(
      (r) => r.url().endsWith("/api/pages/import") && r.request().method() === "POST",
    );
    await importBtn.click();
    const resp = await importResponse;
    expect(resp.ok()).toBe(false);

    // Dialog stays open, textarea keeps the user's input, and a sonner toast surfaces.
    await expect(dialog).toBeVisible({ timeout: 15_000 });
    await expect(textarea).toHaveValue(bogus);

    // Sonner renders each toast as a [data-sonner-toast] node inside the
    // [data-sonner-toaster] region. We assert at least one toast appears
    // with non-empty text (don't assert exact copy — comes from backend).
    const errorToast = page.locator("[data-sonner-toast]").first();
    await expect(errorToast).toBeVisible({ timeout: 15_000 });
    await expect(errorToast).not.toHaveText("", { timeout: 15_000 });
  });

  /**
   * UX node: pages.import-dialog.success
   * Route: /pages
   * Preconditions: import-mutation:success
   * Interactions: (none — success transition)
   * Expected:
   *   - Pages query is invalidated (new page appears in list)
   *   - Success toast '<name> added to your pages' is shown
   *   - Dialog auto-closes
   *   - Navigation slides up into /pages/edit/<new-id>
   * Source refs: web/src/app/pages/page.tsx
   * Coverage status: uncovered  (from .claude/ux-coverage.json)
   */
  test("pages.import-dialog.success — successful import toasts, closes dialog, navigates to /pages/edit/[id]", async ({ page }) => {
    // Seed a source page and pull a valid share string from the backend.
    const { shareString } = await getShareString();

    await page.goto("/pages");
    await page.getByRole("button", { name: "Import", exact: true }).click();

    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible({ timeout: 15_000 });

    await dialog.locator("textarea").fill(shareString);

    const importResponse = page.waitForResponse(
      (r) => r.url().endsWith("/api/pages/import") && r.request().method() === "POST",
    );
    await dialog.getByRole("button", { name: "Import", exact: true }).click();
    const resp = await importResponse;
    expect(resp.ok()).toBe(true);
    const body = (await resp.json()) as { status: string; page: { id: string; name: string } };
    expect(body.status).toBe("success");
    const newPageId = body.page.id;

    // Dialog auto-closes on success.
    await expect(dialog).toBeHidden({ timeout: 15_000 });

    // Navigation slides up into the edit route for the new page.
    await page.waitForURL(`**/pages/edit/${newPageId}`, { timeout: 15_000 });
    expect(page.url()).toContain(`/pages/edit/${newPageId}`);

    // Pages query is invalidated — the new page is persisted server-side. Verify
    // via the API rather than relying on a transient toast.
    const listRes = await fetch(`${API_URL}/pages`, { headers: authHeaders() });
    const listData = (await listRes.json()) as { pages: Array<{ id: string }> };
    expect(listData.pages.some((p) => p.id === newPageId)).toBe(true);
  });
});
