/**
 * FiestaBoard — status banners and the BoardSelector hub line (slice 2.3,
 * WEB-10 / WEB-09; Figma 07a `Web / Banner` `298:2280`, `302:2146`).
 *
 *   1. Paused: Home says so under the header, and Resume un-pauses the board.
 *   2. Silenced: a display's own page shows the Silence Schedule banner.
 *   3. Hub unreachable: when the status poll gets no answer, Home says so,
 *      the hub line reads "Can't reach", and Try again recovers.
 *   4. You're offline: the browser loses its network.
 *   5. Display offline: H12 `health.reachable === false` on the board.
 *   6. The hub line reads "host · Online" on a LAN address.
 *   7. a11y of the banners.
 */
import type { Page, Route } from "@playwright/test";
import { getViolations, injectAxe } from "axe-playwright";

import {
  API_URL,
  authHeaders,
  configureBoard,
  ensureTwoBoards,
  expect,
  resetToSingleBoard,
  setScheduleEnabled,
  suppressWizard,
  test,
} from "./helpers";

async function primaryBoard(): Promise<{ id: string; name: string }> {
  const res = await fetch(`${API_URL}/settings/board`, { headers: authHeaders() });
  const data = await res.json();
  return { id: data.boards[0].id, name: data.boards[0].name };
}

async function setPaused(boardId: string, paused: boolean) {
  const res = await fetch(`${API_URL}/v1/boards/${boardId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ paused }),
  });
  if (!res.ok) throw new Error(`pause failed: ${res.status} ${await res.text()}`);
}

async function isPaused(boardId: string): Promise<boolean> {
  const res = await fetch(`${API_URL}/v1/boards/${boardId}`, { headers: authHeaders() });
  return (await res.json()).paused === true;
}

function utcHhmm(offsetMinutes: number): string {
  const d = new Date(Date.now() + offsetMinutes * 60_000);
  return `${String(d.getUTCHours()).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")}+00:00`;
}

async function setSilence(enabled: boolean, boardId?: string) {
  const res = await fetch(`${API_URL}/settings/silence-schedule`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({
      enabled,
      start_time: utcHhmm(-60),
      end_time: utcHhmm(60),
      mode: "freeze",
      ...(boardId ? { board_id: boardId } : {}),
    }),
  });
  if (!res.ok) throw new Error(`silence failed: ${res.status} ${await res.text()}`);
}

const statusBanner = (page: Page, kind: string) => page.locator(`[data-slot="status-banner"][data-kind="${kind}"]`);

async function expectNoSeriousViolations(page: Page, selector: string, label: string) {
  // The route's entrance fade would otherwise be measured as low contrast.
  await page.evaluate(() => Promise.all(document.getAnimations().map((a) => a.finished.catch(() => {}))));
  await injectAxe(page);
  const violations = await getViolations(page, selector, {
    runOnly: { type: "tag" as const, values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "best-practice"] },
  });
  expect(
    violations
      .filter((v) => v.impact === "critical" || v.impact === "serious")
      .map((v) => `${v.id}: ${v.nodes.map((n) => `${n.target} ${n.failureSummary}`).join(" | ")}`),
    label,
  ).toEqual([]);
}

test.beforeEach(async ({ page }) => {
  await configureBoard();
  await resetToSingleBoard();
  await setScheduleEnabled(false);
  await suppressWizard(page);
});

test.afterEach(async () => {
  const board = await primaryBoard();
  await setPaused(board.id, false).catch(() => {});
  await setSilence(false).catch(() => {});
  await resetToSingleBoard();
});

test.describe("Status banners", () => {
  test("paused: Home says so under the header, and Resume un-pauses the board", async ({ page }) => {
    const board = await primaryBoard();
    await setPaused(board.id, true);

    await page.goto("/");
    const banner = statusBanner(page, "paused");
    await expect(banner).toBeVisible({ timeout: 15_000 });
    await expect(banner).toContainText(`${board.name} is paused`);
    await expectNoSeriousViolations(page, '[data-slot="status-banner"]', "paused banner");

    await banner.getByRole("button", { name: "Resume" }).click();
    await expect(banner).toBeHidden({ timeout: 15_000 });
    expect(await isPaused(board.id)).toBe(false);
  });

  test("silenced: a display's own page shows the Silence Schedule banner, with no action", async ({ page }) => {
    const board = await primaryBoard();
    await setSilence(true);

    await page.goto(`/displays/${encodeURIComponent(board.id)}`);
    const banner = statusBanner(page, "silenced");
    await expect(banner).toBeVisible({ timeout: 15_000 });
    await expect(banner).toContainText("Silence Schedule until");
    await expect(banner.getByRole("button")).toHaveCount(0);
  });

  test("hub unreachable: Home says so, the hub line reads Can't reach, and Try again recovers", async ({ page }) => {
    await ensureTwoBoards();
    let down = false;
    await page.route("**/api/v1/status", (route: Route) =>
      down ? route.abort("connectionrefused") : route.continue(),
    );

    await page.goto("/");
    await expect(page.locator('[data-slot="board-selector-hub"]', { hasText: "Online" })).not.toHaveCount(0, {
      timeout: 15_000,
    });

    down = true;
    // The next poll (15 s) or a refetch on focus finds the hub gone.
    await page.evaluate(() => window.dispatchEvent(new Event("focus")));
    const banner = statusBanner(page, "hub-unreachable");
    await expect(banner).toBeVisible({ timeout: 40_000 });
    await expect(banner).toContainText("Can't reach your hub at");
    await expect(banner).toContainText("Last connected");
    await expect(banner.getByRole("link", { name: /Connection help/ })).toHaveAttribute("target", "_blank");
    await expect(page.locator('[data-slot="board-selector-hub"]', { hasText: "Can't reach" })).not.toHaveCount(0);
    await expectNoSeriousViolations(page, '[data-slot="status-banner"]', "hub-unreachable banner");

    down = false;
    await banner.getByRole("button", { name: "Try again" }).click();
    await expect(banner).toBeHidden({ timeout: 15_000 });
  });

  test("you're offline: the browser loses its network", async ({ page, context }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible({ timeout: 15_000 });

    await context.setOffline(true);
    const banner = statusBanner(page, "device-offline");
    await expect(banner).toBeVisible({ timeout: 10_000 });
    await expect(banner).toContainText("You're offline");
    await expect(statusBanner(page, "hub-unreachable")).toHaveCount(0);

    await context.setOffline(false);
    await expect(banner).toBeHidden({ timeout: 10_000 });
  });

  test("display offline: H12 says the hub can't reach the board", async ({ page }) => {
    const board = await primaryBoard();
    // Drive the H12 fields the hub reports for an unreachable display.
    await page.route("**/api/v1/status", async (route: Route) => {
      const response = await route.fetch();
      const body = await response.json();
      const entry = body.boards?.[board.id];
      if (entry) {
        entry.health = {
          ...(entry.health ?? {}),
          last_connected_at: new Date(Date.now() - 30 * 60_000).toISOString(),
          last_error_at: new Date().toISOString(),
          last_error: "unreachable",
          reachable: false,
          breaker_open: false,
        };
      }
      await route.fulfill({ response, json: body });
    });

    await page.goto("/");
    const banner = statusBanner(page, "display-offline");
    await expect(banner).toBeVisible({ timeout: 15_000 });
    await expect(banner).toContainText(`${board.name} is offline`);
    await expect(banner).toContainText("Last connected");
    await banner.getByRole("link", { name: "Diagnostics" }).click();
    await expect(page).toHaveURL(new RegExp(`/displays/${board.id}\\?section=settings`));
  });

  test("the hub line reads 'host · Online' on a LAN address", async ({ page }) => {
    await ensureTwoBoards();
    await page.goto("/");
    const host = new URL(page.url()).hostname;
    // The sidebar reads "host · State"; the phone header pill leads with the state.
    await expect(page.locator('[data-slot="board-selector-hub"]', { hasText: `${host} · Online` })).not.toHaveCount(0, {
      timeout: 15_000,
    });
  });
});
