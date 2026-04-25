import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright configuration for FiestaBoard E2E tests.
 *
 * Tests run against the unified container (same as production).
 * CI sets WORKER_URLS (comma-separated) for per-worker backend
 * isolation, enabling parallel execution across 4 workers.
 * Locally it defaults to http://localhost:4420 with 1 worker.
 *
 * Screenshot generation tests are always excluded in CI.
 *
 * Visual regression tests are excluded by default in CI and opt-in
 * via the RUN_VISUAL_REGRESSION env var, which is set by the dedicated
 * `visual-regression` job in `.github/workflows/ci.yml`. Baselines must
 * be committed to the repo for the comparison step to pass; the first
 * run uploads the generated snapshots as artifacts.
 */
const ciIgnore = ["**/generate-screenshots.spec.ts"];
if (!process.env.RUN_VISUAL_REGRESSION) {
  ciIgnore.push("**/visual-regression.spec.ts");
}

export default defineConfig({
  testDir: "./tests",
  outputDir: process.env.PLAYWRIGHT_OUTPUT_DIR || "playwright-test-results",
  testIgnore: process.env.CI ? ciIgnore : [],
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
