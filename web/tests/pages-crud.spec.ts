/**
 * FiestaBoard Pages CRUD Integration Tests
 *
 * Tests page management through the UI:
 *   - Verify a created page appears in the page list
 *   - Delete a page
 *
 * NOTE: Tests run sequentially. The wizard must have completed and
 * pages must be accessible.
 */
import { test, expect } from "./helpers";

// Suppress the setup wizard for all tests in this file
test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("fiestaboard_wizard_complete", "true");
  });
});

// ---------------------------------------------------------------------------
// Pages list & delete
// ---------------------------------------------------------------------------

test.describe("Pages CRUD", () => {
  test("newly created page appears in the page list", async ({ page }) => {
    const pageName = `E2E Page ${Date.now()}`;

    // Create a page via API so we can verify it shows in the UI
    const createRes = await fetch("http://localhost:8000/pages", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: pageName,
        type: "template",
        template: ["E2E TEST PAGE", "", "", "", "", ""],
      }),
    });
    expect(createRes.ok).toBe(true);

    // Navigate to pages
    await page.goto("/pages");
    await expect(
      page.getByRole("heading", { name: "Pages", exact: true })
    ).toBeVisible({ timeout: 15_000 });

    // Verify the page name appears
    await expect(page.getByText(pageName).first()).toBeVisible({
      timeout: 10_000,
    });
  });

  test("can delete a page", async ({ page }) => {
    const pageName = `Delete Me ${Date.now()}`;

    // Create a page via API
    const createRes = await fetch("http://localhost:8000/pages", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: pageName,
        type: "template",
        template: ["DELETE TEST", "", "", "", "", ""],
      }),
    });
    expect(createRes.ok).toBe(true);
    const created = await createRes.json();
    const pageId = created.page.id;

    // Navigate to pages
    await page.goto("/pages");
    await expect(
      page.getByRole("heading", { name: "Pages", exact: true })
    ).toBeVisible({ timeout: 15_000 });

    // Verify page exists
    await expect(page.getByText(pageName).first()).toBeVisible({
      timeout: 10_000,
    });

    // Delete via API (UI delete usually requires confirmation dialog
    // interaction which varies; API delete is deterministic)
    const deleteRes = await fetch(`http://localhost:8000/pages/${pageId}`, {
      method: "DELETE",
    });
    expect(deleteRes.ok).toBe(true);

    // Reload and verify page is gone
    await page.reload();
    await expect(
      page.getByRole("heading", { name: "Pages", exact: true })
    ).toBeVisible({ timeout: 15_000 });

    // The deleted page name should no longer appear
    await expect(page.getByText(pageName)).toHaveCount(0, {
      timeout: 10_000,
    });
  });
});
