import { defineConfig, devices } from "@playwright/test";

/**
 * Video-recording config for the draw-mode demo walkthrough.
 *
 * Runs only tests/draw-mode-demo.spec.ts (excluded from the main suite via
 * playwright.config.ts testIgnore) and records a .webm of the full flow.
 * Run with: npx playwright test --config playwright-video.config.ts
 */
export default defineConfig({
  testDir: "./tests",
  testMatch: "draw-mode-demo.spec.ts",
  outputDir: "./draw-mode-demo-results",
  fullyParallel: false,
  retries: 0,
  workers: 1,
  reporter: "list",
  timeout: 180_000,
  globalSetup: "./tests/global-setup.ts",
  use: {
    baseURL: process.env.BASE_URL || "http://localhost:4420",
    trace: "off",
    screenshot: "off",
    viewport: { width: 1280, height: 800 },
    video: { mode: "on", size: { width: 1280, height: 800 } },
  },
  projects: [{ name: "draw-demo", use: { ...devices["Desktop Chrome"] } }],
});
