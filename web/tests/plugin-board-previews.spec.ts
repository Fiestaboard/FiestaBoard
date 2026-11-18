/**
 * Board previews in the plugin marketplace.
 *
 * The marketplace used to describe a plugin without ever showing what it puts
 * on a board — the public directory at fiestaboard.app/plugins always has. These
 * cover the two surfaces that closed that gap:
 *   - registry entries carry `teaser` / `previews` (seeded from
 *     plugin-previews.json for plugins that aren't installed)
 *   - marketplace cards render the teaser strip
 *   - the detail page leads with a board hero, switchable by shape and colour
 */
import { type BoardPreviewEntry, messageToText, resolveDimensions } from "@fiestaboard/ui";
import type { Locator, Page } from "@playwright/test";

import { API_URL, configureBoard, expect, suppressWizard, test } from "./helpers";

type PreviewPlugin = { id: string; name: string; teaser: string; previews: BoardPreviewEntry[] };

/** A registry plugin that declares at least one preview, or null if none do. */
async function findPluginWithPreviews(): Promise<PreviewPlugin | null> {
  const res = await fetch(`${API_URL}/plugins/registry`);
  if (!res.ok) return null;
  const registry = await res.json();
  const entry = (registry.entries ?? []).find(
    (e: { previews?: unknown[]; teaser?: string }) => (e.previews?.length ?? 0) > 0 && !!e.teaser,
  );
  return entry ?? null;
}

async function expectNativePreview(page: Page, showcase: Locator, preview: BoardPreviewEntry) {
  const viewport = showcase.locator('[data-slot="board-viewport"]');
  const board = showcase.getByRole("img", { name: /^Board display:/ });
  await expect(viewport).toHaveCount(1);
  await expect(viewport).toHaveAttribute("data-mode", "actual");
  await expect(board).toHaveCount(1);
  await expect(board).toBeVisible();
  // Decode the registry's declared markup through the public hardware grammar;
  // the route must pass this shape's whole message, not another tab's sample.
  const message = messageToText(preview.rows.join("\n"), preview.device_type, undefined, { extendedMarkup: true });
  await expect(board).toHaveAccessibleName(`Board display: ${message}`);
  const dimensions = resolveDimensions(
    preview.device_type ?? "flagship",
    preview.notes_wide ?? 1,
    preview.notes_tall ?? 1,
    preview.grid_rows,
    preview.grid_cols,
  );
  const rows = board.locator("[data-note-row]");
  await expect(rows).toHaveCount(dimensions.rows);
  await expect(rows.first().locator("[data-note-tile]")).toHaveCount(dimensions.cols);
  expect((await board.textContent())?.replace(/\s/g, "")).toBe(message.replace(/\s/g, ""));

  const scroller = viewport.locator('[data-slot="board-viewport-scroller"]');
  const tiles = rows.first().locator("[data-note-tile]");
  const scrolls = (await scroller.getAttribute("tabindex")) === "0";
  if (scrolls) {
    await scroller.focus();
    await page.keyboard.press("Home");
  }
  await expect
    .poll(async () => {
      const tile = await tiles.first().boundingBox();
      const slot = await scroller.boundingBox();
      return !!tile && !!slot && tile.x >= slot.x - 1;
    })
    .toBe(true);
  if (scrolls) await page.keyboard.press("End");
  await expect
    .poll(async () => {
      const tile = await tiles.last().boundingBox();
      const slot = await scroller.boundingBox();
      return !!tile && !!slot && tile.x + tile.width <= slot.x + slot.width + 1;
    })
    .toBe(true);
  if (scrolls) await page.keyboard.press("Home");
}

test.beforeEach(async ({ page }) => {
  await configureBoard();
  await suppressWizard(page);
  await page.addInitScript(() => sessionStorage.setItem("fiestaboard:boardPreviewMode", "actual"));
});

test.describe("Plugin board previews", () => {
  test("registry entries carry a teaser and previews", async () => {
    const res = await fetch(`${API_URL}/plugins/registry`);
    test.skip(!res.ok, "plugin registry unavailable");

    const registry = await res.json();
    const entries = registry.entries ?? [];
    test.skip(entries.length === 0, "no registry entries to check");

    // Every entry has the fields, even when a plugin predates the contract.
    for (const entry of entries) {
      expect(typeof entry.teaser).toBe("string");
      expect(Array.isArray(entry.previews)).toBe(true);
    }

    // The shipped seed covers the registry, so at least one is populated —
    // if this fails, plugin-previews.json didn't make it into the image.
    const withPreviews = entries.filter((e: { previews?: unknown[] }) => (e.previews?.length ?? 0) > 0);
    expect(withPreviews.length).toBeGreaterThan(0);

    const preview = withPreviews[0].previews[0];
    expect(Array.isArray(preview.rows)).toBe(true);
    expect(preview.rows.length).toBeGreaterThan(0);
  });

  test("marketplace cards show the board teaser strip", async ({ page }) => {
    const plugin = await findPluginWithPreviews();
    test.skip(!plugin, "no registry plugin declares a teaser");

    await page.goto("/integrations?tab=marketplace");
    await expect(page.getByRole("heading", { name: /integrations/i })).toBeVisible({ timeout: 15_000 });

    const teasers = page.locator("[data-slot='scaled-board-teaser'] [data-slot='board-teaser']");
    await expect(teasers.first()).toBeVisible({ timeout: 15_000 });

    // The strip is a split-flap rendering of the plugin's own teaser line, so
    // its accessible name carries the teaser text rather than a generic label.
    const label = await teasers.first().getAttribute("aria-label");
    expect(label?.trim().length ?? 0).toBeGreaterThan(0);
  });

  test("detail page leads with a board hero and switches board colour", async ({ page }) => {
    const plugin = await findPluginWithPreviews();
    test.skip(!plugin, "no registry plugin declares previews");

    await page.goto(`/integrations/${plugin!.id}`);

    const showcase = page.locator("[data-slot='board-showcase']");
    await expect(showcase).toBeVisible({ timeout: 15_000 });
    await expectNativePreview(page, showcase, plugin!.previews[0]);

    // The hero leads the plugin's page: the first block under its name
    // (the h2 the Integrations section's breadcrumb row puts above it).
    const showcaseBox = await showcase.boundingBox();
    const headingBox = await page.getByRole("heading", { level: 2 }).first().boundingBox();
    expect(showcaseBox!.y).toBeGreaterThan(headingBox!.y);

    // Board colour is a two-state toggle, seeded from the user's own board.
    await showcase.getByRole("button", { name: /black/i }).click();
    const bezel = showcase.locator('[data-slot="board-viewport-bezel"]');
    const blackColor = await bezel.evaluate((element) => getComputedStyle(element).backgroundColor);
    const whiteBoard = showcase.getByRole("button", { name: /white/i });
    await expect(whiteBoard).toBeVisible();
    await whiteBoard.click();
    await expect(whiteBoard).toHaveAttribute("aria-pressed", "true");
    await expect(bezel).not.toHaveCSS("background-color", blackColor);
  });

  test("detail page tabs between declared board shapes", async ({ page }) => {
    const res = await fetch(`${API_URL}/plugins/registry`);
    test.skip(!res.ok, "plugin registry unavailable");
    const registry = await res.json();
    const multi: PreviewPlugin | undefined = (registry.entries ?? []).find(
      (e: { previews?: unknown[] }) => (e.previews?.length ?? 0) > 1,
    );
    test.skip(!multi, "no registry plugin declares more than one board shape");

    await page.goto(`/integrations/${multi!.id}`);

    const showcase = page.locator("[data-slot='board-showcase']");
    await expect(showcase).toBeVisible({ timeout: 15_000 });

    const tabs = showcase.getByRole("tab");
    expect(await tabs.count()).toBeGreaterThan(1);
    await expectNativePreview(page, showcase, multi!.previews[0]);

    // Switching shape swaps the mounted board rather than adding a second one.
    await tabs.nth(1).click();
    await expect(tabs.nth(1)).toHaveAttribute("aria-selected", "true");
    await expectNativePreview(page, showcase, multi!.previews[1]);
  });
});
