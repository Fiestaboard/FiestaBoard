import { expect, type Page, test } from "@playwright/test";
import { checkA11y, injectAxe } from "axe-playwright";

const key = "B" + "A".repeat(86);
type State = "default" | "allowed" | "denied" | "insecure" | "unsupported" | "install" | "auth" | "error";

async function mockHub(page: Page, state: State = "default", prefix = "", sent = 1, attention = false) {
  const requests: { path: string; method: string; body: unknown }[] = [];
  let status = {
    public_key: key,
    user_enabled: state === "allowed" || state === "denied",
    device_enabled: state === "allowed",
    subscribed: state === "allowed",
    expiration_time: null,
    event_sources: [],
    test_available: state === "allowed",
  };
  await page.addInitScript(
    ({ state, prefix, key }) => {
      Object.assign(window, { __reactRouterContext: { basename: prefix || "/" } });
      let permission: NotificationPermission =
        state === "allowed" ? "granted" : state === "denied" ? "denied" : "default";
      let subscribed = state === "allowed";
      const calls = {
        permission: 0,
        subscribe: 0,
        unsubscribe: 0,
        setBadge: 0,
        clearBadge: 0,
        messages: [] as unknown[],
      };
      Object.assign(window, { pushCalls: calls });
      Object.defineProperty(window, "isSecureContext", { configurable: true, value: state !== "insecure" });
      if (state === "install") {
        Object.defineProperty(navigator, "userAgent", { configurable: true, value: "iPhone OS 17_0 Safari/605" });
      }
      Object.defineProperty(window, "Notification", {
        configurable: true,
        value: {
          get permission() {
            return permission;
          },
          requestPermission: async () => {
            calls.permission++;
            permission = "granted";
            return permission;
          },
        },
      });
      Object.defineProperty(window, "PushManager", {
        configurable: true,
        value: state === "unsupported" ? undefined : function () {},
      });
      const subscription = {
        options: { applicationServerKey: Uint8Array.from(atob(key), (c) => c.charCodeAt(0)).buffer },
        expirationTime: null,
        toJSON: () => ({
          endpoint: "https://fcm.googleapis.com/fake-provider",
          expirationTime: null,
          keys: { p256dh: key, auth: "AAAAAAAAAAAAAAAAAAAAAA" },
        }),
        unsubscribe: async () => {
          subscribed = false;
          calls.unsubscribe++;
          return true;
        },
      };
      const registration = {
        scope: new URL(`${prefix}/`, location.href).href,
        active: { postMessage: (data: unknown) => calls.messages.push(data) },
        getNotifications: async () => [],
        pushManager: {
          getSubscription: async () => (subscribed ? subscription : null),
          subscribe: async () => {
            calls.subscribe++;
            subscribed = true;
            return subscription;
          },
        },
      };
      Object.defineProperty(navigator, "serviceWorker", {
        configurable: true,
        value: { getRegistration: async () => registration },
      });
      Object.defineProperty(navigator, "setAppBadge", {
        configurable: true,
        value: async () => {
          calls.setBadge++;
        },
      });
      Object.defineProperty(navigator, "clearAppBadge", {
        configurable: true,
        value: async () => {
          calls.clearBadge++;
        },
      });
    },
    { state, prefix, key },
  );
  await page.route(
    (url) => url.pathname.startsWith(`${prefix}/api/`),
    async (route) => {
      const path = new URL(route.request().url()).pathname.replace(prefix, "").replace(/^\/api/, "");
      const method = route.request().method();
      if (path.startsWith("/push/")) {
        requests.push({ path, method, body: route.request().postDataJSON() });
        if (state === "auth") return route.fulfill({ status: 401, json: {} });
        if (state === "error") return route.fulfill({ status: 503, json: {} });
        if (method !== "GET") expect(route.request().headers()["x-csrf-token"]).toBe("mock-csrf");
        if (path === "/push/preferences") status = { ...status, user_enabled: route.request().postDataJSON().enabled };
        if (path === "/push/subscription")
          status = {
            ...status,
            device_enabled: method !== "DELETE",
            subscribed: method !== "DELETE",
            test_available: method !== "DELETE" && status.user_enabled,
          };
        if (path === "/push/test")
          return route.fulfill({ json: { sent, failed: 0, skipped: sent ? 0 : 1, expired: 0 } });
        return route.fulfill({ json: status });
      }
      const fixtures: Record<string, unknown> = {
        "/auth/sessions/context": { csrf_token: "mock-csrf", expires_in: 300 },
        "/auth/status": { enabled: true, authenticated: true, username: "maya", mode: "enabled", first_run: false },
        "/settings/all": { general: { instance_name: "Maya's FiestaPi" }, display: {} },
        "/settings/board": { boards: [], primary_board_id: null },
        "/version": { running_version: "11.0.0-alpha.4" },
        "/system/update/status": { managed_externally: false, status: "idle" },
      "/system/update-check": { update_available: attention, latest_version: "11.1.0", current_version: "11.0.0-alpha.4" },
        "/plugins": { plugins: [], total: 0 },
        "/settings/ai": { enabled: false, providers: [] },
        "/health": { status: "ok" },
        "/config/validate": { valid: true, errors: [], warnings: [] },
      };
      return route.fulfill({ json: fixtures[path] ?? {} });
    },
  );
  return requests;
}

async function axe(page: Page) {
  await page.evaluate(() => Promise.all(document.getAnimations().map((animation) => animation.finished)));
  await injectAxe(page);
  await checkA11y(page, undefined, {
    axeOptions: { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21aa"] } },
  });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
}

test("account opt-in, browser permission, test counts and device opt-out through the real route", async ({ page }) => {
  const requests = await mockHub(page, "default", "/ingress/test", 0);
  await page.goto("/tests/layout/notifications.html?route=/settings?section=notifications");
  const account = page.getByRole("switch", { name: "Allow notifications for my account" });
  const device = page.getByRole("switch", { name: "Enable on this browser" });
  await expect(account).not.toBeChecked();
  await expect(device).toBeDisabled();
  expect(
    await page.evaluate(() => (window as unknown as { pushCalls: { permission: number } }).pushCalls.permission),
  ).toBe(0);
  await account.click();
  await expect(account).toBeChecked();
  await expect(device).toBeEnabled();
  await device.focus();
  await page.keyboard.press("Space");
  await expect(device).toBeChecked();
  await expect(page.getByRole("button", { name: "Send a test" })).toBeEnabled();
  await page.getByRole("button", { name: "Send a test" }).click();
  await expect(page.getByRole("status")).toContainText("The test was not sent");
  await axe(page);
  await device.click();
  await expect(device).not.toBeChecked();
  expect(requests.some((r) => r.path === "/push/subscription" && r.method === "DELETE")).toBe(true);
  expect(
    await page.evaluate(() => (window as unknown as { pushCalls: { unsubscribe: number } }).pushCalls.unsubscribe),
  ).toBe(1);
});

for (const width of [390, 768, 1280, 1438]) {
  for (const theme of ["light", "dark"]) {
    for (const state of ["allowed", "denied", "insecure"] as const) {
      test(`notifications ${state} ${width} ${theme}`, async ({ page }, testInfo) => {
        await page.setViewportSize({ width, height: width === 390 ? 722 : 898 });
        await mockHub(page, state);
        await page.goto(`/tests/layout/notifications.html?theme=${theme}`);
        await expect(page.getByRole("switch", { name: "Allow notifications for my account" })).toBeVisible();
        if (state === "allowed") await expect(page.getByRole("button", { name: "Send a test" })).toBeEnabled();
        if (state === "denied") await expect(page.getByText("Notifications blocked by the browser")).toBeVisible();
        if (state === "insecure") await expect(page.getByText("Requires HTTPS")).toBeVisible();
        await axe(page);
        await page.screenshot({ path: testInfo.outputPath(`impl-${state}-${width}-${theme}.png`), fullPage: true });
      });
    }
  }
}

for (const [state, title] of [
  ["unsupported", "Notifications unavailable"],
  ["install", "Add FiestaBoard to your Home Screen"],
  ["auth", "Sign in to enable notifications"],
  ["error", "Could not load notification settings. Check your connection and try again."],
] as const) {
  test(`${state} recovery is explicit and accessible`, async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await mockHub(page, state);
    await page.goto("/tests/layout/notifications.html");
    await expect(page.getByText(title)).toBeVisible();
    await axe(page);
  });
}

test("More opening acknowledges the OS attention badge without restoring it on close", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockHub(page, "allowed", "", 1, true);
  await page.goto("/tests/layout/notifications.html");
  await expect.poll(() => page.evaluate(() => (window as unknown as { pushCalls: { setBadge: number } }).pushCalls.setBadge)).toBeGreaterThan(0);
  const before = await page.evaluate(() => (window as unknown as { pushCalls: { setBadge: number; clearBadge: number } }).pushCalls);
  await page.locator('[data-slot="sidebar-bottom-nav"]').getByRole("button", { name: /More/ }).click();
  await expect(page.getByRole("dialog", { name: "Navigation menu" })).toBeVisible();
  await expect.poll(() => page.evaluate(() => (window as unknown as { pushCalls: { clearBadge: number } }).pushCalls.clearBadge)).toBeGreaterThan(before.clearBadge);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog", { name: "Navigation menu" })).toHaveCount(0);
  expect(await page.evaluate(() => (window as unknown as { pushCalls: { setBadge: number } }).pushCalls.setBadge)).toBe(before.setBadge);
});

test("failed enrollment rolls back the new native subscription", async ({ page }) => {
  await mockHub(page);
  await page.route((url) => url.pathname === "/api/push/subscription", (route) => route.fulfill({ status: 422, json: {} }));
  await page.goto("/tests/layout/notifications.html");
  await page.getByRole("switch", { name: "Allow notifications for my account" }).click();
  const device = page.getByRole("switch", { name: "Enable on this browser" });
  await expect(device).toBeEnabled(); await device.click();
  await expect(page.getByRole("status")).toContainText("Could not update notifications");
  await expect(device).not.toBeChecked();
  expect(await page.evaluate(() => (window as unknown as { pushCalls: { unsubscribe: number } }).pushCalls.unsubscribe)).toBe(1);
  await axe(page);
});

test("embedded HA ingress explains the direct HTTPS alternative", async ({ page }) => {
  await mockHub(page);
  await page.goto("/tests/layout/");
  await page.setContent('<!doctype html><html lang="en"><head><title>Home Assistant</title></head><body><h1>Home Assistant</h1><iframe title="FiestaBoard" src="/tests/layout/notifications.html" width="390" height="844"></iframe></body></html>');
  const app = page.frameLocator('iframe[title="FiestaBoard"]');
  await expect(app.getByText("Open your hub directly")).toBeVisible();
  await expect(app.getByRole("switch", { name: "Enable on this browser" })).toBeDisabled();
});

test("sign-out removes the browser subscription and badge before navigating away", async ({ page }) => {
  await mockHub(page, "allowed");
  // Freeze the navigation target so the departing page's observable calls remain readable.
  await page.route((url) => url.pathname === "/login", (route) => route.abort());
  await page.goto("/tests/layout/notifications.html");
  await page.getByRole("button", { name: "maya", exact: true }).click();
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect.poll(() => page.evaluate(() => (window as unknown as { pushCalls: { unsubscribe: number } }).pushCalls.unsubscribe)).toBe(1);
  expect(await page.evaluate(() => (window as unknown as { pushCalls: { clearBadge: number } }).pushCalls.clearBadge)).toBeGreaterThan(0);
});
