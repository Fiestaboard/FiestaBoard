/**
 * Character code 62 — per-board glyph (issue #1657).
 *
 * Code 62 is ONE code on the wire that lands on different physical flaps:
 * a degree sign on Flagships made before 2026, a heart on newer ones, and
 * always a heart on Note hardware. Nothing FiestaBoard can query tells a
 * degree board from a heart board, so `BoardInstance.code62_glyph` lets the
 * owner say, and every preview surface renders what is actually on the wall.
 *
 * The setting is display-only. The last test in this file is the invariant
 * that matters most: flipping it must never change what is sent to a board.
 */
import {
  API_URL,
  authHeaders,
  BOARD_HOST,
  clearBoardConfig,
  configureBoard,
  createPage,
  deleteAllPages,
  ensureAuthForFetch,
  expect,
  getMockBoardState,
  lastMockMessage,
  openSettingsTab,
  resetMockBoard,
  resetToSingleBoard,
  setActivePage,
  suppressWizard,
  test,
  waitForFirstRun,
} from "./helpers";

/** Character code 62 — the one code both flaps carry. */
const CODE_62 = 62;
/** Column of the code-62 character in the "72°F" template used below. */
const GLYPH_COL = 2;
const DEGREE = "°";
const HEART = "♥";

const BOARD_HOST_FOR_TESTS = process.env.MOCK_BOARD_HOST || "localhost";

/**
 * Replace the board list with a single board of the given shape and flap.
 * Pass `glyph: undefined` to omit the key entirely — that is what a board
 * stored before the setting existed looks like.
 */
async function setSingleBoard(deviceType: "flagship" | "note", glyph?: "degree" | "heart") {
  await ensureAuthForFetch();
  const res = await fetch(`${API_URL}/settings/board`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({
      boards: [
        {
          name: "My Board",
          device_type: deviceType,
          board_color: "black",
          ...(glyph ? { code62_glyph: glyph } : {}),
          enabled: true,
          api_mode: "local",
          host: BOARD_HOST_FOR_TESTS,
          local_api_key: "test-key",
        },
      ],
    }),
  });
  if (!res.ok) throw new Error(`setSingleBoard failed: ${res.status} ${await res.text()}`);
}

/** The stored code-62 flap of the first board, straight from the API. */
async function storedGlyph(): Promise<string | undefined> {
  const res = await fetch(`${API_URL}/settings/board`, { headers: authHeaders() });
  const data = await res.json();
  return data.boards?.[0]?.code62_glyph;
}

/** Push a page to the board without going through the UI. */
async function sendPage(id: string) {
  const res = await fetch(`${API_URL}/pages/${id}/send`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: "{}",
  });
  if (!res.ok) throw new Error(`sendPage failed: ${res.status}`);
}

/** The single split-flap tile at row 0, column `col`, on whatever board is on screen. */
function tile(page: import("@playwright/test").Page, col: number) {
  return page.locator(`[data-testid="char-tile-0-${col}"]`).first();
}

/** Expand the (collapsed) board card on Settings → Hardware. */
async function openBoardCard(page: import("@playwright/test").Page) {
  await page.goto("/settings");
  await openSettingsTab(page, "Hardware");
  const card = page.locator("[data-testid=board-card]").first();
  await expect(card).toBeVisible({ timeout: 15_000 });
  await card.getByRole("button").first().click();
  return card;
}

test.describe("Character code 62 — per-board glyph", () => {
  let pageId: string;

  test.beforeAll(async () => {
    await configureBoard();
    await deleteAllPages();
    // Column 0,1 = "7","2"; column 2 = code 62; column 3 = "F".
    pageId = await createPage("code62 probe", ["72°F", "", "", "", "", ""]);
    await setActivePage(pageId);
  });

  test.afterAll(async () => {
    await setActivePage(null);
    await deleteAllPages();
    await resetToSingleBoard();
  });

  test.beforeEach(async ({ page }) => {
    await suppressWizard(page);
  });

  test("editor preview draws a degree sign when the board's flap is set to degree", async ({ page }) => {
    await setSingleBoard("flagship", "degree");
    await page.goto(`/pages/edit/${pageId}`);
    await expect(tile(page, GLYPH_COL)).toHaveAttribute("data-target-char", DEGREE, { timeout: 20_000 });
  });

  test("editor preview draws a heart when the board's flap is set to heart", async ({ page }) => {
    await setSingleBoard("flagship", "heart");
    await page.goto(`/pages/edit/${pageId}`);
    await expect(tile(page, GLYPH_COL)).toHaveAttribute("data-target-char", HEART, { timeout: 20_000 });
  });

  test("a board stored without the setting draws the degree sign it always drew", async ({ page }) => {
    await setSingleBoard("flagship", undefined);
    expect(await storedGlyph()).toBe("degree");
    await page.goto(`/pages/edit/${pageId}`);
    await expect(tile(page, GLYPH_COL)).toHaveAttribute("data-target-char", DEGREE, { timeout: 20_000 });
  });

  test("the accessible name announces the same glyph the tiles draw", async ({ page }) => {
    // The reporter's specific concern: a board that draws a heart while
    // announcing "degree" is a text alternative for a different image.
    for (const [glyph, drawn] of [
      ["heart", HEART],
      ["degree", DEGREE],
    ] as const) {
      await setSingleBoard("flagship", glyph);
      await sendPage(pageId);
      await page.goto("/");
      await expect(tile(page, GLYPH_COL)).toHaveAttribute("data-target-char", drawn, { timeout: 20_000 });
      await expect(page.getByRole("img", { name: `Board display: 72${drawn}F` })).toBeVisible();
    }
  });

  test("toggling the flap in Settings changes the glyph the board preview draws", async ({ page }) => {
    await setSingleBoard("flagship", "degree");
    const card = await openBoardCard(page);

    const heartSwatch = card.locator("[data-testid=board-code62-heart]");
    await expect(heartSwatch).toHaveAttribute("aria-pressed", "false");
    await heartSwatch.click();
    await expect(heartSwatch).toHaveAttribute("aria-pressed", "true");

    await page.goto(`/pages/edit/${pageId}`);
    await expect(tile(page, GLYPH_COL)).toHaveAttribute("data-target-char", HEART, { timeout: 20_000 });
  });

  test("the flap chosen in Settings survives a reload", async ({ page }) => {
    await setSingleBoard("flagship", "degree");
    const card = await openBoardCard(page);
    await card.locator("[data-testid=board-code62-heart]").click();
    await expect(card.locator("[data-testid=board-code62-heart]")).toHaveAttribute("aria-pressed", "true");
    // The API is the source of truth the reload reads back from.
    await expect.poll(storedGlyph, { timeout: 10_000 }).toBe("heart");

    const reloaded = await openBoardCard(page);
    await expect(reloaded.locator("[data-testid=board-code62-heart]")).toHaveAttribute("aria-pressed", "true");
    await expect(reloaded.locator("[data-testid=board-code62-degree]")).toHaveAttribute("aria-pressed", "false");
  });

  test("a Note board is offered no code-62 choice", async ({ page }) => {
    // Note flaps only ever carried the heart, so the question is not its
    // owner's to answer and the control must not imply otherwise.
    await setSingleBoard("note");
    const card = await openBoardCard(page);
    await expect(card.locator("[data-testid=board-code62-heart]")).toHaveCount(0);
    await expect(card.locator("[data-testid=board-code62-degree]")).toHaveCount(0);
  });

  test("a Note board draws the heart even with a degree preference stored", async ({ page }) => {
    await setSingleBoard("note", "degree");
    expect(await storedGlyph()).toBe("degree");
    const noteId = await createPage("code62 note probe", ["72°F", "", ""], "note");
    try {
      await page.goto(`/pages/edit/${noteId}`);
      await expect(tile(page, GLYPH_COL)).toHaveAttribute("data-target-char", HEART, { timeout: 20_000 });
    } finally {
      await fetch(`${API_URL}/pages/${noteId}`, { method: "DELETE", headers: authHeaders() });
    }
  });

  test("changing the flap does not change what is sent to the board", async ({ page: _page }) => {
    // The whole feature is display-only: both glyphs are character code 62 on
    // the wire. If this ever fails, the preference has leaked into the
    // hardware path and boards are being sent different bytes.
    const filler = await createPage("code62 filler", ["ZZZZ", "", "", "", "", ""]);
    const sentRows: number[][] = [];
    try {
      for (const glyph of ["heart", "degree"] as const) {
        await setSingleBoard("flagship", glyph);
        // A send whose content matches what the board already shows is
        // skipped by the content cache; the filler guarantees a real send.
        await sendPage(filler);
        await resetMockBoard();
        await sendPage(pageId);
        await expect
          .poll(async () => (await getMockBoardState()).history?.length ?? 0, { timeout: 20_000 })
          .toBeGreaterThan(0);
        sentRows.push(lastMockMessage(await getMockBoardState()).characters[0]);
      }
    } finally {
      await fetch(`${API_URL}/pages/${filler}`, { method: "DELETE", headers: authHeaders() });
    }

    expect(sentRows[0][GLYPH_COL]).toBe(CODE_62);
    expect(sentRows[1][GLYPH_COL]).toBe(CODE_62);
    expect(sentRows[0]).toEqual(sentRows[1]);
  });
});

/**
 * The setup wizard is where most owners will answer this question — it is the
 * first thing a new install asks — so the swatch there has to reach the stored
 * board, not just the local form state.
 */
test.describe("Character code 62 — setup wizard", () => {
  test.beforeEach(async () => {
    await clearBoardConfig();
    await waitForFirstRun();
  });

  test.afterEach(async () => {
    await configureBoard();
    await resetToSingleBoard();
  });

  test("the flap chosen in the wizard is saved with the board", async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.removeItem("fiestaboard_wizard_complete");
    });
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Connect Your Board" })).toBeVisible({ timeout: 30_000 });

    await page.getByText("Local API").click();
    await page.getByLabel("Board IP Address").fill(BOARD_HOST);
    await page.getByLabel("Local API Key").fill("test-key");

    // Flagship is the default and the only shape this question applies to.
    const heartSwatch = page.locator("[data-testid=wizard-code62-heart]");
    await heartSwatch.scrollIntoViewIfNeeded();
    await expect(heartSwatch).toHaveAttribute("aria-pressed", "false");
    await heartSwatch.click();
    await expect(heartSwatch).toHaveAttribute("aria-pressed", "true");

    const testConnBtn = page.getByRole("button", { name: "Test Connection" });
    await testConnBtn.scrollIntoViewIfNeeded();
    await testConnBtn.click();
    await expect(page.getByText("Connected!")).toBeVisible({ timeout: 15_000 });

    const res = await fetch(`${API_URL}/settings/board`, { headers: authHeaders() });
    const data = await res.json();
    expect(data.boards[0].code62_glyph).toBe("heart");
  });

  test("the wizard offers no code-62 choice once Note is selected", async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.removeItem("fiestaboard_wizard_complete");
    });
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Connect Your Board" })).toBeVisible({ timeout: 30_000 });

    await expect(page.locator("[data-testid=wizard-code62-heart]")).toHaveCount(1);
    await page.getByRole("button", { name: "Note 3 × 15 characters" }).click();
    await expect(page.locator("[data-testid=wizard-code62-heart]")).toHaveCount(0);
    await expect(page.locator("[data-testid=wizard-code62-degree]")).toHaveCount(0);
  });
});
