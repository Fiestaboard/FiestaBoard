import { fileURLToPath } from "node:url";

import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: ".",
  testMatch: "*.spec.ts",
  workers: 1,
  use: {
    baseURL: "http://127.0.0.1:4398",
    screenshot: "only-on-failure",
    launchOptions: { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH },
  },
  webServer: {
    cwd: fileURLToPath(new URL("../../", import.meta.url)),
    command:
      "node node_modules/vite/bin/vite.js --config tests/layout/vite.config.ts --host 127.0.0.1 --port 4398 --strictPort",
    url: "http://127.0.0.1:4398/tests/layout/",
    reuseExistingServer: false,
  },
});
