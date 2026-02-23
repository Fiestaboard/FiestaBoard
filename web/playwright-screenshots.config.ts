import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  testMatch: "generate-screenshots.spec.ts",
  outputDir: "./screenshot-results",
  fullyParallel: false,
  forbidOnly: false,
  retries: 0,
  workers: 1,
  reporter: "list",
  timeout: 120_000,

  use: {
    baseURL: "http://localhost:4420",
    trace: "off",
    screenshot: "off",
    viewport: { width: 1280, height: 800 },
    colorScheme: "dark",
  },

  projects: [
    {
      name: "screenshots",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
