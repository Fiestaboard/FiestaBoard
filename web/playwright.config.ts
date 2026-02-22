import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright configuration for FiestaBoard integration tests.
 *
 * These tests exercise the full stack:
 *   Mock Vestaboard API (port 7000)  ←  FastAPI backend (port 8000)  ←  Next.js UI (port 3000)  ←  Playwright browser
 *
 * The tests are designed to run in CI (merge queue) but can also be run locally.
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
    /* Base URL points to the Next.js dev server */
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

  /* Start all three servers before tests run */
  webServer: [
    {
      /* 1. Mock Vestaboard board API (ports 7000, 7001 for multi-board e2e) */
      command: "python ../integration-tests/mock-board/server.py",
      port: 7000,
      reuseExistingServer: true,
      env: { PORTS: "7000,7001" },
    },
    {
      /* 2. FastAPI backend — cwd is ".." (repo root) so uvicorn can find src.api_server */
      command:
        "uvicorn src.api_server:app --host 0.0.0.0 --port 8000",
      port: 8000,
      cwd: "..",
      reuseExistingServer: true,
      env: {
        PYTHONPATH: "..",
        FIESTA_API_URL: "http://localhost:8000",
      },
    },
    {
      /* 3. Next.js UI dev server */
      command: "npm run dev",
      port: 3000,
      reuseExistingServer: true,
      timeout: 120_000,
    },
  ],
});
