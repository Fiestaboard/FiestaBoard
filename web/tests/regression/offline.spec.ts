/**
 * Auto-generated regression stubs from .claude/ux-coverage.json.
 * Subarea: offline (disconnected / reconnecting indicators)
 */
import { configureBoard, ensureAuthForFetch, expect, loginIfNeeded, slowRoute, test } from "../helpers";

test.beforeEach(async ({ context, page }) => {
  await ensureAuthForFetch();
  await loginIfNeeded(context);
  await configureBoard();
  await page.addInitScript(() => {
    localStorage.setItem("fiestaboard_wizard_complete", "true");
  });
});

test.describe("regression: offline", () => {
  /**
   * UX node: offline.disconnected
   * Route: (any) global offline indicator
   * Preconditions: navigator.onLine:false OR api-heartbeat:failed
   * Expected: offline banner/toast surfaces; queued mutations indicated
   * Source refs: web/src/components/offline/*
   * Coverage status: uncovered
   */
  test("offline.disconnected — offline indicator surfaces on disconnect", async ({ page }) => {
    // The /offline route is the PWA's offline fallback page. It reads
    // navigator.onLine on mount; when offline it names this device and
    // retains the Try again action.
    await page.addInitScript(() => {
      Object.defineProperty(navigator, "onLine", {
        configurable: true,
        get: () => false,
      });
    });
    await page.goto("/offline");

    await expect(page.getByRole("heading", { level: 1, name: "You’re offline" })).toBeVisible({ timeout: 15_000 });

    // Try Again CTA only appears in the disconnected state — verifies we
    // aren't accidentally seeing the reconnecting state.
    await expect(page.getByRole("button", { name: /try again/i })).toBeVisible();
  });

  /**
   * UX node: offline.reconnecting
   * Route: (any) global offline indicator
   * Preconditions: heartbeat:retrying
   * Expected: 'Reconnecting...' indicator; clears once heartbeat succeeds
   * Source refs: web/src/components/offline/*
   * Coverage status: uncovered
   */
  test("offline.reconnecting — reconnecting indicator surfaces when connection is restored", async ({ page }) => {
    // Mount the offline page while offline, then flip navigator.onLine to
    // true and dispatch the 'online' event. Hold the real health request
    // so the labelled reconnecting spinner can be observed before Home.
    await page.addInitScript(() => {
      Object.defineProperty(navigator, "onLine", {
        configurable: true,
        get: () => false,
      });
    });
    await page.goto("/offline");

    await expect(page.getByRole("heading", { level: 1, name: "You’re offline" })).toBeVisible({ timeout: 15_000 });

    const releaseHealth = await slowRoute(page, "**/api/health");

    // Flip to online and fire the event the listener is bound to.
    await page.evaluate(() => {
      Object.defineProperty(navigator, "onLine", {
        configurable: true,
        get: () => true,
      });
      window.dispatchEvent(new Event("online"));
    });

    await expect(page.getByRole("status").filter({ hasText: "Reconnecting…" })).toBeVisible({ timeout: 5_000 });

    // Try Again button is gone in the reconnecting state.
    await expect(page.getByRole("button", { name: /try again/i })).toHaveCount(0);

    releaseHealth();
    await expect(page).toHaveURL(/\/$/, { timeout: 15_000 });
    await expect(page.getByRole("status").filter({ hasText: "Reconnecting…" })).toHaveCount(0);
  });
});
