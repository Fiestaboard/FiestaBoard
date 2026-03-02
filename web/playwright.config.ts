import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright configuration for FiestaBoard E2E tests.
 *
 * Tests run against the unified container (same as production).
 * CI sets WORKER_URLS (comma-separated) for per-worker backend
 * isolation, enabling parallel execution across 4 workers.
 * Locally it defaults to http://localhost:4420 with 1 worker.
 *
 * Screenshot generation tests are excluded in CI since they're for
 * docs, not functional validation.
 */
export default defineConfig({
  testDir: "./tests",
  outputDir: process.env.PLAYWRIGHT_OUTPUT_DIR || "playwright-test-results",
  testIgnore: process.env.CI ? ["**/generate-screenshots.spec.ts"] : [],
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: process.env.CI ? 4 : 1,
  reporter: process.env.CI ? "github" : "list",
  timeout: 30_000,
  globalSetup: "./tests/global-setup.ts",

  use: {
    baseURL: process.env.BASE_URL || "http://localhost:4420",
    trace: "off",
    screenshot: "only-on-failure",
  },

  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
