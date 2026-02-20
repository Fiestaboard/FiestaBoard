/**
 * Vestaboard Note (3×15) page integration tests.
 *
 * Covers:
 *  - API-level CRUD specific to Note pages
 *  - UI: creating a Note page through the builder
 *  - UI: editor shows 3 lines (not 6)
 *  - UI: editing an existing Note page
 *  - UI: preview renders 3×15 grid
 *  - UI: pages list tabs filter by device type
 */
import {
  test,
  expect,
  configureBoard,
  createNotePage,
  createPage,
  deleteAllPages,
  getMockBoardState,
  API_URL,
  MOCK_BOARD_URL,
} from "./helpers";

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

test.beforeEach(async ({ page }) => {
  await configureBoard();
  // Enable both flagship + note devices
  await fetch(`${API_URL}/settings/board`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ devices: ["flagship", "note"] }),
  });
  await page.addInitScript(() => {
    localStorage.setItem("fiestaboard_wizard_complete", "true");
  });
});

test.afterEach(async () => {
  await deleteAllPages();
  // Reset to flagship only
  await fetch(`${API_URL}/settings/board`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ devices: ["flagship"] }),
  });
});

// ---------------------------------------------------------------------------
// API-level Note page tests
// ---------------------------------------------------------------------------

test.describe("Note pages – API", () => {
  test("create Note page returns device_type=note and 3-line template", async () => {
    const name = `API Note ${Date.now()}`;
    const res = await fetch(`${API_URL}/pages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name,
        type: "template",
        device_type: "note",
        template: ["LINE ONE", "LINE TWO", ""],
      }),
    });
    expect(res.ok).toBe(true);
    const { page: created } = await res.json();
    expect(created.device_type).toBe("note");
    expect(created.template).toHaveLength(3);
    expect(created.template[0]).toBe("LINE ONE");
  });

  test("GET single Note page preserves device_type and template length", async () => {
    const id = await createNotePage(`GET Note ${Date.now()}`, [
      "GET TEST",
      "",
      "",
    ]);
    const res = await fetch(`${API_URL}/pages/${id}`);
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data.device_type).toBe("note");
    expect(data.template).toHaveLength(3);
  });

  test("update Note page retains 3-line template", async () => {
    const id = await createNotePage(`Update Note ${Date.now()}`);
    const res = await fetch(`${API_URL}/pages/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        template: ["UPDATED", "LINE", "THREE"],
      }),
    });
    expect(res.ok).toBe(true);
    const getRes = await fetch(`${API_URL}/pages/${id}`);
    const data = await getRes.json();
    expect(data.template).toEqual(["UPDATED", "LINE", "THREE"]);
    expect(data.device_type).toBe("note");
  });

  test("delete Note page succeeds", async () => {
    const id = await createNotePage(`Delete Note ${Date.now()}`);
    const res = await fetch(`${API_URL}/pages/${id}`, { method: "DELETE" });
    expect(res.ok).toBe(true);
    const getRes = await fetch(`${API_URL}/pages/${id}`);
    expect(getRes.status).toBe(404);
  });
});

// ---------------------------------------------------------------------------
// UI-level Note page tests
// ---------------------------------------------------------------------------

test.describe("Note pages – UI", () => {
  test("create Note page through builder", async ({ page }) => {
    const pageName = `UI Note ${Date.now()}`;

    await page.goto("/pages/new?device=note");
    await expect(page.getByText("Create Page")).toBeVisible({ timeout: 15_000 });

    // Fill name
    await page.getByPlaceholder("My Custom Page").fill(pageName);

    // Type in the editor
    const editor = page.locator('[contenteditable="true"]').first();
    await editor.click();
    await editor.pressSequentially("HELLO NOTE");

    // Save
    await page.locator('[title="Save Page"]').click();

    // After save, verify via API
    await page.waitForTimeout(2_000);
    const listRes = await fetch(`${API_URL}/pages`);
    const listData = await listRes.json();
    const created = listData.pages.find(
      (p: { name: string }) => p.name === pageName,
    );
    expect(created).toBeDefined();
    expect(created.device_type).toBe("note");
    expect(created.template).toHaveLength(3);
  });

  test("Note editor shows 3-line area (not 6)", async ({ page }) => {
    await page.goto("/pages/new?device=note");
    await expect(page.getByText("Create Page")).toBeVisible({ timeout: 15_000 });

    const editor = page.locator('[contenteditable="true"]').first();
    await expect(editor).toBeVisible();

    // Count hard breaks in the editor – a 3-line document has 2 <br> elements
    const brCount = await editor.locator("br").count();
    expect(brCount).toBe(2);
  });

  test("edit existing Note page", async ({ page }) => {
    const name = `Edit Note ${Date.now()}`;
    const id = await createNotePage(name, ["ORIGINAL", "", ""]);

    await page.goto(`/pages/edit/${id}`);
    await expect(page.getByText("Edit Page")).toBeVisible({ timeout: 15_000 });

    // Verify editor loaded with Note content
    const editor = page.locator('[contenteditable="true"]').first();
    await expect(editor).toBeVisible();

    // The editor should contain 2 hard breaks (3 lines)
    const brCount = await editor.locator("br").count();
    expect(brCount).toBe(2);
  });

  test("Note page preview renders 3×15 grid", async ({ page }) => {
    await page.goto("/pages/new?device=note");
    await expect(page.getByText("Create Page")).toBeVisible({ timeout: 15_000 });

    // Type some text so preview renders
    const editor = page.locator('[contenteditable="true"]').first();
    await editor.click();
    await editor.pressSequentially("ABC");

    // Wait for debounced preview
    await page.waitForTimeout(1_000);

    // Note grid: rows 0-2, cols 0-14
    // First tile should exist
    await expect(page.locator('[data-testid="char-tile-0-0"]')).toBeVisible({
      timeout: 10_000,
    });
    // Last Note tile should exist
    await expect(page.locator('[data-testid="char-tile-2-14"]')).toBeVisible();
    // Flagship-only row should NOT exist
    await expect(page.locator('[data-testid="char-tile-3-0"]')).toHaveCount(0);
    // Flagship-only column should NOT exist
    await expect(page.locator('[data-testid="char-tile-0-15"]')).toHaveCount(0);
  });

  test("pages list tabs filter by device type", async ({ page }) => {
    const flagshipName = `Flagship ${Date.now()}`;
    const noteName = `Note ${Date.now()}`;

    await createPage(flagshipName);
    await createNotePage(noteName);

    await page.goto("/pages");
    await expect(
      page.getByRole("heading", { name: "Pages", exact: true }),
    ).toBeVisible({ timeout: 15_000 });

    // Both tabs should be visible since we configured flagship + note
    const flagshipTab = page.getByRole("tab", { name: "Flagship" });
    const noteTab = page.getByRole("tab", { name: "Note" });
    await expect(flagshipTab).toBeVisible({ timeout: 5_000 });
    await expect(noteTab).toBeVisible();

    // Flagship tab should show the flagship page
    await flagshipTab.click();
    await expect(page.getByText(flagshipName).first()).toBeVisible({
      timeout: 5_000,
    });

    // Note tab should show the note page
    await noteTab.click();
    await expect(page.getByText(noteName).first()).toBeVisible({
      timeout: 5_000,
    });
  });
});

// ---------------------------------------------------------------------------
// Send to board — "money path" (end-to-end board array verification)
// ---------------------------------------------------------------------------

test.describe("Note pages – Send to Board", () => {
  test("sending a Note page delivers a 3x15 character array to the board", async () => {
    // Reset mock board
    await fetch(`${MOCK_BOARD_URL}/mock/reset`, { method: "POST" });

    const id = await createNotePage(`Send Note ${Date.now()}`, [
      "HELLO",
      "",
      "",
    ]);

    // Send the page to the board
    const sendRes = await fetch(`${API_URL}/pages/${id}/send`, {
      method: "POST",
    });
    expect(sendRes.ok).toBe(true);
    const sendData = await sendRes.json();
    expect(sendData.sent_to_board).toBe(true);

    // Check mock board received a 3x15 array
    const state = await getMockBoardState();
    expect(state.message_count).toBeGreaterThanOrEqual(1);

    const lastMessage = state.history[state.history.length - 1];
    expect(lastMessage.dimensions).toEqual([3, 15]);
    expect(lastMessage.characters).toHaveLength(3);
    for (const row of lastMessage.characters) {
      expect(row).toHaveLength(15);
    }
  });

  test("sending a Flagship page delivers a 6x22 character array to the board", async () => {
    // Reset mock board
    await fetch(`${MOCK_BOARD_URL}/mock/reset`, { method: "POST" });

    const id = await createPage(`Send Flagship ${Date.now()}`, [
      "FLAGSHIP TEST",
      "",
      "",
      "",
      "",
      "",
    ]);

    const sendRes = await fetch(`${API_URL}/pages/${id}/send`, {
      method: "POST",
    });
    expect(sendRes.ok).toBe(true);
    const sendData = await sendRes.json();
    expect(sendData.sent_to_board).toBe(true);

    const state = await getMockBoardState();
    expect(state.message_count).toBeGreaterThanOrEqual(1);

    const lastMessage = state.history[state.history.length - 1];
    expect(lastMessage.dimensions).toEqual([6, 22]);
    expect(lastMessage.characters).toHaveLength(6);
    for (const row of lastMessage.characters) {
      expect(row).toHaveLength(22);
    }
  });
});
