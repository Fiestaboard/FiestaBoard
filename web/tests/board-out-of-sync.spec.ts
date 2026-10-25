/**
 * Another app wrote to the board (issue #1945), end to end.
 *
 * The other app is the test runner writing straight to the mock Vestaboard's
 * Local API, exactly as the Vestaboard app or a script would. FiestaBoard
 * notices on its next board read (primed here with ?force=true so the test
 * does not wait for the 30 s poll), and Home shows the out-of-sync banner.
 *
 * "Restore automatically" (#2354) is on by default: once the poll confirms
 * the write, the engine paints the page back by itself. Every test here that
 * drives the live out-of-sync face or the manual Restore turns it off for the
 * board in beforeEach, so the board stays overwritten while the test acts;
 * the auto-restore tests turn it back on.
 *
 *   1. Save as page keeps what the other app wrote, then becomes "Saved as".
 *   2. Restore puts this board's page back (POST /v1/boards/primary/restore).
 *   3. Restore while paused tells the truth: nothing was sent.
 *   4. During silence the notice stays hidden.
 *   5. The frame survives FiestaBoard's repaint (the "kept" notice).
 *   6. Auto-restore on: FiestaBoard puts the page back by itself, kept notice.
 *   7. The "Restore automatically" switch persists.
 *   8. The kept notice, driven by a route mock.
 *   9. Phone layout.
 *  10. a11y of both faces.
 */
import type { Page } from "@playwright/test";
import { getViolations, injectAxe } from "axe-playwright";

import {
  API_URL,
  authHeaders,
  configureBoard,
  createPage,
  deleteAllPages,
  expect,
  getAutoRestore,
  getMockBoardState,
  gridToText,
  MOCK_BOARD_URL,
  mockBoardGrid,
  openDisplay,
  resetMockBoard,
  setActivePage,
  setAutoRestore,
  setScheduleEnabled,
  suppressWizard,
  test,
} from "./helpers";

const ROWS = 6;
const COLS = 22;

/** "HI" and a red tile on row 0: what the other app writes. */
function hiRed(): number[][] {
  const grid = Array.from({ length: ROWS }, () => Array(COLS).fill(0));
  grid[0][0] = 8;
  grid[0][1] = 9;
  grid[0][2] = 63;
  return grid;
}

/** Another app writes *characters* to the mock board, bypassing FiestaBoard. */
async function writeFromAnotherApp(characters: number[][] = hiRed(), boardUrl = MOCK_BOARD_URL) {
  const res = await fetch(`${boardUrl}/local-api/message`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Vestaboard-Local-Api-Key": "test-key" },
    body: JSON.stringify({ characters }),
  });
  if (!res.ok) throw new Error(`external write failed: ${res.status}`);
}

/** Have FiestaBoard read the board now instead of at its next 30 s poll. */
async function primeBoardRead(boardId?: string) {
  const query = boardId ? `?board_id=${boardId}&force=true` : "?force=true";
  await fetch(`${API_URL}/board/current-message${query}`, { headers: authHeaders() });
}

async function primaryBoardId(): Promise<string> {
  const res = await fetch(`${API_URL}/settings/board`, { headers: authHeaders() });
  const data = await res.json();
  return data.boards[0].id;
}

async function setPaused(boardId: string, paused: boolean) {
  const res = await fetch(`${API_URL}/v1/boards/${boardId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ paused }),
  });
  if (!res.ok) throw new Error(`pause failed: ${res.status} ${await res.text()}`);
}

function utcHhmm(offsetMinutes: number): string {
  const d = new Date(Date.now() + offsetMinutes * 60_000);
  return `${String(d.getUTCHours()).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")}+00:00`;
}

async function setSilence(enabled: boolean) {
  const res = await fetch(`${API_URL}/settings/silence-schedule`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ enabled, start_time: utcHhmm(-60), end_time: utcHhmm(60), mode: "freeze" }),
  });
  if (!res.ok) throw new Error(`silence failed: ${res.status} ${await res.text()}`);
}

async function setLocalReadInterval(seconds: number) {
  const res = await fetch(`${API_URL}/settings/polling`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ board_read_interval_local: seconds }),
  });
  if (!res.ok) throw new Error(`polling failed: ${res.status} ${await res.text()}`);
}

async function listPages(): Promise<Array<{ id: string; name: string; template?: string[] }>> {
  const res = await fetch(`${API_URL}/v1/pages`, { headers: authHeaders() });
  const data = await res.json();
  return data.pages ?? [];
}

/**
 * Letters only, different every call: the driver dedupes a frame it already
 * sent, so a page identical to an earlier test's would never reach the
 * freshly reset mock board.
 */
function uniqueWord(): string {
  return Array.from({ length: 6 }, () => String.fromCharCode(65 + Math.floor(Math.random() * 26))).join("");
}

/** FiestaBoard shows a "HELLO …" page; the board shows it. */
async function showHelloPage(): Promise<string> {
  const text = `HELLO ${uniqueWord()}`;
  const pageId = await createPage(`Hello ${Date.now()}`, [text, "", "", "", "", ""]);
  await setActivePage(pageId);
  await expect
    .poll(async () => gridToText(mockBoardGrid(await getMockBoardState()))[0], { timeout: 15_000 })
    .toContain(text);
  return pageId;
}

const banner = (page: Page) => page.getByTestId("board-out-of-sync");

test.beforeEach(async ({ page }) => {
  await configureBoard();
  // Keep what another app writes on the board until the test acts on it
  // (see the header). After configureBoard, which rewrites board settings.
  await setAutoRestore("primary", false);
  // Manual mode: only the active page is ever painted, so nothing but the
  // test's own sends can paint over what "another app" wrote.
  await setScheduleEnabled(false);
  // A spec earlier on this backend may have stopped the display loop, which
  // also stops the board-state poll these tests depend on.
  await fetch(`${API_URL}/start`, { method: "POST", headers: authHeaders() });
  await deleteAllPages();
  await suppressWizard(page);
});

test.afterEach(async () => {
  await setAutoRestore("primary", true);
  await deleteAllPages();
  await resetMockBoard();
});

test.describe("Board changed by another app", () => {
  test("another app wrote the board → Save as page keeps it", async ({ page }) => {
    await showHelloPage();
    await writeFromAnotherApp();
    await primeBoardRead();

    await page.goto("/");
    const alert = page.locator('[data-testid="board-out-of-sync"][data-face="out-of-sync"]');
    await expect(alert).toBeVisible({ timeout: 15_000 });
    await expect(alert).toContainText("Another app changed this board");

    const created = page.waitForResponse((r) => r.url().includes("/api/v1/pages") && r.request().method() === "POST");
    await alert.getByRole("button", { name: "Save as page" }).click();
    expect((await created).status()).toBe(201);

    await expect(alert).toContainText("Saved as “From board");
    await expect(alert.getByRole("button", { name: "Save as page" })).toHaveCount(0);

    const saved = (await listPages()).find((p) => p.name.startsWith("From board"));
    expect(saved, "the saved page exists").toBeTruthy();
    expect(saved!.template?.[0]).toBe("HI{{red}}");

    await alert.getByRole("link", { name: "Open page" }).click();
    await expect(page).toHaveURL(new RegExp(`/pages/edit/${saved!.id}$`));
  });

  test("Restore puts this board's page back and says so", async ({ page }) => {
    await showHelloPage();
    const shownByFiestaBoard = mockBoardGrid(await getMockBoardState());
    await writeFromAnotherApp();
    await primeBoardRead();

    await page.goto("/");
    await expect(banner(page)).toBeVisible({ timeout: 15_000 });
    await expect(banner(page)).toHaveAttribute("data-face", "out-of-sync");

    // This one board's restore, not the install-wide /force-refresh.
    const restoreRequests: string[] = [];
    page.on("request", (r) => {
      if (r.method() === "POST" && /\/api\/(force-refresh|v1\/boards\/[^/]+\/restore)/.test(r.url())) {
        restoreRequests.push(new URL(r.url()).pathname);
      }
    });
    const restored = page.waitForResponse(
      (r) => r.url().includes("/api/v1/boards/primary/restore") && r.request().method() === "POST",
    );
    await banner(page).getByRole("button", { name: "Restore" }).click();
    const response = await restored;
    expect(response.status()).toBe(200);
    expect((await response.json()).sent).toBe(true);

    await expect(page.getByText("Board restored")).toBeVisible({ timeout: 10_000 });
    await expect
      .poll(async () => mockBoardGrid(await getMockBoardState()), { timeout: 10_000 })
      .toEqual(shownByFiestaBoard);
    await expect(banner(page)).toHaveCount(0, { timeout: 10_000 });
    // Past the banner's own confirming refetch (4 s after the send): the
    // backend's read of the board agrees, so the banner stays gone.
    await page.waitForTimeout(5_000);
    await expect(banner(page)).toHaveCount(0);
    await page.reload();
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible({ timeout: 15_000 });
    await page.waitForTimeout(2_000);
    await expect(banner(page)).toHaveCount(0);
    expect(restoreRequests).toEqual(["/api/v1/boards/primary/restore"]);
  });

  test.describe("Restore while paused", () => {
    let boardId = "";
    test.afterEach(async () => {
      if (boardId) await setPaused(boardId, false);
    });

    test("tells the truth: nothing was sent", async ({ page }) => {
      await showHelloPage();
      await writeFromAnotherApp();
      // Read before pausing: a paused board is never read live.
      await primeBoardRead();
      boardId = await primaryBoardId();
      await setPaused(boardId, true);
      const before = (await getMockBoardState()).history?.length ?? 0;

      await page.goto("/");
      await expect(banner(page)).toBeVisible({ timeout: 15_000 });
      await expect(banner(page)).toContainText(
        "This display is paused, so Restore won't send anything until you resume it.",
      );
      await banner(page).getByRole("button", { name: "Restore" }).click();

      await expect(page.getByText("Nothing was sent: this display is paused")).toBeVisible({ timeout: 10_000 });
      await page.waitForTimeout(5_000);
      await expect(banner(page)).toBeVisible();
      expect((await getMockBoardState()).history?.length ?? 0).toBe(before);
    });
  });

  test.describe("during silence", () => {
    test.afterEach(async () => {
      await setSilence(false);
    });

    test("the notice stays hidden, since FiestaBoard is leaving the board alone", async ({ page }) => {
      await showHelloPage();
      await setSilence(true);
      await writeFromAnotherApp();
      await primeBoardRead();

      await page.goto("/");
      await expect(page.getByTestId("silence-alert")).toBeVisible({ timeout: 15_000 });
      await expect(banner(page)).toHaveCount(0);
    });
  });

  test.describe("after FiestaBoard repaints", () => {
    test.afterEach(async () => {
      await setLocalReadInterval(30);
    });

    test("the frame survives FiestaBoard's repaint", async ({ page }) => {
      test.setTimeout(150_000);
      await setLocalReadInterval(20);
      await showHelloPage();
      await writeFromAnotherApp();

      // The poll confirms an external write on its second mismatching read.
      await expect
        .poll(
          async () => {
            const res = await fetch(`${API_URL}/board/current-message`, { headers: authHeaders() });
            return (await res.json()).external_characters ?? null;
          },
          { timeout: 90_000, intervals: [2_000] },
        )
        .toEqual(hiRed());

      // FiestaBoard paints a different page over it.
      const otherText = `OTHER ${uniqueWord()}`;
      const other = await createPage(`Other ${Date.now()}`, [otherText, "", "", "", "", ""]);
      await setActivePage(other);
      await expect
        .poll(async () => gridToText(mockBoardGrid(await getMockBoardState()))[0], { timeout: 15_000 })
        .toContain(otherText);
      // ...and FiestaBoard's own read of the board has caught up with it.
      await expect
        .poll(
          async () => {
            const res = await fetch(`${API_URL}/board/current-message`, { headers: authHeaders() });
            const state = await res.json();
            return JSON.stringify(state.characters) === JSON.stringify(state.expected_characters);
          },
          { timeout: 15_000 },
        )
        .toBe(true);

      await page.goto("/");
      const kept = page.locator('[data-testid="board-out-of-sync"][data-face="kept"]');
      await expect(kept).toBeVisible({ timeout: 15_000 });
      await expect(kept).toContainText(/Another app wrote to this board at/);

      await kept.getByRole("button", { name: "Save as page" }).click();
      await expect(kept.getByRole("link", { name: "Open page" })).toBeVisible({ timeout: 10_000 });
      const saved = (await listPages()).find((p) => p.name.startsWith("From board"));
      expect(saved?.template?.[0]).toBe("HI{{red}}");

      await kept.getByRole("button", { name: "Dismiss" }).click();
      await expect(banner(page)).toHaveCount(0);
      await page.reload();
      await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible({ timeout: 15_000 });
      await page.waitForTimeout(2_000);
      await expect(banner(page)).toHaveCount(0);
    });
  });

  test.describe("with Restore automatically on (the default)", () => {
    test.afterEach(async () => {
      await setLocalReadInterval(30);
    });

    test("FiestaBoard puts the page back by itself, and the kept notice offers Save as page", async ({ page }) => {
      test.setTimeout(150_000);
      await setLocalReadInterval(20);
      await setAutoRestore("primary", true);
      await showHelloPage();
      const shownByFiestaBoard = mockBoardGrid(await getMockBoardState());
      await writeFromAnotherApp();
      // The other app's write landed: the board shows it, not the page.
      expect(mockBoardGrid(await getMockBoardState())).toEqual(hiRed());

      // No Restore, no forced read: the poll confirms the write on its second
      // mismatching read (20 s apart) and the engine's next pass repaints.
      await expect
        .poll(async () => mockBoardGrid(await getMockBoardState()), { timeout: 90_000, intervals: [2_000] })
        .toEqual(shownByFiestaBoard);
      // ...and still remembers what the other app wrote.
      const state = await (await fetch(`${API_URL}/board/current-message`, { headers: authHeaders() })).json();
      expect(state.external_characters).toEqual(hiRed());

      await page.goto("/");
      const kept = page.locator('[data-testid="board-out-of-sync"][data-face="kept"]');
      await expect(kept).toBeVisible({ timeout: 15_000 });
      await expect(kept).toContainText(/Another app wrote to this board at/);
      // The board is back in sync: no live face, nothing to Restore.
      await expect(page.locator('[data-testid="board-out-of-sync"][data-face="out-of-sync"]')).toHaveCount(0);
      await expect(kept.getByRole("button", { name: "Restore" })).toHaveCount(0);
      await expect(kept.getByRole("button", { name: "Dismiss" })).toBeVisible();

      const created = page.waitForRequest((r) => r.url().includes("/api/v1/pages") && r.method() === "POST");
      await kept.getByRole("button", { name: "Save as page" }).click();
      const body = (await created).postDataJSON() as { template: string[] };
      expect(body.template[0]).toBe("HI{{red}}");
      await expect(kept.getByRole("link", { name: "Open page" })).toBeVisible({ timeout: 10_000 });
      // Saving keeps the frame as a page; it never repaints the board.
      expect(mockBoardGrid(await getMockBoardState())).toEqual(shownByFiestaBoard);
    });
  });

  test("the Restore automatically switch on the display's page persists", async ({ page }) => {
    // beforeEach turned it off.
    const board = await (await fetch(`${API_URL}/v1/boards/primary`, { headers: authHeaders() })).json();
    const card = await openDisplay(page, board.name);
    const toggle = card.getByTestId("board-auto-restore-switch");
    await expect(toggle).not.toBeChecked();

    await toggle.click();
    await expect(toggle).toBeChecked();
    await expect.poll(() => getAutoRestore(board.id), { timeout: 10_000 }).toBe(true);

    await page.reload();
    const reloaded = page.getByTestId("board-auto-restore-switch");
    await expect(reloaded).toBeChecked({ timeout: 15_000 });
    await reloaded.click();
    await expect(reloaded).not.toBeChecked();
    await expect.poll(() => getAutoRestore(board.id), { timeout: 10_000 }).toBe(false);

    await page.reload();
    await expect(page.getByTestId("board-auto-restore-switch")).not.toBeChecked({ timeout: 15_000 });
  });

  test("kept notice via route mock offers Save and Dismiss and saves the held frame", async ({ page }) => {
    await showHelloPage();
    const expected = mockBoardGrid(await getMockBoardState());
    await page.route(/\/api\/board\/current-message/, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          characters: expected,
          message: "",
          rows: ROWS,
          cols: COLS,
          expected_characters: expected,
          cached_at: new Date().toISOString(),
          api_mode: "local",
          external_characters: hiRed(),
          external_detected_at: new Date().toISOString(),
        }),
      });
    });

    await page.goto("/");
    const kept = page.locator('[data-testid="board-out-of-sync"][data-face="kept"]');
    await expect(kept).toBeVisible({ timeout: 15_000 });
    await expect(kept.getByRole("button", { name: "Save as page" })).toBeVisible();
    await expect(kept.getByRole("button", { name: "Dismiss" })).toBeVisible();

    const request = page.waitForRequest((r) => r.url().includes("/api/v1/pages") && r.method() === "POST");
    await kept.getByRole("button", { name: "Save as page" }).click();
    const body = (await request).postDataJSON() as { template: string[] };
    expect(body.template).toEqual(["HI{{red}}", "", "", "", "", ""]);
  });

  test.describe("on a phone", () => {
    test.use({ viewport: { width: 390, height: 844 } });

    test("the actions sit under the sentence, inside the screen, and the ⋮ menu is unchanged", async ({ page }) => {
      await showHelloPage();
      await writeFromAnotherApp();
      await primeBoardRead();

      await page.goto("/");
      const alert = banner(page);
      await expect(alert).toBeVisible({ timeout: 15_000 });
      const title = await alert.getByText("Another app changed this board").boundingBox();
      for (const name of ["Restore", "Save as page"]) {
        const button = alert.getByRole("button", { name });
        await expect(button).toBeVisible();
        const box = await button.boundingBox();
        expect(box!.y).toBeGreaterThanOrEqual(title!.y + title!.height);
        expect(box!.x + box!.width).toBeLessThanOrEqual(390);
      }
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);

      await page.getByRole("button", { name: "More options" }).click();
      const items = page.getByRole("menuitem");
      await expect(items).toHaveCount(2);
      await expect(items.nth(0)).toHaveText(/Pause sends/);
      await expect(items.nth(1)).toHaveText(/Change Page/);
    });
  });

  test("both faces pass axe", async ({ page }) => {
    await showHelloPage();
    const expected = mockBoardGrid(await getMockBoardState());
    let face: "out-of-sync" | "kept" = "out-of-sync";
    await page.route(/\/api\/board\/current-message/, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          characters: face === "out-of-sync" ? hiRed() : expected,
          message: "",
          rows: ROWS,
          cols: COLS,
          expected_characters: expected,
          cached_at: new Date().toISOString(),
          api_mode: "local",
          ...(face === "kept" ? { external_characters: hiRed(), external_detected_at: new Date().toISOString() } : {}),
        }),
      });
    });

    for (const which of ["out-of-sync", "kept"] as const) {
      face = which;
      await page.goto("/");
      await expect(page.locator(`[data-testid="board-out-of-sync"][data-face="${which}"]`)).toBeVisible({
        timeout: 15_000,
      });
      // Audit the settled page: mid-entrance the text is still fading in,
      // and axe would measure the blend rather than the colours.
      await page.waitForFunction(
        () =>
          document
            .getAnimations()
            .every((a) => a.playState !== "running" || a.effect?.getTiming().iterations === Infinity),
        null,
        { timeout: 10_000 },
      );
      await injectAxe(page);
      const violations = await getViolations(page, '[data-testid="board-out-of-sync"]', {
        runOnly: { type: "tag" as const, values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "best-practice"] },
      });
      expect(
        violations
          .filter((v) => v.impact === "critical" || v.impact === "serious")
          .map((v) => `${v.id}: ${v.nodes.map((n) => `${n.target} ${n.failureSummary}`).join(" | ")}`),
        `${which} face`,
      ).toEqual([]);
    }
  });
});
