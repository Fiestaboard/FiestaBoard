import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright configuration for FiestaBoard integration tests.
 *
 * Tests run against the unified container (same as production) on port 3000.
 * CI workflows build the Docker image, start the container + mock board,
 * then invoke Playwright. Locally, start the dev container first:
 *   docker-compose -f docker-compose.dev.yml up -d
 */
export default defineConfig({
  testDir: "./tests",
  outputDir: process.env.PLAYWRIGHT_OUTPUT_DIR || "playwright-test-results",
  fullyParallel: false, // Run tests sequentially – they share backend state
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: process.env.CI ? "github" : "list",
  timeout: 60_000,
  globalSetup: "./tests/global-setup.ts",

  use: {
    baseURL: "http://localhost:3000",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },

  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
