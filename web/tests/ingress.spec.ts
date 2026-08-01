/**
 * HA Ingress E2E regression tests.
 *
 * Runs against the HA Ingress simulator (infra/ha-ingress-proxy.conf),
 * which mimics HA Supervisor's Ingress flow: strips the per-install
 * prefix `/api/hassio_ingress/test-token` from incoming requests,
 * forwards to FiestaBoard's nginx with an `X-Ingress-Path` header, and
 * 404s anything that arrives WITHOUT the prefix — so any URL the SPA
 * builds that escapes the prefix fails loudly here, exactly like it
 * does inside Home Assistant.
 *
 * The FiestaBoard container must run the PRODUCTION bundle
 * (`docker build --target runtime`) with
 * `FIESTABOARD_INGRESS_PATH_REWRITE=true`: the historical escapes were
 * artifacts of the minified output (rolldown's `__vite__mapDeps`
 * relative deps resolved by a runtime `"/" + file` helper; backtick
 * string literals that nginx sub_filter patterns didn't match), which
 * `vite dev` never exhibits.
 *
 * Gated behind RUN_INGRESS_TESTS (mirrors RUN_AUTH_TESTS): the main e2e
 * matrix talks to the container directly, without the simulator.
 *
 * Env:
 *   BASE_URL        — the simulator origin (e.g. http://localhost:5050)
 *   INGRESS_PREFIX  — override for the simulated prefix (defaults to
 *                     the token baked into infra/ha-ingress-proxy.conf)
 */
import { expect, type Page, test } from "@playwright/test";

const PREFIX = process.env.INGRESS_PREFIX || "/api/hassio_ingress/test-token";
// The simulator origin. Everything the SPA requests from this origin must
// carry the prefix — the simulator 404s anything that doesn't, exactly
// like Home Assistant would.
const SIMULATOR_ORIGIN = process.env.BASE_URL ? new URL(process.env.BASE_URL).origin : "";

test.skip(!process.env.RUN_INGRESS_TESTS, "RUN_INGRESS_TESTS not set — ingress simulator not running");

/** Requests that escaped the ingress prefix, and prefixed static assets that 404'd. */
function trackIngressViolations(page: Page) {
  const escapes: string[] = [];
  const notFound: string[] = [];

  page.on("request", (request) => {
    if (!/^https?:/.test(request.url())) return; // data:/blob: are out of scope
    const url = new URL(request.url());
    // Cross-origin URLs (none expected — fonts ship locally) don't go
    // through the simulator.
    if (url.origin !== SIMULATOR_ORIGIN) return;
    if (!url.pathname.startsWith(`${PREFIX}/`) && url.pathname !== PREFIX) {
      escapes.push(`${request.method()} ${url.pathname}`);
    }
  });

  page.on("response", (response) => {
    if (!/^https?:/.test(response.url())) return;
    const url = new URL(response.url());
    if (url.origin !== SIMULATOR_ORIGIN) return;
    // API endpoints may legitimately return errors on a fresh install
    // (e.g. 503 "Board client not initialized"); static assets must not.
    const isStatic = /^\/(assets|icons)\/|\/(favicon\.ico|manifest\.json|sw\.js|registerSW\.js)$/.test(
      url.pathname.replace(PREFIX, ""),
    );
    if (isStatic && response.status() >= 400) {
      notFound.push(`${response.status()} ${url.pathname}`);
    }
  });

  return { escapes, notFound };
}

function suppressWizard(page: Page) {
  return page.addInitScript(() => {
    localStorage.setItem("fiestaboard_wizard_complete", "true");
  });
}

test.describe("HA Ingress", () => {
  test.beforeAll(async ({ request }) => {
    // Take the fresh container out of first-run mode so routes render
    // instead of the setup wizard. Going through the prefixed API is
    // deliberate — it exercises PUT requests through the simulator. The
    // board host is a placeholder; nothing here reads from the board.
    await request.put(`${PREFIX}/api/config/board`, {
      data: { api_mode: "local", local_api_key: "test-key", host: "mock-board" },
    });
    await request.put(`${PREFIX}/api/settings/board`, {
      data: { devices: ["flagship"] },
    });
  });

  test.beforeEach(async ({ page }) => {
    await suppressWizard(page);
  });

  test("dashboard loads under the prefix with zero escaping requests", async ({ page }) => {
    const { escapes, notFound } = trackIngressViolations(page);

    await page.goto(`${PREFIX}/`);
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible({ timeout: 15_000 });

    expect(escapes, "requests must stay under the ingress prefix").toEqual([]);
    expect(notFound, "prefixed static assets must resolve").toEqual([]);
  });

  test("lazy-route navigation stays under the prefix", async ({ page }) => {
    // THE historical failure mode: the first route was fine (its chunks
    // are <link modulepreload> in the sub_filter-rewritten HTML), but
    // client-side navigation lazy-loads route chunks through Vite's
    // runtime preload helper, which used to build root-absolute
    // `/assets/...` URLs that bypassed the prefix and 404'd against the
    // Home Assistant origin.
    const { escapes, notFound } = trackIngressViolations(page);

    await page.goto(`${PREFIX}/`);
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible({ timeout: 15_000 });

    for (const [link, heading] of [
      ["Pages", "Pages"],
      ["Settings", "Settings"],
    ] as const) {
      await page.getByRole("link", { name: link }).first().click();
      await expect(page.getByRole("heading", { name: heading, exact: true })).toBeVisible({ timeout: 10_000 });
    }

    expect(escapes, "lazy-route requests must stay under the ingress prefix").toEqual([]);
    expect(notFound, "lazy-route chunks and icons must resolve").toEqual([]);
  });

  test("in-app logo icon renders (not just requested)", async ({ page }) => {
    // The sidebar logo is a JSX `<img src>` that lands in the JS bundle,
    // where sub_filter can't reliably reach it — it must go through the
    // runtime base path (appUrl) instead.
    await page.goto(`${PREFIX}/`);
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible({ timeout: 15_000 });

    // The sidebar renders several logo copies (desktop expanded/collapsed,
    // mobile) — assert on the one that's actually visible.
    const logo = page.locator('img[src*="/icons/favicon-32x32.png"]').filter({ visible: true }).first();
    await expect(logo).toBeVisible({ timeout: 10_000 });
    expect(await logo.getAttribute("src"), "logo src must carry the ingress prefix").toContain(PREFIX);
    await expect
      .poll(async () => logo.evaluate((el: HTMLImageElement) => el.naturalWidth), {
        message: "logo image bytes must actually load",
      })
      .toBeGreaterThan(0);
  });

  test("deep-route document load resolves under the prefix", async ({ page }) => {
    // Covers the HTML + React Router basename path for a non-root
    // document URL (HA reloads the iframe at the panel root, but users
    // can land on deep links via browser history/bookmarks).
    const { escapes, notFound } = trackIngressViolations(page);

    await page.goto(`${PREFIX}/pages`);
    await expect(page.getByRole("heading", { name: "Pages", exact: true })).toBeVisible({ timeout: 15_000 });

    expect(escapes, "deep-route requests must stay under the ingress prefix").toEqual([]);
    expect(notFound, "deep-route assets must resolve").toEqual([]);
  });
});
