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
 *  - Alignment: center/right justify uses 15-column width (not 22)
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
    await page.getByRole("button", { name: "Save Page" }).click();

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

    // Send the page to the board (force target=board to bypass output target settings)
    const sendRes = await fetch(`${API_URL}/pages/${id}/send?target=board`, {
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

    const sendRes = await fetch(`${API_URL}/pages/${id}/send?target=board`, {
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

  test("Note page character encoding fidelity: specific text produces expected codes", async () => {
    await fetch(`${MOCK_BOARD_URL}/mock/reset`, { method: "POST" });

    // "HI" on row 1 should encode to H=8, I=9, then blanks
    const id = await createNotePage(`Encoding ${Date.now()}`, ["HI", "", ""]);

    const sendRes = await fetch(`${API_URL}/pages/${id}/send?target=board`, {
      method: "POST",
    });
    expect(sendRes.ok).toBe(true);
    const sendData = await sendRes.json();
    expect(sendData.sent_to_board).toBe(true);

    const state = await getMockBoardState();
    const history = state.history ?? [];
    // Prefer the Note-sized payload — another send (e.g. active page) may append a Flagship message after ours.
    const noteMsg = [...history].reverse().find(
      (h: { dimensions?: number[]; characters?: number[][] }) =>
        Array.isArray(h.dimensions) && h.dimensions[0] === 3 && h.dimensions[1] === 15,
    );
    expect(noteMsg, "expected a 3×15 (note) message in mock history").toBeDefined();
    if (!noteMsg?.characters) {
      throw new Error("mock history entry missing characters");
    }

    // H=8, I=9, rest are blank (0)
    expect(noteMsg.characters[0][0]).toBe(8);
    expect(noteMsg.characters[0][1]).toBe(9);
    for (let c = 2; c < 15; c++) {
      expect(noteMsg.characters[0][c]).toBe(0);
    }
    // Rows 2+3 are blank
    for (const row of [noteMsg.characters[1], noteMsg.characters[2]]) {
      for (const code of row) {
        expect(code).toBe(0);
      }
    }
  });

  test("special characters encode correctly on board send", async () => {
    await fetch(`${MOCK_BOARD_URL}/mock/reset`, { method: "POST" });

    // "A!@+" exercises letter + punctuation codes
    const id = await createNotePage(`Specials ${Date.now()}`, ["A!@+", "", ""]);

    const sendRes = await fetch(`${API_URL}/pages/${id}/send?target=board`, {
      method: "POST",
    });
    expect(sendRes.ok).toBe(true);
    expect((await sendRes.json()).sent_to_board).toBe(true);

    const state = await getMockBoardState();
    const row0 = state.history[state.history.length - 1].characters[0];
    expect(row0[0]).toBe(1);   // A
    expect(row0[1]).toBe(37);  // !
    expect(row0[2]).toBe(38);  // @
    expect(row0[3]).toBe(46);  // +
  });
});

// ---------------------------------------------------------------------------
// Heart character and code 62
// ---------------------------------------------------------------------------

test.describe("Note pages – Heart / Degree character", () => {
  test("code 62 is delivered to the board for degree symbol on Note page", async () => {
    await fetch(`${MOCK_BOARD_URL}/mock/reset`, { method: "POST" });

    // The backend text_to_board_array maps '°' to code 62
    const id = await createNotePage(`Heart ${Date.now()}`, ["A°B", "", ""]);

    const sendRes = await fetch(`${API_URL}/pages/${id}/send?target=board`, {
      method: "POST",
    });
    expect(sendRes.ok).toBe(true);
    expect((await sendRes.json()).sent_to_board).toBe(true);

    const state = await getMockBoardState();
    const row0 = state.history[state.history.length - 1].characters[0];
    expect(row0[0]).toBe(1);   // A
    expect(row0[1]).toBe(62);  // ° -> code 62 (heart on Note)
    expect(row0[2]).toBe(2);   // B
  });

  test("UI preview renders code 62 as heart on Note device", async ({ page }) => {
    // Create a Note page with degree symbol via API (ensures ° is in the template)
    const id = await createNotePage(`HeartUI ${Date.now()}`, ["A°B", "", ""]);

    // Navigate to the edit page where the builder shows the live preview
    await page.goto(`/pages/edit/${id}`);

    // Wait for the preview char tiles to appear
    const firstTile = page.locator('[data-testid="char-tile-0-0"]');
    await expect(firstTile).toBeVisible({ timeout: 15_000 });

    // Tile at (0,0) = A, tile at (0,1) = heart on Note, tile at (0,2) = B
    await expect(firstTile).toHaveAttribute("data-target-char", "A");
    const heartTile = page.locator('[data-testid="char-tile-0-1"]');
    await expect(heartTile).toHaveAttribute("data-target-char", "♥");
  });
});

// ---------------------------------------------------------------------------
// Note alignment – center & right justify respect 15-column width
// (Regression: https://github.com/Fiestaboard/FiestaBoard/issues/XXX)
// ---------------------------------------------------------------------------

test.describe("Note pages – Alignment", () => {
  test("center alignment via /templates/render uses 15-column width for Note", async () => {
    // Render "HELLO WORLD" (11 chars) centered on a Note board (15 cols).
    // Expected: 2 spaces + HELLO WORLD + 2 spaces = 15 chars per line, 3 lines.
    const res = await fetch(`${API_URL}/templates/render`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        template: ["HELLO WORLD", "", ""],
        line_metadata: [
          { alignment: "center", wrap: false },
          { alignment: "left", wrap: false },
          { alignment: "left", wrap: false },
        ],
        device_type: "note",
      }),
    });
    expect(res.ok).toBe(true);
    const data = await res.json();

    // Should return 3 lines (Note = 3 rows), each exactly 15 chars
    expect(data.line_count).toBe(3);
    for (const line of data.lines) {
      expect(line).toHaveLength(15);
    }

    // First line: "HELLO WORLD" centered in 15 chars
    const line0 = data.lines[0];
    expect(line0.trim()).toBe("HELLO WORLD");
    const leftPad = line0.length - line0.trimStart().length;
    const rightPad = line0.length - line0.trimEnd().length;
    expect(Math.abs(leftPad - rightPad)).toBeLessThanOrEqual(1);
    // Must NOT be 22 chars (the old Flagship-based bug)
    expect(line0).toHaveLength(15);
  });

  test("right alignment via /templates/render uses 15-column width for Note", async () => {
    // Render "TEST" (4 chars) right-aligned on a Note board (15 cols).
    // Expected: 11 spaces + TEST = 15 chars
    const res = await fetch(`${API_URL}/templates/render`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        template: ["TEST", "", ""],
        line_metadata: [
          { alignment: "right", wrap: false },
          { alignment: "left", wrap: false },
          { alignment: "left", wrap: false },
        ],
        device_type: "note",
      }),
    });
    expect(res.ok).toBe(true);
    const data = await res.json();

    expect(data.line_count).toBe(3);
    const line0 = data.lines[0];
    expect(line0).toHaveLength(15);
    expect(line0.endsWith("TEST")).toBe(true);
    expect(line0.trimStart()).toBe("TEST");
  });

  test("Flagship center alignment still uses 22-column width", async () => {
    // Guard: ensure the fix didn't break Flagship alignment
    const res = await fetch(`${API_URL}/templates/render`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        template: ["HELLO WORLD", "", "", "", "", ""],
        line_metadata: [
          { alignment: "center", wrap: false },
          { alignment: "left", wrap: false },
          { alignment: "left", wrap: false },
          { alignment: "left", wrap: false },
          { alignment: "left", wrap: false },
          { alignment: "left", wrap: false },
        ],
        device_type: "flagship",
      }),
    });
    expect(res.ok).toBe(true);
    const data = await res.json();

    expect(data.line_count).toBe(6);
    const line0 = data.lines[0];
    expect(line0).toHaveLength(22);
    expect(line0.trim()).toBe("HELLO WORLD");
  });

  test("sending a center-aligned Note page delivers correctly centered 3×15 array", async () => {
    await fetch(`${MOCK_BOARD_URL}/mock/reset`, { method: "POST" });

    // Create a Note page with "HI" centered (line_metadata)
    // "HI" = 2 chars, centered in 15 → 6 blanks + H I + 7 blanks (or 7+6)
    const createRes = await fetch(`${API_URL}/pages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: `Centered Note ${Date.now()}`,
        type: "template",
        device_type: "note",
        template: ["HI", "", ""],
        line_metadata: [
          { alignment: "center", wrap: false },
          { alignment: "left", wrap: false },
          { alignment: "left", wrap: false },
        ],
      }),
    });
    expect(createRes.ok).toBe(true);
    const { page: created } = await createRes.json();

    // Send it to the mock board
    const sendRes = await fetch(
      `${API_URL}/pages/${created.id}/send?target=board`,
      { method: "POST" },
    );
    expect(sendRes.ok).toBe(true);
    expect((await sendRes.json()).sent_to_board).toBe(true);

    // Verify mock board got a 3×15 array with H and I centered
    const state = await getMockBoardState();
    const history = (state.history ?? []) as Array<{
      dimensions?: number[];
      characters?: number[][];
    }>;
    const noteMsg = [...history]
      .reverse()
      .find(
        (h) =>
          Array.isArray(h.dimensions) &&
          h.dimensions[0] === 3 &&
          h.dimensions[1] === 15,
      );
    expect(noteMsg, "expected a 3×15 (note) message in mock history").toBeDefined();

    const row0 = noteMsg!.characters![0];
    expect(row0).toHaveLength(15);

    // H=8, I=9. They should be near the center (columns 6-7 for 6-left-pad).
    // Find position of H
    const hIdx = row0.indexOf(8);
    const iIdx = row0.indexOf(9);
    expect(hIdx).toBeGreaterThanOrEqual(0);
    expect(iIdx).toBe(hIdx + 1);

    // Verify centering: left pad ≈ right pad (within 1)
    const leftBlanks = hIdx; // blanks before H
    const rightBlanks = 15 - iIdx - 1; // blanks after I
    expect(Math.abs(leftBlanks - rightBlanks)).toBeLessThanOrEqual(1);

    // Must NOT be centered for 22 cols (would put H at col ~10)
    expect(hIdx).toBeLessThan(10);
  });

  test("sending a right-aligned Note page delivers correctly right-justified 3×15 array", async () => {
    await fetch(`${MOCK_BOARD_URL}/mock/reset`, { method: "POST" });

    const createRes = await fetch(`${API_URL}/pages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: `Right Note ${Date.now()}`,
        type: "template",
        device_type: "note",
        template: ["AB", "", ""],
        line_metadata: [
          { alignment: "right", wrap: false },
          { alignment: "left", wrap: false },
          { alignment: "left", wrap: false },
        ],
      }),
    });
    expect(createRes.ok).toBe(true);
    const { page: created } = await createRes.json();

    const sendRes = await fetch(
      `${API_URL}/pages/${created.id}/send?target=board`,
      { method: "POST" },
    );
    expect(sendRes.ok).toBe(true);
    expect((await sendRes.json()).sent_to_board).toBe(true);

    const state = await getMockBoardState();
    const history = (state.history ?? []) as Array<{
      dimensions?: number[];
      characters?: number[][];
    }>;
    const noteMsg = [...history]
      .reverse()
      .find(
        (h) =>
          Array.isArray(h.dimensions) &&
          h.dimensions[0] === 3 &&
          h.dimensions[1] === 15,
      );
    expect(noteMsg, "expected a 3×15 (note) message").toBeDefined();

    const row0 = noteMsg!.characters![0];
    expect(row0).toHaveLength(15);

    // A=1, B=2, right-aligned means they should be in cols 13 and 14
    expect(row0[13]).toBe(1); // A
    expect(row0[14]).toBe(2); // B
    // Everything before should be blank (0)
    for (let c = 0; c < 13; c++) {
      expect(row0[c]).toBe(0);
    }
  });

  test("UI preview shows centered text correctly on Note board", async ({ page }) => {
    // Create a Note page with "HI" centered via API
    const id = await createNotePage(`UI Center ${Date.now()}`, ["HI", "", ""]);

    // Update it to have center alignment metadata
    await fetch(`${API_URL}/pages/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        line_metadata: [
          { alignment: "center", wrap: false },
          { alignment: "left", wrap: false },
          { alignment: "left", wrap: false },
        ],
      }),
    });

    // Navigate to edit page where preview is shown
    await page.goto(`/pages/edit/${id}`);
    const firstTile = page.locator('[data-testid="char-tile-0-0"]');
    await expect(firstTile).toBeVisible({ timeout: 15_000 });

    // Note board: 15 columns (0..14). "HI" centered → cols 6,7 have H,I.
    // Wait for the preview to render the centered content (H should appear in row 0)
    const hTileLocator = page.locator('[data-testid^="char-tile-0-"][data-target-char="H"]');
    await expect(hTileLocator).toBeVisible({ timeout: 10_000 });

    // Grid should be 3×15 (no flagship row 3 or col 15)
    await expect(page.locator('[data-testid="char-tile-2-14"]')).toBeVisible();
    await expect(page.locator('[data-testid="char-tile-3-0"]')).toHaveCount(0);
    await expect(page.locator('[data-testid="char-tile-0-15"]')).toHaveCount(0);

    // Verify H and I are present somewhere in row 0 and are roughly centered
    // (the exact column depends on padding rounding, but they must be within the 15-col grid)
    let foundH = false;
    let hCol = -1;
    for (let col = 0; col < 15; col++) {
      const tile = page.locator(`[data-testid="char-tile-0-${col}"]`);
      const char = await tile.getAttribute("data-target-char");
      if (char === "H") {
        foundH = true;
        hCol = col;
      }
    }
    expect(foundH).toBe(true);
    // H should be near center (col 6 or 7), not at col 0 (left) or col 10+ (22-col centering)
    expect(hCol).toBeGreaterThanOrEqual(4);
    expect(hCol).toBeLessThanOrEqual(8);
  });
});
