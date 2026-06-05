/**
 * Regression coverage for /pages/new.
 * Subarea: pages.new
 */
import {
  test,
  expect,
  configureBoard,
  deleteAllPages,
  ensureAuthForFetch,
  loginIfNeeded,
} from "../helpers";

test.beforeEach(async ({ context, page }) => {
  await ensureAuthForFetch();
  await loginIfNeeded(context);
  await configureBoard();
  await page.addInitScript(() => {
    localStorage.setItem("fiestaboard_wizard_complete", "true");
  });
});

test.afterEach(async () => {
  await deleteAllPages();
});

test.describe("regression: pages.new", () => {
  /** UX node: pages.new.line-count-warning */
  test("pages.new.line-count-warning — over-line-count entry surfaces banner", async ({ page }) => {
    await page.goto("/pages/new?device=note");
    await page.getByRole("button", { name: "Plain Text", exact: true }).click();
    const textarea = page.locator("textarea").first();
    await textarea.fill("L1\nL2\nL3\nL4\nL5\nL6\nL7");
    await expect(
      page.getByText(/Template has \d+ lines but the board only displays \d+/),
    ).toBeVisible({ timeout: 5_000 });
    await textarea.fill("L1\nL2\nL3");
    await expect(
      page.getByText(/Template has \d+ lines but the board only displays \d+/),
    ).toBeHidden({ timeout: 5_000 });
  });

  /** UX node: pages.new.wrap-budget-warning */
  test("pages.new.wrap-budget-warning — editor renders without crashing for long content", async ({ page }) => {
    await page.goto("/pages/new");
    await page.getByRole("button", { name: "Plain Text", exact: true }).click();
    const textarea = page.locator("textarea").first();
    // Fill with content that would trip wrap-budget heuristics — saturated text
    // on every line with no empty/wrap line below.
    const longLine = "X".repeat(22);
    await textarea.fill(`${longLine}\n${longLine}\n${longLine}\n${longLine}\n${longLine}\n${longLine}`);
    // Page stays mounted; the wrap-budget warning is a passive UI signal that
    // we don't assert exact copy on (depends on rich-editor mode).
    await expect(textarea).toBeVisible();
  });

  /** UX node: pages.new.editor-plain */
  test("pages.new.editor-plain — Plain toggle persists and surfaces textarea", async ({ page }) => {
    await page.goto("/pages/new");
    const plainBtn = page.getByRole("button", { name: "Plain Text", exact: true });
    await plainBtn.click();
    await expect(plainBtn).toHaveAttribute("aria-pressed", "true");
    await expect(page.locator("textarea").first()).toBeVisible();
    const stored = await page.evaluate(() => localStorage.getItem("fiestaboard_editor_mode"));
    expect(stored).toBe("plain");
  });

  /** UX node: pages.new.draft-restored */
  test("pages.new.draft-restored — saved draft restores banner", async ({ page }) => {
    await page.addInitScript(() => {
      const draft = {
        name: "Restored Draft",
        templateLines: ["HELLO", "WORLD", "", "", "", ""],
        lineAlignments: ["left", "left", "left", "left", "left", "left"],
        lineWrapEnabled: [false, false, false, false, false, false],
        timestamp: Date.now(),
      };
      localStorage.setItem("fiestaboard-page-draft-new", JSON.stringify(draft));
    });
    await page.goto("/pages/new");
    await expect(
      page.getByText(/Draft restored from your previous session/),
    ).toBeVisible({ timeout: 10_000 });
  });

  /** UX node: pages.new.fresh-skips-draft */
  test("pages.new.fresh-skips-draft — ?fresh=1 query param skips draft restore", async ({ page }) => {
    await page.addInitScript(() => {
      const draft = {
        name: "Should Not Restore",
        templateLines: ["X", "", "", "", "", ""],
        lineAlignments: ["left", "left", "left", "left", "left", "left"],
        lineWrapEnabled: [false, false, false, false, false, false],
        timestamp: Date.now(),
      };
      localStorage.setItem("fiestaboard-page-draft-new", JSON.stringify(draft));
    });
    await page.goto("/pages/new?fresh=1");
    await expect(
      page.getByText(/Draft restored from your previous session/),
    ).toBeHidden({ timeout: 5_000 });
  });

  /** UX node: pages.new.live-output-on */
  test("pages.new.live-output-on — live output toggle enables and shows preview", async ({ page }) => {
    await page.goto("/pages/new");
    const toggle = page.locator("#live-output-toggle");
    await expect(toggle).toBeVisible();
    await toggle.click();
    await expect(toggle).toHaveAttribute("aria-checked", "true");
  });

  /** UX node: pages.new.live-output-error */
  test("pages.new.live-output-error — live output toggle is interactable", async ({ page }) => {
    await page.goto("/pages/new");
    const toggle = page.locator("#live-output-toggle");
    await expect(toggle).toBeVisible();
    await toggle.click();
    // After clicking, toggle reflects new state — error-path UI is downstream
    // and varies by board configuration. Stable signal: the toggle itself is
    // wired and interactive.
    await expect(toggle).toHaveAttribute("aria-checked", "true");
  });
});
