import { mkdir } from "node:fs/promises";
import path from "node:path";

import { expect, type Page, test } from "@playwright/test";

import { kitchenMorning, mockHub } from "./creator-ide-hub";

// FABLE-WALK-2 W-1: a Wrap the board has no rows for is disabled with the
// reason, and a wrap that runs off the last row is a Problem in the H4 family:
// the card, the Console and the state line's count say the same thing.
// W-3: the first save's "Saved to Pages" toast follows the editor's
// bottom-right toast rule (UX-8-2), clear of Export · Save · Show now.

const LUNCH = "LUNCH AT NOON TODAY FOR EVERYONE IN THE OFFICE"; // 46 columns: 3 rows at 22
const PAST = "Line 5 wraps past the board's 6 rows · 1 row won't show";

/** The saved page holds LUNCH on row 5; the hub answers validate as the engine does. */
async function openLunchPage(page: Page, { wrapped }: { wrapped: boolean }) {
  await mockHub(page, { notScheduled: true });
  const lunch = {
    ...kitchenMorning,
    template: ["", "", "", "HELLO WORLD", LUNCH, ""],
    line_metadata: Array.from({ length: 6 }, (_, index) => ({ alignment: "left", wrap: wrapped && index === 4 })),
  };
  await page.route(
    (url) => url.pathname === `/api/v1/pages/${kitchenMorning.id}`,
    (route) => route.fulfill({ json: lunch }),
  );
  await page.route(
    (url) => url.pathname === "/api/templates/validate",
    (route) => {
      const body = route.request().postDataJSON() as { line_metadata?: { wrap?: boolean }[] };
      const wraps = body.line_metadata?.[4]?.wrap === true;
      route.fulfill({
        json: {
          valid: false,
          rows: 6,
          cols: 22,
          errors: [
            wraps
              ? { line: 5, column: 0, code: "beyond_board", message: PAST, max_length: null }
              : {
                  line: 5,
                  column: 22,
                  code: "line_too_long",
                  message: "Line may be too long (up to 46 chars, max 22)",
                  max_length: 46,
                },
          ],
        },
      });
    },
  );
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto(`/tests/layout/editor-window.html?${new URLSearchParams({ path: "/pages/edit/kitchen-morning" })}`);
  await expect(page.getByRole("textbox", { name: /page name/i })).toHaveValue("Kitchen morning");
}

const card = (page: Page) => page.locator('[data-slot="line-overflow-warnings"] [data-slot="editor-warning"]');

test("Wrap is disabled with the reason when the rows below are full (W-1)", async ({ page }, testInfo) => {
  await openLunchPage(page, { wrapped: false });
  await expect(card(page)).toContainText("46 of 22 columns · 24 cut off");
  const wrap = card(page).getByRole("button", { name: "Wrap line 5" });
  await expect(wrap).toBeDisabled();
  await expect(wrap).toHaveAccessibleDescription("Needs 1 more row");
  await expect(card(page).getByText("Needs 1 more row")).toBeVisible();
  const shots = process.env.W3A1_SHOTS || testInfo.outputPath("shots");
  await mkdir(shots, { recursive: true });
  await page.screenshot({ path: path.join(shots, "wrap-disabled-1440.png") });
});

test("a wrap past the last row is one problem, in the same words everywhere (W-1)", async ({ page }, testInfo) => {
  await openLunchPage(page, { wrapped: true });
  // The H4 card: the Console's kind as its badge, the hub's words as its title.
  await expect(card(page)).toHaveCount(1);
  await expect(card(page)).toContainText("Past the last row");
  await expect(card(page)).toContainText(PAST);
  // The state line counts it.
  const status = page.locator('[data-slot="preview-status"]');
  await expect(status.getByRole("button", { name: "1 problem" })).toBeVisible();
  // The Console lists it in the same words.
  const consoleRegion = page.getByRole("region", { name: "Console" });
  await expect(consoleRegion).not.toContainText("No problems");
  await status.getByRole("button", { name: "1 problem" }).click();
  await expect(consoleRegion.getByRole("tab", { name: "Problems 1" })).toBeVisible();
  await expect(consoleRegion.getByRole("listitem")).toContainText(["Past the last row · Row 5"]);
  await expect(consoleRegion.getByRole("listitem")).toContainText([PAST]);
  const shots = process.env.W3A1_SHOTS || testInfo.outputPath("shots");
  await mkdir(shots, { recursive: true });
  await page.screenshot({ path: path.join(shots, "wrap-past-board-1440.png") });
});

for (const width of [1440, 1024, 390]) {
  test(`${width}px: the first save's toast sits bottom-right, clear of the header actions (W-3)`, async ({
    page,
  }, testInfo) => {
    await mockHub(page, { noProblems: true });
    await page.setViewportSize({ width, height: width >= 1440 ? 900 : width >= 1024 ? 768 : 844 });
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto(`/tests/layout/editor-window.html?${new URLSearchParams({ path: "/pages/new" })}`);
    const editor = page.locator(".ProseMirror").first();
    await expect(editor).toBeVisible();
    await page.getByRole("textbox", { name: /page name/i }).fill("Kitchen morning");
    await editor.click();
    await page.keyboard.type("HELLO");
    await page.getByRole("button", { name: /save page/i }).click();

    const toast = page.locator("[data-sonner-toast]").filter({ hasText: "Saved to Pages" });
    await expect(toast).toBeVisible();
    const toaster = page.locator("[data-sonner-toaster]").filter({ has: toast });
    await expect(toaster).toHaveAttribute("data-y-position", "bottom");
    await expect(toaster).toHaveAttribute("data-x-position", "right");
    // Settled (no motion), it sits low and over none of the header's (or phone toolbar's) actions.
    await expect
      .poll(async () => {
        const box = (await toast.boundingBox())!;
        return box.y + box.height;
      })
      .toBeGreaterThan((width >= 1440 ? 900 : width >= 1024 ? 768 : 844) * 0.6);
    const toastBox = (await toast.boundingBox())!;
    const header = page.locator('[data-slot="card-header"]').first();
    // On a phone the editor's touch toolbar sits at the bottom: the toast rises above it.
    const covered = [...(await header.getByRole("button").all())];
    if (width < 768) {
      const toolbar = page.locator('[data-slot="editor-toolbar"]').last();
      await expect(toolbar).toBeVisible();
      covered.push(...(await toolbar.getByRole("button").all()));
    }
    for (const button of covered) {
      const box = await button.boundingBox();
      if (!box) continue;
      const overlaps =
        box.x < toastBox.x + toastBox.width &&
        toastBox.x < box.x + box.width &&
        box.y < toastBox.y + toastBox.height &&
        toastBox.y < box.y + box.height;
      expect(overlaps, `toast covers ${(await button.getAttribute("aria-label")) ?? (await button.innerText())}`).toBe(
        false,
      );
    }
    const shots = process.env.W3A1_SHOTS || testInfo.outputPath("shots");
    await mkdir(shots, { recursive: true });
    await page.screenshot({ path: path.join(shots, `saved-toast-${width}.png`) });
  });
}
