/**
 * FiestaBoard: the app-shell service worker, offline, and the last-known
 * board (slice 2.8, WEB-16; Figma 07e `329:47360` You're offline,
 * `329:48320` Can't reach your hub; 07 `59:69165` last known).
 *
 * A service worker only runs in a secure context, so run these against
 * localhost (the CI default), which browsers treat as secure like https.
 * The http-only behaviour is pwa-https.spec.ts.
 *
 *   1. The worker registers at the app's base, and controls the page.
 *   2. Reloading with no network opens the cached shell and says
 *      "You're offline" (this device), not "Waiting to start".
 *   3. No API response is ever in any cache.
 *   4. An online page load fetches the shell from the network and refreshes
 *      the cached copy (nobody is stranded on an old release).
 *   5. The last frame seen on a board is shown offline, and the sign-in page
 *      wipes it.
 *   6. a11y of the offline screen.
 */
import type { BrowserContext, Page } from "@playwright/test";
import { getViolations, injectAxe } from "axe-playwright";

import { API_URL, authHeaders, configureBoard, expect, suppressWizard, test } from "./helpers";

const ORIGIN = new URL(process.env.BASE_URL || "http://localhost:4420").origin;

async function controlledHome(page: Page) {
  suppressWizard(page);
  await page.goto("/");
  await page.evaluate(async () => {
    await navigator.serviceWorker.ready;
  });
  // The worker claims open pages on activate; reload once so this load is
  // fetched through it and the shell is cached from a real navigation.
  await page.reload();
  await expect.poll(() => page.evaluate(() => navigator.serviceWorker.controller !== null)).toBe(true);
}

async function cachedUrls(page: Page): Promise<string[]> {
  return page.evaluate(async () => {
    const urls: string[] = [];
    for (const name of await caches.keys()) {
      const cache = await caches.open(name);
      for (const req of await cache.keys()) urls.push(req.url);
    }
    return urls;
  });
}

async function readLastKnown(page: Page): Promise<number> {
  return page.evaluate(
    () =>
      new Promise<number>((resolve) => {
        const open = indexedDB.open("fiestaboard-offline", 2);
        open.onupgradeneeded = () => {
          open.result.createObjectStore("last-known-boards", { keyPath: "boardId" });
          open.result.createObjectStore("session");
        };
        open.onsuccess = () => {
          const req = open.result.transaction("last-known-boards").objectStore("last-known-boards").count();
          req.onsuccess = () => {
            open.result.close();
            resolve(req.result);
          };
        };
      }),
  );
}

async function goOffline(context: BrowserContext, page: Page) {
  await context.setOffline(true);
  await page.reload();
}

test.describe("PWA shell and offline (2.8, WEB-16)", () => {
  test.beforeAll(async () => {
    await configureBoard();
  });

  test("registers the service worker at the app's base", async ({ page }) => {
    await controlledHome(page);
    const scope = await page.evaluate(async () => (await navigator.serviceWorker.ready).scope);
    expect(scope).toBe(`${ORIGIN}/`);
  });

  test("an offline reload opens the cached shell and says this device is offline", async ({ page, context }) => {
    await controlledHome(page);
    await goOffline(context, page);
    await expect(page.getByRole("heading", { level: 1, name: "You’re offline" })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText(/hub and displays are fine/)).toBeVisible();
    await expect(page.getByText(/Waiting to start/)).toHaveCount(0);
    await context.setOffline(false);
  });

  test("never keeps an API response in any cache", async ({ page }) => {
    await controlledHome(page);
    // Let Home make its API calls (status, pages, board state, auth) through the worker.
    await page.waitForLoadState("networkidle");
    const urls = await cachedUrls(page);
    expect(urls.length).toBeGreaterThan(0);
    expect(urls.filter((u) => new URL(u).pathname.startsWith("/api"))).toEqual([]);
  });

  test("an online page load gets the shell from the network and refreshes the cached copy", async ({ page }) => {
    await controlledHome(page);
    const shellDate = () =>
      page.evaluate(async () => {
        const registration = await navigator.serviceWorker.ready;
        const hit = await caches.match(new Request(registration.scope), {
          cacheName: `fb-scope-${encodeURIComponent(registration.scope)}-shell-v3`,
        });
        return hit?.headers.get("date") ?? null;
      });
    const before = await shellDate();
    expect(before).not.toBeNull();
    await page.waitForTimeout(1_100); // HTTP Date has 1 s resolution
    await page.goto("/pages");
    await expect.poll(shellDate, { timeout: 10_000 }).not.toBe(before);
  });

  test("shows the last frame seen on the board while offline", async ({ page, context }) => {
    // The first request may precede verified auth; record the next 30-second poll.
    test.setTimeout(60_000);
    const res = await fetch(`${API_URL}/settings/board`, { headers: authHeaders() });
    const boardId = (await res.json()).boards[0].id as string;
    const send = await fetch(`${API_URL}/v1/boards/${boardId}/message`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ lines: ["LAST KNOWN TEST"] }),
    });
    expect(send.ok).toBe(true);

    await controlledHome(page);
    await expect.poll(() => readLastKnown(page), { timeout: 40_000 }).toBeGreaterThan(0);
    await goOffline(context, page);
    const card = page.getByTestId("last-known-board");
    await expect(card).toBeVisible({ timeout: 15_000 });
    await expect(card).toContainText("may be out of date");
    await context.setOffline(false);
  });

  test("the sign-in page wipes the last-known board", async ({ page }) => {
    await controlledHome(page);
    await page.evaluate(
      () =>
        new Promise<void>((resolve) => {
          const open = indexedDB.open("fiestaboard-offline", 2);
          open.onupgradeneeded = () => {
            open.result.createObjectStore("last-known-boards", { keyPath: "boardId" });
            open.result.createObjectStore("session");
          };
          open.onsuccess = () => {
            const tx = open.result.transaction("last-known-boards", "readwrite");
            tx.objectStore("last-known-boards").put({
              boardId: "x",
              owner: "someone",
              message: "X",
              rows: 6,
              cols: 22,
              board: null,
              savedAt: 1,
            });
            tx.oncomplete = () => {
              open.result.close();
              resolve();
            };
          };
        }),
    );
    expect(await readLastKnown(page)).toBeGreaterThan(0);
    await page.goto("/login");
    await expect.poll(() => readLastKnown(page), { timeout: 10_000 }).toBe(0);
  });

  test("the offline screen has no axe violations", async ({ page, context }) => {
    await controlledHome(page);
    await goOffline(context, page);
    await expect(page.getByRole("heading", { level: 1, name: "You’re offline" })).toBeVisible({ timeout: 15_000 });
    await injectAxe(page);
    const violations = await getViolations(page);
    await context.setOffline(false);
    expect(violations.map((v) => `${v.id}: ${v.help}`)).toEqual([]);
  });
});
