/**
 * Board Switch UX E2E Tests
 *
 * Switching the managed board via the sidebar selector must read as a
 * SWITCH — the old page slides out, the new one slides in (View Transitions
 * API, see current-board-context.tsx) — instead of collapsing the page to a
 * skeleton and replaying the "fly up from the bottom" entrance animation.
 *
 * Videos are recorded (`test.use({ video: "on" })`) so the transition can be
 * validated visually.
 */
import { API_URL, configureBoard, ensureTwoBoards, expect, resetToSingleBoard, suppressWizard, test } from "./helpers";

test.use({ video: "on" });

/** Give the two boards recognizable names so the video reads clearly. */
async function nameBoards(names: [string, string]) {
  const res = await fetch(`${API_URL}/settings/board`);
  const data = await res.json();
  const boards = (data.boards ?? []).map((b: Record<string, unknown>, i: number) => ({
    ...b,
    name: names[i] ?? b.name,
  }));
  await fetch(`${API_URL}/settings/board`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ boards }),
  });
}

/**
 * Install a MutationObserver that records every value the board-switch
 * transition stamps on <html data-board-switch>. Lets us assert the
 * transition actually ran (and in which direction) without racing its
 * ~300ms lifetime.
 */
async function watchBoardSwitchAttribute(page: import("@playwright/test").Page) {
  await page.evaluate(() => {
    const seen: string[] = [];
    (window as unknown as { __boardSwitchDirections: string[] }).__boardSwitchDirections = seen;
    new MutationObserver(() => {
      const v = document.documentElement.dataset.boardSwitch;
      if (v && seen[seen.length - 1] !== v) seen.push(v);
    }).observe(document.documentElement, { attributes: true, attributeFilter: ["data-board-switch"] });
  });
}

async function recordedDirections(page: import("@playwright/test").Page): Promise<string[]> {
  return page.evaluate(() => (window as unknown as { __boardSwitchDirections: string[] }).__boardSwitchDirections);
}

async function switchBoardTo(page: import("@playwright/test").Page, boardName: string) {
  // The selector renders in both the (hidden) mobile header and the desktop
  // sidebar — scope to the sidebar to satisfy strict mode.
  await page.locator("aside").getByLabel("Select board to manage").click();
  await page.getByRole("option", { name: boardName }).click();
}

test.describe("Board switch UX", () => {
  test.beforeEach(async ({ page }) => {
    await configureBoard();
    await ensureTwoBoards();
    await nameBoards(["Kitchen", "Office"]);
    await suppressWizard(page);
  });

  test.afterEach(async () => {
    await resetToSingleBoard();
  });

  test("switching boards on /schedule slides between boards without remounting the page", async ({ page }) => {
    await page.goto("/schedule");
    const heading = page.getByRole("heading", { name: "Schedule", exact: true });
    await expect(heading).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("active-board-indicator")).toContainText("Kitchen");

    // Tag the page header DOM node. If the switch collapses the page to the
    // loading skeleton (the old bug), this node unmounts and the tag is lost.
    await page.evaluate(() => {
      const h1 = document.querySelector("main h1");
      if (h1) (h1 as unknown as { __stable: boolean }).__stable = true;
    });
    await watchBoardSwitchAttribute(page);

    await switchBoardTo(page, "Office");
    await expect(page.getByTestId("active-board-indicator")).toContainText("Office");

    // The directional view transition ran (Chromium supports the API)…
    expect(await recordedDirections(page)).toContain("forward");
    // …and the page content was never torn down to a skeleton mid-switch.
    const stable = await page.evaluate(() => {
      const h1 = document.querySelector("main h1");
      return h1 ? (h1 as unknown as { __stable?: boolean }).__stable === true : false;
    });
    expect(stable).toBe(true);

    // Give the video a beat on the new board, then switch back (backward slide).
    await page.waitForTimeout(600);
    await switchBoardTo(page, "Kitchen");
    await expect(page.getByTestId("active-board-indicator")).toContainText("Kitchen");
    expect(await recordedDirections(page)).toEqual(["forward", "backward"]);

    // Transition cleanup: the direction attribute never lingers.
    await expect.poll(async () => page.evaluate(() => document.documentElement.dataset.boardSwitch ?? null)).toBeNull();
  });

  test("switching boards on the dashboard plays the directional transition", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 }).first()).toBeVisible({ timeout: 15_000 });
    await watchBoardSwitchAttribute(page);

    await switchBoardTo(page, "Office");
    expect(await recordedDirections(page)).toContain("forward");

    await page.waitForTimeout(600);
    await switchBoardTo(page, "Kitchen");
    expect(await recordedDirections(page)).toEqual(["forward", "backward"]);
  });
});
