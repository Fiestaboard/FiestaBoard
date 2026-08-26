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
  board_id: string;
}

async function createPanel(name: string): Promise<CreatedPanel> {
  const res = await fetch(`${API_URL}/panels`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ name, device_type: "note", screen_diagonal_inches: 43 }),
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
      await page.goto(`/panel/${panel.id}`);

      const board = page.getByRole("img");
      await expect(board).toBeVisible({ timeout: 15000 });
      await expect(board).toHaveAttribute("aria-label", /PANEL E2E OK/, { timeout: 10000 });

      // Still on the panel route (no /login redirect) and chrome-less.
      expect(new URL(page.url()).pathname).toContain(`/panel/${panel.id}`);
      await expect(page.getByRole("navigation")).toHaveCount(0);
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

  test("shows the not-found state for an unknown panel", async ({ page }) => {
    await page.goto("/panel/doesnotexist000");
    await expect(page.getByText("This panel no longer exists")).toBeVisible({ timeout: 15000 });
    expect(new URL(page.url()).pathname).toContain("/panel/doesnotexist000");
  });
});
