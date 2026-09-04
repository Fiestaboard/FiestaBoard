/**
 * FiestaPanel viewer E2E: the chrome-less /panel/:panelId page.
 *
 * Covers the TV contract: the page renders with no app chrome and no login
 * bounce, shows the virtual board's content, and picks up new frames from
 * the 2s poll after the platform drives the board.
 */
import { API_URL, authHeaders, ensureAuthForFetch, expect, test } from "./helpers";

interface CreatedPanel {
  id: string;
  short_code: number;
  board_id: string;
}

async function createPanel(name: string): Promise<CreatedPanel> {
  const res = await fetch(`${API_URL}/panels`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ name, screen_diagonal_inches: 43 }),
  });
  expect(res.ok).toBe(true);
  const body = (await res.json()) as { panel: CreatedPanel };
  return body.panel;
}

async function deletePanel(panelId: string): Promise<void> {
  await fetch(`${API_URL}/panels/${panelId}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
}

async function driveBoard(boardId: string, lines: string[]): Promise<void> {
  const res = await fetch(`${API_URL}/templates/render/live`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ template: lines, board_id: boardId }),
  });
  expect(res.ok).toBe(true);
}

test.describe("FiestaPanel viewer", () => {
  test.beforeEach(async () => {
    await ensureAuthForFetch();
  });

  test("renders chrome-less without a session and shows the driven frame", async ({ page }) => {
    const panel = await createPanel("E2E Panel");
    try {
      await driveBoard(panel.board_id, ["PANEL E2E OK", "", ""]);

      // Deliberately NO loginIfNeeded: a TV browser has no session cookie.
      // Use the TV-typable short alias — the long /panel/{id} form shares
      // the same module and API resolution.
      expect(panel.short_code).toBeGreaterThan(0);
      await page.goto(`/p/${panel.short_code}`);

      const board = page.getByRole("img");
      await expect(board).toBeVisible({ timeout: 15000 });
      await expect(board).toHaveAttribute("aria-label", /PANEL E2E OK/, { timeout: 10000 });

      // Still on the panel route (no /login redirect) and chrome-less.
      expect(new URL(page.url()).pathname).toContain(`/p/${panel.short_code}`);
      await expect(page.getByRole("navigation")).toHaveCount(0);

      // Seamless grid: the renderer's note-array block seams are zeroed on
      // the panel, so tiles sit at the normal gutter end to end. The 43"
      // auto-fit board is 15×9 (3 notes tall) → row seams exist to check.
      const seamTile = page.locator('[data-note-row-seam="true"]').first();
      await expect(seamTile).toBeAttached();
      await expect(seamTile).toHaveCSS("margin-top", "0px");
    } finally {
      await deletePanel(panel.id);
    }
  });

  test("picks up a new frame from the poll without reloading", async ({ page }) => {
    const panel = await createPanel("E2E Live Panel");
    try {
      await driveBoard(panel.board_id, ["FIRST FRAME", "", ""]);
      await page.goto(`/panel/${panel.id}`);
      await expect(page.getByRole("img")).toHaveAttribute("aria-label", /FIRST FRAME/, {
        timeout: 15000,
      });

      await driveBoard(panel.board_id, ["SECOND FRAME", "", ""]);
      // 2s poll cadence + flap animation time.
      await expect(page.getByRole("img")).toHaveAttribute("aria-label", /SECOND FRAME/, {
        timeout: 10000,
      });
    } finally {
      await deletePanel(panel.id);
    }
  });

  test("/p/display follows the designated panel", async ({ page }) => {
    const first = await createPanel("E2E Display A");
    const second = await createPanel("E2E Display B");
    try {
      await driveBoard(first.board_id, ["FIRST BOARD", "", ""]);
      await driveBoard(second.board_id, ["SECOND BOARD", "", ""]);

      // No designation yet: the kiosk URL asks for one.
      await page.goto("/p/display");
      await expect(page.getByText("No panel is set as the display output")).toBeVisible({
        timeout: 15000,
      });

      const designate = async (panelId: string) => {
        const res = await fetch(`${API_URL}/panels/${panelId}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json", ...authHeaders() },
          body: JSON.stringify({ is_display: true }),
        });
        expect(res.ok).toBe(true);
      };

      await designate(first.id);
      await page.reload();
      await expect(page.getByRole("img")).toHaveAttribute("aria-label", /FIRST BOARD/, {
        timeout: 15000,
      });

      // Re-pointing the display moves the same URL to the other panel.
      await designate(second.id);
      await page.reload();
      await expect(page.getByRole("img")).toHaveAttribute("aria-label", /SECOND BOARD/, {
        timeout: 15000,
      });
    } finally {
      await deletePanel(first.id);
      await deletePanel(second.id);
    }
  });

  test("renders tiles at true physical scale with a visible, sane geometry", async ({ page }) => {
    // Guards the class of bug the other assertions are blind to: a TV that
    // is structurally "correct" (aria-label matches, elements attached) but
    // visually broken — crop stuck transparent, scale collapsed to 0/1, or
    // the life-size anchor wired to the wrong pitch. The expected pitch is
    // derived from the SPEC (a real Note is 24.5" across 15 columns, at the
    // screen's ppi, stretched ≤10% toward the nearest edge), not from the
    // implementation, so it fails if the math itself regresses.
    const panel = await createPanel("E2E Scale Panel"); // 43" 16:9
    try {
      await driveBoard(panel.board_id, ["SCALE CHECK", "", ""]);
      await page.goto(`/p/${panel.short_code}`);
      await expect(page.getByRole("img")).toHaveAttribute("aria-label", /SCALE CHECK/, { timeout: 15000 });

      // Wait for measurement: the crop window sizes itself once the grid is
      // measured; before that it is width:auto with opacity 0.
      const crop = page.getByTestId("panel-board-crop");
      await expect(async () => {
        const width = await crop.evaluate((el) => (el as HTMLElement).style.width);
        expect(width).not.toBe("");
      }).toPass({ timeout: 10000 });

      const metrics = await page.evaluate(() => {
        const cropEl = document.querySelector<HTMLElement>('[data-testid="panel-board-crop"]');
        const scaler = document.querySelector<HTMLElement>('[data-testid="panel-board-scaler"]');
        const t0 = document.querySelector<HTMLElement>('[data-testid="char-tile-0-0"]');
        const t1 = document.querySelector<HTMLElement>('[data-testid="char-tile-0-1"]');
        const transform = scaler ? getComputedStyle(scaler).transform : "none";
        const scale = transform === "none" ? 1 : new DOMMatrixReadOnly(transform).a;
        const rect = t0?.getBoundingClientRect();
        return {
          cropOpacity: cropEl ? getComputedStyle(cropEl).opacity : null,
          cropWidth: cropEl?.clientWidth ?? 0,
          scale,
          unscaledPitchPx: t0 && t1 ? t1.offsetLeft - t0.offsetLeft : 0,
          firstTile: rect ? { x: rect.x, y: rect.y, width: rect.width } : null,
          screenWidth: window.screen.width,
          screenHeight: window.screen.height,
        };
      });

      // The crop window is actually visible (a failed measurement leaves it
      // transparent — the "silent black TV" failure mode).
      expect(metrics.cropOpacity).toBe("1");
      expect(metrics.cropWidth).toBeGreaterThan(0);
      expect(metrics.scale).toBeGreaterThan(0);

      // Life-size invariant: rendered column pitch equals the physical pitch
      // at this screen's ppi, within the allowed ≤10% fill stretch (plus a
      // small rounding allowance).
      const ppi = Math.hypot(metrics.screenWidth, metrics.screenHeight) / 43;
      const physicalPitchPx = (24.5 / 15) * ppi;
      const renderedPitchPx = metrics.unscaledPitchPx * metrics.scale;
      expect(renderedPitchPx).toBeGreaterThanOrEqual(physicalPitchPx * 0.98);
      expect(renderedPitchPx).toBeLessThanOrEqual(physicalPitchPx * 1.12);

      // The first tile really is on screen with a paintable area — content
      // parked outside the viewport reads as a blank TV.
      expect(metrics.firstTile).not.toBeNull();
      expect(metrics.firstTile!.width).toBeGreaterThan(5);
      expect(metrics.firstTile!.x).toBeGreaterThanOrEqual(0);
      expect(metrics.firstTile!.y).toBeGreaterThanOrEqual(0);
    } finally {
      await deletePanel(panel.id);
    }
  });

  test("shows the not-found state for an unknown panel", async ({ page }) => {
    await page.goto("/panel/doesnotexist000");
    await expect(page.getByText("This panel no longer exists")).toBeVisible({ timeout: 15000 });
    expect(new URL(page.url()).pathname).toContain("/panel/doesnotexist000");
  });
});
