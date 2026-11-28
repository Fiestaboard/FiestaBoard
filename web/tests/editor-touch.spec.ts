/**
 * WEB-03/04/05. Breakpoints follow WEB-BATCH3-RULINGS and 07c:
 * sheets <640, touch tools <768 or coarse, docked preview <1024.
 */
import type { Page } from "@playwright/test";
import { getViolations, injectAxe } from "axe-playwright";

import { configureBoard, createPage, deletePage, expect, setScheduleEnabled, suppressWizard, test } from "./helpers";

const PREVIEW = '[data-slot="editor-preview"]';
const TOUCH_TOOLS = '[data-slot="editor-toolbar"][data-size="touch"]';
const MODE_TOGGLE = '[data-slot="board-preview-mode-toggle"]';

async function openEditor(page: Page, id?: string) {
  await page.goto(id ? `/pages/edit/${id}` : "/pages/new");
  await expect(page.locator('[contenteditable="true"]').first()).toBeVisible({ timeout: 15_000 });
  await expect(page.locator(PREVIEW)).toBeVisible();
}

async function openMore(page: Page) {
  await page.locator(TOUCH_TOOLS).getByRole("button", { name: "More", exact: true }).click();
  const sheet = page.locator('[data-slot="sheet-content"]');
  await expect(sheet).toBeVisible();
  return sheet;
}

test.beforeEach(async ({ page }) => {
  await configureBoard();
  await suppressWizard(page);
});

test.describe("Editor breakpoint contracts with a fine pointer", () => {
  for (const width of [390, 639, 640, 767, 768, 1023, 1024, 1280]) {
    test(`${width}px keeps preview visible and chooses the correct tools`, async ({ page }) => {
      await page.setViewportSize({ width, height: 1024 });
      await openEditor(page);
      await expect(page.locator(PREVIEW)).toHaveAttribute("data-variant", width < 1024 ? "docked" : "pane");
      await expect(page.locator(TOUCH_TOOLS)).toHaveCount(width < 768 ? 1 : 0);
      await expect(page.getByRole("button", { name: /show preview/i })).toHaveCount(0);
      await page.locator('[contenteditable="true"]').first().fill("VISIBLE PREVIEW");
      await expect(page.locator(PREVIEW)).toBeInViewport();
      await expect(page.locator(`${PREVIEW} [data-slot="editor-preview-board"]`)).toBeVisible();
    });
  }

  for (const width of [639, 640]) {
    test(`Colors uses ${width < 640 ? "a sheet" : "an anchored picker"} at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 1024 });
      await openEditor(page);
      await page.locator(TOUCH_TOOLS).getByRole("button", { name: "Colors", exact: true }).click();
      const sheet = page.locator('[data-slot="sheet-content"]');
      if (width < 640) {
        await expect(sheet).toBeVisible();
        await expect(sheet.getByText("Colors", { exact: true }).first()).toBeVisible();
      } else {
        await expect(sheet).toHaveCount(0);
        await expect(page.getByRole("listbox", { name: "Color picker" })).toBeVisible();
      }
      await expect(page.locator(PREVIEW)).toBeVisible();
      await page.keyboard.press("Escape");
      await expect(page.getByRole("listbox", { name: "Color picker" })).toHaveCount(0);
    });
  }
});

test.describe("Editor coarse pointer", () => {
  test.use({ viewport: { width: 1024, height: 900 }, hasTouch: true });

  test("uses labelled touch tools on a wide touch display while retaining a pane preview", async ({ page }) => {
    await openEditor(page);
    expect(await page.evaluate(() => matchMedia("(pointer: coarse)").matches)).toBe(true);
    await expect(page.locator(PREVIEW)).toHaveAttribute("data-variant", "pane");
    for (const label of ["Variables", "Colors", "Spacing", "Formula", "More"]) {
      await expect(page.locator(TOUCH_TOOLS).getByRole("button", { name: label, exact: true })).toBeVisible();
    }
  });
});

test.describe("Editor phone flows", () => {
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });

  test("More mirrors only after opting in, and disabling it stops live renders", async ({ page }) => {
    const requests: Record<string, unknown>[] = [];
    await page.route("**/api/templates/render/live", async (route) => {
      requests.push(route.request().postDataJSON());
      await route.fulfill({
        json: { rendered: "MIRROR ME", lines: ["MIRROR ME"], line_count: 1, sent_to_board: true },
      });
    });
    await openEditor(page);
    const editor = page.locator('[contenteditable="true"]').first();
    await editor.fill("MIRROR ME");
    let sheet = await openMore(page);
    const mirror = sheet.getByRole("switch", { name: "Mirror to board while editing" });
    await expect(mirror).not.toBeChecked();
    expect(requests).toHaveLength(0);
    await mirror.click();
    await expect(mirror).toBeChecked();
    await expect.poll(() => requests.length).toBe(1);
    expect(requests[0]).toMatchObject({
      template: expect.arrayContaining(["MIRROR ME"]),
      board_id: expect.any(String),
    });
    await page.keyboard.press("Escape");
    await expect(page.locator(PREVIEW).getByText("Mirroring", { exact: true })).toBeVisible();
    sheet = await openMore(page);
    await expect(sheet.getByRole("switch", { name: "Mirror to board while editing" })).toBeChecked();
    await sheet.getByRole("switch", { name: "Mirror to board while editing" }).click();
    await page.keyboard.press("Escape");
    const count = requests.length;
    const previewResponse = page.waitForResponse(
      (response) =>
        /\/api\/templates\/render$/.test(new URL(response.url()).pathname) && response.request().method() === "POST",
    );
    await editor.fill("PREVIEW ONLY");
    // Regular preview completion proves the changed text has passed its debounce.
    await previewResponse;
    expect(requests).toHaveLength(count);
  });

  test("has one controlled size toggle, opens at Fit, persists Actual size and restores it on reopen", async ({
    page,
  }) => {
    await openEditor(page);
    await expect(page.locator(MODE_TOGGLE)).toHaveCount(1);
    const toggle = page.locator(MODE_TOGGLE);
    // Fit by default on every geometry (UX-4-2, FABLE-2651 should-fix 1).
    await expect(toggle.getByRole("button", { name: "Fit", exact: true })).toHaveAttribute("aria-pressed", "true");
    await toggle.getByRole("button", { name: "Actual size", exact: true }).click();
    await expect(toggle.getByRole("button", { name: "Actual size", exact: true })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(await page.evaluate(() => sessionStorage.getItem("fiestaboard:boardPreviewMode"))).toBe("actual");
    await page.reload();
    await expect(page.locator(MODE_TOGGLE)).toHaveCount(1);
    await expect(page.locator(MODE_TOGGLE).getByRole("button", { name: "Actual size", exact: true })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  test("Save persists without sending; Show now saves current edits before activating that page", async ({ page }) => {
    const id = await createPage("Touch save flow", ["BEFORE", "", "", "", "", ""]);
    try {
      const events: Array<{ kind: string; body: Record<string, unknown> }> = [];
      await page.route(`**/api/v1/pages/${id}`, async (route) => {
        if (route.request().method() === "PUT") {
          events.push({ kind: "save", body: route.request().postDataJSON() });
        }
        await route.continue();
      });
      await page.route("**/api/settings/active-page", async (route) => {
        if (route.request().method() === "PUT") {
          events.push({ kind: "show", body: route.request().postDataJSON() });
          await route.fulfill({ json: { status: "success", message: "Page activated" } });
        } else await route.continue();
      });
      await setScheduleEnabled(false);
      await openEditor(page, id);
      const editor = page.locator('[contenteditable="true"]').first();
      await editor.fill("SAVED ONLY");
      await page.getByRole("button", { name: "Save Page", exact: true }).click();
      await expect.poll(() => events.filter((event) => event.kind === "save").length).toBe(1);
      expect(events.map((event) => event.kind)).toEqual(["save"]);
      await expect(editor).toBeVisible();
      await editor.fill("SHOW THIS EDIT");
      await page.getByRole("button", { name: "Show now", exact: true }).first().click();
      const duration = page.locator('[data-slot="sheet-content"]');
      await expect(duration.getByRole("radio", { name: "Until I cancel", exact: true })).toBeVisible();
      expect(events.map((event) => event.kind)).toEqual(["save", "save"]);
      await duration.getByRole("radio", { name: "Until I cancel", exact: true }).click();
      await duration.getByRole("button", { name: "Show now", exact: true }).click();
      await expect.poll(() => events.map((event) => event.kind)).toEqual(["save", "save", "show"]);
      expect(events[1].body.template).toEqual(expect.arrayContaining(["SHOW THIS EDIT"]));
      expect(events[2].body).toMatchObject({ page_id: id, board_id: expect.any(String) });
    } finally {
      await deletePage(id);
    }
  });

  test("first Save creates a page and announces Saved to Pages without activating it", async ({ page }) => {
    let createdId: string | undefined;
    const activationRequests: unknown[] = [];
    await page.route("**/api/settings/active-page", async (route) => {
      if (route.request().method() === "PUT") activationRequests.push(route.request().postDataJSON());
      await route.continue();
    });
    try {
      await openEditor(page);
      const name = `Touch first save ${Date.now()}`;
      await page.getByPlaceholder("My Custom Page").fill(name);
      await page.locator('[contenteditable="true"]').first().fill("FIRST SAVE");
      const created = page.waitForResponse(
        (response) =>
          /\/api\/v1\/pages$/.test(new URL(response.url()).pathname) && response.request().method() === "POST",
      );
      await page.getByRole("button", { name: "Save Page", exact: true }).click();
      const response = await created;
      expect(response.status()).toBe(201);
      const stored = await response.json();
      createdId = stored.id;
      expect(stored).toMatchObject({ id: expect.any(String), name, template: expect.arrayContaining(["FIRST SAVE"]) });
      const toast = page.locator("[data-sonner-toast]").filter({ hasText: "Saved to Pages" });
      await expect(toast).toBeVisible();
      await expect(toast.getByRole("button", { name: "Show now", exact: true })).toBeVisible();
      await expect(toast.getByRole("button", { name: "Add to Schedule", exact: true })).toBeVisible();
      expect(activationRequests).toEqual([]);
    } finally {
      if (createdId) await deletePage(createdId);
    }
  });

  test("the More sheet and dock expose no serious accessibility violations", async ({ page }) => {
    await openEditor(page);
    await openMore(page);
    await injectAxe(page);
    const violations = await getViolations(page, `${PREVIEW}, [data-slot="sheet-content"]`, {
      runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] },
      rules: { "color-contrast": { enabled: false } },
    });
    expect(violations.filter((violation) => violation.impact === "serious" || violation.impact === "critical")).toEqual(
      [],
    );
  });
});
