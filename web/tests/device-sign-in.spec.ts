import { type APIRequestContext, expect, test } from "@playwright/test";
const credentials = { username: "admin", password: "correct-password" };
const origin = "http://127.0.0.1:4430";
async function mutate(context: APIRequestContext, api: string, path: string, method: string, data?: unknown) {
  const response = await context.get(`${api}/auth/sessions/context`);
  expect(response.ok()).toBe(true);
  const { csrf_token } = await response.json();
  return context.fetch(`${api}${path}`, {
    method,
    data,
    headers: { Origin: origin, "X-CSRF-Token": csrf_token, "Content-Type": "application/json" },
  });
}
for (const prefix of ["", "/test-prefix"]) {
  test.describe(`Device sign-in ${prefix || "root"}`, () => {
    const api = `${origin}${prefix}/api`;
    test("fresh browser explicitly approves TV then revokes only selected sign-ins", async ({ page, playwright }) => {
      const administrator = await playwright.request.newContext();
      const tv = await playwright.request.newContext();
      const secondBrowser = await playwright.request.newContext();
      try {
        const status = await (await administrator.get(`${api}/auth/status`)).json();
        expect(status.session_management_supported).toBe(true);
        if (status.setup_required) {
          expect((await administrator.post(`${api}/auth/setup`, { data: credentials })).ok()).toBe(true);
          const settings = await (await administrator.get(`${api}/auth/device/settings`)).json();
          expect(settings.enabled).toBe(true);
        } else expect((await administrator.post(`${api}/auth/login`, { data: credentials })).ok()).toBe(true);
        expect((await mutate(administrator, api, "/auth/device/settings", "PUT", { enabled: true })).ok()).toBe(true);
        const authorization = await tv.post(`${api}/auth/device/authorize`, {
          data: { client_id: "fiestaboard-tvos", device_name: "Acceptance TV", app_version: "test" },
        });
        expect(authorization.ok()).toBe(true);
        const challenge = await authorization.json();
        const leaked: string[] = [];
        page.on("request", (request) => {
          if (new URL(request.url()).origin !== origin && request.url().includes(challenge.user_code))
            leaked.push(request.url());
        });
        await page.goto(`${prefix}/activate?user_code=${encodeURIComponent(challenge.user_code)}`);
        await expect(page.getByRole("heading", { name: "Sign in to FiestaBoard" })).toBeVisible();
        await page.getByLabel("Username").fill(credentials.username);
        await page.getByLabel("Password", { exact: true }).fill(credentials.password);
        await page.getByRole("button", { name: "Sign in", exact: true }).click();
        await expect(page.getByRole("heading", { name: "Acceptance TV", exact: true })).toBeFocused();
        // Scanning and login never authorize on their own.
        const pending = await tv.post(`${api}/auth/device/token`, {
          data: { device_code: challenge.device_code, client_id: "fiestaboard-tvos" },
        });
        expect((await pending.json()).error).toBe("authorization_pending");
        await page.getByRole("button", { name: "Allow this TV" }).click();
        await expect(page.getByText("TV approved. Return to your TV to finish signing in.")).toBeVisible();
        await page.waitForTimeout(challenge.interval * 1000 + 100);
        const redeemed = await tv.post(`${api}/auth/device/token`, {
          data: { device_code: challenge.device_code, client_id: "fiestaboard-tvos" },
        });
        expect(redeemed.ok()).toBe(true);
        const token = await redeemed.json();
        const bearer = { Authorization: `Bearer ${token.access_token}` };
        expect((await tv.get(`${api}/panels`, { headers: bearer })).ok()).toBe(true);
        expect((await secondBrowser.post(`${api}/auth/login`, { data: credentials })).ok()).toBe(true);
        const secondList = await (await secondBrowser.get(`${api}/auth/sessions`)).json();
        // Configure a synthetic display so the ordinary settings route is not captured by setup.
        expect(
          (
            await page.request.put(`${api}/config/board`, {
              data: { api_mode: "local", local_api_key: "acceptance-stub", host: "127.0.0.1" },
            })
          ).ok(),
        ).toBe(true);
        await page.goto(`${prefix}/settings?section=account`);
        await expect(page.getByText("Signed-in devices", { exact: true })).toBeVisible();
        await expect(page.getByText("This browser", { exact: true })).toBeVisible();
        const row = page.getByRole("listitem", { name: "Acceptance TV", exact: true });
        await row.getByRole("button", { name: "Revoke Acceptance TV", exact: true }).click();
        await expect(row).toHaveCount(0);
        expect((await tv.get(`${api}/panels`, { headers: bearer })).status()).toBe(401);
        expect(
          (await mutate(page.request, api, `/auth/sessions/${secondList.current_session_id}`, "DELETE")).ok(),
        ).toBe(true);
        expect((await secondBrowser.get(`${api}/auth/sessions`)).status()).toBe(401);
        expect((await page.request.get(`${api}/auth/sessions`)).ok()).toBe(true);
        expect(leaked).toEqual([]);
        // Disabling enrollment keeps device management and this session available.
        await page.getByRole("switch", { name: "TV sign-in" }).click();
        await expect(page.getByRole("switch", { name: "TV sign-in" })).not.toBeChecked();
        await expect(page.getByText("This browser", { exact: true })).toBeVisible();
      } finally {
        await administrator.dispose();
        await tv.dispose();
        await secondBrowser.dispose();
      }
    });
    test("manual code denial and retired-worker cleanup cannot replay an authenticated cache offline", async ({
      page,
      playwright,
    }) => {
      const tv = await playwright.request.newContext();
      try {
        expect((await page.request.post(`${api}/auth/login`, { data: credentials })).ok()).toBe(true);
        expect((await mutate(page.request, api, "/auth/device/settings", "PUT", { enabled: true })).ok()).toBe(true);
        const challenge = await (
          await tv.post(`${api}/auth/device/authorize`, {
            data: { client_id: "fiestaboard-androidtv", device_name: "Manual TV", app_version: "test" },
          })
        ).json();
        await page.goto(`${prefix}/activate`);
        await page.getByLabel("TV code").fill(challenge.user_code.toLowerCase().replace("-", " "));
        await page.getByRole("button", { name: "Continue", exact: true }).click();
        await expect(page.getByRole("heading", { name: "Manual TV", exact: true })).toBeFocused();
        await page.getByRole("button", { name: "Deny", exact: true }).click();
        await expect(page.getByText("The request was denied.")).toBeVisible();
        const denied = await tv.post(`${api}/auth/device/token`, {
          data: { device_code: challenge.device_code, client_id: "fiestaboard-androidtv" },
        });
        expect((await denied.json()).error).toBe("access_denied");
        await page.evaluate(
          async ({ prefix }) => {
            for (const registration of await navigator.serviceWorker.getRegistrations())
              await registration.unregister();
            const cache = await caches.open("offlineCache");
            for (const endpoint of ["/auth/status", "/auth/sessions"])
              await cache.put(
                `${prefix}/api${endpoint}`,
                new Response(JSON.stringify({ authenticated: true, sessions: [{ id: "stale" }] })),
              );
            await caches.open("another-app");
            await navigator.serviceWorker.register(`${prefix}/sw.js?cleanup-test`, { scope: `${prefix}/` });
          },
          { prefix },
        );
        await expect.poll(() => page.evaluate(() => caches.has("offlineCache"))).toBe(false);
        expect(await page.evaluate(() => caches.has("another-app"))).toBe(true);
        expect((await mutate(page.request, api, "/auth/sessions/revoke", "POST", { include_current: true })).ok()).toBe(
          true,
        );
        await page.context().setOffline(true);
        for (const endpoint of ["/auth/status", "/auth/sessions"]) {
          expect(
            await page.evaluate(async (url) => {
              try {
                await fetch(url);
                return "cached";
              } catch {
                return "offline";
              }
            }, `${prefix}/api${endpoint}`),
          ).toBe("offline");
        }
        await page.context().setOffline(false);
      } finally {
        await tv.dispose();
      }
    });
  });
}

test("live API: consent is separate from browser login and revocation is immediate", async ({ playwright }) => {
  const api = `${origin}/api`;
  const browser = await playwright.request.newContext();
  const tv = await playwright.request.newContext();
  try {
    const initial = await (await browser.get(`${api}/auth/status`)).json();
    expect(initial.session_management_supported).toBe(true);
    const loginPath = initial.setup_required ? "/auth/setup" : "/auth/login";
    expect((await browser.post(`${api}${loginPath}`, { data: credentials })).ok()).toBe(true);
    expect((await mutate(browser, api, "/auth/device/settings", "PUT", { enabled: true })).ok()).toBe(true);
    const challengeResponse = await tv.post(`${api}/auth/device/authorize`, {
      data: { client_id: "fiestaboard-tvos", device_name: "API acceptance TV", app_version: "test" },
    });
    expect(challengeResponse.ok()).toBe(true);
    const challenge = await challengeResponse.json();
    const inspection = await mutate(browser, api, "/auth/device/inspect", "POST", { user_code: challenge.user_code });
    expect(inspection.ok()).toBe(true);
    expect((await inspection.json()).device_name).toBe("API acceptance TV");
    const pending = await tv.post(`${api}/auth/device/token`, {
      data: { client_id: "fiestaboard-tvos", device_code: challenge.device_code },
    });
    expect((await pending.json()).error).toBe("authorization_pending");
    expect((await mutate(browser, api, "/auth/device/approve", "POST", { user_code: challenge.user_code })).ok()).toBe(
      true,
    );
    await new Promise((resolve) => setTimeout(resolve, challenge.interval * 1000 + 100));
    const tokenResponse = await tv.post(`${api}/auth/device/token`, {
      data: { client_id: "fiestaboard-tvos", device_code: challenge.device_code },
    });
    expect(tokenResponse.ok()).toBe(true);
    const token = await tokenResponse.json();
    const headers = { Authorization: `Bearer ${token.access_token}` };
    expect((await tv.get(`${api}/panels`, { headers })).ok()).toBe(true);
    expect((await tv.get(`${api}/auth/sessions`, { headers })).status()).toBe(403);
    const list = await (await browser.get(`${api}/auth/sessions`)).json();
    expect(list.sessions.some((row: { id: string }) => row.id === token.session_id)).toBe(true);
    expect((await mutate(browser, api, `/auth/sessions/${token.session_id}`, "DELETE")).ok()).toBe(true);
    expect((await tv.get(`${api}/panels`, { headers })).status()).toBe(401);
    expect((await browser.get(`${api}/auth/sessions`)).ok()).toBe(true);
  } finally {
    await browser.dispose();
    await tv.dispose();
  }
});
