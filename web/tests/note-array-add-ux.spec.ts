/**
 * Note Array Add-Board UX E2E Tests
 *
 * Note Array is a first-class device choice when adding a board (matching how
 * Vestaboard owners set up an "array" in the Vestaboard app), starting as a
 * cloud-mode 2×1 array. Switching to Local API mode swaps the cloud token
 * field for the per-tile assignment grid (one slot per Note).
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

    const addButton = page.getByRole("button", { name: "Add Board" });
    await addButton.scrollIntoViewIfNeeded();
    await addButton.hover();
    await page.waitForTimeout(600);
    await addButton.click();

    // All three Vestaboard product shapes are offered — Note Array is its own
    // one-click choice, not "add a Note, then convert its type". Hover each so
    // the recording clearly shows the picker.
    const flagshipChoice = page.getByRole("button", { name: "Flagship", exact: true });
    const noteChoice = page.getByRole("button", { name: "Note", exact: true });
    const arrayChoice = page.getByRole("button", { name: "Note Array", exact: true });
    await expect(flagshipChoice).toBeVisible();
    await expect(noteChoice).toBeVisible();
    await expect(arrayChoice).toBeVisible();
    await flagshipChoice.hover();
    await page.waitForTimeout(450);
    await noteChoice.hover();
    await page.waitForTimeout(450);
    await arrayChoice.hover();
    await page.waitForTimeout(700);
    await arrayChoice.click();

    // The new board card appears as a 2×1 note array (3 rows × 30 cols).
    const card = page.getByTestId("board-card").filter({ hasText: "My Board 2" });
    await expect(card).toBeVisible({ timeout: 10_000 });
    await expect(card).toContainText("3 × 30");
    await expect(card).toContainText("2 side-by-side");
    await page.waitForTimeout(600);

    // Expand the card: cloud mode is active with the token field visible.
    await card.getByText("My Board 2").click();
    const localMode = card.getByRole("button", { name: /Local API/ });
    await expect(localMode).toBeVisible();
    await expect(card.getByText("Cloud API Token", { exact: true })).toBeVisible();
    // A tokenless array is not usable yet — the form says which credential it needs.
    await expect(card.getByText("Cloud API token is required")).toBeVisible();

    // Bring the connection section on screen and dwell so the video
    // clearly shows the mode switch.
    await localMode.scrollIntoViewIfNeeded();
    await localMode.hover();
    await page.waitForTimeout(900);

    // Switching to Local API replaces the token field with the tile grid:
    // one slot per Note (2×1 array → slots 1 and 2), none assigned yet.
    await localMode.click();
    const tileGrid = card.getByTestId("tile-grid-assignment");
    await expect(tileGrid).toBeVisible({ timeout: 10_000 });
    await expect(card.getByTestId("tile-slot-0-0")).toBeVisible();
    await expect(card.getByTestId("tile-slot-0-1")).toBeVisible();
    await expect(tileGrid).toContainText("0/2 tiles assigned");
    await expect(card.getByText("Cloud API Token", { exact: true })).not.toBeVisible();
    await tileGrid.evaluate((el) => el.scrollIntoView({ block: "center" }));
    await page.waitForTimeout(900);

    // Clicking a slot opens the assignment dialog with host + key fields.
    await card.getByTestId("tile-slot-0-1").click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await expect(dialog.getByText("Board Host")).toBeVisible();
    await expect(dialog.getByRole("button", { name: /Identify/ })).toBeVisible();
    await page.waitForTimeout(1_200);
    await page.keyboard.press("Escape");

    // Switching back to cloud restores the token field.
    await card.getByRole("button", { name: /Cloud API/ }).click();
    await expect(card.getByText("Cloud API Token", { exact: true })).toBeVisible({ timeout: 10_000 });

    // Pause so the video captures the final state before teardown.
    await page.waitForTimeout(1_200);
  });
});
