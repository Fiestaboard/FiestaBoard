import { expect, type Page, test } from "@playwright/test";

import { mockHub } from "./creator-ide-hub";

// Editor UX FP-1b: the header and save model. D8 (DD-W157): one breakpoint at
// 1280; labels never change with the width, the primary keeps its words, Save /
// Save draft and Export are icon + tooltip at 1024–1279, and an open Explorer
// overlays the template there. D6 (DD-W158): Figma's two pairs. UX-1-5: the
// rename ring hugs the name. UX-8-2: editor toasts bottom-right, under modals.

async function openEditor(page: Page, width: number, options: { notScheduled?: boolean } = {}) {
  await mockHub(page, options);
  await page.setViewportSize({ width, height: width >= 1440 ? 900 : width >= 1280 ? 800 : 768 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto(`/tests/layout/editor-window.html?${new URLSearchParams({ path: "/pages/edit/kitchen-morning" })}`);
  await expect(page.getByRole("textbox", { name: /page name/i })).toHaveValue("Kitchen morning");
}

const header = (page: Page) => page.locator('[data-slot="card-header"]').first();

for (const notScheduled of [false, true]) {
  const [secondary, primary] = notScheduled ? ["Save", "Show now"] : ["Save draft", "Save & update board"];
  test(`${notScheduled ? "not live" : "live"}: Export · ${secondary} · ${primary}, labels by width (D6, D8)`, async ({
    page,
  }) => {
    await openEditor(page, 1440, { notScheduled });
    const primaryButton = header(page).getByRole("button", { name: primary });
    await expect(primaryButton).toBeVisible();
    // 1440: every button labelled, in Figma's order, and no ⚡ Shortcuts.
    const labels = (await header(page).getByRole("button").allInnerTexts()).map((text) => text.trim()).filter(Boolean);
    expect(labels.slice(-3)).toEqual(["Export", secondary, primary]);
    await expect(header(page).getByRole("button", { name: /shortcuts/i })).toHaveCount(0);

    for (const width of [1279, 1024]) {
      await page.setViewportSize({ width, height: 768 });
      // The primary keeps its full words; "Update" is retired.
      await expect(primaryButton).toHaveText(primary);
      await expect(header(page)).not.toContainText(/\bUpdate\b/);
      // Save / Save draft and Export are icons, named and with a tooltip.
      const save = header(page).getByRole("button", { name: notScheduled ? "Save Page" : "Save draft" });
      const exportButton = header(page).getByRole("button", { name: "Export Page" });
      await expect(save).toHaveText("");
      await expect(exportButton).toHaveText("");
      await save.hover();
      await expect(page.locator('[data-slot="tooltip-content"]').last()).toContainText(
        notScheduled ? "Save Page" : "Save draft",
      );
      const box = (await primaryButton.boundingBox())!;
      expect(box.x + box.width).toBeLessThanOrEqual(width);
      expect((await page.locator('[data-slot="page-editor-name"]').boundingBox())!.width).toBeGreaterThanOrEqual(240);
    }
    await page.setViewportSize({ width: 1280, height: 800 });
    await expect(header(page).getByRole("button", { name: "Export Page" })).toHaveText("Export");
  });
}

test("1024–1279: an open Explorer overlays the template; from 1280 it is a column (D8)", async ({ page }) => {
  await openEditor(page, 1024);
  const template = page.locator('[data-slot="page-editor-template-column"]');
  const before = (await template.boundingBox())!;
  await page.getByRole("button", { name: "Explorer", exact: true, pressed: false }).click();
  const explorer = page.getByRole("navigation", { name: "Explorer" });
  await expect(explorer).toBeVisible();
  const after = (await template.boundingBox())!;
  // The template neither moves nor narrows; the Explorer lies over it.
  expect(after.x).toBe(before.x);
  expect(after.width).toBe(before.width);
  const panel = (await explorer.boundingBox())!;
  expect(panel.x + panel.width).toBeGreaterThan(after.x + 40);
  await page.setViewportSize({ width: 1440, height: 900 });
  const wide = (await template.boundingBox())!;
  const widePanel = (await explorer.boundingBox())!;
  expect(widePanel.x + widePanel.width).toBeLessThanOrEqual(wide.x);
});

test("rename: the ring hugs the name, the meta line stays outside it (UX-1-5)", async ({ page }) => {
  await openEditor(page, 1440);
  const name = page.getByRole("textbox", { name: /page name/i });
  await name.click();
  const field = (await name.boundingBox())!;
  const meta = (await page.getByTestId("page-editor-meta").boundingBox())!;
  expect(field.height).toBeLessThanOrEqual(32);
  expect(field.y + field.height).toBeLessThanOrEqual(meta.y);
  // "Kitchen morning" at 24 px is far narrower than the 600 px+ the field used to take.
  expect(field.width).toBeLessThan(320);
  await page.keyboard.type(" x");
  await page.keyboard.press("Escape");
  await expect(name).toHaveValue("Kitchen morning");
  await expect(name).not.toBeFocused();
});

test("editor toasts sit bottom-right, under the modal layer (UX-8-2)", async ({ page }) => {
  await openEditor(page, 1440);
  await page.getByRole("button", { name: "Save & update board" }).click();
  const toaster = page.locator("[data-sonner-toaster]");
  await expect(toaster).toHaveAttribute("data-y-position", "bottom");
  await expect(toaster).toHaveAttribute("data-x-position", "right");
  const [toastZ, modalZ] = await toaster.evaluate((el) => [
    Number(getComputedStyle(el).zIndex),
    Number(getComputedStyle(document.documentElement).getPropertyValue("--z-modal")),
  ]);
  expect(toastZ).toBeLessThan(modalZ);
});
