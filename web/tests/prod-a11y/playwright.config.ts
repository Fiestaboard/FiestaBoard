import { defineConfig } from "@playwright/test";
import path from "node:path";

import { campaign } from "./campaign";

const viewports = [
  { name: "desktop", width: 1280, height: 800, isMobile: false, hasTouch: false },
  { name: "medium", width: 900, height: 984, isMobile: false, hasTouch: false },
  { name: "phone-touch", width: 390, height: 844, isMobile: true, hasTouch: true },
];

export default defineConfig({
  testDir: ".",
  // .audit.ts deliberately stays outside the default *.spec.ts discovery.
  testMatch: "routes.audit.ts",
  outputDir: path.join(campaign.artifactDir, "results"),
  reporter: [["list"], ["json", { outputFile: path.join(campaign.artifactDir, "report.json") }]],
  workers: 1,
  fullyParallel: false,
  forbidOnly: true,
  retries: 0,
  timeout: 60_000,
  expect: { timeout: 15_000 },
  metadata: {
    campaign: campaign.kind,
    image: campaign.image,
    sourceSha: campaign.sourceSha,
    auth: campaign.auth,
    runId: campaign.runId,
    dataset: campaign.dataset,
    scope: "bounded settled-route survey; manual WCAG checks and full flows remain unrun",
  },
  // No webServer and no globalSetup: the parent provisions the isolated hub.
  use: {
    baseURL: campaign.baseURL,
    browserName: "chromium",
    locale: "en-US",
    timezoneId: "UTC",
    serviceWorkers: "block",
    reducedMotion: "no-preference",
    storageState: campaign.storageState,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: viewports.flatMap(({ name, width, height, isMobile, hasTouch }) =>
    (["light", "dark"] as const).map((colorScheme) => ({
      name: `${name}-${colorScheme}`,
      use: { viewport: { width, height }, screen: { width, height }, isMobile, hasTouch, colorScheme },
    })),
  ),
});
