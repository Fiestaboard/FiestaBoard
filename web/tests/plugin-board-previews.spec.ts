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
import { API_URL, configureBoard, expect, suppressWizard, test } from "./helpers";

/** A registry plugin that declares at least one preview, or null if none do. */
async function findPluginWithPreviews(): Promise<{ id: string; name: string; teaser: string } | null> {
  const res = await fetch(`${API_URL}/plugins/registry`);
  if (!res.ok) return null;
  const registry = await res.json();
  const entry = (registry.entries ?? []).find(
    (e: { previews?: unknown[]; teaser?: string }) => (e.previews?.length ?? 0) > 0 && !!e.teaser,
  );
  return entry ? { id: entry.id, name: entry.name, teaser: entry.teaser } : null;
}

test.beforeEach(async ({ page }) => {
  await configureBoard();
  await suppressWizard(page);
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
    await expect(showcase.locator("[data-slot='static-board-display']")).toBeVisible();

    // The hero sits above the header card, the way the public directory leads.
    const showcaseBox = await showcase.boundingBox();
    const headingBox = await page.getByRole("heading", { level: 1 }).first().boundingBox();
    expect(showcaseBox!.y).toBeLessThan(headingBox!.y);

    // Board colour is a two-state toggle, seeded from the user's own board.
    const whiteBoard = showcase.getByRole("button", { name: /white/i });
    await expect(whiteBoard).toBeVisible();
    await whiteBoard.click();
    await expect(whiteBoard).toHaveAttribute("aria-pressed", "true");
  });

  test("detail page tabs between declared board shapes", async ({ page }) => {
    const res = await fetch(`${API_URL}/plugins/registry`);
    test.skip(!res.ok, "plugin registry unavailable");
    const registry = await res.json();
    const multi = (registry.entries ?? []).find((e: { previews?: unknown[] }) => (e.previews?.length ?? 0) > 1);
    test.skip(!multi, "no registry plugin declares more than one board shape");

    await page.goto(`/integrations/${multi.id}`);

    const showcase = page.locator("[data-slot='board-showcase']");
    await expect(showcase).toBeVisible({ timeout: 15_000 });

    const tabs = showcase.getByRole("tab");
    expect(await tabs.count()).toBeGreaterThan(1);

    // Switching shape swaps the mounted board rather than adding a second one.
    await tabs.nth(1).click();
    await expect(tabs.nth(1)).toHaveAttribute("aria-selected", "true");
    await expect(showcase.locator("[data-slot='static-board-display']")).toHaveCount(1);
  });
});
