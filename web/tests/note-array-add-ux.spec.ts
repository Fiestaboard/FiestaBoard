/**
 * Note Array Add-Board UX E2E Tests
 *
 * Note Array is a first-class device choice when adding a board (matching how
 * Vestaboard owners set up an "array" in the Vestaboard app), starting as a
 * cloud-mode 2×1 array. Local API mode renders as a "Coming soon" teaser for
 * arrays instead of a selectable mode.
 *
 * Videos are recorded (`test.use({ video: "on" })`) so the flow can be
 * validated visually.
 */
import { configureBoard, expect, openSettingsTab, resetToSingleBoard, suppressWizard, test } from "./helpers";

test.use({ video: "on" });

test.describe("Add Note Array board", () => {
  test.beforeEach(async ({ page }) => {
    await configureBoard();
    await resetToSingleBoard();
    await suppressWizard(page);
  });

  test.afterEach(async () => {
    await resetToSingleBoard();
  });

  test("Note Array is offered as a device type and starts as a cloud 2×1 array", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.getByRole("heading", { name: "Settings", exact: true })).toBeVisible({ timeout: 15_000 });
    await openSettingsTab(page, "Hardware");

    await page.getByRole("button", { name: "Add Board" }).click();
    // All three Vestaboard product shapes are offered.
    await expect(page.getByRole("button", { name: "Flagship", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Note", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Note Array", exact: true }).click();

    // The new board card appears as a 2×1 note array (3 rows × 30 cols).
    const card = page.getByTestId("board-card").filter({ hasText: "My Board 2" });
    await expect(card).toBeVisible({ timeout: 10_000 });
    await expect(card).toContainText("3 × 30");
    await expect(card).toContainText("2 side-by-side");
    await page.waitForTimeout(600);

    // Expand the card: cloud mode is active, Local API is a coming-soon teaser.
    await card.getByText("My Board 2").click();
    const localTeaser = card.getByRole("button", { name: /Local API/ });
    await expect(localTeaser).toContainText("Coming soon");
    await expect(card.getByText("Cloud API Token", { exact: true })).toBeVisible();
    // A tokenless array is not usable yet — the form says which credential it needs.
    await expect(card.getByText("Cloud API token is required")).toBeVisible();

    // Bring the connection section on screen and dwell so the video
    // clearly shows the Coming soon teaser before and after the click.
    await localTeaser.scrollIntoViewIfNeeded();
    await localTeaser.hover();
    await page.waitForTimeout(900);

    // Clicking the teaser hypes the roadmap instead of switching modes.
    await localTeaser.click();
    const hypeNote = card.getByText(/Stay tuned!/);
    await expect(hypeNote).toBeVisible();
    // Center the note in the viewport so the recording frames it fully.
    await hypeNote.evaluate((el) => el.scrollIntoView({ block: "center" }));
    // Still cloud-only: no local host/key fields appeared.
    await expect(card.getByText("Board Host")).not.toBeVisible();

    // Pause so the video captures the teaser before teardown.
    await page.waitForTimeout(1_800);
  });
});
