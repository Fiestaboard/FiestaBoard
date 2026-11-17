import { expect, type Page, test } from "@playwright/test";

import { attachJson, auditDocument } from "./audit";
import { campaign } from "./campaign";

const blockedWrites = new WeakMap<Page, string[]>();

test.beforeEach(async ({ page, context }, testInfo) => {
  const writes: string[] = [];
  blockedWrites.set(page, writes);
  // Browsing a route must not configure a hub, drive a board or mutate data.
  await context.route("**/*", async (route) => {
    const request = route.request();
    if (!["GET", "HEAD", "OPTIONS"].includes(request.method())) {
      writes.push(`${request.method()} ${new URL(request.url()).pathname}`);
      await route.abort("blockedbyclient");
      return;
    }
    await route.continue();
  });
  const dark = testInfo.project.use.colorScheme === "dark";
  await context.addCookies([{ name: "NEXT_LOCALE", value: "en", url: campaign.baseURL }]);
  await page.addInitScript((theme) => {
    localStorage.setItem("theme", theme);
    localStorage.setItem("fiestaboard_wizard_complete", "true");
  }, dark ? "dark" : "light");

  const authResponse = await page.request.get("/api/auth/status");
  expect(authResponse.ok(), "Synthetic hub auth precondition must be reachable").toBe(true);
  const auth = (await authResponse.json()) as { enabled: boolean; authenticated: boolean; setup_required: boolean };
  expect(auth.setup_required, "Provision synthetic auth before running the survey").toBe(false);
  expect(auth.enabled, "Runtime auth mode must match campaign metadata").toBe(campaign.auth === "authenticated");
  if (campaign.auth === "authenticated") expect(auth.authenticated).toBe(true);
  await attachJson(testInfo, "campaign-preflight.json", {
    campaign: campaign.kind,
    runId: campaign.runId,
    image: campaign.image,
    declaredSourceSha: campaign.sourceSha,
    dataset: campaign.dataset,
    auth: { enabled: auth.enabled, authenticated: auth.authenticated, setupRequired: auth.setup_required },
    limits: "Image/source values are operator-supplied provenance; pair with actual Docker inspection evidence.",
  });
});

test.afterEach(async ({ page }, testInfo) => {
  const writes = blockedWrites.get(page) ?? [];
  await attachJson(testInfo, "blocked-browser-writes.json", writes);
  if (testInfo.status !== testInfo.expectedStatus && !page.isClosed()) {
    await attachJson(testInfo, "failure-state.json", {
      url: page.url(),
      title: await page.title(),
      outcome: "FAIL; inspect error to distinguish readiness precondition from an axe finding",
    });
    await testInfo.attach("failure-state.png", {
      body: await page.screenshot({ fullPage: true }),
      contentType: "image/png",
    });
  }
  expect(writes, "Unexpected browser mutation was blocked; this state is not a valid read-only survey").toEqual([]);
});

const routes = [
  { path: "/", title: "Home", api: ["/api/settings/board", "/api/v1/pages"] },
  { path: "/pages", title: "Pages", api: ["/api/v1/pages"] },
  { path: "/collections", title: "Collections", api: ["/api/v1/collections"] },
  { path: "/schedule", title: "Schedule", api: ["/api/v1/schedules"] },
  { path: "/displays", title: "Displays", api: ["/api/settings/board"] },
  { path: "/integrations", title: "Integrations", api: ["/api/plugins", "/api/plugins/registry"] },
  { path: "/settings", title: "Settings", api: ["/api/settings/board"] },
  { path: "/picks", title: "Staff Picks", api: ["/api/staff-picks"] },
  { path: "/debug", title: "Monitor", api: [] },
];

for (const scenario of routes) {
  test(`settled route ${scenario.path}`, async ({ page }, testInfo) => {
    const setupResponse = await page.request.get("/api/config/validate");
    expect(setupResponse.ok()).toBe(true);
    const setup = (await setupResponse.json()) as { is_first_run: boolean };
    expect(
      setup.is_first_run,
      "This survey requires an already configured synthetic hub; setup is a separate campaign",
    ).toBe(false);

    const responses = scenario.api.map((apiPath) =>
      page.waitForResponse(
        (response) => new URL(response.url()).pathname === apiPath && response.request().method() === "GET",
      ),
    );
    const [navigation, ...apiResponses] = await Promise.all([page.goto(scenario.path), ...responses]);
    expect(navigation?.ok(), "Route document must load successfully").toBe(true);
    await expect(page).toHaveURL(new URL(scenario.path, campaign.baseURL).href);
    const responseEvidence = [];
    for (const response of apiResponses) {
      expect(response?.ok(), `Required route API ${response?.url()} must succeed`).toBe(true);
      if (!response) throw new Error("Missing route API response");
      await response.finished();
      const payload: unknown = await response.json();
      expect(payload !== null && typeof payload === "object", "Route API must return JSON data").toBe(true);
      responseEvidence.push({ path: new URL(response.url()).pathname, status: response.status() });
    }
    await expect(page.getByRole("heading", { name: scenario.title, exact: true }).first()).toBeVisible();
    await auditDocument(page, testInfo, {
      kind: "unmocked-settled-route",
      path: scenario.path,
      dataset: campaign.dataset,
      successfulRequiredResponses: responseEvidence,
      coverage: "Current seeded state only; not empty/populated/error/dialog flow coverage.",
    });
  });
}

const panelScenarios = [
  { id: "not-found", status: 404, body: { detail: "Panel not found" }, text: "This panel no longer exists" },
  {
    id: "no-display-selection",
    status: 404,
    body: { detail: "No display panel selected" },
    text: "No panel is set as the display output",
  },
];

for (const scenario of panelScenarios) {
  test(`synthetic Panel ${scenario.id}`, async ({ page }, testInfo) => {
    const panelPath = `/panel/prod-a11y-${scenario.id}`;
    let requests = 0;
    await page.route(
      (url) => url.pathname === `/api${panelPath}` || url.pathname === `/api${panelPath}/frame`,
      async (route) => {
        if (route.request().method() !== "GET") {
          await route.fallback();
          return;
        }
        requests += 1;
        await route.fulfill({
          status: scenario.status,
          contentType: "application/json",
          body: JSON.stringify(scenario.body),
        });
      },
    );
    await page.goto(panelPath);
    await expect(page).toHaveURL(new URL(panelPath, campaign.baseURL).href);
    await expect(page.getByTestId("panel-scene")).toBeVisible();
    await expect(page.getByText(scenario.text, { exact: true })).toBeVisible();
    expect(requests, "Synthetic API fixture must actually be reached").toBeGreaterThan(0);
    await auditDocument(page, testInfo, {
      kind: "synthetic-browser-api-state",
      path: panelPath,
      fixture: { status: scenario.status, body: scenario.body },
      coverage: "Published/candidate UI bundle with browser-intercepted Panel API; not backend error behavior.",
    });
  });
}
