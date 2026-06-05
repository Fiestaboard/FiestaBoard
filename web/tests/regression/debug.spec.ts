/**
 * Auto-generated regression stubs from .claude/ux-coverage.json.
 * Subarea: debug
 */
import { configureBoard, ensureAuthForFetch, expect, loginIfNeeded, test } from "../helpers";

test.beforeEach(async ({ context, page }) => {
  await ensureAuthForFetch();
  await loginIfNeeded(context);
  await configureBoard();
  await page.addInitScript(() => {
    localStorage.setItem("fiestaboard_wizard_complete", "true");
  });
});

test.describe("regression: debug", () => {
  /**
   * UX node: debug.monitor-removed
   * Route: /debug (or wherever the removed monitor surface used to live)
   * Preconditions: legacy monitor route hit
   * Expected: route either 404s gracefully or redirects to a replacement page —
   *           no stale 'monitor' UI is reachable
   * Source refs: web/src/app/debug/*
   * Coverage status: uncovered
   */
  test("debug.monitor-removed — removed monitor surface returns 404/redirect, not stale UI", async ({ page }) => {
    // The /debug page is a near-tombstone: it renders a "Monitoring Removed"
    // card explaining that in-container Prometheus/Grafana have been removed
    // and pointing users at `docker logs fiestaboard`. The intent of this
    // regression test is to make sure no stale monitor UI (charts, metrics,
    // dashboards) creeps back onto this route.
    await page.goto("/debug");

    // Tombstone heading is visible.
    await expect(page.getByRole("heading", { name: /monitoring removed/i })).toBeVisible({ timeout: 15_000 });

    // The replacement guidance points to docker logs — load-bearing.
    await expect(page.getByText(/docker logs fiestaboard/i)).toBeVisible();

    // Negative assertion for *active* monitor UI — the tombstone may still
    // *mention* prometheus/grafana to explain what was removed, so we only flag
    // an explicit "Open Dashboard" link as the regression signal.
    await expect(page.getByRole("link", { name: /open dashboard/i })).toHaveCount(0);
  });
});
