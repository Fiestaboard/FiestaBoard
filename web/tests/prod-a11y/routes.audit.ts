import { expect, type Page, type Request, type Response, test } from "@playwright/test";

import { attachJson, auditDocument } from "./audit";
import { campaign } from "./campaign";

interface NetworkLedger {
  blocked: string[];
  failed: string[];
  pendingApi: Set<Request>;
  apiResponses: { path: string; status: number }[];
  expectedErrors: Set<string>;
}

const networks = new WeakMap<Page, NetworkLedger>();

function jsonObject(value: unknown, label: string): Record<string, unknown> {
  expect(value !== null && typeof value === "object" && !Array.isArray(value), `${label} must be a JSON object`).toBe(
    true,
  );
  return value as Record<string, unknown>;
}

function assertEmpty(payload: Record<string, unknown>, key: "pages" | "collections") {
  expect(payload[key], `The complete ${key} dataset must be empty, not a display-filtered subset`).toEqual([]);
  expect(payload.total, `${key}.total must corroborate the empty dataset`).toBe(0);
}

async function preflightJson(page: Page, apiPath: string) {
  const url = new URL(apiPath, campaign.baseURL).href;
  const response = await page.request.get(url, { maxRedirects: 0 });
  expect(response.url(), "Preflight must remain on the exact same-origin API URL").toBe(url);
  expect(response.status(), "Preflight redirects and errors are unsupported").toBeGreaterThanOrEqual(200);
  expect(response.status(), "Preflight redirects and errors are unsupported").toBeLessThan(300);
  expect(response.headers()["content-type"]).toContain("application/json");
  return jsonObject(await response.json(), apiPath);
}

function waitForApi(page: Page, apiPath: string) {
  return page.waitForResponse((response) => {
    const url = new URL(response.url());
    return url.origin === campaign.baseURL && url.pathname === apiPath && response.request().method() === "GET";
  });
}

async function browserJson(response: Response, apiPath: string) {
  expect(new URL(response.url()).origin).toBe(campaign.baseURL);
  expect(new URL(response.url()).pathname).toBe(apiPath);
  expect(response.ok(), `Required browser API ${apiPath} must succeed`).toBe(true);
  await response.finished();
  expect(response.headers()["content-type"]).toContain("application/json");
  return jsonObject(await response.json(), apiPath);
}

async function settledNetwork(page: Page) {
  const ledger = networks.get(page)!;
  // Empty/static fixtures have no continuous stream. A pending request is a
  // readiness failure, never permission to scan a default/error branch.
  await page.waitForLoadState("networkidle");
  await expect.poll(() => ledger.pendingApi.size).toBe(0);
  expect(ledger.blocked, "Blocked HTTP requests invalidate this fixture").toEqual([]);
  expect(ledger.failed, "Failed HTTP requests invalidate this fixture").toEqual([]);
  expect(
    ledger.apiResponses.filter(({ path, status }) => status >= 300 && !ledger.expectedErrors.has(`${path}:${status}`)),
    "Unexpected browser API errors invalidate this settled state",
  ).toEqual([]);
}

test.beforeEach(async ({ page, context }, testInfo) => {
  const ledger: NetworkLedger = {
    blocked: [],
    failed: [],
    pendingApi: new Set(),
    apiResponses: [],
    expectedErrors: new Set(),
  };
  networks.set(page, ledger);
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.origin === campaign.baseURL && url.pathname.startsWith("/api/")) ledger.pendingApi.add(request);
  });
  page.on("requestfinished", (request) => ledger.pendingApi.delete(request));
  page.on("requestfailed", (request) => {
    ledger.pendingApi.delete(request);
    ledger.failed.push(`${request.method()} ${new URL(request.url()).origin}${new URL(request.url()).pathname}`);
  });
  page.on("response", (response) => {
    const url = new URL(response.url());
    if (url.origin === campaign.baseURL && url.pathname.startsWith("/api/")) {
      ledger.apiResponses.push({ path: url.pathname, status: response.status() });
    }
  });
  await context.route("**/*", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (!["http:", "https:"].includes(url.protocol)) {
      await route.continue();
      return;
    }
    const description = `${request.method()} ${url.origin}${url.pathname}`;
    if (url.origin !== campaign.baseURL || !["GET", "HEAD", "OPTIONS"].includes(request.method())) {
      ledger.blocked.push(description);
      await route.abort("blockedbyclient");
      return;
    }
    // Fetch without following redirects: a same-origin URL must not send the
    // browser (or the forwarding request) to an external origin unnoticed.
    try {
      const response = await route.fetch({ maxRedirects: 0 });
      if (response.status() >= 300 && response.status() < 400) {
        ledger.blocked.push(`${description} redirect ${response.status()}`);
        await route.abort("blockedbyclient");
        return;
      }
      await route.fulfill({ response });
    } catch {
      ledger.failed.push(description);
      await route.abort("failed");
    }
  });
  const dark = testInfo.project.use.colorScheme === "dark";
  await context.addCookies([{ name: "NEXT_LOCALE", value: "en", url: campaign.baseURL }]);
  await page.addInitScript((theme) => {
    localStorage.setItem("theme", theme);
    localStorage.setItem("fiestaboard_wizard_complete", "true");
    sessionStorage.removeItem("fiestaboard_pages_display_filter");
    localStorage.removeItem("fiestaboard_pages_view_mode");
    localStorage.removeItem("fiestaboard_collections_view_mode");
  }, dark ? "dark" : "light");

  const auth = await preflightJson(page, "/api/auth/status");
  expect(auth.setup_required, "Provision synthetic auth before the survey").toBe(false);
  expect(auth.enabled, "Runtime auth must match campaign metadata").toBe(campaign.auth === "authenticated");
  if (campaign.auth === "authenticated") expect(auth.authenticated).toBe(true);
  await attachJson(testInfo, "campaign-preflight.json", {
    campaign: campaign.kind,
    runId: campaign.runId,
    image: campaign.image,
    declaredSourceSha: campaign.sourceSha,
    dataset: campaign.dataset,
    auth: { enabled: auth.enabled, authenticated: auth.authenticated, setupRequired: auth.setup_required },
    limits: "Operator-declared image/source provenance requires separate actual-container inspection evidence.",
  });
});

test.afterEach(async ({ page }, testInfo) => {
  const ledger = networks.get(page);
  await attachJson(testInfo, "browser-network.json", {
    blocked: ledger?.blocked ?? [],
    failed: ledger?.failed ?? [],
    apiResponses: ledger?.apiResponses ?? [],
    pendingApi: [...(ledger?.pendingApi ?? [])].map((request) => new URL(request.url()).pathname),
    limits: "Browser HTTP forwarding only; does not constrain backend egress or prove OS-level isolation.",
  });
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
  expect(ledger?.blocked ?? [], "A blocked HTTP request invalidates this survey state").toEqual([]);
  expect(ledger?.failed ?? [], "A failed HTTP request invalidates this survey state").toEqual([]);
  expect(
    ledger?.apiResponses.filter(
      ({ path, status }) => status >= 300 && !ledger.expectedErrors.has(`${path}:${status}`),
    ) ?? [],
    "Unexpected API errors also invalidate the final captured state",
  ).toEqual([]);
});

const shellApis = [
  "/api/health",
  "/api/config/validate",
  "/api/settings/board",
  "/api/settings/all",
  "/api/settings/ai",
  "/api/plugins",
  "/api/system/update/status",
  "/api/system/update-check",
  "/api/settings/restore-notice",
];

const routes = [
  { path: "/pages", title: "Pages", marker: "No pages created yet.", kind: "empty-pages" },
  { path: "/collections", title: "Collections", marker: "No collections yet", kind: "empty-collections" },
  { path: "/debug", title: "Monitor", marker: "Monitoring Removed", kind: "monitor-tombstone" },
];

for (const scenario of routes) {
  test(`${scenario.kind} ${scenario.path}`, async ({ page }, testInfo) => {
    const setup = await preflightJson(page, "/api/config/validate");
    expect(setup.is_first_run, "This survey requires a configured synthetic hub").toBe(false);
    expect(setup.valid, "Invalid setup is a separate state, not this configured fixture").toBe(true);
    // Assert whole stores, before navigation: an empty display filter is not
    // this fixture and can still cause preview POSTs for other stored pages.
    assertEmpty(await preflightJson(page, "/api/v1/pages"), "pages");
    assertEmpty(await preflightJson(page, "/api/v1/collections"), "collections");

    const apiPaths = [
      ...shellApis,
      ...(testInfo.project.use.isMobile ? [] : ["/api/version", "/api/auth/status"]),
      ...(scenario.path === "/debug" ? [] : ["/api/v1/pages", "/api/v1/collections"]),
    ];
    const responses = apiPaths.map((apiPath) => waitForApi(page, apiPath));
    const [navigation, ...apiResponses] = await Promise.all([page.goto(scenario.path), ...responses]);
    expect(navigation?.ok(), "Route document must load successfully").toBe(true);
    await expect(page).toHaveURL(new URL(scenario.path, campaign.baseURL).href);
    const observed: Record<string, Record<string, unknown>> = {};
    for (let index = 0; index < apiPaths.length; index += 1) {
      const response = apiResponses[index];
      if (!response) throw new Error(`Missing browser response for ${apiPaths[index]}`);
      observed[apiPaths[index]] = await browserJson(response, apiPaths[index]);
    }
    expect(observed["/api/config/validate"].is_first_run).toBe(false);
    expect(observed["/api/config/validate"].valid).toBe(true);
    const boards = observed["/api/settings/board"].boards;
    expect(Array.isArray(boards), "A configured board list is required").toBe(true);
    expect(boards, "This bounded shell fixture requires one synthetic board").toHaveLength(1);
    expect(observed["/api/settings/ai"].enabled, "This bounded shell fixture has no enabled assistant").toBe(false);
    const plugins = observed["/api/plugins"].plugins;
    expect(Array.isArray(plugins), "Plugin state must finish loading").toBe(true);
    for (const plugin of plugins as unknown[]) expect(jsonObject(plugin, "plugin").enabled).toBe(false);
    const general = jsonObject(observed["/api/settings/all"].general, "general settings");
    expect(
      observed["/api/settings/restore-notice"].notice,
      "Restore banners are outside this static fixture",
    ).toBeNull();
    expect(typeof observed["/api/system/update-check"].update_available).toBe("boolean");
    expect(observed["/api/system/update-check"].error, "Update-discovery failures are a separate shell state").toBeNull();
    expect(typeof observed["/api/system/update/status"].managed_externally).toBe("boolean");
    if (observed["/api/version"]) expect(observed["/api/version"].running_version).toEqual(expect.any(String));
    if (scenario.path !== "/debug") {
      assertEmpty(observed["/api/v1/pages"], "pages");
      assertEmpty(observed["/api/v1/collections"], "collections");
    }
    await expect(page.getByRole("heading", { name: scenario.title, exact: true }).first()).toBeVisible();
    await expect(page.getByText(scenario.marker, { exact: true })).toBeVisible();
    if (scenario.path === "/debug") {
      await expect(page.getByText("docker logs fiestaboard", { exact: true })).toBeVisible();
    }
    await settledNetwork(page);
    await auditDocument(page, testInfo, {
      kind: scenario.kind,
      path: scenario.path,
      marker: scenario.marker,
      completeDatasets: { pages: 0, collections: 0 },
      shell: {
        boards: (boards as Record<string, unknown>[]).map(({ id, name }) => ({ id, name })),
        aiEnabled: false,
        pluginCount: (plugins as unknown[]).length,
        enabledPlugins: 0,
        restoreNotice: null,
        timeFormat: general.time_format,
        dateFormat: general.date_format,
        updateAvailable: observed["/api/system/update-check"].update_available,
        updateManagedExternally: observed["/api/system/update/status"].managed_externally,
        requiredApis: apiPaths,
      },
      coverage: "Explicit empty/static state only; browser HTTP is forwarded without following redirects.",
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
    const apiPaths = [`/api${panelPath}`, `/api${panelPath}/frame`];
    const seen = new Set<string>();
    for (const apiPath of apiPaths) networks.get(page)!.expectedErrors.add(`${apiPath}:404`);
    await page.route(
      (url) => url.origin === campaign.baseURL && apiPaths.includes(url.pathname),
      async (route) => {
        if (route.request().method() !== "GET") {
          await route.fallback();
          return;
        }
        seen.add(new URL(route.request().url()).pathname);
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
    await expect.poll(() => [...seen].sort()).toEqual([...apiPaths].sort());
    await settledNetwork(page);
    await auditDocument(page, testInfo, {
      kind: "synthetic-browser-api-state",
      path: panelPath,
      fixture: { status: scenario.status, body: scenario.body, interceptedPaths: [...seen].sort() },
      coverage: "Real UI bundle with intercepted Panel APIs; not backend error behavior or live-frame/fullscreen coverage.",
    });
  });
}
