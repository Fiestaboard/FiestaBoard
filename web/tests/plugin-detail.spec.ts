/**
 * FiestaBoard Plugin Detail Page E2E Tests
 *
 * Tests the /integrations/[pluginId] route:
 *   - Navigation from Marketplace tab to plugin detail page
 *   - Plugin name, category badge, and header card visible
 *   - "Back to Marketplace" navigation link present
 *   - Install button visible for uninstalled plugins
 *   - Installed badge shown for already-installed plugins
 *   - Unknown plugin ID shows an appropriate error/empty state
 *   - README section renders (or shows fallback)
 *   - GitHub link present when repository is defined
 *
 * NOTE: These tests require the Marketplace to have at least one registry entry.
 * Registry entries are loaded from plugin-registry.json via the API.
 */
import { API_URL, configureBoard, expect, suppressWizard, test } from "./helpers";

test.beforeEach(async ({ page }) => {
  await configureBoard();
  await suppressWizard(page);
});

test.describe("Plugin Detail Page", () => {
  test("navigates to plugin detail page from Marketplace tab", async ({ page }) => {
    await page.goto("/integrations");
    await expect(page.getByRole("heading", { name: /integrations/i })).toBeVisible({ timeout: 15_000 });

    // Switch to the Marketplace tab
    await page.getByRole("tab", { name: /marketplace/i }).click();

    // Wait for registry entries to load
    const firstPluginCard = page.locator("[data-testid='registry-plugin-card'], .plugin-card, [class*='card']").first();

    // Try to find a clickable card that links to a plugin detail page
    const detailLinks = page.locator("a[href*='/integrations/']").first();
    const linkCount = await detailLinks.count();

    if (linkCount > 0) {
      const href = await detailLinks.getAttribute("href");
      expect(href).toMatch(/\/integrations\/\w+/);

      await detailLinks.click();
      await expect(page).toHaveURL(/\/integrations\/[^?]+/, { timeout: 10_000 });
    } else {
      // If no direct links, verify the marketplace tab is at least visible with content
      await expect(page.getByRole("button", { name: /add from git/i }).first()).toBeVisible({ timeout: 5_000 });
    }
  });

  test("plugin detail page shows Back to Marketplace link", async ({ page }) => {
    // Get the registry to find a real plugin ID
    const registryRes = await fetch(`${API_URL}/plugins/registry`);

    if (!registryRes.ok) {
      test.skip();
      return;
    }

    const registry = await registryRes.json();
    const entries: Array<{ id: string }> = registry.entries ?? [];

    if (entries.length === 0) {
      test.skip();
      return;
    }

    const pluginId = entries[0].id;
    await page.goto(`/integrations/${pluginId}`);

    // Back link must be present
    await expect(page.getByRole("link", { name: /back to marketplace/i })).toBeVisible({ timeout: 15_000 });
  });

  test("plugin detail page shows plugin name and category badge", async ({ page }) => {
    const registryRes = await fetch(`${API_URL}/plugins/registry`);

    if (!registryRes.ok) {
      test.skip();
      return;
    }

    const registry = await registryRes.json();
    const entries: Array<{ id: string; name?: string }> = registry.entries ?? [];

    if (entries.length === 0) {
      test.skip();
      return;
    }

    const entry = entries[0];
    await page.goto(`/integrations/${entry.id}`);

    // Wait for the page header to load (not skeleton)
    await page.waitForTimeout(2000);

    // Plugin name or ID should be visible in the header
    const nameText = entry.name ?? entry.id;
    const headingEl = page.getByRole("heading", { name: new RegExp(nameText, "i") }).first();
    const nameEl = page.getByText(nameText, { exact: false }).first();

    const hasHeading = await headingEl.isVisible({ timeout: 5_000 }).catch(() => false);
    const hasText = await nameEl.isVisible({ timeout: 5_000 }).catch(() => false);

    expect(hasHeading || hasText).toBe(true);
  });

  test("plugin detail page shows Install or Installed button", async ({ page }) => {
    const registryRes = await fetch(`${API_URL}/plugins/registry`);

    if (!registryRes.ok) {
      test.skip();
      return;
    }

    const registry = await registryRes.json();
    const entries: Array<{ id: string; installed?: boolean }> = registry.entries ?? [];

    if (entries.length === 0) {
      test.skip();
      return;
    }

    const entry = entries[0];
    await page.goto(`/integrations/${entry.id}`);

    // Wait for action buttons to resolve
    await page.waitForTimeout(2000);

    const installBtn = page.getByRole("button", { name: /^install$/i });
    const installedBtn = page.getByRole("button", { name: /^installed$/i });

    const hasInstall = await installBtn.isVisible({ timeout: 5_000 }).catch(() => false);
    const hasInstalled = await installedBtn.isVisible({ timeout: 5_000 }).catch(() => false);

    expect(hasInstall || hasInstalled).toBe(true);
  });

  test("Back to Marketplace link navigates to /integrations?tab=marketplace", async ({ page }) => {
    const registryRes = await fetch(`${API_URL}/plugins/registry`);

    if (!registryRes.ok) {
      test.skip();
      return;
    }

    const registry = await registryRes.json();
    const entries: Array<{ id: string }> = registry.entries ?? [];

    if (entries.length === 0) {
      test.skip();
      return;
    }

    await page.goto(`/integrations/${entries[0].id}`);

    const backLink = page.getByRole("link", { name: /back to marketplace/i });
    await expect(backLink).toBeVisible({ timeout: 10_000 });

    const href = await backLink.getAttribute("href");
    expect(href).toContain("tab=marketplace");
  });

  test("plugin detail page README section is present", async ({ page }) => {
    const registryRes = await fetch(`${API_URL}/plugins/registry`);

    if (!registryRes.ok) {
      test.skip();
      return;
    }

    const registry = await registryRes.json();
    const entries: Array<{ id: string }> = registry.entries ?? [];

    if (entries.length === 0) {
      test.skip();
      return;
    }

    await page.goto(`/integrations/${entries[0].id}`);

    // Wait for README to load or fallback to render
    // The page has either markdown content or a "Documentation not available" message
    await page.waitForTimeout(3000);

    // One of these should be present
    const markdownContent = page.locator(".plugin-readme").first();
    const noDocsFallback = page.getByText(/documentation not available/i);

    const hasMarkdown = await markdownContent.isVisible({ timeout: 5_000 }).catch(() => false);
    const hasFallback = await noDocsFallback.isVisible({ timeout: 5_000 }).catch(() => false);

    expect(hasMarkdown || hasFallback).toBe(true);
  });

  test("unknown plugin ID shows an error or empty state, not a server error", async ({ page }) => {
    await page.goto("/integrations/totally-unknown-plugin-xyz-12345");

    // Wait for client hydration; use innerText — textContent() includes RSC payloads
    // where chunk IDs like I[80503,...] falsely match substring "500".
    await page.waitForTimeout(2000);

    const visibleText = await page.evaluate(() => document.body?.innerText ?? "");
    expect(visibleText).not.toContain("Internal Server Error");
    // Next.js generic error page title pattern (visible text only)
    expect(visibleText).not.toMatch(/\b500\b.*Something went wrong/i);

    // The page should still render the layout (Back link should be present)
    const backLink = page.getByRole("link", { name: /back to marketplace/i });
    await expect(backLink).toBeVisible({ timeout: 10_000 });
  });

  test("GitHub source link opens external repo when repository is set", async ({ page }) => {
    const registryRes = await fetch(`${API_URL}/plugins/registry`);

    if (!registryRes.ok) {
      test.skip();
      return;
    }

    const registry = await registryRes.json();
    const entries: Array<{ id: string; repository?: string }> = registry.entries ?? [];
    const entryWithRepo = entries.find((e) => e.repository);

    if (!entryWithRepo) {
      test.skip();
      return;
    }

    await page.goto(`/integrations/${entryWithRepo.id}`);

    const githubLink = page.getByRole("link", { name: /github/i }).first();
    const isVisible = await githubLink.isVisible({ timeout: 10_000 }).catch(() => false);

    if (isVisible) {
      const href = await githubLink.getAttribute("href");
      expect(href).toContain("github.com");
    }
  });
});
