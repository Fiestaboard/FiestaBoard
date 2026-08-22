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
    // Docs shots must be deterministic. Without this, /settings' Animations
    // card runs a live demo board that cycles its message, so every run
    // produced a different DOM capture (and a PNG caught mid-flap). Reduced
    // motion settles every board immediately and hides that one motion demo —
    // which a static screenshot could never convey anyway. Verified not to
    // remove real board content: / and /pages still render all 132 tiles.
    reducedMotion: "reduce",
  },

  projects: [
    {
      name: "screenshots-dark",
      use: { ...devices["Desktop Chrome"], colorScheme: "dark" },
    },
    {
      name: "screenshots-light",
      use: { ...devices["Desktop Chrome"], colorScheme: "light" },
    },
  ],
});
