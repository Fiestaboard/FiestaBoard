import { defineConfig, devices } from "@playwright/test";
export default defineConfig({
  testDir: "./tests",
  testMatch: "device-sign-in.spec.ts",
  workers: 1,
  fullyParallel: false,
  timeout: 30000,
  reporter: process.env.CI ? [["github"], ["json", { outputFile: "playwright-device-report.json" }]] : [["list"]],
  outputDir: "playwright-device-test-results",
  use: {
    baseURL: process.env.BASE_URL ?? "http://127.0.0.1:4430",
    ...devices["Desktop Chrome"],
    screenshot: "only-on-failure",
  },
  webServer: { command: "node tests/device-sign-in-server.mjs", port: 4430, reuseExistingServer: false },
});
