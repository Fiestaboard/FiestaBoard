import { fileURLToPath } from "node:url";

import { defineConfig } from "@playwright/test";

const port = Number(process.env.WEB_LAYOUT_PORT ?? 4398);

export default defineConfig({
  testDir: ".",
  testMatch: "*.spec.ts",
  workers: 1,
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    screenshot: "only-on-failure",
    launchOptions: { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH },
  },
  webServer: {
    cwd: fileURLToPath(new URL("../../", import.meta.url)),
    command: `node node_modules/vite/bin/vite.js --config tests/layout/vite.config.ts --host 127.0.0.1 --port ${port} --strictPort`,
    url: `http://127.0.0.1:${port}/tests/layout/`,
    reuseExistingServer: false,
  },
});
